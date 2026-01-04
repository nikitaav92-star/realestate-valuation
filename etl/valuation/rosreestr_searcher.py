"""K-Nearest Neighbors searcher for Rosreestr transactions."""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class RosreestrComparable:
    """Rosreestr transaction as comparable."""
    deal_id: int
    street: str
    area: float
    price: float
    price_per_sqm: float
    year_build: Optional[int]
    floor: Optional[int]
    deal_date: datetime
    distance_km: float
    lat: float
    lon: float
    similarity_score: float = 0.0
    weight: float = 0.0


@dataclass
class RosreestrEstimate:
    """Estimate from Rosreestr data."""
    avg_price_per_sqm: float
    median_price_per_sqm: float
    comparables: List[RosreestrComparable]
    confidence: int
    total_weight: float = 1.0


class RosreestrSearcher:
    """
    Find K most similar Rosreestr transactions.

    Key differences from CIAN searcher:
    - Uses rosreestr_deals table (completed transactions)
    - NO bargain discount (these are actual sale prices)
    - Typically more reliable but older data
    """

    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv(
            "PG_DSN",
            "postgresql://realuser:strongpass123@localhost:5432/realdb"
        )

    def search(
        self,
        lat: float,
        lon: float,
        area_total: float,
        rooms: Optional[int] = None,
        floor: Optional[int] = None,
        total_floors: Optional[int] = None,
        building_year: Optional[int] = None,
        k: int = 10,
        max_distance_km: float = 5.0,
        max_age_days: int = 365
    ) -> Optional[RosreestrEstimate]:
        """Find K nearest Rosreestr transactions."""

        if not lat or not lon:
            return None

        conn = psycopg2.connect(self.dsn, cursor_factory=RealDictCursor)

        try:
            candidates = self._find_candidates(
                conn, lat, lon, area_total, rooms,
                k * 3, max_distance_km, max_age_days
            )

            if not candidates:
                return None

            # Filter by building class
            filtered = self._filter_by_building_class(
                candidates, total_floors, building_year
            )

            if not filtered:
                filtered = candidates  # Fallback to unfiltered

            # Score comparables
            scored = self._score_comparables(
                filtered, area_total, rooms, floor, building_year
            )

            # Take top K
            top_k = sorted(scored, key=lambda c: c.similarity_score, reverse=True)[:k]

            # Assign weights
            weighted = self._assign_weights(top_k)

            return self._calculate_estimate(weighted)

        finally:
            conn.close()

    def _find_candidates(
        self, conn, lat, lon, area_total, rooms,
        limit, max_distance_km, max_age_days
    ) -> List[dict]:
        """Query database for candidate transactions."""

        cutoff_date = datetime.now() - timedelta(days=max_age_days)

        # Area range: ±20%
        area_min = area_total * 0.8
        area_max = area_total * 1.2

        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id as deal_id,
                    street,
                    area,
                    deal_price as price,
                    price_per_sqm,
                    year_build,
                    floor,
                    deal_date,
                    lat,
                    lon,
                    ST_Distance(
                        ST_MakePoint(%s, %s)::geography,
                        ST_MakePoint(lon, lat)::geography
                    ) / 1000.0 as distance_km
                FROM rosreestr_deals
                WHERE lat IS NOT NULL AND lon IS NOT NULL
                  AND area > 0
                  AND price_per_sqm > 0
                  AND deal_date >= %s
                  AND area BETWEEN %s AND %s
                  AND lat BETWEEN %s - 0.05 AND %s + 0.05
                  AND lon BETWEEN %s - 0.07 AND %s + 0.07
                ORDER BY distance_km ASC
                LIMIT %s
            """, (
                lon, lat, cutoff_date,
                area_min, area_max,
                lat, lat, lon, lon,
                limit
            ))
            return cur.fetchall()

    def _filter_by_building_class(
        self,
        candidates: List[dict],
        target_floors: Optional[int],
        target_year: Optional[int]
    ) -> List[dict]:
        """Filter candidates by building class."""

        if not target_floors and not target_year:
            return candidates

        filtered = []

        for row in candidates:
            # Skip if distance too far
            if row['distance_km'] > 10.0:
                continue

            comp_year = row.get('year_build')

            # Filter by year if both known
            if target_year and comp_year:
                # Modern building (2000+)
                if target_year >= 2000:
                    if comp_year < 1990:  # Exclude Soviet era
                        continue
                # Soviet building (before 1990)
                elif target_year < 1990:
                    if comp_year >= 2010:  # Exclude modern
                        continue

            filtered.append(row)

        # If too few remain, return all
        if len(filtered) < 3 and len(candidates) >= 3:
            return candidates

        return filtered if filtered else candidates

    def _score_comparables(
        self,
        candidates: List[dict],
        area_total: float,
        rooms: Optional[int],
        floor: Optional[int],
        building_year: Optional[int]
    ) -> List[RosreestrComparable]:
        """Calculate similarity score for each comparable."""

        scored = []
        now = datetime.now()

        for row in candidates:
            if row['distance_km'] > 10.0:
                continue

            scores = []

            # Area similarity (30 pts)
            if area_total > 0 and row['area'] > 0:
                area_comp = float(row['area'])
                ratio = min(area_total, area_comp) / max(area_total, area_comp)
                scores.append(30 * ratio)
            else:
                scores.append(15)

            # Year similarity (25 pts)
            if building_year and row['year_build']:
                year_diff = abs(building_year - row['year_build'])
                if year_diff <= 5:
                    scores.append(25)
                elif year_diff <= 10:
                    scores.append(20)
                elif year_diff <= 20:
                    scores.append(10)
                else:
                    scores.append(5)
            else:
                scores.append(12)

            # Floor similarity (15 pts)
            if floor and row['floor']:
                floor_diff = abs(floor - row['floor'])
                if floor_diff == 0:
                    scores.append(15)
                elif floor_diff <= 2:
                    scores.append(12)
                elif floor_diff <= 5:
                    scores.append(8)
                else:
                    scores.append(5)
            else:
                scores.append(7)

            # Distance (30 pts)
            dist = row['distance_km']
            if dist <= 0.5:
                scores.append(30)
            elif dist <= 1.0:
                scores.append(25)
            elif dist <= 2.0:
                scores.append(20)
            elif dist <= 3.0:
                scores.append(15)
            elif dist <= 5.0:
                scores.append(10)
            else:
                scores.append(max(0, 10 - (dist - 5) * 2))

            similarity = sum(scores)

            # Calculate corrected price per sqm
            actual_psm = float(row['price_per_sqm'])
            comparable_area = float(row['area'])

            # Area adjustment: 0.1% per 1m² difference
            # Economic logic: smaller apartments have HIGHER ₽/m², larger have LOWER ₽/m²
            # If target is LARGER than comparable → comparable's ₽/m² is too high → DECREASE
            AREA_ADJUSTMENT_COEF = 0.001
            area_diff = area_total - comparable_area  # positive = target larger
            correction_factor = 1.0 - (AREA_ADJUSTMENT_COEF * area_diff)  # minus to decrease when larger

            corrected_psm = actual_psm * correction_factor if abs(area_diff) > 0.5 else actual_psm

            deal_date = row['deal_date']
            if isinstance(deal_date, datetime):
                age_days = (now - deal_date).days
            else:
                age_days = 180  # Default

            comp = RosreestrComparable(
                deal_id=row['deal_id'],
                street=row['street'] or "",
                area=comparable_area,
                price=float(row['price']),
                price_per_sqm=corrected_psm,
                year_build=row['year_build'],
                floor=row['floor'],
                deal_date=deal_date if isinstance(deal_date, datetime) else now,
                distance_km=float(row['distance_km']),
                lat=row['lat'],
                lon=row['lon'],
                similarity_score=similarity,
                weight=0.0
            )
            scored.append(comp)

        return scored

    def _assign_weights(self, comparables: List[RosreestrComparable]) -> List[RosreestrComparable]:
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

    def _calculate_estimate(self, comparables: List[RosreestrComparable]) -> RosreestrEstimate:
        """Calculate weighted price estimates."""
        if not comparables:
            raise ValueError("No comparables")

        # Weighted average
        weighted_psm = sum(c.price_per_sqm * c.weight for c in comparables)

        # Median
        psm_sorted = sorted(c.price_per_sqm for c in comparables)
        n = len(comparables)
        median_psm = psm_sorted[n // 2] if n % 2 else (psm_sorted[n // 2 - 1] + psm_sorted[n // 2]) / 2

        # Confidence based on sample size and similarity
        avg_sim = sum(c.similarity_score for c in comparables) / n
        avg_dist = sum(c.distance_km for c in comparables) / n

        confidence = min(100, int(
            (n / 10) * 20 + (avg_sim / 100) * 50 + (1 / (1 + avg_dist)) * 30
        ))

        return RosreestrEstimate(
            avg_price_per_sqm=weighted_psm,
            median_price_per_sqm=median_psm,
            comparables=comparables,
            confidence=confidence,
            total_weight=sum(c.weight for c in comparables)
        )
