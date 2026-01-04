#!/usr/bin/env python3
"""
Assign district_id to listings based on coordinates and address.

This script uses three methods in order of priority:
1. PostGIS ST_Contains - match by coordinates (most accurate)
2. Text parsing - extract district name from address
3. Nearest district - fallback for unmatched listings
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
import re
from typing import Optional, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Database connection
DSN = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")


def assign_by_coordinates(cursor, batch_size: int = 1000) -> int:
    """
    Assign districts based on coordinates using PostGIS ST_Contains.

    This is the most accurate method as it uses actual geographic boundaries.

    Args:
        cursor: Database cursor
        batch_size: Number of listings to process per batch

    Returns:
        Number of listings updated
    """
    print("📍 Method 1: Assigning districts by coordinates (PostGIS)...")

    cursor.execute("""
        UPDATE listings l
        SET district_id = (
            SELECT d.district_id
            FROM districts d
            WHERE ST_Contains(
                d.geometry,
                ST_SetSRID(ST_MakePoint(l.lon, l.lat), 4326)
            )
            LIMIT 1
        )
        WHERE l.district_id IS NULL
          AND l.lat IS NOT NULL
          AND l.lon IS NOT NULL
          AND l.lat BETWEEN 55.0 AND 56.5
          AND l.lon BETWEEN 36.5 AND 38.5
        RETURNING id
    """)

    updated = cursor.rowcount
    print(f"  ✓ Assigned {updated} listings by coordinates")
    return updated


def extract_district_from_address(address: str) -> Optional[str]:
    """
    Extract district name from address string using regex patterns.

    Args:
        address: Address string

    Returns:
        District name or None
    """
    if not address:
        return None

    # Patterns for Moscow districts
    patterns = [
        # Районы (rayons)
        r'р-н\s+([А-Яа-яёЁ][А-Яа-яё\s-]+?)(?:\s*,|\s*$)',
        r'район\s+([А-Яа-яёЁ][А-Яа-яё\s-]+?)(?:\s*,|\s*$)',
        r'мкр\.\s+([А-Яа-яёЁ][А-Яа-яё\s-]+?)(?:\s*,|\s*$)',
        r'микрорайон\s+([А-Яа-яёЁ][А-Яа-яё\s-]+?)(?:\s*,|\s*$)',

        # Округа (okrugs) - administrative districts
        r'\b(ЦАО|САО|СВАО|ВАО|ЮВАО|ЮАО|ЮЗАО|ЗАО|СЗАО|ЗелАО)\b',

        # Named districts without prefix
        r',\s+([А-Яа-яёЁ][А-Яа-яё\s-]{5,30}?)\s+улица',
        r',\s+([А-Яа-яёЁ][А-Яа-яё\s-]{5,30}?)\s+ул\.',
    ]

    for pattern in patterns:
        match = re.search(pattern, address)
        if match:
            district_name = match.group(1).strip()
            # Clean up common noise
            district_name = district_name.replace('мунициальный', '').strip()
            if len(district_name) >= 3:
                return district_name

    return None


def assign_by_address_text(cursor) -> int:
    """
    Assign districts by parsing address text.

    Args:
        cursor: Database cursor

    Returns:
        Number of listings updated
    """
    print("🔤 Method 2: Assigning districts by address text parsing...")

    # Get unassigned listings with addresses
    cursor.execute("""
        SELECT id, address, address_full, fias_address
        FROM listings
        WHERE district_id IS NULL
          AND (address IS NOT NULL OR address_full IS NOT NULL OR fias_address IS NOT NULL)
        LIMIT 10000
    """)

    listings = cursor.fetchall()
    updated = 0
    matched = {}

    for listing in listings:
        # Try different address fields
        addresses_to_try = [
            listing['fias_address'],
            listing['address_full'],
            listing['address']
        ]

        district_name = None
        for addr in addresses_to_try:
            district_name = extract_district_from_address(addr)
            if district_name:
                break

        if not district_name:
            continue

        # Find matching district in database (cached)
        if district_name not in matched:
            cursor.execute("""
                SELECT district_id
                FROM districts
                WHERE name ILIKE %s
                   OR full_name ILIKE %s
                   OR name ILIKE %s
                LIMIT 1
            """, (
                district_name,
                f'%{district_name}%',
                f'%{district_name}%'
            ))

            result = cursor.fetchone()
            matched[district_name] = result['district_id'] if result else None

        district_id = matched[district_name]
        if district_id:
            cursor.execute("""
                UPDATE listings
                SET district_id = %s
                WHERE id = %s
            """, (district_id, listing['id']))
            updated += 1

    print(f"  ✓ Assigned {updated} listings by address text")
    return updated


def assign_by_nearest(cursor) -> int:
    """
    Assign remaining listings to nearest district (fallback method).

    Args:
        cursor: Database cursor

    Returns:
        Number of listings updated
    """
    print("📏 Method 3: Assigning to nearest district (fallback)...")

    cursor.execute("""
        WITH nearest_district AS (
            SELECT
                l.id,
                (
                    SELECT d.district_id
                    FROM districts d
                    WHERE d.center_lat IS NOT NULL
                      AND d.center_lon IS NOT NULL
                    ORDER BY
                        ST_Distance(
                            ST_MakePoint(d.center_lon, d.center_lat)::geography,
                            ST_MakePoint(l.lon, l.lat)::geography
                        )
                    LIMIT 1
                ) as nearest_district_id
            FROM listings l
            WHERE l.district_id IS NULL
              AND l.lat IS NOT NULL
              AND l.lon IS NOT NULL
              AND l.lat BETWEEN 55.0 AND 56.5
              AND l.lon BETWEEN 36.5 AND 38.5
        )
        UPDATE listings l
        SET district_id = nd.nearest_district_id
        FROM nearest_district nd
        WHERE l.id = nd.id
          AND nd.nearest_district_id IS NOT NULL
        RETURNING l.id
    """)

    updated = cursor.rowcount
    print(f"  ✓ Assigned {updated} listings to nearest district")
    return updated


def show_statistics(cursor):
    """Show assignment statistics."""
    print("\n📊 Assignment Statistics:")
    print("=" * 60)

    # Total listings
    cursor.execute("SELECT COUNT(*) as total FROM listings WHERE is_active = TRUE")
    total = cursor.fetchone()['total']

    # Assigned
    cursor.execute("""
        SELECT COUNT(*) as assigned
        FROM listings
        WHERE is_active = TRUE AND district_id IS NOT NULL
    """)
    assigned = cursor.fetchone()['assigned']

    # By district
    cursor.execute("""
        SELECT
            d.name,
            COUNT(l.id) as count
        FROM districts d
        LEFT JOIN listings l ON l.district_id = d.district_id AND l.is_active = TRUE
        WHERE l.id IS NOT NULL
        GROUP BY d.district_id, d.name
        ORDER BY count DESC
        LIMIT 10
    """)

    top_districts = cursor.fetchall()

    print(f"Total active listings: {total}")
    print(f"Assigned to districts: {assigned} ({100.0 * assigned / total if total > 0 else 0:.1f}%)")
    print(f"Unassigned: {total - assigned}")

    print("\n🏆 Top 10 districts by listings:")
    for i, row in enumerate(top_districts, 1):
        print(f"  {i:2d}. {row['name']:<30s} - {row['count']:>5d} listings")


def main():
    """Main function."""
    print("🗺️  Assigning districts to listings")
    print("=" * 60)

    conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        # Method 1: PostGIS coordinates
        updated_coords = assign_by_coordinates(cursor)
        conn.commit()

        # Method 2: Address text parsing
        updated_text = assign_by_address_text(cursor)
        conn.commit()

        # Method 3: Nearest district (fallback)
        updated_nearest = assign_by_nearest(cursor)
        conn.commit()

        # Show statistics
        show_statistics(cursor)

        print("\n" + "=" * 60)
        print(f"✅ Total updated: {updated_coords + updated_text + updated_nearest}")
        print(f"   - By coordinates: {updated_coords}")
        print(f"   - By address text: {updated_text}")
        print(f"   - By nearest: {updated_nearest}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()

    print("\n💡 Next: Run scripts/aggregate_districts.py to calculate district statistics")


if __name__ == '__main__':
    main()
