#!/usr/bin/env python3
"""
Comprehensive geocoding for all listings.

Cascading strategy:
1. Parse from CIAN HTML/JSON (if available)
2. DaData API (10,000 free/day)
3. District center + random offset (fallback)
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
import re
from typing import Optional, Tuple
import time
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env file
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

DSN = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")


def extract_district_from_address(address: str) -> Optional[str]:
    """Extract district name from CIAN address."""
    patterns = [
        r'р-н\s+([А-ЯЁ][А-ЯЁа-яё\-\s]+?)(?:,|\s|$)',
        r'район\s+([А-ЯЁ][А-ЯЁа-яё\-\s]+?)(?:,|\s|$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, address)
        if match:
            district = match.group(1).strip()
            district = re.sub(r'\s+', ' ', district)
            return district
    
    return None


def geocode_by_district_center(address: str, conn) -> Optional[Tuple[float, float]]:
    """
    Fallback: Use district center + random offset.
    Good enough for ±1-2km accuracy.
    """
    district_name = extract_district_from_address(address)
    if not district_name:
        return None
    
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT center_lat, center_lon
            FROM districts
            WHERE LOWER(name) LIKE LOWER(%s)
              AND center_lat IS NOT NULL
              AND center_lon IS NOT NULL
            ORDER BY level DESC
            LIMIT 1
        """, (f'%{district_name}%',))
        
        result = cursor.fetchone()
        if result:
            # Add random offset ±0.01° (~1km)
            lat = result['center_lat'] + random.uniform(-0.01, 0.01)
            lon = result['center_lon'] + random.uniform(-0.01, 0.01)
            return (lat, lon)
    
    return None


def clean_address_for_dadata(address: str) -> str:
    """Clean CIAN address format for DaData API.

    CIAN format: "Москва, СВАО, р-н Алексеевский, просп. Мира, 110/2"
    DaData needs: "Москва, просп. Мира, 110/2"
    """
    # Remove округ abbreviations (ЦАО, СВАО, ВАО, etc.)
    address = re.sub(r',?\s*[СЗЦЮВ]+АО\b', '', address)

    # Remove район (р-н XXX, район XXX)
    address = re.sub(r',?\s*р-н\s+[А-ЯЁа-яё\-\s]+?(?=,|$)', '', address)
    address = re.sub(r',?\s*район\s+[А-ЯЁа-яё\-\s]+?(?=,|$)', '', address)

    # Remove metro station names at the end (common in CIAN)
    address = re.sub(r',\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ]?[а-яё]+)*$', '', address)

    # Clean up multiple commas and spaces
    address = re.sub(r',\s*,', ',', address)
    address = re.sub(r'\s+', ' ', address)
    address = address.strip(' ,')

    return address


def geocode_via_dadata(address: str) -> Optional[Tuple[float, float]]:
    """Geocode using DaData Suggest API (free tier)."""
    api_key = os.getenv("DADATA_API_KEY")

    if not api_key:
        return None

    import requests

    # Clean address for better DaData recognition
    clean_addr = clean_address_for_dadata(address)

    try:
        response = requests.post(
            "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Token {api_key}",
            },
            json={"query": clean_addr, "count": 1},
            timeout=10
        )
        response.raise_for_status()

        data = response.json()
        suggestions = data.get("suggestions", [])
        if suggestions:
            result = suggestions[0].get("data", {})
            lat = result.get("geo_lat")
            lon = result.get("geo_lon")

            if lat and lon:
                return (float(lat), float(lon))

    except Exception as e:
        print(f"  DaData error: {e}")

    return None


def geocode_all(batch_size: int = 1000):
    """Geocode all listings without coordinates."""
    
    print("=" * 80)
    print("🌍 COMPREHENSIVE GEOCODING")
    print("=" * 80)
    
    conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    # Check current state
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(lat) as with_coords,
            COUNT(*) - COUNT(lat) as need_geocoding
        FROM listings
    """)
    
    stats = cursor.fetchone()
    print(f"\n📊 Current State:")
    print(f"  Total: {stats['total']:,}")
    print(f"  With coordinates: {stats['with_coords']:,} ({100*stats['with_coords']/stats['total']:.1f}%)")
    print(f"  Need geocoding: {stats['need_geocoding']:,}")
    
    if stats['need_geocoding'] == 0:
        print("\n✅ All listings already geocoded!")
        return
    
    # Check if DaData is configured
    has_dadata = bool(os.getenv("DADATA_API_KEY"))
    print(f"\n🔑 DaData API: {'✅ Configured' if has_dadata else '❌ Not configured (using fallback)'}")
    
    # Get listings without coordinates
    cursor.execute("""
        SELECT id, COALESCE(address_full, address) as address
        FROM listings
        WHERE lat IS NULL OR lon IS NULL
        ORDER BY id
        LIMIT %s
    """, (batch_size,))
    
    listings = cursor.fetchall()
    
    print(f"\n🚀 Processing {len(listings)} listings...")
    print("-" * 80)
    
    success = {
        'dadata': 0,
        'district': 0,
        'failed': 0
    }
    
    for i, listing in enumerate(listings, 1):
        coords = None
        method = None
        
        # Strategy 1: DaData API (if configured)
        if has_dadata:
            coords = geocode_via_dadata(listing['address'])
            if coords:
                method = 'dadata'
                success['dadata'] += 1
        
        # Strategy 2: District center (fallback)
        if not coords:
            coords = geocode_by_district_center(listing['address'], conn)
            if coords:
                method = 'district'
                success['district'] += 1
        
        # Update if found
        if coords:
            cursor.execute("""
                UPDATE listings
                SET lat = %s, lon = %s
                WHERE id = %s
            """, (coords[0], coords[1], listing['id']))
            
            if i % 100 == 0:
                conn.commit()
                print(f"  Progress: {i}/{len(listings)} "
                      f"(DaData: {success['dadata']}, District: {success['district']}, Failed: {success['failed']})")
        else:
            success['failed'] += 1
        
        # Rate limiting for DaData
        if method == 'dadata' and i % 10 == 0:
            time.sleep(1)  # 10 req/sec max
    
    conn.commit()
    
    # Final stats
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(lat) as with_coords,
            ROUND(100.0 * COUNT(lat) / COUNT(*), 1) as pct
        FROM listings
    """)
    
    final = cursor.fetchone()
    
    print("\n" + "=" * 80)
    print("✅ GEOCODING COMPLETE")
    print("=" * 80)
    print(f"\n📊 Results:")
    print(f"  DaData API: {success['dadata']:,}")
    print(f"  District fallback: {success['district']:,}")
    print(f"  Failed: {success['failed']:,}")
    print(f"\n📈 Final Coverage:")
    print(f"  Total: {final['total']:,}")
    print(f"  With coordinates: {final['with_coords']:,} ({final['pct']}%)")
    
    cursor.close()
    conn.close()


if __name__ == '__main__':
    geocode_all(batch_size=10000)

