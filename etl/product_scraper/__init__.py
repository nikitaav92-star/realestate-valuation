"""Mass product scraping system with queue-based orchestration.

This package provides infrastructure for scalable e-commerce data collection:
- Queue-based task management (Redis or Postgres)
- Per-site fetchers with anti-bot helpers
- Worker CLI for parallel execution
- Unified product schema persistence
"""

from .queue import ProductTask, TaskQueue, PostgresQueue
from .worker import Worker, WorkerConfig
from .fetcher import ProductFetcher, FetchResult

__all__ = [
    "ProductTask",
    "TaskQueue",
    "PostgresQueue",
    "Worker",
    "WorkerConfig",
    "ProductFetcher",
    "FetchResult",
]
