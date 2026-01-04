"""CLI tool to normalize existing addresses using the public FIAS API."""
from __future__ import annotations

import argparse
import logging
from typing import Optional

from etl.address_normalizer import get_normalizer
from etl.upsert import get_db_connection, upsert_fias_data

LOGGER = logging.getLogger(__name__)


def normalize_all_addresses(limit: Optional[int] = None, skip_existing: bool = True) -> dict:
    """Normalize addresses stored in the database using FIAS data only."""
    normalizer = get_normalizer()
    conn = get_db_connection()

    with conn.cursor() as cur:
        query = [
            "SELECT id, address, lat, lon",
            "FROM listings",
            "WHERE 1=1",
        ]
        if skip_existing:
            query.append("AND fias_id IS NULL")
        if limit:
            query.append(f"LIMIT {limit}")
        cur.execute(" ".join(query))
        rows = cur.fetchall()

    total = len(rows)
    LOGGER.info("📊 Found %s listings to normalize", total)

    stats = {
        "total": total,
        "success": 0,
        "failed": 0,
        "with_cadastral": 0,
        "exact_match": 0,
        "good_match": 0,
        "need_review": 0,
    }

    for idx, (listing_id, address, lat, lon) in enumerate(rows, 1):
        try:
            normalized = None
            if address:
                LOGGER.debug("[%s/%s] Normalizing address: %s", idx, total, address)
                normalized = normalizer.normalize(address)

            if normalized:
                upsert_fias_data(
                    conn,
                    listing_id=listing_id,
                    fias_address=normalized.fias_address,
                    fias_id=normalized.fias_id,
                    postal_code=normalized.postal_code,
                    cadastral_number=normalized.cadastral_number,
                    quality_code=normalized.qc,
                )
                conn.commit()

                stats["success"] += 1
                if normalized.cadastral_number:
                    stats["with_cadastral"] += 1

                if normalized.qc == 0:
                    stats["exact_match"] += 1
                elif normalized.qc == 1:
                    stats["good_match"] += 1
                elif normalized.qc is not None:
                    stats["need_review"] += 1

                fias_preview = (normalized.fias_address or "")[:50]
                cadastral_value = normalized.cadastral_number or "N/A"
                qc_value = normalized.qc if normalized.qc is not None else "N/A"
                LOGGER.info(
                    "✅ [%s/%s] ID=%s, FIAS=%s..., Cadastral=%s, QC=%s",
                    idx,
                    total,
                    listing_id,
                    fias_preview,
                    cadastral_value,
                    qc_value,
                )
            else:
                stats["failed"] += 1
                LOGGER.warning("⚠️ [%s/%s] Failed to normalize listing %s", idx, total, listing_id)
        except Exception as exc:
            stats["failed"] += 1
            LOGGER.error("❌ [%s/%s] Error processing listing %s: %s", idx, total, listing_id, exc)
            conn.rollback()

    conn.close()

    LOGGER.info("=" * 60)
    LOGGER.info("📊 Normalization Summary:")
    success_pct = (100 * stats["success"] / stats["total"]) if stats["total"] else 0
    LOGGER.info("  Total processed: %s", stats["total"])
    LOGGER.info("  ✅ Success: %s (%.1f%%)", stats["success"], success_pct)
    LOGGER.info("  ❌ Failed: %s", stats["failed"])
    LOGGER.info("  🏠 With cadastral: %s", stats["with_cadastral"])
    LOGGER.info("  🎯 Exact match (QC=0): %s", stats["exact_match"])
    LOGGER.info("  ✓ Good match (QC=1): %s", stats["good_match"])
    LOGGER.info("  ⚠️ Need review (QC>=2): %s", stats["need_review"])
    LOGGER.info("=" * 60)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize addresses using the FIAS public API")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of addresses to process (default: all)",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-normalize addresses that already have FIAS data",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(message)s")

    normalize_all_addresses(limit=args.limit, skip_existing=not args.no_skip_existing)


if __name__ == "__main__":
    main()
