#!/usr/bin/env python3
"""
Скрипт для анализа обременений в существующих объявлениях.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import psycopg2
import psycopg2.extras
import json
from etl.encumbrance_analyzer import analyze_description, get_analyzer

def main():
    """Анализировать все существующие описания."""
    dsn = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Получить все объявления с описаниями
    cur.execute("""
        SELECT id, description, url
        FROM listings
        WHERE is_active = TRUE 
          AND description IS NOT NULL
          AND LENGTH(description) > 50
        ORDER BY id DESC
    """)
    
    listings = cur.fetchall()
    
    print(f"📊 Найдено объявлений с описаниями: {len(listings)}")
    print("="*80)
    
    analyzer = get_analyzer()
    updated_count = 0
    encumbrance_count = 0
    
    for listing in listings:
        listing_id = listing['id']
        description = listing['description']
        
        # Анализ
        analysis = analyze_description(description)
        
        if analysis['has_encumbrances']:
            encumbrance_count += 1
            print(f"\n⚠️  Listing {listing_id}")
            print(f"URL: {listing['url']}")
            print(analyzer.get_summary(analysis))
        
        # Обновить БД
        cur.execute("""
            UPDATE listings
            SET
                has_encumbrances = %s,
                encumbrance_types = %s,
                encumbrance_details = %s,
                encumbrance_confidence = %s
            WHERE id = %s
        """, (
            analysis['has_encumbrances'],
            analysis.get('flags', []),
            json.dumps(analysis),
            analysis.get('confidence', 0.0),
            listing_id
        ))
        
        updated_count += 1
        
        if updated_count % 10 == 0:
            conn.commit()
            print(f"✅ Обработано: {updated_count}/{len(listings)}")
    
    conn.commit()
    
    print("\n" + "="*80)
    print(f"✅ Анализ завершен!")
    print(f"   Обработано: {updated_count}")
    print(f"   С обременениями: {encumbrance_count} ({encumbrance_count/updated_count*100:.1f}%)")
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    main()

