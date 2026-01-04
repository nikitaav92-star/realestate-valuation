#!/usr/bin/env python3
"""
Assign geographic segments to listings for precise valuation.

This script assigns the most granular (smallest) segment to each listing:
1. Try level 4 (Квартал) - most precise
2. Fallback to level 3 (Микрорайон)
3. Fallback to level 2 (Район)
4. Fallback to level 1 (Округ)

Uses multiple methods:
- PostGIS spatial containment (primary)
- Address text matching (fallback)
- Nearest segment (last resort)
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
import re
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DSN = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")


def assign_by_coordinates_multilevel(batch_size: int = 1000) -> Tuple[int, int, int, int]:
    """
    Assign segments by coordinates, preferring most granular level.
    
    Returns:
        Tuple of (level_4_count, level_3_count, level_2_count, level_1_count)
    """
    print("📍 METHOD 1: Assigning by coordinates (PostGIS spatial containment)")
    print("-" * 70)
    
    conn = psycopg2.connect(DSN)
    cursor = conn.cursor()
    
    # Assign to most granular segment available (prefer level 4, then 3, then 2, then 1)
    cursor.execute("""
        WITH segment_matches AS (
            SELECT 
                l.id as listing_id,
                d.district_id,
                d.level,
                ROW_NUMBER() OVER (
                    PARTITION BY l.id 
                    ORDER BY d.level DESC  -- Prefer higher (more granular) levels
                ) as rn
            FROM listings l
            CROSS JOIN LATERAL (
                SELECT district_id, level
                FROM districts
                WHERE ST_Contains(
                    geometry, 
                    ST_SetSRID(ST_Point(l.lon, l.lat), 4326)
                )
                ORDER BY level DESC
                LIMIT 1
            ) d
            WHERE l.lat IS NOT NULL 
              AND l.lon IS NOT NULL
              AND l.district_id IS NULL
        )
        UPDATE listings l
        SET district_id = sm.district_id
        FROM segment_matches sm
        WHERE l.id = sm.listing_id 
          AND sm.rn = 1
    """)
    
    total_assigned = cursor.rowcount
    conn.commit()
    
    # Count by level
    cursor.execute("""
        SELECT d.level, COUNT(*) as count
        FROM listings l
        JOIN districts d ON l.district_id = d.district_id
        GROUP BY d.level
        ORDER BY d.level DESC
    """)
    
    level_counts = {row[0]: row[1] for row in cursor.fetchall()}
    
    cursor.close()
    conn.close()
    
    print(f"✅ Assigned {total_assigned} listings by coordinates")
    print(f"   Level 4 (Квартал): {level_counts.get(4, 0)}")
    print(f"   Level 3 (Микрорайон): {level_counts.get(3, 0)}")
    print(f"   Level 2 (Район): {level_counts.get(2, 0)}")
    print(f"   Level 1 (Округ): {level_counts.get(1, 0)}")
    
    return (
        level_counts.get(4, 0),
        level_counts.get(3, 0),
        level_counts.get(2, 0),
        level_counts.get(1, 0)
    )


def assign_by_nearest_segment(limit: int = 1000) -> int:
    """
    Assign to nearest segment for listings without spatial match.
    Uses KNN (k-nearest neighbors) on segment centroids.
    
    Args:
        limit: Maximum listings to process
    
    Returns:
        Number of listings assigned
    """
    print("\n📍 METHOD 2: Assigning by nearest segment (KNN fallback)")
    print("-" * 70)
    
    conn = psycopg2.connect(DSN)
    cursor = conn.cursor()
    
    # Find nearest segment (prefer level 3-4)
    cursor.execute("""
        WITH nearest_segments AS (
            SELECT DISTINCT ON (l.id)
                l.id as listing_id,
                d.district_id,
                d.level,
                ST_Distance(
                    ST_SetSRID(ST_Point(l.lon, l.lat), 4326)::geography,
                    ST_Centroid(d.geometry)::geography
                ) as distance_m
            FROM listings l
            CROSS JOIN LATERAL (
                SELECT district_id, level, geometry
                FROM districts
                WHERE level >= 2  -- Only районы and below
                ORDER BY 
                    ST_Centroid(geometry) <-> ST_SetSRID(ST_Point(l.lon, l.lat), 4326),
                    level DESC  -- Prefer more granular if same distance
                LIMIT 1
            ) d
            WHERE l.lat IS NOT NULL
              AND l.lon IS NOT NULL
              AND l.district_id IS NULL
            LIMIT %s
        )
        UPDATE listings l
        SET district_id = ns.district_id
        FROM nearest_segments ns
        WHERE l.id = ns.listing_id
          AND ns.distance_m < 5000  -- Max 5km distance
        RETURNING l.id
    """, (limit,))
    
    assigned = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"✅ Assigned {assigned} listings to nearest segment (within 5km)")
    
    return assigned


def assign_by_address_text(limit: int = 1000) -> int:
    """
    Assign segment by parsing district name from address text.
    Fallback for listings without coordinates.
    
    Args:
        limit: Maximum listings to process
    
    Returns:
        Number of listings assigned
    """
    print("\n📍 METHOD 3: Assigning by address text (regex parsing)")
    print("-" * 70)
    
    conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    # Get listings without segment
    cursor.execute("""
        SELECT id, COALESCE(address_full, address) as address
        FROM listings
        WHERE district_id IS NULL
          AND (address IS NOT NULL OR address_full IS NOT NULL)
        LIMIT %s
    """, (limit,))
    
    listings = cursor.fetchall()
    
    if not listings:
        print("⚠️  No listings to process")
        return 0
    
    print(f"Processing {len(listings)} listings...")
    
    # Patterns for extracting district names
    patterns = [
        r'р-н\s+([А-ЯЁа-яё\-]+(?:\s+[А-ЯЁа-яё\-]+)?)',
        r'район\s+([А-ЯЁа-яё\-]+(?:\s+[А-ЯЁа-яё\-]+)?)',
        r'(ЦАО|САО|СВАО|ВАО|ЮВАО|ЮАО|ЮЗАО|ЗАО|СЗАО|ЗелАО)',
        r'мкр\.\s+([А-ЯЁа-яё\-]+)',
        r'микрорайон\s+([А-ЯЁа-яё\-]+)',
    ]
    
    assigned = 0
    
    for listing in listings:
        district_name = None
        
        for pattern in patterns:
            match = re.search(pattern, listing['address'], re.IGNORECASE)
            if match:
                district_name = match.group(1).strip()
                break
        
        if not district_name:
            continue
        
        # Find matching segment (prefer higher levels)
        cursor.execute("""
            SELECT district_id
            FROM districts
            WHERE LOWER(name) LIKE LOWER(%s)
               OR LOWER(full_name) LIKE LOWER(%s)
            ORDER BY level DESC, name
            LIMIT 1
        """, (f'%{district_name}%', f'%{district_name}%'))
        
        result = cursor.fetchone()
        if result:
            cursor.execute("""
                UPDATE listings
                SET district_id = %s
                WHERE id = %s
            """, (result['district_id'], listing['id']))
            assigned += 1
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"✅ Assigned {assigned} listings by address text")
    
    return assigned


def show_assignment_stats():
    """Display detailed assignment statistics."""
    print("\n" + "=" * 70)
    print("📊 ASSIGNMENT STATISTICS")
    print("=" * 70)
    
    conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    # Overall stats
    cursor.execute("""
        SELECT 
            COUNT(*) as total_listings,
            COUNT(district_id) as assigned,
            COUNT(*) - COUNT(district_id) as unassigned,
            ROUND(100.0 * COUNT(district_id) / NULLIF(COUNT(*), 0), 2) as pct_assigned
        FROM listings
    """)
    
    overall = cursor.fetchone()
    print(f"\n📈 Overall:")
    print(f"  Total listings: {overall['total_listings']:,}")
    print(f"  Assigned to segments: {overall['assigned']:,} ({overall['pct_assigned']}%)")
    print(f"  Unassigned: {overall['unassigned']:,}")
    
    # By segment level
    print(f"\n📊 Distribution by segment level:")
    cursor.execute("""
        SELECT 
            d.level,
            CASE d.level
                WHEN 1 THEN 'Округ'
                WHEN 2 THEN 'Район'
                WHEN 3 THEN 'Микрорайон'
                WHEN 4 THEN 'Квартал'
                ELSE 'Unknown'
            END as level_name,
            COUNT(l.id) as listings_count,
            ROUND(100.0 * COUNT(l.id) / (SELECT COUNT(*) FROM listings WHERE district_id IS NOT NULL), 2) as pct
        FROM listings l
        JOIN districts d ON l.district_id = d.district_id
        GROUP BY d.level
        ORDER BY d.level DESC
    """)
    
    print(f"  {'Level':<20} {'Listings':>12} {'%':>8}")
    print("  " + "-" * 42)
    for row in cursor.fetchall():
        level_desc = f"{row['level']}-{row['level_name']}"
        print(f"  {level_desc:<20} {row['listings_count']:>12,} {row['pct']:>7.2f}%")
    
    # Top segments by listing count
    print(f"\n🏆 Top 10 segments by listing count:")
    cursor.execute("""
        SELECT 
            d.name,
            d.level,
            COUNT(l.id) as listings_count,
            ROUND(AVG(l.price_current / NULLIF(l.area_total, 0))::numeric, 0) as avg_price_per_sqm
        FROM listings l
        JOIN districts d ON l.district_id = d.district_id
        WHERE l.price_current > 0 AND l.area_total > 0
        GROUP BY d.district_id, d.name, d.level
        ORDER BY listings_count DESC
        LIMIT 10
    """)
    
    print(f"  {'Segment':<35} {'Lvl':>3} {'Listings':>10} {'Avg ₽/m²':>12}")
    print("  " + "-" * 63)
    for row in cursor.fetchall():
        avg_price = int(row['avg_price_per_sqm']) if row['avg_price_per_sqm'] else 0
        print(f"  {row['name']:<35} {row['level']:>3} {row['listings_count']:>10,} {avg_price:>12,}")
    
    # Data quality check
    print(f"\n🔍 Data quality:")
    cursor.execute("""
        SELECT 
            COUNT(*) FILTER (WHERE lat IS NOT NULL AND lon IS NOT NULL) as with_coords,
            COUNT(*) FILTER (WHERE lat IS NULL OR lon IS NULL) as no_coords,
            COUNT(*) FILTER (WHERE district_id IS NOT NULL AND (lat IS NOT NULL AND lon IS NOT NULL)) as assigned_with_coords,
            COUNT(*) FILTER (WHERE district_id IS NOT NULL AND (lat IS NULL OR lon IS NULL)) as assigned_no_coords
        FROM listings
    """)
    
    quality = cursor.fetchone()
    print(f"  Listings with coordinates: {quality['with_coords']:,}")
    print(f"  Listings without coordinates: {quality['no_coords']:,}")
    print(f"  Assigned with coords: {quality['assigned_with_coords']:,}")
    print(f"  Assigned without coords (text-based): {quality['assigned_no_coords']:,}")
    
    cursor.close()
    conn.close()


def main():
    """Main execution."""
    print("\n" + "=" * 70)
    print("🎯 ASSIGN SEGMENTS TO LISTINGS")
    print("=" * 70)
    print("\nThis will assign the most granular segment to each listing")
    print("=" * 70)
    
    # Method 1: Spatial containment (coordinates)
    level_4, level_3, level_2, level_1 = assign_by_coordinates_multilevel()
    
    # Method 2: Nearest segment (for edge cases)
    nearest_assigned = assign_by_nearest_segment(limit=1000)
    
    # Method 3: Address text parsing (fallback)
    text_assigned = assign_by_address_text(limit=1000)
    
    # Show statistics
    show_assignment_stats()
    
    print("\n" + "=" * 70)
    print("✅ Segment assignment completed!")
    print("\n💡 Next steps:")
    print("  1. Run: python scripts/aggregate_districts.py")
    print("  2. View results: python scripts/analyze_segmentation.py")
    print("  3. Start API: python web/api.py")
    print("=" * 70)


if __name__ == '__main__':
    main()

