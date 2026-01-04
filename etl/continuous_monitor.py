"""
Непрерывный мониторинг CIAN.

Режимы работы:
1. INITIAL - первичный сбор всей базы (pages=1..2000)
2. MONITOR - мониторинг новых (pages=1..5, каждые 15 мин)
3. DEEP_SCAN - глубокое сканирование (pages=1..50, каждый час)

Логика обнаружения:
- Новое объявление: cian_id нет в базе
- Изменение цены: цена отличается → запись в историю
- Удаление: объявление было, но исчезло → помечаем is_active=False
"""
import os
import sys
import time
import logging
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/cian_monitor.log')
    ]
)
LOGGER = logging.getLogger(__name__)

# Импорт парсера
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.collector_cian.browser_fetcher import CianBrowserFetcher
from etl.address_parser import parse_address
from etl.encumbrance_analyzer import analyze_description


class ContinuousMonitor:
    """Непрерывный мониторинг CIAN."""

    # Интервалы проверки (секунды)
    QUICK_INTERVAL = 5 * 60         # 5 минут - быстрая проверка (1 страница)
    MONITOR_INTERVAL = 15 * 60      # 15 минут - стандартная проверка
    DEEP_SCAN_INTERVAL = 60 * 60    # 1 час - глубокое сканирование
    FULL_SCAN_INTERVAL = 6 * 60 * 60  # 6 часов - полное сканирование

    # Количество страниц для разных режимов
    QUICK_PAGES = 1       # Только первая страница (28 объявлений)
    MONITOR_PAGES = 3     # Стандартный мониторинг
    DEEP_SCAN_PAGES = 10  # Глубокое сканирование
    FULL_SCAN_PAGES = 50  # Полное сканирование

    def __init__(self, db_url: str = None, telegram_token: str = None, telegram_chat: str = None):
        """
        Инициализация монитора.

        Parameters
        ----------
        db_url : str
            URL базы данных
        telegram_token : str
            Токен Telegram бота для алертов
        telegram_chat : str
            ID чата для алертов
        """
        self.db_url = db_url or os.getenv('DATABASE_URL')
        self.telegram_token = telegram_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat = telegram_chat or os.getenv('TELEGRAM_CHAT_ID')

        self.conn = None
        self.fetcher = None

        # Статистика
        self.stats = {
            'new_listings': 0,
            'price_changes': 0,
            'alerts_sent': 0,
            'errors': 0,
            'last_scan': None,
        }

    def connect_db(self):
        """Подключение к БД."""
        if self.conn is None or self.conn.closed:
            # Параметры из переменных окружения (совместимость с .env)
            self.conn = psycopg2.connect(
                host=os.getenv('PG_HOST', os.getenv('DB_HOST', 'localhost')),
                port=os.getenv('PG_PORT', os.getenv('DB_PORT', '5432')),
                dbname=os.getenv('PG_DB', os.getenv('DB_NAME', 'realdb')),
                user=os.getenv('PG_USER', os.getenv('DB_USER', 'realuser')),
                password=os.getenv('PG_PASS', os.getenv('DB_PASSWORD', 'strongpass123')),
            )
            LOGGER.info("✅ Подключено к БД")

    def get_existing_listings(self) -> Dict[int, Dict]:
        """Получить существующие объявления из БД."""
        self.connect_db()
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT cian_id, price, address, area_total, rooms, is_active
                FROM listings
                WHERE is_error = FALSE
            """)
            return {row['cian_id']: dict(row) for row in cur.fetchall()}

    def get_district_stats(self) -> Dict[str, Dict]:
        """Получить статистику цен по районам."""
        self.connect_db()
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    district,
                    rooms,
                    COUNT(*) as count,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price) as median_price,
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY price) as p25_price,
                    AVG(price / NULLIF(area_total, 0)) as avg_price_per_m2
                FROM listings
                WHERE is_active = TRUE
                  AND is_error = FALSE
                  AND district IS NOT NULL
                  AND price > 0
                GROUP BY district, rooms
                HAVING COUNT(*) >= 5
            """)

            stats = {}
            for row in cur.fetchall():
                key = f"{row['district']}_{row['rooms']}"
                stats[key] = dict(row)
            return stats

    def check_if_good_deal(self, listing: Dict, district_stats: Dict) -> Optional[Dict]:
        """
        Проверить, является ли объявление выгодным.

        Returns
        -------
        dict or None
            Информация о выгодности если это хорошая сделка
        """
        # Парсим адрес для получения района
        parsed = parse_address(listing.get('address', ''))
        district = parsed.district
        rooms = listing.get('rooms')
        price = listing.get('price', 0)

        if not district or not rooms or not price:
            return None

        key = f"{district}_{rooms}"
        stats = district_stats.get(key)

        if not stats:
            return None

        median = stats['median_price']
        p25 = stats['p25_price']

        # Выгодное если цена ниже 25-го перцентиля
        if price < p25:
            discount_pct = (1 - price / median) * 100
            return {
                'is_good_deal': True,
                'discount_pct': discount_pct,
                'price': price,
                'median_price': median,
                'p25_price': p25,
                'district': district,
                'rooms': rooms,
            }

        return None

    def send_telegram_alert(self, listing: Dict, deal_info: Dict):
        """Отправить алерт в Telegram."""
        if not self.telegram_token or not self.telegram_chat:
            LOGGER.warning("Telegram не настроен, алерт пропущен")
            return

        try:
            import requests

            # Анализ обременений
            enc_result = analyze_description(listing.get('description', ''))
            enc_warning = ""
            if enc_result['has_encumbrances']:
                enc_warning = "\n⚠️ ВОЗМОЖНЫЕ ОБРЕМЕНЕНИЯ!"

            message = f"""
🔥 *ВЫГОДНОЕ ПРЕДЛОЖЕНИЕ!*

📍 {listing.get('address', 'Адрес не указан')}
💰 *{listing.get('price', 0):,}* ₽ (-{deal_info['discount_pct']:.0f}% от медианы)
📊 Медиана района: {deal_info['median_price']:,.0f} ₽

🏠 {listing.get('rooms', '?')}-комн, {listing.get('area_total', '?')} м²
🏢 Этаж: {listing.get('floor', '?')}/{listing.get('floors_total', '?')}
🔨 Тип: {listing.get('building_type', '?')}
{enc_warning}
🔗 https://www.cian.ru/sale/flat/{listing.get('cian_id')}/
            """.strip()

            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            resp = requests.post(url, json={
                'chat_id': self.telegram_chat,
                'text': message,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': False,
            }, timeout=10)

            if resp.status_code == 200:
                self.stats['alerts_sent'] += 1
                LOGGER.info(f"📱 Алерт отправлен: {listing.get('cian_id')}")
            else:
                LOGGER.error(f"Ошибка Telegram: {resp.text}")

        except Exception as e:
            LOGGER.error(f"Ошибка отправки алерта: {e}")

    def record_price_change(self, cian_id: int, old_price: int, new_price: int, listing_id: int = None):
        """Записать изменение цены."""
        self.connect_db()
        with self.conn.cursor() as cur:
            # Добавить в историю
            cur.execute("""
                INSERT INTO listing_price_history (listing_id, cian_id, price, source)
                VALUES (
                    COALESCE(%(listing_id)s, (SELECT id FROM listings WHERE cian_id = %(cian_id)s)),
                    %(cian_id)s,
                    %(price)s,
                    'monitor'
                )
            """, {
                'listing_id': listing_id,
                'cian_id': cian_id,
                'price': new_price,
            })

            # Обновить в listings
            cur.execute("""
                UPDATE listings
                SET price = %(new_price)s,
                    price_change_count = COALESCE(price_change_count, 0) + 1,
                    initial_price = COALESCE(initial_price, %(old_price)s),
                    last_seen_at = NOW()
                WHERE cian_id = %(cian_id)s
            """, {
                'cian_id': cian_id,
                'old_price': old_price,
                'new_price': new_price,
            })

        self.conn.commit()
        self.stats['price_changes'] += 1

        change_pct = ((new_price - old_price) / old_price) * 100 if old_price else 0
        direction = "📈" if new_price > old_price else "📉"
        LOGGER.info(f"{direction} Цена изменилась: {old_price:,} → {new_price:,} ({change_pct:+.1f}%) [cian_id={cian_id}]")

    def scan_pages(self, pages: int, sort_by: str = 'creation_date') -> List[Dict]:
        """
        Сканировать страницы CIAN.

        Parameters
        ----------
        pages : int
            Количество страниц
        sort_by : str
            Сортировка: 'creation_date' (новые) или 'price' (дешевые)
        """
        if self.fetcher is None:
            self.fetcher = CianBrowserFetcher()

        LOGGER.info(f"🔍 Сканирование {pages} страниц (сортировка: {sort_by})")

        # Формируем URL с сортировкой
        # sort=creation_date_desc - по дате создания (новые первые)
        # sort=price_object_order - по цене
        base_url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1&sort=creation_date_desc"

        all_listings = []
        try:
            listings = self.fetcher.fetch_listings(
                base_url=base_url,
                max_pages=pages,
                headless=True
            )
            all_listings.extend(listings)
        except Exception as e:
            LOGGER.error(f"Ошибка сканирования: {e}")
            self.stats['errors'] += 1

        return all_listings

    def process_listings(self, listings: List[Dict], existing: Dict[int, Dict], district_stats: Dict):
        """Обработать найденные объявления."""
        for listing in listings:
            cian_id = listing.get('cian_id')
            if not cian_id:
                continue

            # Новое объявление?
            if cian_id not in existing:
                self.stats['new_listings'] += 1
                LOGGER.info(f"🆕 Новое: {cian_id} - {listing.get('price', 0):,} ₽ - {listing.get('address', '')[:50]}")

                # Проверить на выгодность
                deal_info = self.check_if_good_deal(listing, district_stats)
                if deal_info and deal_info['discount_pct'] >= 15:
                    self.send_telegram_alert(listing, deal_info)

            # Изменение цены?
            elif existing[cian_id]['price'] != listing.get('price'):
                old_price = existing[cian_id]['price']
                new_price = listing.get('price')
                self.record_price_change(cian_id, old_price, new_price)

                # Если цена снизилась значительно - тоже алерт
                if new_price < old_price:
                    drop_pct = (1 - new_price / old_price) * 100
                    if drop_pct >= 10:
                        deal_info = self.check_if_good_deal(listing, district_stats)
                        if deal_info:
                            deal_info['price_drop'] = drop_pct
                            self.send_telegram_alert(listing, deal_info)

    def run_monitor_cycle(self):
        """Один цикл мониторинга."""
        LOGGER.info("=" * 60)
        LOGGER.info("🔄 Запуск цикла мониторинга")

        try:
            # Получить текущие данные
            existing = self.get_existing_listings()
            district_stats = self.get_district_stats()

            LOGGER.info(f"📊 В базе: {len(existing)} объявлений, {len(district_stats)} районов со статистикой")

            # Сканировать новые (используем _current_pages если задано, иначе MONITOR_PAGES)
            pages = getattr(self, '_current_pages', self.MONITOR_PAGES)
            listings = self.scan_pages(pages)

            # Обработать
            self.process_listings(listings, existing, district_stats)

            self.stats['last_scan'] = datetime.now()

            LOGGER.info(f"✅ Цикл завершен: +{self.stats['new_listings']} новых, "
                       f"{self.stats['price_changes']} изменений цен, "
                       f"{self.stats['alerts_sent']} алертов")

        except Exception as e:
            LOGGER.error(f"❌ Ошибка цикла: {e}")
            self.stats['errors'] += 1

    def run_forever(self, aggressive: bool = True):
        """
        Запуск непрерывного мониторинга.

        Parameters
        ----------
        aggressive : bool
            Агрессивный режим - проверка каждые 5 минут
        """
        LOGGER.info("🚀 Запуск непрерывного мониторинга CIAN")
        LOGGER.info(f"   Режим: {'АГРЕССИВНЫЙ' if aggressive else 'СТАНДАРТНЫЙ'}")

        last_deep_scan = datetime.min
        last_full_scan = datetime.min
        cycle_count = 0

        while True:
            try:
                now = datetime.now()
                cycle_count += 1

                # Определить тип сканирования
                if (now - last_full_scan).total_seconds() >= self.FULL_SCAN_INTERVAL:
                    # Полное сканирование каждые 6 часов
                    pages = self.FULL_SCAN_PAGES
                    scan_type = "FULL"
                    last_full_scan = now
                    interval = self.MONITOR_INTERVAL
                elif (now - last_deep_scan).total_seconds() >= self.DEEP_SCAN_INTERVAL:
                    # Глубокое сканирование каждый час
                    pages = self.DEEP_SCAN_PAGES
                    scan_type = "DEEP"
                    last_deep_scan = now
                    interval = self.MONITOR_INTERVAL
                elif aggressive:
                    # Агрессивный режим - 1 страница каждые 5 минут
                    pages = self.QUICK_PAGES
                    scan_type = "QUICK"
                    interval = self.QUICK_INTERVAL
                else:
                    # Стандартный режим
                    pages = self.MONITOR_PAGES
                    scan_type = "STANDARD"
                    interval = self.MONITOR_INTERVAL

                LOGGER.info(f"[{cycle_count}] {scan_type}: {pages} стр.")
                self._current_pages = pages
                self.run_monitor_cycle()

                # Пауза
                LOGGER.info(f"😴 Пауза {interval // 60} мин до следующей проверки...")
                time.sleep(interval)

            except KeyboardInterrupt:
                LOGGER.info("⏹️ Остановка по Ctrl+C")
                break
            except Exception as e:
                LOGGER.error(f"❌ Критическая ошибка: {e}")
                time.sleep(60)  # Пауза перед повтором

    def run_initial_scan(self, max_pages: int = 2000):
        """Первичное полное сканирование."""
        LOGGER.info(f"📥 Запуск первичного сканирования ({max_pages} страниц)")

        existing = self.get_existing_listings()
        district_stats = self.get_district_stats()

        # Сканируем порциями
        batch_size = 50
        for start_page in range(1, max_pages + 1, batch_size):
            end_page = min(start_page + batch_size - 1, max_pages)
            LOGGER.info(f"📄 Страницы {start_page}-{end_page}...")

            try:
                listings = self.scan_pages(batch_size)
                self.process_listings(listings, existing, district_stats)

                # Обновить existing
                for l in listings:
                    if l.get('cian_id'):
                        existing[l['cian_id']] = l

                # Пауза между батчами
                time.sleep(30)

            except Exception as e:
                LOGGER.error(f"Ошибка на страницах {start_page}-{end_page}: {e}")
                time.sleep(60)

        LOGGER.info(f"✅ Первичное сканирование завершено: {self.stats['new_listings']} объявлений")


def main():
    parser = argparse.ArgumentParser(description='Непрерывный мониторинг CIAN')
    parser.add_argument('--mode', choices=['monitor', 'initial', 'once'],
                       default='monitor', help='Режим работы')
    parser.add_argument('--pages', type=int, default=5, help='Количество страниц')
    parser.add_argument('--interval', type=int, default=15, help='Интервал проверки (минуты)')
    parser.add_argument('--aggressive', action='store_true',
                       help='Агрессивный режим: проверка каждые 5 мин')

    args = parser.parse_args()

    monitor = ContinuousMonitor()

    if args.mode == 'initial':
        monitor.run_initial_scan(max_pages=args.pages)
    elif args.mode == 'once':
        monitor._current_pages = args.pages
        monitor.run_monitor_cycle()
    else:
        monitor.MONITOR_INTERVAL = args.interval * 60
        monitor.run_forever(aggressive=args.aggressive)


if __name__ == '__main__':
    main()
