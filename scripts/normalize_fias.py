#!/usr/bin/env python3
"""
Autonomous FIAS address normalization script.

Runs separately from the main parser to normalize addresses in the background.
Can be run via cron or systemd timer.

Usage:
    python scripts/normalize_fias.py --batch-size 100 --delay 1.0
    python scripts/normalize_fias.py --limit 1000  # Process max 1000 addresses
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

from etl.fias_normalizer import normalize_address
from etl.upsert import get_db_connection, upsert_fias_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger(__name__)


def get_addresses_to_normalize(conn, limit: int = 100) -> list[tuple[int, str]]:
    """Get listings with address_full but without fias_address."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, address_full
            FROM listings
            WHERE address_full IS NOT NULL
              AND address_full != ''
              AND fias_address IS NULL
              AND is_active = TRUE
            ORDER BY first_seen DESC
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()


def get_normalization_stats(conn) -> dict:
    """Get current normalization statistics."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) as total,
                COUNT(address_full) as with_address,
                COUNT(fias_address) as normalized,
                COUNT(*) FILTER (WHERE address_full IS NOT NULL AND fias_address IS NULL) as pending
            FROM listings
            WHERE is_active = TRUE
            """
        )
        row = cur.fetchone()
        return {
            "total": row[0],
            "with_address": row[1],
            "normalized": row[2],
            "pending": row[3],
        }


def normalize_batch(
    conn,
    batch_size: int = 100,
    delay: float = 1.0,
    max_errors: int = 10,
) -> tuple[int, int, int]:
    """
    Normalize a batch of addresses.

    Returns:
        Tuple of (processed, success, errors)
    """
    addresses = get_addresses_to_normalize(conn, batch_size)

    if not addresses:
        LOGGER.info("No addresses to normalize")
        return 0, 0, 0

    LOGGER.info(f"Processing {len(addresses)} addresses...")

    processed = 0
    success = 0
    errors = 0
    consecutive_errors = 0

    for listing_id, address in addresses:
        try:
            LOGGER.debug(f"[{processed + 1}/{len(addresses)}] Normalizing: {address[:60]}...")

            fias_data = normalize_address(address)

            if fias_data:
                upsert_fias_data(
                    conn,
                    listing_id,
                    fias_address=fias_data.get("fias_address"),
                    fias_id=fias_data.get("fias_id"),
                    postal_code=fias_data.get("postal_code"),
                    quality_code=fias_data.get("quality_code"),
                )
                # Also save coordinates if available (bonus from DaData Suggest)
                lat = fias_data.get("lat")
                lon = fias_data.get("lon")
                if lat is not None and lon is not None:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE listings SET lat = %s, lon = %s WHERE id = %s AND lat IS NULL",
                            (lat, lon, listing_id),
                        )
                conn.commit()
                success += 1
                consecutive_errors = 0
                coords_info = f", coords: ({lat:.4f}, {lon:.4f})" if lat and lon else ""
                LOGGER.info(f"  ✅ [{listing_id}] Normalized: {fias_data.get('fias_address', '')[:50]}{coords_info}")
            else:
                # Mark as attempted (set empty fias_address to avoid re-processing)
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE listings SET fias_address = '' WHERE id = %s",
                        (listing_id,),
                    )
                conn.commit()
                errors += 1
                consecutive_errors += 1
                LOGGER.warning(f"  ❌ [{listing_id}] Failed to normalize: {address[:50]}")

            processed += 1

            # Check for too many consecutive errors
            if consecutive_errors >= max_errors:
                LOGGER.error(f"Too many consecutive errors ({consecutive_errors}), stopping batch")
                break

            # Delay between requests to avoid rate limiting
            if delay > 0 and processed < len(addresses):
                time.sleep(delay)

        except Exception as e:
            LOGGER.error(f"  ❌ Error processing [{listing_id}]: {e}")
            errors += 1
            consecutive_errors += 1
            try:
                conn.rollback()
            except:
                pass

            if consecutive_errors >= max_errors:
                LOGGER.error(f"Too many consecutive errors ({consecutive_errors}), stopping batch")
                break

    return processed, success, errors


def main():
    parser = argparse.ArgumentParser(description="FIAS address normalization")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of addresses to process per batch (default: 50)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay between API calls in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum total addresses to process (0 = unlimited)",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=10,
        help="Stop after N consecutive errors (default: 10)",
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only show statistics, don't process",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    conn = get_db_connection()

    try:
        # Show initial stats
        stats = get_normalization_stats(conn)
        LOGGER.info("=" * 50)
        LOGGER.info("FIAS Normalization Statistics")
        LOGGER.info("=" * 50)
        LOGGER.info(f"  Total active listings: {stats['total']}")
        LOGGER.info(f"  With address_full:     {stats['with_address']}")
        LOGGER.info(f"  Already normalized:    {stats['normalized']}")
        LOGGER.info(f"  Pending:               {stats['pending']}")
        LOGGER.info("=" * 50)

        if args.stats_only:
            return

        if stats['pending'] == 0:
            LOGGER.info("No addresses pending normalization")
            return

        # Process in batches
        total_processed = 0
        total_success = 0
        total_errors = 0
        batch_num = 0

        while True:
            batch_num += 1
            LOGGER.info(f"\n📦 Batch {batch_num} starting...")

            processed, success, errors = normalize_batch(
                conn,
                batch_size=args.batch_size,
                delay=args.delay,
                max_errors=args.max_errors,
            )

            total_processed += processed
            total_success += success
            total_errors += errors

            LOGGER.info(
                f"📊 Batch {batch_num} complete: "
                f"processed={processed}, success={success}, errors={errors}"
            )

            # Check if we should stop
            if processed == 0:
                LOGGER.info("No more addresses to process")
                break

            if args.limit > 0 and total_processed >= args.limit:
                LOGGER.info(f"Reached limit of {args.limit} addresses")
                break

            # Check remaining
            stats = get_normalization_stats(conn)
            if stats['pending'] == 0:
                LOGGER.info("All addresses normalized")
                break

            LOGGER.info(f"📋 Remaining: {stats['pending']} addresses")

        # Final stats
        LOGGER.info("\n" + "=" * 50)
        LOGGER.info("FINAL RESULTS")
        LOGGER.info("=" * 50)
        LOGGER.info(f"  Total processed: {total_processed}")
        LOGGER.info(f"  Success:         {total_success}")
        LOGGER.info(f"  Errors:          {total_errors}")
        if total_processed > 0:
            LOGGER.info(f"  Success rate:    {total_success / total_processed * 100:.1f}%")
        LOGGER.info("=" * 50)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
