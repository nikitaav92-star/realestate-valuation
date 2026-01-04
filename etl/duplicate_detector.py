"""
Детектор дублей объявлений.

Выявляет перепосты объявлений (когда удаляют старое и создают новое,
чтобы сбросить счетчики и поднять вверх в выдаче).

Критерии дубля:
1. Точное совпадение: адрес + площадь + комнаты
2. Похожее совпадение: адрес + похожая площадь (±2м²) + те же комнаты
3. Совпадение по фото (хеш первых фото)
"""
import logging
from typing import Dict, List, Optional, Tuple
import hashlib

LOGGER = logging.getLogger(__name__)


class DuplicateDetector:
    """Детектор дублей объявлений."""

    def __init__(self, conn):
        """
        Parameters
        ----------
        conn : psycopg2.connection
            Соединение с БД
        """
        self.conn = conn

    def find_duplicates(self, listing: Dict) -> List[Dict]:
        """
        Найти потенциальные дубли для объявления.

        Parameters
        ----------
        listing : dict
            Данные объявления (address, area_total, rooms, cian_id)

        Returns
        -------
        list
            Список потенциальных дублей с оценкой схожести
        """
        duplicates = []

        # 1. Точное совпадение по адресу + площадь + комнаты
        exact = self._find_exact_match(listing)
        duplicates.extend(exact)

        # 2. Похожее совпадение (площадь ±2м²)
        similar = self._find_similar_match(listing)
        duplicates.extend(similar)

        # Убрать дубли из результатов
        seen_ids = set()
        unique_duplicates = []
        for d in duplicates:
            if d['id'] not in seen_ids and d['id'] != listing.get('id'):
                seen_ids.add(d['id'])
                unique_duplicates.append(d)

        return unique_duplicates

    def _find_exact_match(self, listing: Dict) -> List[Dict]:
        """Точное совпадение по адресу + площадь + комнаты."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT id, cian_id, address, area_total, rooms, price,
                       first_seen_at, published_at
                FROM listings
                WHERE address = %(address)s
                  AND area_total = %(area_total)s
                  AND rooms = %(rooms)s
                  AND cian_id != %(cian_id)s
                ORDER BY first_seen_at ASC
            """, {
                'address': listing.get('address'),
                'area_total': listing.get('area_total'),
                'rooms': listing.get('rooms'),
                'cian_id': listing.get('cian_id', 0),
            })

            results = []
            for row in cur.fetchall():
                results.append({
                    'id': row[0],
                    'cian_id': row[1],
                    'address': row[2],
                    'area_total': row[3],
                    'rooms': row[4],
                    'price': row[5],
                    'first_seen_at': row[6],
                    'published_at': row[7],
                    'similarity_score': 1.0,
                    'match_reason': 'exact_match',
                })
            return results

    def _find_similar_match(self, listing: Dict) -> List[Dict]:
        """Похожее совпадение: адрес + площадь ±2м² + комнаты."""
        area = listing.get('area_total')
        if not area:
            return []

        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT id, cian_id, address, area_total, rooms, price,
                       first_seen_at, published_at
                FROM listings
                WHERE address = %(address)s
                  AND area_total BETWEEN %(area_min)s AND %(area_max)s
                  AND area_total != %(area_exact)s
                  AND rooms = %(rooms)s
                  AND cian_id != %(cian_id)s
                ORDER BY first_seen_at ASC
            """, {
                'address': listing.get('address'),
                'area_min': area - 2,
                'area_max': area + 2,
                'area_exact': area,
                'rooms': listing.get('rooms'),
                'cian_id': listing.get('cian_id', 0),
            })

            results = []
            for row in cur.fetchall():
                # Рассчитать схожесть по площади
                area_diff = abs(row[3] - area) if row[3] else 2
                similarity = 1.0 - (area_diff / 10.0)  # ±2м² = 0.8 similarity

                results.append({
                    'id': row[0],
                    'cian_id': row[1],
                    'address': row[2],
                    'area_total': row[3],
                    'rooms': row[4],
                    'price': row[5],
                    'first_seen_at': row[6],
                    'published_at': row[7],
                    'similarity_score': similarity,
                    'match_reason': 'similar_area',
                })
            return results

    def detect_repost(self, listing: Dict) -> Optional[Dict]:
        """
        Определить, является ли объявление перепостом.

        Returns
        -------
        dict or None
            Оригинальное объявление если это перепост, иначе None
        """
        duplicates = self.find_duplicates(listing)

        if not duplicates:
            return None

        # Найти самое старое объявление (оригинал)
        oldest = min(duplicates, key=lambda x: x['first_seen_at'] or x['published_at'])

        listing_date = listing.get('first_seen_at') or listing.get('published_at')
        oldest_date = oldest['first_seen_at'] or oldest['published_at']

        # Если текущее объявление новее - это перепост
        if listing_date and oldest_date and listing_date > oldest_date:
            return oldest

        return None

    def link_duplicates(self, listing_id: int, original_id: int,
                        similarity: float, reason: str):
        """Сохранить связь между дублями в БД."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO listing_duplicates
                    (original_listing_id, duplicate_listing_id, similarity_score, match_reason)
                VALUES (%(original)s, %(duplicate)s, %(similarity)s, %(reason)s)
                ON CONFLICT (original_listing_id, duplicate_listing_id) DO UPDATE
                SET similarity_score = %(similarity)s,
                    match_reason = %(reason)s,
                    detected_at = NOW()
            """, {
                'original': original_id,
                'duplicate': listing_id,
                'similarity': similarity,
                'reason': reason,
            })

            # Обновить флаги в listings
            cur.execute("""
                UPDATE listings
                SET is_repost = TRUE,
                    original_listing_id = %(original)s
                WHERE id = %(duplicate)s
            """, {
                'original': original_id,
                'duplicate': listing_id,
            })

        self.conn.commit()

    def get_price_history_from_duplicates(self, listing_id: int) -> List[Dict]:
        """
        Получить историю цен из цепочки дублей.

        Если объявление перепостили несколько раз, собрать все цены.
        """
        with self.conn.cursor() as cur:
            # Найти всю цепочку связанных объявлений
            cur.execute("""
                WITH RECURSIVE chain AS (
                    -- Начинаем с текущего объявления
                    SELECT id, cian_id, price, published_at, original_listing_id, 0 as depth
                    FROM listings WHERE id = %(listing_id)s

                    UNION ALL

                    -- Идем к оригиналу
                    SELECT l.id, l.cian_id, l.price, l.published_at, l.original_listing_id, c.depth + 1
                    FROM listings l
                    JOIN chain c ON l.id = c.original_listing_id
                    WHERE c.depth < 10  -- защита от бесконечной рекурсии
                )
                SELECT cian_id, price, published_at
                FROM chain
                ORDER BY published_at ASC
            """, {'listing_id': listing_id})

            history = []
            for row in cur.fetchall():
                history.append({
                    'cian_id': row[0],
                    'price': row[1],
                    'date': row[2],
                })
            return history


def calculate_exposure_stats(conn, listing_id: int) -> Dict:
    """
    Рассчитать статистику экспозиции объявления.

    Returns
    -------
    dict
        {
            'days_on_market': int,
            'initial_price': int,
            'current_price': int,
            'price_change_pct': float,
            'price_change_count': int,
            'is_repost': bool,
        }
    """
    with conn.cursor() as cur:
        # Базовые данные объявления
        cur.execute("""
            SELECT price, published_at, first_seen_at, initial_price,
                   price_change_count, is_repost, original_listing_id
            FROM listings WHERE id = %(id)s
        """, {'id': listing_id})

        row = cur.fetchone()
        if not row:
            return {}

        current_price = row[0]
        published_at = row[1]
        first_seen_at = row[2]
        initial_price = row[3] or current_price
        price_change_count = row[4] or 0
        is_repost = row[5] or False
        original_id = row[6]

        # Срок экспозиции
        from datetime import datetime
        start_date = first_seen_at or published_at
        if start_date:
            days_on_market = (datetime.now() - start_date).days
        else:
            days_on_market = 0

        # Если это перепост - добавить дни от оригинала
        if is_repost and original_id:
            cur.execute("""
                SELECT published_at, first_seen_at
                FROM listings WHERE id = %(id)s
            """, {'id': original_id})
            orig_row = cur.fetchone()
            if orig_row:
                orig_date = orig_row[1] or orig_row[0]
                if orig_date:
                    days_on_market = (datetime.now() - orig_date).days

        # Изменение цены в %
        if initial_price and initial_price > 0:
            price_change_pct = ((current_price - initial_price) / initial_price) * 100
        else:
            price_change_pct = 0

        return {
            'days_on_market': days_on_market,
            'initial_price': initial_price,
            'current_price': current_price,
            'price_change_pct': round(price_change_pct, 2),
            'price_change_count': price_change_count,
            'is_repost': is_repost,
        }


def record_price_change(conn, listing_id: int, cian_id: int,
                        old_price: int, new_price: int):
    """Записать изменение цены в историю."""
    with conn.cursor() as cur:
        # Добавить в историю
        cur.execute("""
            INSERT INTO listing_price_history (listing_id, cian_id, price, source)
            VALUES (%(listing_id)s, %(cian_id)s, %(price)s, 'parser')
        """, {
            'listing_id': listing_id,
            'cian_id': cian_id,
            'price': new_price,
        })

        # Обновить счетчик изменений
        cur.execute("""
            UPDATE listings
            SET price_change_count = COALESCE(price_change_count, 0) + 1,
                initial_price = COALESCE(initial_price, %(old_price)s),
                price_change_pct = CASE
                    WHEN COALESCE(initial_price, %(old_price)s) > 0
                    THEN ((%(new_price)s - COALESCE(initial_price, %(old_price)s))::float /
                          COALESCE(initial_price, %(old_price)s) * 100)
                    ELSE 0
                END
            WHERE id = %(listing_id)s
        """, {
            'listing_id': listing_id,
            'old_price': old_price,
            'new_price': new_price,
        })

    conn.commit()
    LOGGER.info(f"💰 Цена изменилась: {old_price:,} → {new_price:,} ({listing_id})")
