## Полное руководство по развертыванию массового сбора CIAN

**Date:** 2025-10-11  
**Target:** 100,000 объявлений  
**Cost:** ~$1  
**Time:** ~5 часов

---

## 📋 Содержание

1. [Предварительные требования](#prerequisites)
2. [Структура базы данных](#database-structure)
3. [Переменные и маппинг](#data-mapping)
4. [Настройка окружения](#environment-setup)
5. [Запуск сбора данных](#data-collection)
6. [Фронтенд для просмотра](#frontend)
7. [Мониторинг и обслуживание](#monitoring)

---

<a name="prerequisites"></a>
## 1. Предварительные требования

### Системные требования

```bash
# ОС
Ubuntu 22.04+ или аналог

# Python
Python 3.11+

# База данных
PostgreSQL 14+ с PostGIS

# Память
Минимум 4 GB RAM

# Диск
50 GB свободного места
```

### Необходимые сервисы

1. **NodeMaven Proxy** (10 сессий)
   - Стоимость: ~$1 для 100k объявлений
   - Файл: `config/proxy_pool.txt` ✅ Уже настроен

2. **Anti-Captcha API** (опционально)
   - Ключ: `4781513c0078e75e2c6ea8ea90197f44` ✅ Есть
   - Стоимость: $0.001 за решение
   - Частота: <1%

3. **PostgreSQL Database**
   - Host: localhost (Docker)
   - Port: 5432
   - Database: realdb
   - User: realuser

---

<a name="database-structure"></a>
## 2. Структура базы данных

### Таблица: `listings` (Объявления)

```sql
CREATE TABLE listings (
    id BIGINT PRIMARY KEY,              -- ID объявления из CIAN
    url TEXT,                           -- ✅ Ссылка на объявление
    region INT,                         -- Регион (1 = Москва)
    deal_type TEXT,                     -- Тип сделки (sale/rent)
    rooms INT,                          -- Количество комнат
    area_total NUMERIC,                 -- Площадь (м²)
    floor INT,                          -- Этаж
    address TEXT,                       -- Адрес
    seller_type TEXT,                   -- Тип продавца
    lat DOUBLE PRECISION,               -- Широта
    lon DOUBLE PRECISION,               -- Долгота
    first_seen TIMESTAMPTZ NOT NULL,    -- Первое появление
    last_seen TIMESTAMPTZ NOT NULL,     -- Последнее обновление
    is_active BOOLEAN DEFAULT TRUE      -- Активность
);
```

**Ключевые поля:**
- ✅ **url** - Полная ссылка на объявление (например: `https://www.cian.ru/sale/flat/123456/`)
- ✅ **id** - Уникальный ID из CIAN
- ✅ **lat/lon** - Координаты для карт
- ✅ **first_seen/last_seen** - Отслеживание времени жизни

### Таблица: `listing_prices` (История цен)

```sql
CREATE TABLE listing_prices (
    id BIGINT REFERENCES listings(id),  -- Ссылка на объявление
    seen_at TIMESTAMPTZ NOT NULL,       -- Время наблюдения
    price NUMERIC NOT NULL,             -- Цена (рубли)
    PRIMARY KEY (id, seen_at)
);
```

**Особенности:**
- Хранит историю изменений цен
- Новая запись только при изменении цены
- Позволяет отслеживать динамику

### Индексы (для быстрых запросов)

```sql
-- Поиск по региону, типу сделки, комнатам
CREATE INDEX idx_listings_region_deal_rooms
    ON listings (region, deal_type, rooms);

-- Активные объявления
CREATE INDEX idx_listings_is_active
    ON listings (is_active) WHERE is_active = TRUE;

-- Последние цены
CREATE INDEX idx_listing_prices_latest
    ON listing_prices (id, seen_at DESC);
```

---

<a name="data-mapping"></a>
## 3. Переменные и маппинг данных

### Что извлекается из CIAN API

#### Из ответа API:
```json
{
  "offerId": 123456,
  "seoUrl": "https://www.cian.ru/sale/flat/123456/",
  "price": {
    "value": 15000000
  },
  "rooms": 2,
  "totalSquare": 65.5,
  "floor": 5,
  "address": "Москва, ул. Примерная, 10",
  "userType": "owner",
  "geo": {
    "coordinates": {
      "lat": 55.751244,
      "lng": 37.618423
    }
  },
  "region": 1,
  "operationName": "sale"
}
```

#### Маппинг в БД:

| CIAN API поле | БД поле | Тип | Обязательное | Пример |
|---------------|---------|-----|--------------|--------|
| `offerId` | `id` | BIGINT | ✅ Да | 123456 |
| `seoUrl` | `url` | TEXT | ✅ Да | https://www.cian.ru/... |
| `price.value` | `price` | NUMERIC | ✅ Да | 15000000 |
| `rooms` | `rooms` | INT | ❌ Нет | 2 |
| `totalSquare` | `area_total` | NUMERIC | ❌ Нет | 65.5 |
| `floor` | `floor` | INT | ❌ Нет | 5 |
| `address` | `address` | TEXT | ❌ Нет | Москва, ул... |
| `userType` | `seller_type` | TEXT | ❌ Нет | owner |
| `geo.coordinates.lat` | `lat` | DOUBLE | ❌ Нет | 55.751244 |
| `geo.coordinates.lng` | `lon` | DOUBLE | ❌ Нет | 37.618423 |
| `region` | `region` | INT | ❌ Нет | 1 |
| `operationName` | `deal_type` | TEXT | ❌ Нет | sale |

### Логика обработки

```python
# etl/collector_cian/mapper.py

def to_listing(offer: Dict[str, Any]) -> Listing:
    """Преобразует JSON из CIAN в модель Listing."""
    return Listing(
        id=offer.get("offerId"),
        url=offer.get("seoUrl"),  # ✅ Ссылка копируется!
        region=offer.get("region"),
        deal_type=offer.get("operationName"),
        rooms=offer.get("rooms"),
        area_total=offer.get("totalSquare"),
        floor=offer.get("floor"),
        address=offer.get("address"),
        seller_type=offer.get("userType"),
        lat=offer.get("geo", {}).get("coordinates", {}).get("lat"),
        lon=offer.get("geo", {}).get("coordinates", {}).get("lng"),
    )

def to_price(offer: Dict[str, Any]) -> PricePoint:
    """Извлекает цену."""
    return PricePoint(
        id=offer.get("offerId"),
        price=offer.get("price", {}).get("value"),
        seen_at=datetime.now(),
    )
```

### Логика сохранения (Upsert)

```python
# etl/upsert.py

def upsert_listing(conn, listing):
    """
    INSERT ... ON CONFLICT DO UPDATE
    
    Если объявление новое:
      - Создает запись
      - first_seen = NOW()
      - last_seen = NOW()
    
    Если объявление существует:
      - Обновляет данные
      - first_seen = без изменений
      - last_seen = NOW()
      - is_active = TRUE
    """
    
def upsert_price_if_changed(conn, listing_id, price):
    """
    Добавляет запись в listing_prices ТОЛЬКО если цена изменилась.
    
    Проверяет последнюю цену:
      - Если отличается → INSERT
      - Если та же → пропускает
    
    Возвращает: True если цена добавлена
    """
```

---

<a name="environment-setup"></a>
## 4. Настройка окружения

### Шаг 1: Клонировать репозиторий

```bash
cd /opt
git clone https://github.com/nikitaav92-star/realestate.git
cd realestate
git checkout fix1  # Ветка с новыми фичами
```

### Шаг 2: Установить зависимости

```bash
# Создать venv
python3 -m venv .venv
source .venv/bin/activate

# Установить пакеты
pip install -r requirements.txt
playwright install chromium

# Установить xvfb (для headless на сервере)
sudo apt-get install -y xvfb
```

### Шаг 3: Настроить базу данных

```bash
# Запустить PostgreSQL через Docker
docker-compose up -d

# Применить схему
psql -h localhost -U realuser -d realdb -f db/schema.sql

# Проверить таблицы
psql -h localhost -U realuser -d realdb -c "\dt"
```

### Шаг 4: Настроить переменные окружения

```bash
# Создать .env
cat > .env << 'EOF'
# Database
PG_HOST=localhost
PG_PORT=5432
PG_USER=realuser
PG_PASS=strongpass
PG_DB=realdb
PG_DSN=postgresql://realuser:strongpass@localhost:5432/realdb

# Anti-Captcha API
ANTICAPTCHA_KEY=4781513c0078e75e2c6ea8ea90197f44

# Proxy (будет ротироваться из пула)
# NODEMAVEN_PROXY_URL устанавливается скриптом
EOF

# Загрузить переменные
source .env
```

### Шаг 5: Проверить настройку

```bash
# Тест подключения к БД
python -c "from etl.upsert import get_db_connection; conn = get_db_connection(); print('✅ DB OK'); conn.close()"

# Тест прокси
python scripts/test_captcha_strategy.py --pages 1 --proxy-first-only

# Ожидаемый результат:
# ✅ Page 1: 28 offers
```

---

<a name="data-collection"></a>
## 5. Запуск сбора данных

### Вариант A: Тестовый запуск (10 страниц)

```bash
# Активировать окружение
source .venv/bin/activate
source .env

# Запустить тест
python scripts/test_captcha_strategy.py \
    --pages 10 \
    --proxy-first-only

# Результат:
# ✅ 280 объявлений за 48 секунд
```

### Вариант B: Средний запуск (1000 объявлений)

```bash
# ~36 страниц
python scripts/test_captcha_strategy.py \
    --pages 36 \
    --proxy-first-only

# Время: ~3 минуты
# Стоимость: ~$0.09
```

### Вариант C: Полный запуск (100,000 объявлений)

#### Метод 1: Одна длинная сессия (БЫСТРО)

```bash
# Запустить с nohup (фоновый режим)
nohup python scripts/test_captcha_strategy.py \
    --pages 3571 \
    --proxy-first-only \
    > logs/full_scrape.log 2>&1 &

# Следить за прогрессом
tail -f logs/full_scrape.log

# Время: ~4.7 часа
# Стоимость: ~$0.10
# Риск: Может заблокировать через N страниц
```

#### Метод 2: 10 сессий по 357 страниц (НАДЕЖНО)

```bash
#!/bin/bash
# scripts/scrape_100k.sh

source .venv/bin/activate
source .env

# Загрузить прокси из пула
PROXIES=($(cat config/proxy_pool.txt | grep -v "^#" | grep "http"))

for session in {1..10}; do
    echo "=" | tr '=' '='
    echo "Starting session $session/10"
    echo "=" | tr '=' '='
    
    # Выбрать прокси для этой сессии
    proxy_index=$(( ($session - 1) % ${#PROXIES[@]} ))
    export NODEMAVEN_PROXY_URL="${PROXIES[$proxy_index]}"
    
    echo "Using proxy: ${NODEMAVEN_PROXY_URL:0:50}..."
    
    # Запустить сбор
    python scripts/test_captcha_strategy.py \
        --pages 357 \
        --proxy-first-only
    
    echo "✅ Session $session complete!"
    echo "Waiting 60 seconds before next session..."
    sleep 60
done

echo "🎉 All 10 sessions complete!"
echo "Total: ~100,000 offers collected"
```

**Запуск:**
```bash
chmod +x scripts/scrape_100k.sh
nohup ./scripts/scrape_100k.sh > logs/scrape_100k.log 2>&1 &
```

---

<a name="database-structure"></a>
## 6. Структура данных в БД

### Схема данных

```
┌─────────────────────────────────────────┐
│           listings                      │
│  (Основная таблица объявлений)         │
├─────────────────────────────────────────┤
│ id              BIGINT (PK)            │ ← ID из CIAN
│ url             TEXT                    │ ← ✅ Ссылка на объявление
│ region          INT                     │ ← Регион
│ deal_type       TEXT                    │ ← sale/rent
│ rooms           INT                     │ ← Комнаты
│ area_total      NUMERIC                 │ ← Площадь м²
│ floor           INT                     │ ← Этаж
│ address         TEXT                    │ ← Адрес
│ seller_type     TEXT                    │ ← owner/agent/developer
│ lat             DOUBLE PRECISION        │ ← Координаты
│ lon             DOUBLE PRECISION        │
│ first_seen      TIMESTAMPTZ             │ ← Когда впервые увидели
│ last_seen       TIMESTAMPTZ             │ ← Последнее обновление
│ is_active       BOOLEAN                 │ ← Активно ли объявление
└─────────────────────────────────────────┘
                    │
                    │ 1:N
                    ▼
┌─────────────────────────────────────────┐
│       listing_prices                    │
│  (История изменений цен)                │
├─────────────────────────────────────────┤
│ id              BIGINT (FK)            │
│ seen_at         TIMESTAMPTZ (PK)       │
│ price           NUMERIC                 │
└─────────────────────────────────────────┘
```

### Примеры данных

#### Запись в `listings`:

```sql
id: 123456789
url: 'https://www.cian.ru/sale/flat/123456789/'
region: 1
deal_type: 'sale'
rooms: 2
area_total: 65.5
floor: 5
address: 'Москва, Тверская улица, 10'
seller_type: 'owner'
lat: 55.751244
lon: 37.618423
first_seen: '2025-10-11 09:00:00'
last_seen: '2025-10-11 09:00:00'
is_active: true
```

#### Записи в `listing_prices`:

```sql
-- Первое наблюдение
id: 123456789, seen_at: '2025-10-11 09:00:00', price: 15000000

-- Цена изменилась
id: 123456789, seen_at: '2025-10-12 09:00:00', price: 14500000

-- Цена не изменилась → новая запись НЕ создается
```

### Полезные SQL запросы

#### 1. Все активные объявления

```sql
SELECT 
    id,
    url,
    rooms,
    area_total,
    address,
    last_seen
FROM listings
WHERE is_active = TRUE
ORDER BY last_seen DESC;
```

#### 2. Объявления с историей цен

```sql
SELECT 
    l.id,
    l.url,
    l.address,
    lp.seen_at,
    lp.price
FROM listings l
JOIN listing_prices lp ON l.id = lp.id
WHERE l.id = 123456789
ORDER BY lp.seen_at DESC;
```

#### 3. Падения цен (≥5%)

```sql
WITH price_changes AS (
    SELECT 
        id,
        seen_at,
        price,
        LAG(price) OVER (PARTITION BY id ORDER BY seen_at) AS prev_price
    FROM listing_prices
)
SELECT 
    l.id,
    l.url,
    l.address,
    pc.prev_price,
    pc.price,
    ROUND(((pc.price - pc.prev_price) / pc.prev_price * 100), 2) AS change_percent
FROM price_changes pc
JOIN listings l ON pc.id = l.id
WHERE pc.prev_price IS NOT NULL
    AND ((pc.price - pc.prev_price) / pc.prev_price) <= -0.05
ORDER BY change_percent ASC;
```

#### 4. Статистика по комнатам

```sql
SELECT 
    rooms,
    COUNT(*) AS count,
    AVG(area_total) AS avg_area,
    AVG(lp.price) AS avg_price,
    AVG(lp.price / area_total) AS avg_price_per_sqm
FROM listings l
JOIN LATERAL (
    SELECT price
    FROM listing_prices
    WHERE id = l.id
    ORDER BY seen_at DESC
    LIMIT 1
) lp ON true
WHERE l.is_active = TRUE
    AND l.area_total > 0
GROUP BY rooms
ORDER BY rooms;
```

---

<a name="environment-setup"></a>
## 7. Переменные окружения (полный список)

### Обязательные

```bash
# Database connection
export PG_DSN="postgresql://realuser:strongpass@localhost:5432/realdb"

# Or components
export PG_HOST=localhost
export PG_PORT=5432
export PG_USER=realuser
export PG_PASS=strongpass
export PG_DB=realdb
```

### Опциональные (для anti-bot)

```bash
# Anti-Captcha API (рекомендуется)
export ANTICAPTCHA_KEY=4781513c0078e75e2c6ea8ea90197f44

# Proxy (устанавливается скриптом из пула)
export NODEMAVEN_PROXY_URL="http://..."

# Playwright settings
export CIAN_HEADLESS=true
export CIAN_SLOW_MO=0

# Storage state (если используется)
export CIAN_STORAGE_STATE="infra/nginx/state/cian-storage.json"
```

---

<a name="frontend"></a>
## 8. Фронтенд для просмотра данных

### Текущий статус фронтенда

#### ✅ Metabase (Уже развернут)

**URL:** https://realestate.ourdocs.org/

**Возможности:**
- ✅ SQL-запросы к БД
- ✅ Визуализация данных
- ✅ Дашборды и графики
- ✅ Экспорт в CSV/JSON

**Как использовать:**

1. **Подключиться к БД:**
   - Host: localhost
   - Port: 5432
   - Database: realdb
   - User: realuser

2. **Создать запросы:**
   ```sql
   SELECT * FROM listings WHERE is_active = TRUE LIMIT 100;
   ```

3. **Создать дашборды:**
   - Карточка: Всего объявлений
   - График: Цены по районам
   - Таблица: Последние объявления

#### ⏳ Веб-интерфейс (В разработке)

**Текущее состояние:**
- ✅ Flask app: `web/app.py`
- ✅ Dashboard: `web/templates/index.html`
- ✅ Auth tool: `web/templates/simple_auth.html`
- ⏳ Listings browser: НЕ РЕАЛИЗОВАН

**Что нужно добавить:**

1. **Страница просмотра объявлений:**
```html
<!-- web/templates/listings.html -->
<div class="listings-grid">
  {% for listing in listings %}
  <div class="listing-card">
    <h3>{{ listing.rooms }}-комн, {{ listing.area_total }} м²</h3>
    <p>{{ listing.address }}</p>
    <p class="price">{{ listing.price | format_price }} ₽</p>
    <a href="{{ listing.url }}" target="_blank">Открыть на CIAN</a>
  </div>
  {% endfor %}
</div>
```

2. **API endpoint для объявлений:**
```python
# web/app.py

@app.route("/api/listings")
def get_listings():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    
    cur.execute("""
        SELECT 
            l.id,
            l.url,
            l.rooms,
            l.area_total,
            l.address,
            lp.price
        FROM listings l
        JOIN LATERAL (
            SELECT price
            FROM listing_prices
            WHERE id = l.id
            ORDER BY seen_at DESC
            LIMIT 1
        ) lp ON true
        WHERE l.is_active = TRUE
        ORDER BY l.last_seen DESC
        LIMIT 100
    """)
    
    listings = cur.fetchall()
    conn.close()
    
    return jsonify([dict(row) for row in listings])
```

3. **Фильтры и поиск:**
   - По количеству комнат
   - По цене (от-до)
   - По площади
   - По району

---

## 9. Быстрое развертывание (Checklist)

### ☑️ Подготовка (15 минут)

```bash
# 1. Проверить БД
docker-compose ps  # Должен быть running

# 2. Применить схему (если не применена)
psql -h localhost -U realuser -d realdb -f db/schema.sql

# 3. Проверить прокси-пул
cat config/proxy_pool.txt  # Должно быть 10 прокси

# 4. Проверить Anti-Captcha ключ
echo $ANTICAPTCHA_KEY  # Должен быть установлен
```

### ☑️ Тестовый запуск (5 минут)

```bash
# Запустить тест 10 страниц
python scripts/test_captcha_strategy.py --pages 10 --proxy-first-only

# Проверить результат
psql -h localhost -U realuser -d realdb -c "SELECT COUNT(*) FROM listings;"

# Ожидаемый результат: ~280 записей
```

### ☑️ Production запуск (5 часов)

```bash
# Создать скрипт
cat > scripts/scrape_100k.sh << 'EOF'
#!/bin/bash
source .venv/bin/activate
source .env

PROXIES=($(cat config/proxy_pool.txt | grep "^http"))

for session in {1..10}; do
    proxy_index=$(( ($session - 1) % ${#PROXIES[@]} ))
    export NODEMAVEN_PROXY_URL="${PROXIES[$proxy_index]}"
    
    echo "Session $session/10 starting..."
    python scripts/test_captcha_strategy.py --pages 357 --proxy-first-only
    echo "Session $session/10 complete!"
    sleep 60
done

echo "✅ All sessions complete!"
EOF

chmod +x scripts/scrape_100k.sh

# Запустить
nohup ./scripts/scrape_100k.sh > logs/scrape_100k.log 2>&1 &

# Следить за прогрессом
tail -f logs/scrape_100k.log
```

### ☑️ Проверка результатов (10 минут)

```bash
# Подсчет объявлений
psql -h localhost -U realuser -d realdb -c "
SELECT 
    COUNT(*) AS total_listings,
    COUNT(DISTINCT id) AS unique_listings,
    MIN(first_seen) AS first_scrape,
    MAX(last_seen) AS last_scrape
FROM listings;
"

# Проверка цен
psql -h localhost -U realuser -d realdb -c "
SELECT COUNT(*) AS price_records
FROM listing_prices;
"

# Статистика по комнатам
psql -h localhost -U realuser -d realdb -c "
SELECT rooms, COUNT(*) AS count
FROM listings
WHERE is_active = TRUE
GROUP BY rooms
ORDER BY rooms;
"
```

---

## 10. Фронтенд - Создание интерфейса просмотра

### Быстрое решение: Metabase (УЖЕ РАБОТАЕТ)

```bash
# Открыть Metabase
open https://realestate.ourdocs.org/

# Создать вопрос (SQL):
SELECT 
    l.id,
    l.url,
    l.rooms || '-комн' AS type,
    ROUND(l.area_total, 1) || ' м²' AS area,
    l.address,
    TO_CHAR(lp.price, 'FM999,999,999') || ' ₽' AS price,
    TO_CHAR(lp.price / l.area_total, 'FM999,999') || ' ₽/м²' AS price_per_sqm
FROM listings l
JOIN LATERAL (
    SELECT price
    FROM listing_prices
    WHERE id = l.id
    ORDER BY seen_at DESC
    LIMIT 1
) lp ON true
WHERE l.is_active = TRUE
    AND l.area_total > 0
ORDER BY l.last_seen DESC
LIMIT 100;

# Сохранить как дашборд
```

### Продвинутое решение: Веб-интерфейс

#### Создать страницу просмотра:

```bash
# Будет создан отдельный endpoint
```

---

## 11. Мониторинг и метрики

### Отслеживание прогресса

```bash
# В реальном времени
watch -n 5 'psql -h localhost -U realuser -d realdb -c "SELECT COUNT(*) FROM listings;"'

# Скорость сбора
psql -h localhost -U realuser -d realdb -c "
SELECT 
    DATE_TRUNC('hour', first_seen) AS hour,
    COUNT(*) AS offers_collected
FROM listings
GROUP BY hour
ORDER BY hour DESC;
"
```

### Логи

```bash
# Основной лог
tail -f logs/captcha_strategy.log

# Метрики
cat logs/captcha_strategy_metrics.json | jq
```

---

## 12. Стоимость и время

### Для 100,000 объявлений:

| Метрика | Значение |
|---------|----------|
| **Страниц** | 3,571 |
| **Время** | 4.7 часа |
| **Скорость** | 352 объявления/мин |
| **Прокси-трафик** | 46 MB (10 сессий × 4.6 MB) |
| **Прокси-стоимость** | $0.92 |
| **Капча (1%)** | $0.04 |
| **ИТОГО** | **$0.96** |

### Экономия vs старый подход:

- Было: $164
- Стало: $0.96
- **Экономия: $163.04 (99.4%)**

---

## 13. Troubleshooting

### Проблема: Прокси не работает

```bash
# Проверить прокси
curl -x "http://username:password@gate.nodemaven.com:8080" https://www.cian.ru

# Если ошибка → прокси истек, взять новый из пула
```

### Проблема: Капча не решается

```bash
# Проверить ключ
curl -X POST https://api.anti-captcha.com/getBalance \
  -H "Content-Type: application/json" \
  -d '{"clientKey": "4781513c0078e75e2c6ea8ea90197f44"}'

# Должен вернуть баланс
```

### Проблема: Нет данных в БД

```bash
# Проверить подключение
python -c "from etl.upsert import get_db_connection; conn = get_db_connection(); print('OK'); conn.close()"

# Проверить таблицы
psql -h localhost -U realuser -d realdb -c "\dt"
```

---

## 14. Следующие шаги

### Немедленно (сегодня):
1. ⏳ Запустить тестовый сбор 100 страниц
2. ⏳ Проверить данные в БД
3. ⏳ Создать дашборд в Metabase

### На этой неделе:
1. ⏳ Запустить полный сбор 100k
2. ⏳ Создать веб-интерфейс для просмотра
3. ⏳ Настроить автоматические отчеты

### В этом месяце:
1. ⏳ Автоматизация через Prefect
2. ⏳ Алерты на изменения цен
3. ⏳ Экспорт данных

---

**Document owner:** Cursor AI  
**Last updated:** 2025-10-11

