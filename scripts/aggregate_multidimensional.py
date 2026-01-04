#!/usr/bin/env python3
"""
Calculate multi-dimensional price aggregates.
Runs daily to update multidim_aggregates table.
"""

import os
import sys
import psycopg2
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DSN = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")


def aggregate_prices():
    """Calculate aggregates for each district × property_segment combination."""
    
    print("=" * 80)
    print("📊 MULTI-DIMENSIONAL AGGREGATION")
    print("=" * 80)
    
    conn = psycopg2.connect(DSN)
    cursor = conn.cursor()
    
    today = date.today()
    
    print(f"\n📅 Date: {today}")
    print(f"\n🔄 Calculating aggregates...\n")
    
    # Delete today's aggregates (if re-running)
    cursor.execute("DELETE FROM multidim_aggregates WHERE date = %s", (today,))
    print(f"  Deleted {cursor.rowcount} old records for today")
    
    # Calculate new aggregates
    cursor.execute("""
        INSERT INTO multidim_aggregates (
            district_id,
            property_segment_id,
            date,
            avg_price_per_sqm,
            median_price_per_sqm,
            min_price,
            max_price,
            total_listings,
            avg_area,
            price_stddev,
            confidence_score
        )
        SELECT
            l.district_id,
            l.property_segment_id,
            %s as date,
            
            AVG(COALESCE(lp.price, l.initial_price) / NULLIF(l.area_total, 0))::numeric(12,2) as avg_price_per_sqm,
            PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY COALESCE(lp.price, l.initial_price) / NULLIF(l.area_total, 0)
            )::numeric(12,2) as median_price_per_sqm,
            
            MIN(COALESCE(lp.price, l.initial_price))::numeric(12,2) as min_price,
            MAX(COALESCE(lp.price, l.initial_price))::numeric(12,2) as max_price,
            
            COUNT(*) as total_listings,
            AVG(l.area_total)::numeric(6,2) as avg_area,
            
            STDDEV(COALESCE(lp.price, l.initial_price) / NULLIF(l.area_total, 0))::numeric(12,2) as price_stddev,
            
            -- Confidence score based on sample size
            LEAST(100, 20 + (COUNT(*) / 5) * 10) as confidence_score
            
        FROM listings l
        LEFT JOIN LATERAL (
            SELECT price
            FROM listing_prices
            WHERE id = l.id
            ORDER BY seen_at DESC
            LIMIT 1
        ) lp ON TRUE
        
        WHERE l.district_id IS NOT NULL
          AND l.property_segment_id IS NOT NULL
          AND l.area_total > 0
          AND COALESCE(lp.price, l.initial_price) > 0
          AND l.is_active = TRUE
          AND l.last_seen >= CURRENT_DATE - INTERVAL '90 days'
        
        GROUP BY l.district_id, l.property_segment_id
        HAVING COUNT(*) >= 3  -- Minimum 3 listings for statistical significance
    """, (today,))
    
    inserted = cursor.rowcount
    conn.commit()
    
    print(f"  ✅ Inserted {inserted} aggregate records")
    
    # Summary stats
    cursor.execute("""
        SELECT
            COUNT(*) as total_aggregates,
            COUNT(DISTINCT district_id) as districts_covered,
            COUNT(DISTINCT property_segment_id) as segments_covered,
            SUM(total_listings) as total_listings_aggregated,
            ROUND(AVG(confidence_score)) as avg_confidence
        FROM multidim_aggregates
        WHERE date = %s
    """, (today,))
    
    stats = cursor.fetchone()
    
    print(f"\n📈 Summary:")
    print(f"  Total aggregates: {stats[0]:,}")
    print(f"  Districts covered: {stats[1]:,}")
    print(f"  Property segments covered: {stats[2]:,}")
    print(f"  Listings aggregated: {stats[3]:,}")
    print(f"  Avg confidence: {stats[4]:.0f}%")
    
    # Top segments by volume
    print(f"\n🏆 Top 10 segments by volume:")
    cursor.execute("""
        SELECT
            d.name as district,
            ps.building_type,
            ps.building_height,
            ps.rooms_count,
            ma.total_listings,
            ma.median_price_per_sqm
        FROM multidim_aggregates ma
        JOIN districts d ON ma.district_id = d.district_id
        JOIN property_segments ps ON ma.property_segment_id = ps.segment_id
        WHERE ma.date = %s
        ORDER BY ma.total_listings DESC
        LIMIT 10
    """, (today,))
    
    for row in cursor.fetchall():
        print(f"  {row[0][:30]:30} | {row[1]:12} | {row[2]:6} | {row[3]}R | "
              f"{row[4]:4} listings | {row[5]:,.0f} ₽/m²")
    
    print("\n" + "=" * 80)
    print("✅ AGGREGATION COMPLETE")
    print("=" * 80)
    
    cursor.close()
    conn.close()


if __name__ == '__main__':
    aggregate_prices()
