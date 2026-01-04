#!/usr/bin/env python3
"""
Load multi-level geographic segments for precise real estate valuation.

Segmentation levels:
1. Округ (Okrug) - admin_level=8 - ~10 segments
2. Район (Rayon) - admin_level=9 - ~125 segments  
3. Микрорайон (Microrayon) - admin_level=10 - ~500 segments
4. Квартал (Quarter/Block) - based on street grid - ~5000+ segments

This creates a hierarchical segmentation for accurate price modeling.
"""

import os
import sys
import json
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Optional, Tuple
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DSN = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Rate limiting for Overpass API
OVERPASS_DELAY = 2  # seconds between requests


def fetch_osm_segments(admin_level: int, parent_area: str = "Москва") -> List[Dict]:
    """
    Fetch administrative segments from OSM by admin level.
    
    Args:
        admin_level: OSM admin level (8=округ, 9=район, 10=микрорайон, 11=квартал)
        parent_area: Parent area name (e.g., "Москва")
    
    Returns:
        List of OSM elements with geometry
    """
    print(f"📡 Fetching segments (admin_level={admin_level}) from OpenStreetMap...")
    
    query = f"""
    [out:json][timeout:180];
    area["name"="{parent_area}"]["admin_level"="4"]->.city;
    (
      relation["boundary"="administrative"]["admin_level"="{admin_level}"](area.city);
    );
    out geom;
    """
    
    try:
        response = requests.post(
            OVERPASS_URL,
            data={'data': query},
            timeout=200
        )
        response.raise_for_status()
        data = response.json()
        
        elements = data.get('elements', [])
        print(f"✅ Received {len(elements)} segments (level {admin_level}) from OSM")
        return elements
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching from Overpass API: {e}")
        return []


def fetch_street_segments(bbox: Tuple[float, float, float, float]) -> List[Dict]:
    """
    Fetch street-based segments (квартал) by creating grid based on streets.
    
    Args:
        bbox: Bounding box (min_lat, min_lon, max_lat, max_lon)
    
    Returns:
        List of street segments
    """
    print(f"📡 Fetching street network for квартал segmentation...")
    
    min_lat, min_lon, max_lat, max_lon = bbox
    
    query = f"""
    [out:json][timeout:180];
    (
      way["highway"]["name"]({min_lat},{min_lon},{max_lat},{max_lon});
    );
    out geom;
    """
    
    try:
        response = requests.post(
            OVERPASS_URL,
            data={'data': query},
            timeout=200
        )
        response.raise_for_status()
        data = response.json()
        
        elements = data.get('elements', [])
        print(f"✅ Received {len(elements)} street segments from OSM")
        return elements
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching streets: {e}")
        return []


def convert_osm_to_geojson(osm_element: Dict) -> Optional[Dict]:
    """
    Convert OSM relation/way to GeoJSON MultiPolygon.
    """
    element_type = osm_element.get('type')
    
    if element_type == 'relation':
        # Extract outer ways (polygons)
        polygons = []
        
        for member in osm_element.get('members', []):
            if member.get('role') == 'outer' and member.get('type') == 'way':
                coords = []
                for node in member.get('geometry', []):
                    coords.append([node['lon'], node['lat']])
                
                # Close polygon
                if coords and coords[0] != coords[-1]:
                    coords.append(coords[0])
                
                if len(coords) >= 4:
                    polygons.append([coords])
        
        if polygons:
            return {
                'type': 'MultiPolygon',
                'coordinates': polygons
            }
    
    elif element_type == 'way':
        # Simple way to polygon
        coords = []
        for node in osm_element.get('geometry', []):
            coords.append([node['lon'], node['lat']])
        
        # Close polygon
        if coords and coords[0] != coords[-1]:
            coords.append(coords[0])
        
        if len(coords) >= 4:
            return {
                'type': 'MultiPolygon',
                'coordinates': [[[coords]]]
            }
    
    return None


def calculate_center(geometry: Dict) -> Tuple[float, float]:
    """Calculate centroid of MultiPolygon."""
    all_lons, all_lats = [], []
    
    for polygon in geometry.get('coordinates', []):
        for ring in polygon:
            for lon, lat in ring:
                all_lons.append(lon)
                all_lats.append(lat)
    
    if all_lons and all_lats:
        return (
            sum(all_lats) / len(all_lats),
            sum(all_lons) / len(all_lons)
        )
    
    return (55.75, 37.62)


def insert_segments(segments: List[Dict], level: int, parent_id: Optional[int] = None) -> int:
    """
    Insert geographic segments into database.
    
    Args:
        segments: List of OSM elements
        level: Hierarchy level (1=округ, 2=район, 3=микрорайон, 4=квартал)
        parent_id: Parent district_id for hierarchy
    
    Returns:
        Number of segments inserted
    """
    if not segments:
        print(f"⚠️  No segments to insert for level {level}")
        return 0
    
    print(f"💾 Inserting {len(segments)} segments (level {level})...")
    
    conn = psycopg2.connect(DSN)
    cursor = conn.cursor()
    
    inserted = 0
    skipped = 0
    
    for osm_element in segments:
        tags = osm_element.get('tags', {})
        name = tags.get('name') or tags.get('addr:street') or f"Segment_{osm_element.get('id', 'unknown')}"
        
        # Convert to GeoJSON
        geometry = convert_osm_to_geojson(osm_element)
        if not geometry:
            skipped += 1
            continue
        
        # Calculate center
        center_lat, center_lon = calculate_center(geometry)
        
        # Extract metadata
        full_name = tags.get('official_name') or tags.get('alt_name') or name
        geometry_json = json.dumps(geometry)
        
        try:
            cursor.execute("""
                INSERT INTO districts (
                    name, full_name, region_code, level,
                    parent_district_id,
                    geometry, center_lat, center_lon
                )
                VALUES (
                    %s, %s, '77', %s, %s,
                    ST_GeomFromGeoJSON(%s), %s, %s
                )
                ON CONFLICT DO NOTHING
                RETURNING district_id
            """, (
                name, full_name, level, parent_id,
                geometry_json, center_lat, center_lon
            ))
            
            result = cursor.fetchone()
            if result:
                inserted += 1
                if inserted % 50 == 0:
                    print(f"  Progress: {inserted} segments inserted...")
            else:
                skipped += 1
        
        except Exception as e:
            print(f"  ❌ Error inserting {name}: {e}")
            skipped += 1
            conn.rollback()
            continue
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"✅ Level {level}: Inserted {inserted} segments, skipped {skipped}")
    return inserted


def create_grid_segments(bbox: Tuple[float, float, float, float], grid_size: float = 0.01) -> List[Dict]:
    """
    Create grid-based segments (квартал) for areas without street data.
    
    Args:
        bbox: Bounding box (min_lat, min_lon, max_lat, max_lon)
        grid_size: Grid cell size in degrees (~1km = 0.01°)
    
    Returns:
        List of grid segments
    """
    print(f"🔲 Creating grid segments with cell size {grid_size}°...")
    
    min_lat, min_lon, max_lat, max_lon = bbox
    
    segments = []
    lat = min_lat
    idx = 0
    
    while lat < max_lat:
        lon = min_lon
        while lon < max_lon:
            # Create rectangular segment
            segment = {
                'type': 'grid',
                'tags': {'name': f'Grid_{idx}'},
                'geometry': {
                    'type': 'MultiPolygon',
                    'coordinates': [[[[
                        [lon, lat],
                        [lon + grid_size, lat],
                        [lon + grid_size, lat + grid_size],
                        [lon, lat + grid_size],
                        [lon, lat]
                    ]]]]
                }
            }
            segments.append(segment)
            idx += 1
            lon += grid_size
        lat += grid_size
    
    print(f"✅ Created {len(segments)} grid segments")
    return segments


def load_all_segments():
    """
    Load all segmentation levels in hierarchical order.
    """
    print("🗺️  Multi-Level Segmentation Loading")
    print("=" * 70)
    
    # Moscow bounding box
    moscow_bbox = (55.49, 37.35, 55.96, 37.84)
    
    stats = {'level_1': 0, 'level_2': 0, 'level_3': 0, 'level_4': 0}
    
    # Level 1: Округа (Okrugs) - admin_level=8
    print("\n📍 LEVEL 1: Округа (Okrugs)")
    print("-" * 70)
    okrugs = fetch_osm_segments(admin_level=8)
    if okrugs:
        stats['level_1'] = insert_segments(okrugs, level=1)
        time.sleep(OVERPASS_DELAY)
    
    # Level 2: Районы (Rayons) - admin_level=9
    print("\n📍 LEVEL 2: Районы (Rayons)")
    print("-" * 70)
    rayons = fetch_osm_segments(admin_level=9)
    if rayons:
        stats['level_2'] = insert_segments(rayons, level=2)
        time.sleep(OVERPASS_DELAY)
    
    # Level 3: Микрорайоны (Microrayons) - admin_level=10
    print("\n📍 LEVEL 3: Микрорайоны (Microrayons)")
    print("-" * 70)
    microrayons = fetch_osm_segments(admin_level=10)
    if microrayons:
        stats['level_3'] = insert_segments(microrayons, level=3)
        time.sleep(OVERPASS_DELAY)
    else:
        # Fallback: subdivide level 2 into smaller segments
        print("⚠️  No microrayons found, using grid subdivision")
        grid_segments = create_grid_segments(moscow_bbox, grid_size=0.02)  # ~2km cells
        stats['level_3'] = insert_segments(grid_segments, level=3)
    
    # Level 4: Кварталы (Quarters/Blocks) - street-based or fine grid
    print("\n📍 LEVEL 4: Кварталы (Quarters)")
    print("-" * 70)
    print("Creating fine-grained grid for квартал-level segmentation...")
    quarter_segments = create_grid_segments(moscow_bbox, grid_size=0.005)  # ~500m cells
    stats['level_4'] = insert_segments(quarter_segments, level=4)
    
    return stats


def establish_hierarchy():
    """
    Establish parent-child relationships between segments.
    Uses spatial containment to link child segments to parent segments.
    """
    print("\n🔗 Establishing segment hierarchy...")
    print("-" * 70)
    
    conn = psycopg2.connect(DSN)
    cursor = conn.cursor()
    
    # Link level 2 (районы) to level 1 (округа)
    print("Linking районы → округа...")
    cursor.execute("""
        UPDATE districts d2
        SET parent_district_id = (
            SELECT d1.district_id
            FROM districts d1
            WHERE d1.level = 1
              AND d2.level = 2
              AND ST_Within(ST_Centroid(d2.geometry), d1.geometry)
            LIMIT 1
        )
        WHERE d2.level = 2 AND d2.parent_district_id IS NULL
    """)
    level_2_linked = cursor.rowcount
    
    # Link level 3 (микрорайоны) to level 2 (районы)
    print("Linking микрорайоны → районы...")
    cursor.execute("""
        UPDATE districts d3
        SET parent_district_id = (
            SELECT d2.district_id
            FROM districts d2
            WHERE d2.level = 2
              AND d3.level = 3
              AND ST_Within(ST_Centroid(d3.geometry), d2.geometry)
            LIMIT 1
        )
        WHERE d3.level = 3 AND d3.parent_district_id IS NULL
    """)
    level_3_linked = cursor.rowcount
    
    # Link level 4 (кварталы) to level 3 (микрорайоны)
    print("Linking кварталы → микрорайоны...")
    cursor.execute("""
        UPDATE districts d4
        SET parent_district_id = (
            SELECT d3.district_id
            FROM districts d3
            WHERE d3.level = 3
              AND d4.level = 4
              AND ST_Within(ST_Centroid(d4.geometry), d3.geometry)
            LIMIT 1
        )
        WHERE d4.level = 4 AND d4.parent_district_id IS NULL
    """)
    level_4_linked = cursor.rowcount
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"✅ Hierarchy established:")
    print(f"  Level 2 → Level 1: {level_2_linked} links")
    print(f"  Level 3 → Level 2: {level_3_linked} links")
    print(f"  Level 4 → Level 3: {level_4_linked} links")


def show_summary():
    """Display segmentation summary."""
    print("\n" + "=" * 70)
    print("📊 SEGMENTATION SUMMARY")
    print("=" * 70)
    
    conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            level,
            COUNT(*) as total_segments,
            COUNT(parent_district_id) as with_parent,
            COUNT(geometry) as with_geometry,
            AVG(ST_Area(geometry::geography) / 1000000) as avg_area_km2
        FROM districts
        GROUP BY level
        ORDER BY level
    """)
    
    print("\n{:<15} {:>12} {:>12} {:>12} {:>15}".format(
        "Level", "Segments", "With Parent", "With Geom", "Avg Area (km²)"
    ))
    print("-" * 70)
    
    level_names = {
        1: "Округ",
        2: "Район", 
        3: "Микрорайон",
        4: "Квартал"
    }
    
    for row in cursor.fetchall():
        level_name = f"{row['level']}-{level_names.get(row['level'], 'Unknown')}"
        avg_area = row['avg_area_km2'] if row['avg_area_km2'] else 0
        print("{:<15} {:>12} {:>12} {:>12} {:>15.2f}".format(
            level_name,
            row['total_segments'],
            row['with_parent'],
            row['with_geometry'],
            avg_area
        ))
    
    cursor.close()
    conn.close()


def main():
    """Main execution."""
    print("\n" + "=" * 70)
    print("🏘️  DETAILED GEOGRAPHIC SEGMENTATION FOR VALUATION")
    print("=" * 70)
    print("\nThis will create a 4-level hierarchy:")
    print("  Level 1: Округ (10-15 segments, ~50-100 km² each)")
    print("  Level 2: Район (100-150 segments, ~5-10 km² each)")
    print("  Level 3: Микрорайон (500+ segments, ~1-2 km² each)")
    print("  Level 4: Квартал (5000+ segments, ~0.25 km² each)")
    print("\n⏱️  Expected time: 10-20 minutes")
    print("=" * 70)
    
    response = input("\nContinue? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelled")
        return
    
    # Load all segments
    stats = load_all_segments()
    
    # Establish hierarchy
    establish_hierarchy()
    
    # Show summary
    show_summary()
    
    print("\n" + "=" * 70)
    print("✅ Multi-level segmentation completed!")
    print("\n💡 Next steps:")
    print("  1. Run: python scripts/assign_segments_to_listings.py")
    print("  2. Run: python scripts/aggregate_districts.py")
    print("  3. Check results: python scripts/analyze_segmentation.py")
    print("=" * 70)


if __name__ == '__main__':
    main()

