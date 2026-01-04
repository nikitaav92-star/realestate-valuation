#!/usr/bin/env python3
"""
Load district boundaries from OpenStreetMap and populate districts table.

This script fetches administrative district boundaries for Moscow from OSM
using the Overpass API and stores them in PostGIS format.
"""

import os
import sys
import json
import requests
import psycopg2
from psycopg2.extras import execute_values
from typing import List, Dict, Optional
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Database connection
DSN = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")

# Overpass API endpoint
OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def fetch_moscow_districts() -> List[Dict]:
    """
    Fetch Moscow district boundaries from OpenStreetMap using Overpass API.

    Returns list of districts with geometry and metadata.
    """
    print("📡 Fetching Moscow districts from OpenStreetMap...")

    # Overpass query to get Moscow districts (admin_level=9 are районы)
    # admin_level=8 are округа (okrugs), admin_level=9 are районы (rayons)
    query = """
    [out:json][timeout:90];
    area["name"="Москва"]["admin_level"="4"]->.city;
    (
      relation["boundary"="administrative"]["admin_level"="9"](area.city);
      relation["boundary"="administrative"]["admin_level"="8"](area.city);
    );
    out geom;
    """

    try:
        response = requests.post(
            OVERPASS_URL,
            data={'data': query},
            timeout=120
        )
        response.raise_for_status()
        data = response.json()

        print(f"✅ Received {len(data.get('elements', []))} districts from OSM")
        return data.get('elements', [])

    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching from Overpass API: {e}")
        return []


def convert_osm_to_geojson(osm_element: Dict) -> Optional[Dict]:
    """
    Convert OSM relation to GeoJSON MultiPolygon.

    Args:
        osm_element: OSM relation from Overpass API

    Returns:
        GeoJSON geometry or None if conversion fails
    """
    if osm_element.get('type') != 'relation':
        return None

    # Extract outer ways (polygons)
    polygons = []

    for member in osm_element.get('members', []):
        if member.get('role') == 'outer' and member.get('type') == 'way':
            # Extract coordinates from way geometry
            coords = []
            for node in member.get('geometry', []):
                coords.append([node['lon'], node['lat']])

            # Close polygon if not closed
            if coords and coords[0] != coords[-1]:
                coords.append(coords[0])

            if len(coords) >= 4:  # Valid polygon needs at least 4 points
                polygons.append([coords])

    if not polygons:
        return None

    # Return MultiPolygon GeoJSON
    return {
        'type': 'MultiPolygon',
        'coordinates': polygons
    }


def calculate_center(geometry: Dict) -> tuple:
    """
    Calculate center point of a MultiPolygon.

    Returns:
        (lat, lon) tuple
    """
    all_lons = []
    all_lats = []

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

    return (55.75, 37.62)  # Moscow center as fallback


def insert_districts(districts: List[Dict]) -> int:
    """
    Insert districts into database.

    Args:
        districts: List of OSM district elements

    Returns:
        Number of districts inserted
    """
    if not districts:
        print("⚠️  No districts to insert")
        return 0

    print(f"💾 Inserting {len(districts)} districts into database...")

    conn = psycopg2.connect(DSN)
    cursor = conn.cursor()

    inserted = 0
    skipped = 0

    for osm_element in districts:
        tags = osm_element.get('tags', {})
        name = tags.get('name')

        if not name:
            skipped += 1
            continue

        # Convert to GeoJSON
        geometry = convert_osm_to_geojson(osm_element)
        if not geometry:
            print(f"⚠️  Could not convert geometry for {name}")
            skipped += 1
            continue

        # Calculate center
        center_lat, center_lon = calculate_center(geometry)

        # Extract metadata
        admin_level = int(tags.get('admin_level', '9'))
        level = 1 if admin_level == 8 else 2 if admin_level == 9 else 3
        full_name = tags.get('official_name') or tags.get('alt_name') or name

        # Convert GeoJSON to WKT for PostGIS
        geometry_json = json.dumps(geometry)

        try:
            cursor.execute("""
                INSERT INTO districts (
                    name, full_name, region_code, level,
                    geometry, center_lat, center_lon
                )
                VALUES (
                    %s, %s, '77', %s,
                    ST_GeomFromGeoJSON(%s), %s, %s
                )
                ON CONFLICT DO NOTHING
                RETURNING district_id
            """, (
                name, full_name, level,
                geometry_json, center_lat, center_lon
            ))

            result = cursor.fetchone()
            if result:
                inserted += 1
                print(f"  ✓ {name} (level {level})")
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

    print(f"\n✅ Inserted {inserted} districts, skipped {skipped}")
    return inserted


def add_manual_districts():
    """
    Add some districts manually for MVP (in case OSM fetch fails).
    This adds major Moscow okrugs (округа) as simplified rectangles.
    """
    print("📝 Adding manual districts for MVP...")

    # Manual districts: major Moscow okrugs with approximate boundaries
    manual_districts = [
        {
            'name': 'ЦАО',
            'full_name': 'Центральный административный округ',
            'level': 1,
            'center': (55.7558, 37.6173),
            'bbox': [[37.5500, 55.7300], [37.6900, 55.7800]]  # [lon, lat]
        },
        {
            'name': 'САО',
            'full_name': 'Северный административный округ',
            'level': 1,
            'center': (55.8500, 37.5300),
            'bbox': [[37.4500, 55.8000], [37.6500, 55.9000]]
        },
        {
            'name': 'СВАО',
            'full_name': 'Северо-Восточный административный округ',
            'level': 1,
            'center': (55.8700, 37.6500),
            'bbox': [[37.5500, 55.8200], [37.7500, 55.9200]]
        },
        {
            'name': 'ВАО',
            'full_name': 'Восточный административный округ',
            'level': 1,
            'center': (55.7500, 37.8000),
            'bbox': [[37.7000, 55.7000], [37.9000, 55.8000]]
        },
        {
            'name': 'ЮВАО',
            'full_name': 'Юго-Восточный административный округ',
            'level': 1,
            'center': (55.6800, 37.7500),
            'bbox': [[37.6500, 55.6300], [37.8500, 55.7300]]
        },
        {
            'name': 'ЮАО',
            'full_name': 'Южный административный округ',
            'level': 1,
            'center': (55.6200, 37.6000),
            'bbox': [[37.5000, 55.5700], [37.7000, 55.6700]]
        },
        {
            'name': 'ЮЗАО',
            'full_name': 'Юго-Западный административный округ',
            'level': 1,
            'center': (55.6500, 37.5000),
            'bbox': [[37.4000, 55.6000], [37.6000, 55.7000]]
        },
        {
            'name': 'ЗАО',
            'full_name': 'Западный административный округ',
            'level': 1,
            'center': (55.7200, 37.4500),
            'bbox': [[37.3500, 55.6700], [37.5500, 55.7700]]
        },
        {
            'name': 'СЗАО',
            'full_name': 'Северо-Западный административный округ',
            'level': 1,
            'center': (55.8200, 37.4500),
            'bbox': [[37.3500, 55.7700], [37.5500, 55.8700]]
        },
        {
            'name': 'ЗелАО',
            'full_name': 'Зеленоградский административный округ',
            'level': 1,
            'center': (55.9900, 37.2100),
            'bbox': [[37.1500, 55.9500], [37.2700, 56.0300]]
        },
    ]

    conn = psycopg2.connect(DSN)
    cursor = conn.cursor()

    inserted = 0

    for district in manual_districts:
        # Create simple rectangular polygon from bbox
        bbox = district['bbox']
        polygon = f"""
        {{
            "type": "MultiPolygon",
            "coordinates": [[[[
                [{bbox[0][0]}, {bbox[0][1]}],
                [{bbox[1][0]}, {bbox[0][1]}],
                [{bbox[1][0]}, {bbox[1][1]}],
                [{bbox[0][0]}, {bbox[1][1]}],
                [{bbox[0][0]}, {bbox[0][1]}]
            ]]]]
        }}
        """

        try:
            cursor.execute("""
                INSERT INTO districts (
                    name, full_name, region_code, level,
                    geometry, center_lat, center_lon
                )
                VALUES (
                    %s, %s, '77', %s,
                    ST_GeomFromGeoJSON(%s), %s, %s
                )
                ON CONFLICT DO NOTHING
                RETURNING district_id
            """, (
                district['name'],
                district['full_name'],
                district['level'],
                polygon,
                district['center'][0],
                district['center'][1]
            ))

            result = cursor.fetchone()
            if result:
                inserted += 1
                print(f"  ✓ {district['name']}")

        except Exception as e:
            print(f"  ❌ Error inserting {district['name']}: {e}")
            conn.rollback()
            continue

    conn.commit()
    cursor.close()
    conn.close()

    print(f"✅ Added {inserted} manual districts")
    return inserted


def main():
    """Main function."""
    print("🗺️  Loading Moscow district boundaries")
    print("=" * 60)

    # Try to fetch from OSM first
    osm_districts = fetch_moscow_districts()

    if osm_districts:
        inserted = insert_districts(osm_districts)

        if inserted == 0:
            print("\n⚠️  No districts inserted from OSM, falling back to manual districts")
            add_manual_districts()
    else:
        print("\n⚠️  Could not fetch from OSM, using manual districts")
        add_manual_districts()

    # Show summary
    conn = psycopg2.connect(DSN)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), COUNT(DISTINCT level) FROM districts")
    total, levels = cursor.fetchone()
    cursor.close()
    conn.close()

    print("\n" + "=" * 60)
    print(f"✅ Total districts in database: {total}")
    print(f"✅ Number of levels: {levels}")
    print("\n💡 Next: Run scripts/assign_districts.py to assign districts to listings")


if __name__ == '__main__':
    main()
