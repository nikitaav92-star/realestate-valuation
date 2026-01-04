#!/usr/bin/env python3
"""
Aggregate district statistics for the interactive map.

This script calculates daily aggregated statistics for each district:
- Average and median price per square meter
- Min/max prices
- Total number of listings
- Average area and rooms

Results are stored in district_aggregates table for fast map rendering.
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Database connection
DSN = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")


def aggregate_district_data(target_date: date = None):
    """
    Aggregate data for all districts for a specific date.

    Args:
        target_date: Date to aggregate for (default: today)
    """
    if target_date is None:
        target_date = date.today()

    print(f"📊 Aggregating district data for {target_date.isoformat()}")
    print("=" * 60)

    conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        # Get latest prices for active listings
        print("⏳ Calculating statistics...")

        cursor.execute("""
            WITH latest_prices AS (
                SELECT DISTINCT ON (lp.id)
                    lp.id,
                    lp.price
                FROM listing_prices lp
                ORDER BY lp.id, lp.seen_at DESC
            )
            INSERT INTO district_aggregates (
                district_id, date,
                avg_price_per_sqm, median_price_per_sqm,
                min_price, max_price,
                total_listings, avg_area, avg_rooms
            )
            SELECT
                d.district_id,
                %s as date,
                ROUND(AVG(p.price / NULLIF(l.area_total, 0))::numeric, 2) as avg_price_per_sqm,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                    ORDER BY p.price / NULLIF(l.area_total, 0)
                )::numeric, 2) as median_price_per_sqm,
                MIN(p.price) as min_price,
                MAX(p.price) as max_price,
                COUNT(*) as total_listings,
                ROUND(AVG(l.area_total)::numeric, 2) as avg_area,
                ROUND(AVG(l.rooms::numeric), 2) as avg_rooms
            FROM districts d
            JOIN listings l ON l.district_id = d.district_id
            JOIN latest_prices p ON p.id = l.id
            WHERE l.is_active = TRUE
              AND p.price > 0
              AND l.area_total > 0
            GROUP BY d.district_id
            HAVING COUNT(*) > 0
            ON CONFLICT (district_id, date)
            DO UPDATE SET
                avg_price_per_sqm = EXCLUDED.avg_price_per_sqm,
                median_price_per_sqm = EXCLUDED.median_price_per_sqm,
                min_price = EXCLUDED.min_price,
                max_price = EXCLUDED.max_price,
                total_listings = EXCLUDED.total_listings,
                avg_area = EXCLUDED.avg_area,
                avg_rooms = EXCLUDED.avg_rooms,
                updated_at = NOW()
            RETURNING district_id
        """, (target_date,))

        updated = cursor.rowcount
        conn.commit()

        print(f"✅ Aggregated data for {updated} districts")

        # Show sample results
        print("\n📈 Sample aggregated data:")
        cursor.execute("""
            SELECT
                d.name,
                a.total_listings,
                a.avg_price_per_sqm,
                a.median_price_per_sqm,
                a.min_price,
                a.max_price
            FROM district_aggregates a
            JOIN districts d ON d.district_id = a.district_id
            WHERE a.date = %s
            ORDER BY a.total_listings DESC
            LIMIT 10
        """, (target_date,))

        results = cursor.fetchall()
        if results:
            print(f"\n{'District':<30s} {'Listings':>8s} {'Avg ₽/m²':>12s} {'Median ₽/m²':>12s}")
            print("-" * 70)
            for row in results:
                print(
                    f"{row['name']:<30s} "
                    f"{row['total_listings']:>8d} "
                    f"{row['avg_price_per_sqm']:>12,.0f} "
                    f"{row['median_price_per_sqm']:>12,.0f}"
                )
        else:
            print("⚠️  No aggregated data found")

        # Overall statistics
        print("\n📊 Overall statistics:")
        cursor.execute("""
            SELECT
                COUNT(DISTINCT district_id) as districts_with_data,
                SUM(total_listings) as total_listings,
                ROUND(AVG(avg_price_per_sqm)::numeric, 0) as avg_price_all_districts,
                ROUND(MIN(avg_price_per_sqm)::numeric, 0) as min_price_per_sqm,
                ROUND(MAX(avg_price_per_sqm)::numeric, 0) as max_price_per_sqm
            FROM district_aggregates
            WHERE date = %s
        """, (target_date,))

        stats = cursor.fetchone()
        if stats and stats['districts_with_data']:
            print(f"  Districts with data: {stats['districts_with_data']}")
            print(f"  Total listings: {stats['total_listings']}")
            print(f"  Average price/m² across all districts: {stats['avg_price_all_districts']:,.0f} ₽")
            print(f"  Price range: {stats['min_price_per_sqm']:,.0f} - {stats['max_price_per_sqm']:,.0f} ₽/m²")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()


def clean_old_aggregates(days_to_keep: int = 30):
    """
    Remove old aggregate data to save space.

    Args:
        days_to_keep: Number of days of history to keep
    """
    print(f"\n🧹 Cleaning aggregates older than {days_to_keep} days...")

    conn = psycopg2.connect(DSN)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            DELETE FROM district_aggregates
            WHERE date < CURRENT_DATE - INTERVAL '%s days'
            RETURNING district_id
        """, (days_to_keep,))

        deleted = cursor.rowcount
        conn.commit()

        print(f"✅ Deleted {deleted} old aggregate records")

    except Exception as e:
        print(f"❌ Error cleaning aggregates: {e}")
        conn.rollback()

    finally:
        cursor.close()
        conn.close()


def main():
    """Main function."""
    print("📊 District Data Aggregation")
    print("=" * 60)

    # Aggregate for today
    aggregate_district_data()

    # Clean old data (keep last 30 days)
    clean_old_aggregates(days_to_keep=30)

    print("\n" + "=" * 60)
    print("✅ District aggregation completed")
    print("\n💡 Next: Start the API server and access the map at /map")


if __name__ == '__main__':
    main()
