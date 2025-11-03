"""CLI tool to normalize existing addresses using FIAS/Dadata."""
from __future__ import annotations

import argparse
import logging
from typing import Optional

from etl.address_normalizer import get_normalizer
from etl.upsert import get_db_connection, upsert_fias_data

LOGGER = logging.getLogger(__name__)


def normalize_all_addresses(limit: Optional[int] = None, skip_existing: bool = True) -> dict:
    """
    Normalize all addresses in database.
    
    Args:
        limit: Max number of addresses to process (None = all)
        skip_existing: Skip listings that already have FIAS data
        
    Returns:
        Dictionary with statistics
    """
    normalizer = get_normalizer()
    
    if not normalizer.enabled:
        LOGGER.error("❌ Dadata API keys not configured. Set DADATA_API_KEY and DADATA_SECRET_KEY in .env")
        return {"error": "API keys not configured"}
    
    conn = get_db_connection()
    
    # Get listings to normalize
    with conn.cursor() as cur:
        query = """
            SELECT id, address, lat, lon
            FROM listings
            WHERE 1=1
        """
        if skip_existing:
            query += " AND fias_id IS NULL"
        if limit:
            query += f" LIMIT {limit}"
            
        cur.execute(query)
        rows = cur.fetchall()
    
    total = len(rows)
    LOGGER.info(f"📊 Found {total} listings to normalize")
    
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
            # Try geocoding first if we have coordinates
            normalized = None
            if lat and lon:
                LOGGER.debug(f"[{idx}/{total}] Geocoding coordinates: {lat}, {lon}")
                normalized = normalizer.geocode(lat, lon)
            
            # Fallback to address string
            if not normalized and address:
                LOGGER.debug(f"[{idx}/{total}] Normalizing address: {address}")
                normalized = normalizer.normalize(address)
            
            if normalized:
                # Save to database
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
                
                # Track quality
                if normalized.qc == 0:
                    stats["exact_match"] += 1
                elif normalized.qc == 1:
                    stats["good_match"] += 1
                elif normalized.qc >= 2:
                    stats["need_review"] += 1
                
                LOGGER.info(
                    f"✅ [{idx}/{total}] ID={listing_id}, "
                    f"FIAS={normalized.fias_address[:50]}..., "
                    f"Cadastral={normalized.cadastral_number or N/A}, "
                    f"QC={normalized.qc}"
                )
            else:
                stats["failed"] += 1
                LOGGER.warning(f"⚠️ [{idx}/{total}] Failed to normalize listing {listing_id}")
                
        except Exception as e:
            stats["failed"] += 1
            LOGGER.error(f"❌ [{idx}/{total}] Error processing listing {listing_id}: {e}")
            conn.rollback()
            continue
    
    conn.close()
    
    # Print summary
    LOGGER.info("=" * 60)
    LOGGER.info("📊 Normalization Summary:")
    LOGGER.info(f"  Total processed: {stats[total]}")
    LOGGER.info(f"  ✅ Success: {stats[success]} ({100*stats[success]/stats[total]:.1f}%)")
    LOGGER.info(f"  ❌ Failed: {stats[failed]}")
    LOGGER.info(f"  🏠 With cadastral: {stats[with_cadastral]}")
    LOGGER.info(f"  🎯 Exact match (QC=0): {stats[exact_match]}")
    LOGGER.info(f"  ✓ Good match (QC=1): {stats[good_match]}")
    LOGGER.info(f"  ⚠️ Need review (QC>=2): {stats[need_review]}")
    LOGGER.info("=" * 60)
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Normalize addresses using FIAS/Dadata")
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
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    
    normalize_all_addresses(
        limit=args.limit,
        skip_existing=not args.no_skip_existing,
    )


if __name__ == "__main__":
    main()
