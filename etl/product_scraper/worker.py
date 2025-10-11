"""Worker for processing product scraping tasks."""
from __future__ import annotations

import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Dict, Optional

from .fetcher import ProductFetcher, FetchResult
from .queue import ProductTask, TaskQueue

LOGGER = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    """Worker configuration."""
    
    worker_id: str
    batch_size: int = 5
    poll_interval: float = 5.0  # Seconds between queue polls
    graceful_shutdown: bool = True
    max_tasks: Optional[int] = None  # Max tasks before shutdown (for testing)


class Worker:
    """Task queue worker."""
    
    def __init__(
        self,
        config: WorkerConfig,
        queue: TaskQueue,
        fetchers: Dict[str, ProductFetcher],
    ) -> None:
        """Initialize worker.
        
        Parameters
        ----------
        config : WorkerConfig
            Worker configuration
        queue : TaskQueue
            Task queue instance
        fetchers : dict[str, ProductFetcher]
            Mapping of source_slug → fetcher instance
        """
        self.config = config
        self.queue = queue
        self.fetchers = fetchers
        self.running = False
        self.tasks_processed = 0
        self.tasks_succeeded = 0
        self.tasks_failed = 0
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        if self.config.graceful_shutdown:
            signal.signal(signal.SIGINT, self._handle_shutdown)
            signal.signal(signal.SIGTERM, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame) -> None:
        """Handle shutdown signal."""
        LOGGER.info("Received shutdown signal %s, stopping gracefully...", signum)
        self.running = False
    
    def run(self) -> None:
        """Run worker loop."""
        LOGGER.info(
            "Starting worker %s (batch_size=%d, poll_interval=%.1fs)",
            self.config.worker_id,
            self.config.batch_size,
            self.config.poll_interval,
        )
        
        self.running = True
        
        while self.running:
            try:
                # Check max tasks limit
                if self.config.max_tasks is not None:
                    if self.tasks_processed >= self.config.max_tasks:
                        LOGGER.info(
                            "Reached max tasks limit (%d), shutting down",
                            self.config.max_tasks,
                        )
                        break
                
                # Dequeue tasks
                tasks = self.queue.dequeue(
                    self.config.worker_id,
                    self.config.batch_size,
                )
                
                if not tasks:
                    LOGGER.debug("No tasks available, sleeping...")
                    time.sleep(self.config.poll_interval)
                    continue
                
                # Process tasks
                for task in tasks:
                    if not self.running:
                        LOGGER.info("Shutdown requested, stopping task processing")
                        break
                    
                    self._process_task(task)
                    self.tasks_processed += 1
                
            except KeyboardInterrupt:
                LOGGER.info("Keyboard interrupt, shutting down...")
                self.running = False
            except Exception as exc:
                LOGGER.error("Worker error: %s", exc, exc_info=True)
                time.sleep(self.config.poll_interval)
        
        self._log_stats()
    
    def _process_task(self, task: ProductTask) -> None:
        """Process a single task.
        
        Parameters
        ----------
        task : ProductTask
            Task to process
        """
        LOGGER.info(
            "Processing task %d: %s/%s",
            task.task_id,
            task.source_slug,
            task.external_id,
        )
        
        start_time = time.time()
        
        # Get fetcher for this source
        fetcher = self.fetchers.get(task.source_slug)
        if not fetcher:
            error = f"No fetcher configured for source: {task.source_slug}"
            LOGGER.error(error)
            self.queue.mark_failed(task.task_id, error, retry=False)
            self.tasks_failed += 1
            return
        
        # Fetch product
        try:
            result: FetchResult = fetcher.fetch(task.url, task.external_id)
            
            if result.success:
                # TODO: Persist to database
                # For now, just log success
                LOGGER.info(
                    "Successfully fetched %s/%s (took %.2fs, level=%s)",
                    task.source_slug,
                    task.external_id,
                    time.time() - start_time,
                    result.escalation_level,
                )
                
                self.queue.mark_completed(task.task_id)
                self.tasks_succeeded += 1
            else:
                error = result.error or "Unknown fetch error"
                LOGGER.warning(
                    "Failed to fetch %s/%s: %s",
                    task.source_slug,
                    task.external_id,
                    error,
                )
                
                # Retry if not max retries
                retry = task.retry_count < task.max_retries
                self.queue.mark_failed(task.task_id, error, retry=retry)
                self.tasks_failed += 1
                
        except Exception as exc:
            error = f"Fetch exception: {exc}"
            LOGGER.error(
                "Exception processing task %d: %s",
                task.task_id,
                exc,
                exc_info=True,
            )
            
            retry = task.retry_count < task.max_retries
            self.queue.mark_failed(task.task_id, error, retry=retry)
            self.tasks_failed += 1
    
    def _log_stats(self) -> None:
        """Log worker statistics."""
        LOGGER.info(
            "Worker %s shutting down: processed=%d, succeeded=%d, failed=%d",
            self.config.worker_id,
            self.tasks_processed,
            self.tasks_succeeded,
            self.tasks_failed,
        )

