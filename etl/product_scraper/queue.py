"""Task queue interface for product scraping.

Supports both Postgres (advisory locks) and Redis backends.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol

import psycopg2
from psycopg2.extras import DictCursor

LOGGER = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Task execution status."""
    
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class ProductTask:
    """Product scraping task."""
    
    task_id: Optional[int] = None
    source_slug: str = ""
    external_id: str = ""
    url: str = ""
    priority: int = 0  # Higher = more urgent
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["status"] = self.status.value
        return data


class TaskQueue(Protocol):
    """Abstract task queue interface."""
    
    def enqueue(self, task: ProductTask) -> int:
        """Add task to queue.
        
        Returns
        -------
        int
            Task ID
        """
        ...
    
    def dequeue(self, worker_id: str, batch_size: int = 1) -> List[ProductTask]:
        """Get tasks from queue.
        
        Parameters
        ----------
        worker_id : str
            Worker identifier for tracking
        batch_size : int
            Number of tasks to fetch
            
        Returns
        -------
        list[ProductTask]
            Tasks ready for processing
        """
        ...
    
    def mark_completed(self, task_id: int) -> None:
        """Mark task as completed."""
        ...
    
    def mark_failed(self, task_id: int, error: str, retry: bool = True) -> None:
        """Mark task as failed.
        
        Parameters
        ----------
        task_id : int
            Task ID
        error : str
            Error message
        retry : bool
            Whether to retry the task
        """
        ...
    
    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        ...


class PostgresQueue:
    """Postgres-based task queue using advisory locks."""
    
    def __init__(self, conn_string: str) -> None:
        """Initialize Postgres queue.
        
        Parameters
        ----------
        conn_string : str
            PostgreSQL connection string
        """
        self.conn_string = conn_string
        self._ensure_table()
    
    def _get_connection(self):
        """Get database connection."""
        return psycopg2.connect(self.conn_string)
    
    def _ensure_table(self) -> None:
        """Create queue table if not exists."""
        create_sql = """
        CREATE TABLE IF NOT EXISTS product_tasks (
            task_id SERIAL PRIMARY KEY,
            source_slug VARCHAR(50) NOT NULL,
            external_id VARCHAR(200) NOT NULL,
            url TEXT NOT NULL,
            priority INTEGER DEFAULT 0,
            status VARCHAR(20) DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            metadata JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            error_message TEXT,
            worker_id VARCHAR(100),
            
            CONSTRAINT uq_task_source_external UNIQUE (source_slug, external_id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_tasks_status_priority 
            ON product_tasks(status, priority DESC, created_at);
        CREATE INDEX IF NOT EXISTS idx_tasks_source 
            ON product_tasks(source_slug, status);
        """
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(create_sql)
                conn.commit()
        
        LOGGER.info("Ensured product_tasks table exists")
    
    def enqueue(self, task: ProductTask) -> int:
        """Add task to queue."""
        insert_sql = """
        INSERT INTO product_tasks 
            (source_slug, external_id, url, priority, metadata, max_retries)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_slug, external_id) DO UPDATE
        SET url = EXCLUDED.url,
            priority = EXCLUDED.priority,
            metadata = EXCLUDED.metadata
        RETURNING task_id
        """
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    insert_sql,
                    (
                        task.source_slug,
                        task.external_id,
                        task.url,
                        task.priority,
                        json.dumps(task.metadata) if task.metadata else None,
                        task.max_retries,
                    ),
                )
                task_id = cur.fetchone()[0]
                conn.commit()
        
        LOGGER.debug("Enqueued task %d: %s/%s", task_id, task.source_slug, task.external_id)
        return task_id
    
    def dequeue(self, worker_id: str, batch_size: int = 1) -> List[ProductTask]:
        """Get tasks from queue using advisory locks."""
        # Use Postgres advisory locks to prevent race conditions
        select_sql = """
        UPDATE product_tasks
        SET status = 'in_progress',
            started_at = NOW(),
            worker_id = %s
        WHERE task_id IN (
            SELECT task_id
            FROM product_tasks
            WHERE status IN ('pending', 'retrying')
            ORDER BY priority DESC, created_at ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        )
        RETURNING task_id, source_slug, external_id, url, priority,
                  status, retry_count, max_retries, metadata,
                  created_at, started_at, error_message
        """
        
        tasks = []
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(select_sql, (worker_id, batch_size))
                rows = cur.fetchall()
                
                for row in rows:
                    task = ProductTask(
                        task_id=row["task_id"],
                        source_slug=row["source_slug"],
                        external_id=row["external_id"],
                        url=row["url"],
                        priority=row["priority"],
                        status=TaskStatus(row["status"]),
                        retry_count=row["retry_count"],
                        max_retries=row["max_retries"],
                        metadata=row["metadata"] or {},
                        created_at=row["created_at"],
                        started_at=row["started_at"],
                        error_message=row["error_message"],
                    )
                    tasks.append(task)
                
                conn.commit()
        
        if tasks:
            LOGGER.info("Dequeued %d task(s) for worker %s", len(tasks), worker_id)
        
        return tasks
    
    def mark_completed(self, task_id: int) -> None:
        """Mark task as completed."""
        update_sql = """
        UPDATE product_tasks
        SET status = 'completed',
            completed_at = NOW()
        WHERE task_id = %s
        """
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(update_sql, (task_id,))
                conn.commit()
        
        LOGGER.debug("Marked task %d as completed", task_id)
    
    def mark_failed(self, task_id: int, error: str, retry: bool = True) -> None:
        """Mark task as failed."""
        # Check if we should retry
        check_sql = "SELECT retry_count, max_retries FROM product_tasks WHERE task_id = %s"
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(check_sql, (task_id,))
                row = cur.fetchone()
                
                if not row:
                    LOGGER.warning("Task %d not found", task_id)
                    return
                
                retry_count, max_retries = row
                should_retry = retry and (retry_count < max_retries)
                
                if should_retry:
                    update_sql = """
                    UPDATE product_tasks
                    SET status = 'retrying',
                        retry_count = retry_count + 1,
                        error_message = %s
                    WHERE task_id = %s
                    """
                    new_status = "retrying"
                else:
                    update_sql = """
                    UPDATE product_tasks
                    SET status = 'failed',
                        retry_count = retry_count + 1,
                        error_message = %s,
                        completed_at = NOW()
                    WHERE task_id = %s
                    """
                    new_status = "failed"
                
                cur.execute(update_sql, (error, task_id))
                conn.commit()
        
        LOGGER.warning("Marked task %d as %s: %s", task_id, new_status, error)
    
    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        stats_sql = """
        SELECT 
            status,
            COUNT(*) as count
        FROM product_tasks
        GROUP BY status
        """
        
        stats = {}
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(stats_sql)
                rows = cur.fetchall()
                
                for row in rows:
                    stats[row["status"]] = row["count"]
        
        return stats
    
    def purge_completed(self, older_than_days: int = 7) -> int:
        """Remove old completed tasks.
        
        Parameters
        ----------
        older_than_days : int
            Remove tasks completed more than N days ago
            
        Returns
        -------
        int
            Number of tasks removed
        """
        delete_sql = """
        DELETE FROM product_tasks
        WHERE status = 'completed'
          AND completed_at < NOW() - INTERVAL '%s days'
        """
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(delete_sql, (older_than_days,))
                count = cur.rowcount
                conn.commit()
        
        if count > 0:
            LOGGER.info("Purged %d completed task(s)", count)
        
        return count

