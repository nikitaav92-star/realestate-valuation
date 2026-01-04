#!/usr/bin/env python3
"""Calculate multi-dimensional price aggregates."""
import os
import psycopg2
from datetime import date

DSN = os.getenv("PG_DSN", "postgresql://realuser:strongpass123@localhost:5432/realdb")

conn = psycopg2.connect(DSN)
cursor = conn.cursor()
today = date.today()

print(f"📊 Aggregating for {today}...")

# Delete old
cursor.execute("DELETE FROM multidim_aggregates WHERE date = %s", (today,))

# Insert new
cursor.execute("""
    INSERT INTO multidim_aggregates (
        district_id, property_segment_id, date,
        avg_price_per_sqm, median_price_per_sqm,
        min_price, max_price, total_listings, avg_area,
        price_stddev, confidence_score
    )
    SELECT
        l.district_id, l.property_segment_id, %s,
        AVG(COALESCE(lp.price, l.initial_price) / NULLIF(l.area_total, 0))::numeric(12,2),
        PERCENTILE_CONT(0.5) WITHIN GROUP (
            ORDER BY COALESCE(lp.price, l.initial_price) / NULLIF(l.area_total, 0)
        )::numeric(12,2),
        MIN(COALESCE(lp.price, l.initial_price))::numeric(12,2),
        MAX(COALESCE(lp.price, l.initial_price))::numeric(12,2),
        COUNT(*), AVG(l.area_total)::numeric(6,2),
        STDDEV(COALESCE(lp.price, l.initial_price) / NULLIF(l.area_total, 0))::numeric(12,2),
        LEAST(100, 20 + (COUNT(*) / 5) * 10)
    FROM listings l
    LEFT JOIN LATERAL (
        SELECT price FROM listing_prices
        WHERE id = l.id ORDER BY seen_at DESC LIMIT 1
    ) lp ON TRUE
    WHERE l.district_id IS NOT NULL
      AND l.property_segment_id IS NOT NULL
      AND l.area_total > 0
      AND COALESCE(lp.price, l.initial_price) > 0
      AND l.is_active = TRUE
      AND l.last_seen >= CURRENT_DATE - INTERVAL '90 days'
    GROUP BY l.district_id, l.property_segment_id
    HAVING COUNT(*) >= 3
""", (today,))

inserted = cursor.rowcount
conn.commit()
print(f"✅ Inserted {inserted} aggregates")

cursor.close()
conn.close()
