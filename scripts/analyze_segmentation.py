#!/usr/bin/env python3
"""
Analyze geographic segmentation quality and coverage.

This script provides detailed insights into:
- Segment coverage by level
- Listing distribution across segments
- Price variation by segment
- Data quality metrics
- Recommendations for improvement
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DSN = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")


def show_segment_coverage():
    """Show segment coverage statistics."""
    print("=" * 80)
    print("📊 SEGMENT COVERAGE ANALYSIS")
    print("=" * 80)
    
    conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    # Overall coverage
    cursor.execute("""
        SELECT 
            level,
            CASE level
                WHEN 1 THEN 'Округ'
                WHEN 2 THEN 'Район'
                WHEN 3 THEN 'Микрорайон'
                WHEN 4 THEN 'Квартал'
            END as level_name,
            COUNT(*) as segment_count,
            COUNT(geometry) as with_geometry,
            ROUND(AVG(ST_Area(geometry::geography) / 1000000)::numeric, 2) as avg_area_km2
        FROM districts
        GROUP BY level
        ORDER BY level
    """)
    
    print("\n🗺️  Segments by Level:")
    print(f"{'Level':<20} {'Count':>10} {'With Geom':>12} {'Avg Area (km²)':>18}")
    print("-" * 80)
    
    for row in cursor.fetchall():
        level_desc = f"{row['level']}-{row['level_name']}"
        avg_area = row['avg_area_km2'] if row['avg_area_km2'] else 0
        print(f"{level_desc:<20} {row['segment_count']:>10,} {row['with_geometry']:>12,} {avg_area:>18.2f}")
    
    cursor.close()
    conn.close()


def show_listing_distribution():
    """Show how listings are distributed across segments."""
    print("\n" + "=" * 80)
    print("🏠 LISTING DISTRIBUTION")
    print("=" * 80)
    
    conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    # Overall stats
    cursor.execute("""
        SELECT 
            COUNT(*) as total_listings,
            COUNT(lat) as with_coords,
            COUNT(district_id) as assigned_to_segment,
            ROUND(100.0 * COUNT(district_id) / COUNT(*), 2) as pct_assigned,
            ROUND(100.0 * COUNT(lat) / COUNT(*), 2) as pct_with_coords
        FROM listings
    """)
    
    overall = cursor.fetchone()
    
    print(f"\n📈 Overall:")
    print(f"  Total listings: {overall['total_listings']:,}")
    print(f"  With coordinates: {overall['with_coords']:,} ({overall['pct_with_coords']}%)")
    print(f"  Assigned to segments: {overall['assigned_to_segment']:,} ({overall['pct_assigned']}%)")
    print(f"  Unassigned: {overall['total_listings'] - overall['assigned_to_segment']:,}")
    
    # By segment level
    cursor.execute("""
        SELECT 
            d.level,
            CASE d.level
                WHEN 1 THEN 'Округ'
                WHEN 2 THEN 'Район'
                WHEN 3 THEN 'Микрорайон'
                WHEN 4 THEN 'Квартал'
            END as level_name,
            COUNT(l.id) as listing_count,
            ROUND(100.0 * COUNT(l.id) / (SELECT COUNT(*) FROM listings WHERE district_id IS NOT NULL), 2) as pct
        FROM listings l
        JOIN districts d ON l.district_id = d.district_id
        GROUP BY d.level
        ORDER BY d.level DESC
    """)
    
    print(f"\n📊 Distribution by Segment Level:")
    print(f"{'Level':<20} {'Listings':>12} {'%':>10}")
    print("-" * 80)
    
    for row in cursor.fetchall():
        level_desc = f"{row['level']}-{row['level_name']}"
        print(f"{level_desc:<20} {row['listing_count']:>12,} {row['pct']:>9.2f}%")
    
    cursor.close()
    conn.close()


def show_top_segments():
    """Show top segments by listing count and price."""
    print("\n" + "=" * 80)
    print("🏆 TOP SEGMENTS")
    print("=" * 80)
    
    conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    # Top by listing count
    print("\n📊 Top 15 Segments by Listing Count:")
    cursor.execute("""
        SELECT 
            d.name,
            d.level,
            CASE d.level
                WHEN 1 THEN 'Округ'
                WHEN 2 THEN 'Район'
                WHEN 3 THEN 'Микрорайон'
                WHEN 4 THEN 'Квартал'
            END as level_name,
            COUNT(l.id) as listing_count,
            ROUND(AVG(l.price_current / NULLIF(l.area_total, 0))::numeric, 0) as avg_price_per_sqm,
            ROUND(AVG(l.price_current)::numeric, 0) as avg_price
        FROM listings l
        JOIN districts d ON l.district_id = d.district_id
        WHERE l.price_current > 0 AND l.area_total > 0
        GROUP BY d.district_id, d.name, d.level
        ORDER BY listing_count DESC
        LIMIT 15
    """)
    
    print(f"{'Segment':<35} {'Lvl':>3} {'Listings':>10} {'Avg ₽/m²':>12} {'Avg Price':>15}")
    print("-" * 80)
    
    for row in cursor.fetchall():
        avg_sqm = int(row['avg_price_per_sqm']) if row['avg_price_per_sqm'] else 0
        avg_price = int(row['avg_price']) if row['avg_price'] else 0
        print(f"{row['name'][:34]:<35} {row['level']:>3} {row['listing_count']:>10,} "
              f"{avg_sqm:>12,} {avg_price:>15,}")
    
    # Top by price
    print("\n💰 Top 15 Most Expensive Segments (by avg ₽/m²):")
    cursor.execute("""
        SELECT 
            d.name,
            d.level,
            COUNT(l.id) as listing_count,
            ROUND(AVG(l.price_current / NULLIF(l.area_total, 0))::numeric, 0) as avg_price_per_sqm,
            ROUND(MIN(l.price_current / NULLIF(l.area_total, 0))::numeric, 0) as min_price_per_sqm,
            ROUND(MAX(l.price_current / NULLIF(l.area_total, 0))::numeric, 0) as max_price_per_sqm
        FROM listings l
        JOIN districts d ON l.district_id = d.district_id
        WHERE l.price_current > 0 AND l.area_total > 0
        GROUP BY d.district_id, d.name, d.level
        HAVING COUNT(l.id) >= 5  -- At least 5 listings for statistical significance
        ORDER BY avg_price_per_sqm DESC
        LIMIT 15
    """)
    
    print(f"{'Segment':<35} {'Lvl':>3} {'Count':>7} {'Avg ₽/m²':>12} {'Range':>25}")
    print("-" * 80)
    
    for row in cursor.fetchall():
        avg_sqm = int(row['avg_price_per_sqm'])
        min_sqm = int(row['min_price_per_sqm'])
        max_sqm = int(row['max_price_per_sqm'])
        price_range = f"{min_sqm:,} - {max_sqm:,}"
        print(f"{row['name'][:34]:<35} {row['level']:>3} {row['listing_count']:>7,} "
              f"{avg_sqm:>12,} {price_range:>25}")
    
    cursor.close()
    conn.close()


def show_price_variation():
    """Show price variation across segment levels."""
    print("\n" + "=" * 80)
    print("📈 PRICE VARIATION BY SEGMENT LEVEL")
    print("=" * 80)
    
    conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            d.level,
            CASE d.level
                WHEN 1 THEN 'Округ'
                WHEN 2 THEN 'Район'
                WHEN 3 THEN 'Микрорайон'
                WHEN 4 THEN 'Квартал'
            END as level_name,
            COUNT(DISTINCT d.district_id) as segment_count,
            COUNT(l.id) as listing_count,
            ROUND(AVG(l.price_current / NULLIF(l.area_total, 0))::numeric, 0) as avg_price_per_sqm,
            ROUND(STDDEV(l.price_current / NULLIF(l.area_total, 0))::numeric, 0) as stddev_price,
            ROUND(MIN(l.price_current / NULLIF(l.area_total, 0))::numeric, 0) as min_price,
            ROUND(MAX(l.price_current / NULLIF(l.area_total, 0))::numeric, 0) as max_price,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY l.price_current / NULLIF(l.area_total, 0)
            )::numeric, 0) as median_price
        FROM listings l
        JOIN districts d ON l.district_id = d.district_id
        WHERE l.price_current > 0 AND l.area_total > 0
        GROUP BY d.level
        ORDER BY d.level DESC
    """)
    
    print(f"\n{'Level':<20} {'Segments':>10} {'Listings':>10} {'Avg ₽/m²':>12} "
          f"{'StdDev':>12} {'CV %':>8}")
    print("-" * 80)
    
    for row in cursor.fetchall():
        level_desc = f"{row['level']}-{row['level_name']}"
        avg = int(row['avg_price_per_sqm'])
        stddev = int(row['stddev_price']) if row['stddev_price'] else 0
        cv = (stddev / avg * 100) if avg > 0 else 0
        
        print(f"{level_desc:<20} {row['segment_count']:>10,} {row['listing_count']:>10,} "
              f"{avg:>12,} {stddev:>12,} {cv:>7.1f}%")
    
    print("\n💡 Coefficient of Variation (CV):")
    print("   Lower CV = more homogeneous prices within segment level")
    print("   Higher CV = more price variation within segment level")
    
    cursor.close()
    conn.close()


def show_data_quality():
    """Show data quality metrics."""
    print("\n" + "=" * 80)
    print("🔍 DATA QUALITY METRICS")
    print("=" * 80)
    
    conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    # Address completeness
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(address) as has_address,
            COUNT(address_full) as has_address_full,
            COUNT(lat) as has_lat,
            COUNT(lon) as has_lon,
            COUNT(fias_id) as has_fias,
            COUNT(district_id) as has_district,
            ROUND(100.0 * COUNT(address) / COUNT(*), 2) as pct_address,
            ROUND(100.0 * COUNT(lat) / COUNT(*), 2) as pct_coords,
            ROUND(100.0 * COUNT(district_id) / COUNT(*), 2) as pct_district
        FROM listings
    """)
    
    quality = cursor.fetchone()
    
    print(f"\n✅ Data Completeness:")
    print(f"  Total listings: {quality['total']:,}")
    print(f"  With address: {quality['has_address']:,} ({quality['pct_address']}%)")
    print(f"  With address_full: {quality['has_address_full']:,}")
    print(f"  With coordinates: {quality['has_lat']:,} ({quality['pct_coords']}%)")
    print(f"  With FIAS ID: {quality['has_fias']:,}")
    print(f"  With district: {quality['has_district']:,} ({quality['pct_district']}%)")
    
    # Coordinate quality
    cursor.execute("""
        SELECT 
            COUNT(*) as with_coords,
            COUNT(*) FILTER (WHERE lat BETWEEN 55.0 AND 56.5 AND lon BETWEEN 37.0 AND 38.5) as in_moscow,
            COUNT(*) FILTER (WHERE lat NOT BETWEEN 55.0 AND 56.5 OR lon NOT BETWEEN 37.0 AND 38.5) as outside_moscow
        FROM listings
        WHERE lat IS NOT NULL AND lon IS NOT NULL
    """)
    
    coord_quality = cursor.fetchone()
    
    print(f"\n🌍 Coordinate Quality:")
    print(f"  Total with coords: {coord_quality['with_coords']:,}")
    print(f"  In Moscow bbox: {coord_quality['in_moscow']:,}")
    print(f"  Outside Moscow: {coord_quality['outside_moscow']:,} ⚠️")
    
    # Segment hierarchy quality
    cursor.execute("""
        SELECT 
            level,
            COUNT(*) as total,
            COUNT(parent_district_id) as with_parent,
            COUNT(geometry) as with_geometry,
            ROUND(100.0 * COUNT(parent_district_id) / COUNT(*), 2) as pct_with_parent
        FROM districts
        WHERE level > 1
        GROUP BY level
        ORDER BY level
    """)
    
    print(f"\n🔗 Segment Hierarchy Quality:")
    print(f"{'Level':>5} {'Total':>10} {'With Parent':>15} {'%':>8}")
    print("-" * 80)
    
    for row in cursor.fetchall():
        print(f"{row['level']:>5} {row['total']:>10,} {row['with_parent']:>15,} {row['pct_with_parent']:>7.2f}%")
    
    cursor.close()
    conn.close()


def show_recommendations():
    """Show recommendations for improvement."""
    print("\n" + "=" * 80)
    print("💡 RECOMMENDATIONS")
    print("=" * 80)
    
    conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(lat) as with_coords,
            COUNT(district_id) as with_district,
            COUNT(*) - COUNT(lat) as need_geocoding,
            COUNT(*) - COUNT(district_id) as need_segment_assignment
        FROM listings
    """)
    
    stats = cursor.fetchone()
    
    recommendations = []
    
    if stats['need_geocoding'] > 0:
        recommendations.append({
            'priority': '🔴 HIGH',
            'issue': f"{stats['need_geocoding']:,} listings without coordinates",
            'action': 'Run: python scripts/geocode_all_listings.py',
            'impact': 'Enable spatial analysis and map visualization'
        })
    
    if stats['need_segment_assignment'] > 0:
        recommendations.append({
            'priority': '🟠 MEDIUM',
            'issue': f"{stats['need_segment_assignment']:,} listings without segment",
            'action': 'Run: python scripts/assign_segments_to_listings.py',
            'impact': 'Enable price analysis by micro-location'
        })
    
    # Check if we have detailed segments
    cursor.execute("SELECT COUNT(*) FROM districts WHERE level >= 3")
    detailed_segments = cursor.fetchone()[0]
    
    if detailed_segments < 100:
        recommendations.append({
            'priority': '🟡 LOW',
            'issue': f"Only {detailed_segments} micro-segments (need 500+)",
            'action': 'Run: python scripts/load_segments_detailed.py',
            'impact': 'More precise valuation modeling'
        })
    
    # Check aggregates
    cursor.execute("SELECT COUNT(*) FROM district_aggregates WHERE date = CURRENT_DATE")
    aggregates = cursor.fetchone()[0]
    
    if aggregates == 0:
        recommendations.append({
            'priority': '🟠 MEDIUM',
            'issue': 'No price aggregates calculated',
            'action': 'Run: python scripts/aggregate_districts.py',
            'impact': 'Enable market analysis and price benchmarking'
        })
    
    cursor.close()
    conn.close()
    
    if recommendations:
        print("\n📋 Action Items:\n")
        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. {rec['priority']} {rec['issue']}")
            print(f"   → Action: {rec['action']}")
            print(f"   → Impact: {rec['impact']}\n")
    else:
        print("\n✅ All systems operational! No action items.")


def main():
    """Main execution."""
    print("\n" + "=" * 80)
    print("🔬 GEOGRAPHIC SEGMENTATION ANALYSIS")
    print("=" * 80)
    
    try:
        show_segment_coverage()
        show_listing_distribution()
        show_top_segments()
        show_price_variation()
        show_data_quality()
        show_recommendations()
        
        print("\n" + "=" * 80)
        print("✅ Analysis completed!")
        print("=" * 80)
    
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()

