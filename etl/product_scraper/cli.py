"""CLI for product scraping system."""
from __future__ import annotations

import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

import click

from .queue import PostgresQueue, ProductTask
from .worker import Worker, WorkerConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

LOGGER = logging.getLogger(__name__)


def _get_db_connection_string() -> str:
    """Get database connection string from environment."""
    # Check for full connection string first
    if conn_str := os.getenv("DATABASE_URL"):
        return conn_str
    
    # Build from components
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    user = os.getenv("PG_USER", "realuser")
    password = os.getenv("PG_PASS", "strongpass")
    database = os.getenv("PG_DB", "realdb")
    
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


@click.group()
def cli():
    """Product scraping CLI."""
    pass


@cli.command()
@click.option(
    "--source",
    required=True,
    help="Source slug (e.g., 'ozon', 'wildberries')",
)
@click.option(
    "--url",
    required=True,
    help="Product URL",
)
@click.option(
    "--external-id",
    required=True,
    help="Product ID from source site",
)
@click.option(
    "--priority",
    default=0,
    type=int,
    help="Task priority (higher = more urgent)",
)
def enqueue(source: str, url: str, external_id: str, priority: int) -> None:
    """Enqueue a product scraping task."""
    conn_str = _get_db_connection_string()
    queue = PostgresQueue(conn_str)
    
    task = ProductTask(
        source_slug=source,
        external_id=external_id,
        url=url,
        priority=priority,
    )
    
    task_id = queue.enqueue(task)
    click.echo(f"✅ Enqueued task {task_id}: {source}/{external_id}")


@cli.command()
@click.option(
    "--source",
    required=True,
    help="Source slug",
)
@click.option(
    "--input-file",
    type=click.Path(exists=True),
    help="File with product URLs (one per line)",
)
@click.option(
    "--priority",
    default=0,
    type=int,
    help="Task priority",
)
def enqueue_batch(source: str, input_file: str, priority: int) -> None:
    """Enqueue multiple products from file."""
    conn_str = _get_db_connection_string()
    queue = PostgresQueue(conn_str)
    
    enqueued = 0
    
    with open(input_file, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            # Parse line (format: URL or URL,external_id)
            parts = line.split(",")
            url = parts[0].strip()
            external_id = parts[1].strip() if len(parts) > 1 else f"product-{line_num}"
            
            task = ProductTask(
                source_slug=source,
                external_id=external_id,
                url=url,
                priority=priority,
            )
            
            try:
                queue.enqueue(task)
                enqueued += 1
            except Exception as exc:
                LOGGER.error("Failed to enqueue line %d: %s", line_num, exc)
    
    click.echo(f"✅ Enqueued {enqueued} task(s)")


@cli.command()
@click.option(
    "--source",
    help="Filter by source slug",
)
@click.option(
    "--worker-id",
    help="Worker ID (defaults to hostname-UUID)",
)
@click.option(
    "--batch-size",
    default=5,
    type=int,
    help="Number of tasks to process at once",
)
@click.option(
    "--poll-interval",
    default=5.0,
    type=float,
    help="Seconds between queue polls",
)
@click.option(
    "--max-tasks",
    type=int,
    help="Max tasks before shutdown (for testing)",
)
def run(
    source: Optional[str],
    worker_id: Optional[str],
    batch_size: int,
    poll_interval: float,
    max_tasks: Optional[int],
) -> None:
    """Run worker to process tasks from queue."""
    # Generate worker ID
    if worker_id is None:
        hostname = os.getenv("HOSTNAME", "localhost")
        worker_id = f"{hostname}-{uuid.uuid4().hex[:8]}"
    
    click.echo(f"🚀 Starting worker: {worker_id}")
    
    # Initialize queue
    conn_str = _get_db_connection_string()
    queue = PostgresQueue(conn_str)
    
    # TODO: Initialize fetchers based on source
    # For now, just log error
    if not source:
        click.echo("⚠️  No source specified, worker cannot process tasks yet")
        click.echo("   Implementation needed: create fetcher instances")
        return
    
    fetchers = {}
    # fetchers[source] = OzonFetcher()  # Example
    
    if not fetchers:
        click.echo(f"❌ No fetcher configured for source: {source}")
        return
    
    # Configure worker
    config = WorkerConfig(
        worker_id=worker_id,
        batch_size=batch_size,
        poll_interval=poll_interval,
        max_tasks=max_tasks,
    )
    
    # Run worker
    worker = Worker(config, queue, fetchers)
    worker.run()


@cli.command()
def stats() -> None:
    """Show queue statistics."""
    conn_str = _get_db_connection_string()
    queue = PostgresQueue(conn_str)
    
    stats = queue.get_stats()
    
    click.echo("\n📊 Queue Statistics\n" + "=" * 40)
    
    total = sum(stats.values())
    click.echo(f"Total tasks: {total}")
    
    for status, count in sorted(stats.items()):
        click.echo(f"  {status:15s}: {count:6d}")
    
    click.echo()


@cli.command()
@click.option(
    "--days",
    default=7,
    type=int,
    help="Remove tasks completed more than N days ago",
)
@click.confirmation_option(prompt="Are you sure you want to purge completed tasks?")
def purge(days: int) -> None:
    """Remove old completed tasks."""
    conn_str = _get_db_connection_string()
    queue = PostgresQueue(conn_str)
    
    count = queue.purge_completed(days)
    click.echo(f"✅ Purged {count} completed task(s)")


if __name__ == "__main__":
    cli()
