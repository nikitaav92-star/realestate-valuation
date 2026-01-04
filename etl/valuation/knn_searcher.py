"""K-Nearest Neighbors searcher for property comparables."""

import os
import math
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Optional
from datetime import datetime, timedelta

from .models import PropertyFeatures, Comparable, KNNEstimate


class KNNSearcher:
    """
    Find K most similar properties using weighted distance metric.
    
    Distance = Geographic Distance × Similarity Score
    
    Similarity considers:
    - Building type (exact match bonus)
    - Rooms count (smaller diff = higher score)
    - Area (±20% is good)
    - Floor level
    - Recency (fresh listings weighted higher)
    """
    
    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv(
            "PG_DSN",
            "postgresql://realuser:strongpass123@localhost:5432/realdb"
        )
    
    def search(
        self,
        features: PropertyFeatures,
        k: int = 10,
        max_distance_km: float = 5.0,
        max_age_days: int = 90
    ) -> Optional[KNNEstimate]:
        """Find K nearest comparable properties."""
        
        if not features.lat or not features.lon:
            return None
        
        conn = psycopg2.connect(self.dsn, cursor_factory=RealDictCursor)
        
        try:
            comparables = self._find_comparables(
                conn, features, k * 3, max_distance_km, max_age_days
            )
            
            if not comparables:
                return None
            
            scored = self._score_comparables(features, comparables)
            top_k = sorted(scored, key=lambda c: c.similarity_score, reverse=True)[:k]
            weighted = self._assign_weights(top_k)
            
            return self._calculate_estimate(weighted)
        
        finally:
            conn.close()
    
    def _find_comparables(self, conn, features, limit, max_distance_km, max_age_days):
        """Query database for candidate comparables."""
        cutoff_date = datetime.now() - timedelta(days=max_age_days)

        # Исключаем оцениваемый объект из аналогов (если указан)
        exclude_id = features.exclude_listing_id

        with conn.cursor() as cur:
            cur.execute("""
                WITH latest_prices AS (
                    SELECT DISTINCT ON (id) id, price, seen_at
                    FROM listing_prices
                    WHERE seen_at >= %s
                    ORDER BY id, seen_at DESC
                )
                SELECT
                    l.id, l.url, COALESCE(lp.price, l.initial_price) as price,
                    l.area_total, l.rooms, l.floor, l.total_floors,
                    l.building_type, l.house_year as building_year, l.lat, l.lon,
                    COALESCE(lp.seen_at, l.last_seen) as seen_at,
                    ST_Distance(
                        ST_MakePoint(%s, %s)::geography,
                        ST_MakePoint(l.lon, l.lat)::geography
                    ) / 1000.0 as distance_km
                FROM listings l
                LEFT JOIN latest_prices lp ON l.id = lp.id
                WHERE l.lat IS NOT NULL AND l.lon IS NOT NULL
                  AND l.area_total > 0
                  AND COALESCE(lp.price, l.initial_price) > 0
                  AND l.is_active = TRUE
                  AND l.last_seen >= %s
                  AND l.lat BETWEEN %s - 0.05 AND %s + 0.05
                  AND l.lon BETWEEN %s - 0.07 AND %s + 0.07
                  AND (%s IS NULL OR l.id != %s)  -- Исключаем оцениваемый объект
                  AND (
                      %s IS NULL  -- rooms not specified
                      OR l.rooms = %s  -- exact match
                      OR (l.rooms = %s + 1 AND l.area_total <= %s + 10)  -- +1 room, area within +10m²
                      OR (l.rooms = %s - 1 AND l.area_total >= %s - 10)  -- -1 room, area within -10m²
                  )
                ORDER BY distance_km ASC
                LIMIT %s
            """, (
                cutoff_date, features.lon, features.lat, cutoff_date,
                features.lat, features.lat, features.lon, features.lon,
                exclude_id, exclude_id,  # Для исключения оцениваемого объекта
                features.rooms, features.rooms,
                features.rooms, features.area_total,
                features.rooms, features.area_total,
                limit
            ))
            return cur.fetchall()
    
    def _filter_by_building_class(self, features: PropertyFeatures, candidates: list) -> list:
        """
        Фильтрация аналогов по классу дома:
        - 5-этажки не должны попадать если оцениваемый дом многоэтажный (9+)
        - Многоэтажки не должны попадать если оцениваемый дом малоэтажный (<=5)
        - Дома до 2000 года не должны попадать если оцениваемый дом 2000+ года
        """
        filtered = []
        target_floors = features.total_floors
        target_year = features.building_year

        for row in candidates:
            comp_floors = row.get('total_floors')
            comp_year = row.get('building_year')

            # === Фильтрация по высотности ===
            if target_floors and comp_floors:
                # Оцениваемый дом многоэтажный (9+ этажей)
                if target_floors >= 9:
                    if comp_floors <= 5:  # Исключаем хрущёвки
                        continue
                # Оцениваемый дом малоэтажный (<=5 этажей)
                elif target_floors <= 5:
                    if comp_floors >= 9:  # Исключаем многоэтажки
                        continue
                # Среднеэтажный (6-8) - исключаем крайности
                else:
                    if comp_floors <= 5 or comp_floors >= 17:
                        continue

            # === Фильтрация по году постройки ===
            if target_year and comp_year:
                # Современный дом (2000+)
                if target_year >= 2000:
                    if comp_year < 1990:  # Исключаем советскую застройку
                        continue
                # Советский дом (до 1990)
                elif target_year < 1990:
                    if comp_year >= 2000:  # Исключаем современные
                        continue

            filtered.append(row)

        # Если осталось мало - добавить ближайшие из неотфильтрованных (до 5 макс)
        if len(filtered) < 3 and len(candidates) >= 3:
            # Sort by distance, add closest non-filtered candidates
            remaining = [c for c in candidates if c not in filtered]
            remaining_sorted = sorted(remaining, key=lambda x: x.get('distance_km', 999))
            needed = min(5 - len(filtered), len(remaining_sorted))
            filtered.extend(remaining_sorted[:needed])
        return filtered if filtered else candidates[:5]  # Cap at 5 if all else fails

    def _score_comparables(self, features, candidates):
        """Calculate similarity score for each comparable."""
        # Фильтруем по классу дома
        filtered_candidates = self._filter_by_building_class(features, candidates)

        scored = []
        from datetime import timezone
        now = datetime.now(timezone.utc)

        for row in filtered_candidates:
            if row['distance_km'] > 10.0:
                continue
            
            scores = []
            
            # Building type (20 pts)
            if features.building_type and row['building_type']:
                scores.append(20 if features.building_type.value == row['building_type'] else 5)
            else:
                scores.append(10)
            
            # Rooms (20 pts)
            if features.rooms and row['rooms']:
                scores.append(max(0, 20 - abs(features.rooms - row['rooms']) * 10))
            else:
                scores.append(10)
            
            # Area (25 pts)
            if features.area_total > 0 and row['area_total'] > 0:
                area_comp = float(row['area_total'])
                ratio = min(features.area_total, area_comp) / max(features.area_total, area_comp)
                scores.append(25 * ratio)
            else:
                scores.append(10)
            
            # Floor (15 pts)
            if features.floor and row['floor']:
                scores.append(max(0, 15 - abs(features.floor - row['floor']) * 2))
            else:
                scores.append(7)
            
            # Distance (20 pts)
            dist = row['distance_km']
            if dist <= 1.0:
                scores.append(20)
            elif dist <= 3.0:
                scores.append(15)
            elif dist <= 5.0:
                scores.append(10)
            else:
                scores.append(max(0, 10 - (dist - 5) * 2))
            
            similarity = sum(scores)
            age_days = (now - row['seen_at']).days if isinstance(row['seen_at'], datetime) else 30
            
            # Calculate price per sqm with area correction
            actual_psm = float(row['price']) / float(row['area_total'])
            comparable_area = float(row['area_total'])
            
            # Area adjustment coefficient: 0.1% per 1m² difference
            # Economic logic: smaller apartments have HIGHER ₽/m², larger have LOWER ₽/m²
            # If target is LARGER than comparable → comparable's ₽/m² is too high → DECREASE
            # If target is SMALLER than comparable → comparable's ₽/m² is too low → INCREASE
            AREA_ADJUSTMENT_COEF = 0.001
            area_diff = features.area_total - comparable_area  # positive = target larger
            correction_factor = 1.0 - (AREA_ADJUSTMENT_COEF * area_diff)  # minus to decrease when larger
            
            # Apply area correction only if areas are different
            corrected_psm = actual_psm * correction_factor if abs(area_diff) > 0.5 else actual_psm

            # Aging discount: -1% per 30 days (old listings may have stale prices)
            # Cap at -3% max discount (90 days)
            AGING_DISCOUNT_PER_30_DAYS = 0.01
            aging_discount = min(0.03, (age_days / 30) * AGING_DISCOUNT_PER_30_DAYS)
            corrected_psm = corrected_psm * (1 - aging_discount)

            comp = Comparable(
                listing_id=row['id'],
                url=row.get('url'),
                price=float(row['price']),
                price_per_sqm=corrected_psm,  # Use corrected price per sqm
                area_total=comparable_area,
                rooms=row['rooms'], floor=row['floor'],
                lat=row['lat'], lon=row['lon'],
                distance_km=float(row['distance_km']),
                building_type=row['building_type'],
                building_year=row['building_year'],
                seen_at=row['seen_at'] if isinstance(row['seen_at'], datetime) else now,
                age_days=age_days,
                similarity_score=similarity,
                weight=0.0
            )
            scored.append(comp)
        
        return scored
    
    def _assign_weights(self, comparables):
        """Assign weights based on similarity scores."""
        if not comparables:
            return []
        
        total = sum(c.similarity_score for c in comparables)
        if total == 0:
            weight = 1.0 / len(comparables)
            for c in comparables:
                c.weight = weight
        else:
            for c in comparables:
                c.weight = c.similarity_score / total
        return comparables
    
    def _calculate_estimate(self, comparables):
        """Calculate weighted price estimates."""
        if not comparables:
            raise ValueError("No comparables")
        
        weighted_price = sum(c.price * c.weight for c in comparables)
        weighted_psm = sum(c.price_per_sqm * c.weight for c in comparables)
        
        prices = sorted(c.price for c in comparables)
        psm = sorted(c.price_per_sqm for c in comparables)
        n = len(comparables)
        
        median_price = prices[n//2] if n % 2 else (prices[n//2-1] + prices[n//2]) / 2
        median_psm = psm[n//2] if n % 2 else (psm[n//2-1] + psm[n//2]) / 2
        
        avg_sim = sum(c.similarity_score for c in comparables) / n
        avg_dist = sum(c.distance_km for c in comparables) / n
        
        confidence = min(100, int(
            (n / 10) * 20 + (avg_sim / 100) * 50 + (1 / (1 + avg_dist)) * 30
        ))
        
        return KNNEstimate(
            avg_price=weighted_price,
            median_price=median_price,
            avg_price_per_sqm=weighted_psm,
            median_price_per_sqm=median_psm,
            comparables=comparables,
            confidence=confidence,
            total_weight=sum(c.weight for c in comparables)
        )
