#!/usr/bin/env python3
"""Remove duplicate listings based on identical URLs."""
from __future__ import annotations

import logging
from contextlib import closing

from etl.upsert import get_db_connection

LOGGER = logging.getLogger(__name__)


def deduplicate_listings() -> None:
    conn = get_db_connection()
    conn.autocommit = True
    with closing(conn):
        with conn.cursor() as cur:
            LOGGER.info("🔍 Finding duplicate listings by URL...")
            cur.execute(
                """
                WITH ranked AS (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY url
                            ORDER BY updated_at DESC, id DESC
                        ) AS rn
                    FROM listings
                )
                DELETE FROM listings
                WHERE id IN (
                    SELECT id FROM ranked WHERE rn > 1
                );
                """
            )
            deleted = cur.rowcount
            LOGGER.info("🧹 Removed %s duplicate rows from listings", deleted)

        with conn.cursor() as cur:
            LOGGER.info("📊 Running ANALYZE on listings...")
            cur.execute("ANALYZE listings;")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    deduplicate_listings()
    LOGGER.info("✅ Deduplication completed")


if __name__ == "__main__":
    main()



