## FAQ: Развертывание массового сбора CIAN

**Date:** 2025-10-11

---

## ❓ Что необходимо для развертывания?

### Минимальные требования:

#### 1. **Система**
```bash
✅ Ubuntu 22.04+ (или аналог)
✅ Python 3.11+
✅ 4 GB RAM
✅ 50 GB диск
✅ Доступ в интернет
```

#### 2. **База данных**
```bash
✅ PostgreSQL 14+ (уже есть в Docker)
✅ Таблицы: listings, listing_prices
✅ Применить: db/schema.sql
```

#### 3. **Прокси**
```bash
✅ 10 NodeMaven прокси (уже есть в config/proxy_pool.txt)
✅ Стоимость: ~$1 для 100k объявлений
✅ Ротация автоматическая
```

#### 4. **Anti-Captcha API**
```bash
✅ Ключ: 4781513c0078e75e2c6ea8ea90197f44 (уже есть)
✅ Стоимость: $0.001 за решение
✅ Частота: <1%
```

#### 5. **Python пакеты**
```bash
✅ playwright (browser automation)
✅ httpx (HTTP client)
✅ psycopg2 (PostgreSQL)
✅ flask (web interface)
✅ Все в requirements.txt
```

### Команды для развертывания:

```bash
# 1. Клонировать репозиторий
git clone https://github.com/nikitaav92-star/realestate.git
cd realestate
git checkout fix1

# 2. Установить зависимости
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# 3. Запустить БД
docker-compose up -d
psql -h localhost -U realuser -d realdb -f db/schema.sql

# 4. Настроить переменные
cp .env.example .env
# Отредактировать .env (добавить ANTICAPTCHA_KEY)

# 5. Тестовый запуск
python scripts/test_captcha_strategy.py --pages 10 --proxy-first-only

# 6. Production запуск
./scripts/scrape_100k.sh
```

**Время развертывания:** 30 минут  
**Время первого сбора:** 5 часов  
**Стоимость:** ~$1

---

## ❓ Как структурируется информация в БД?

### Две основные таблицы:

#### 1. `listings` - Объявления (SCD Type 2)

**Структура:**
```
id (PK) → url → region → deal_type → rooms → area_total → 
floor → address → seller_type → lat/lon → 
first_seen → last_seen → is_active
```

**Логика:**
- При первом появлении: `INSERT` с `first_seen = NOW()`
- При повторном: `UPDATE` с `last_seen = NOW()`
- Если пропало: `is_active = FALSE` (мягкое удаление)

**Пример:**
```sql
INSERT INTO listings (id, url, rooms, ...) 
VALUES (123456, 'https://www.cian.ru/...', 2, ...)
ON CONFLICT (id) DO UPDATE
SET last_seen = NOW(), is_active = TRUE;
```

#### 2. `listing_prices` - История цен

**Структура:**
```
id (FK) → seen_at (PK) → price
```

**Логика:**
- Новая запись ТОЛЬКО при изменении цены
- Проверяет последнюю цену перед INSERT
- Позволяет отслеживать динамику

**Пример:**
```sql
-- Цена 15 млн
INSERT: (123456, '2025-10-11 09:00', 15000000)

-- Цена изменилась на 14.5 млн
INSERT: (123456, '2025-10-12 09:00', 14500000)

-- Цена не изменилась
-- Новая запись НЕ создается
```

---

## ❓ Какие переменные попадают в БД?

### Полный список полей:

| № | Поле | Тип | Источник CIAN API | Обязательное | Описание |
|---|------|-----|-------------------|--------------|----------|
| 1 | **id** | BIGINT | `offerId` | ✅ Да | Уникальный ID объявления |
| 2 | **url** | TEXT | `seoUrl` | ✅ Да | **Ссылка на объявление** |
| 3 | **region** | INT | `region` | ❌ Нет | Регион (1=Москва) |
| 4 | **deal_type** | TEXT | `operationName` | ❌ Нет | sale/rent |
| 5 | **rooms** | INT | `rooms` | ❌ Нет | Количество комнат |
| 6 | **area_total** | NUMERIC | `totalSquare` | ❌ Нет | Площадь (м²) |
| 7 | **floor** | INT | `floor` | ❌ Нет | Этаж |
| 8 | **address** | TEXT | `address` | ❌ Нет | Адрес |
| 9 | **seller_type** | TEXT | `userType` | ❌ Нет | owner/agent/developer |
| 10 | **lat** | DOUBLE | `geo.coordinates.lat` | ❌ Нет | Широта |
| 11 | **lon** | DOUBLE | `geo.coordinates.lng` | ❌ Нет | Долгота |
| 12 | **first_seen** | TIMESTAMP | AUTO | ✅ Да | Первое появление |
| 13 | **last_seen** | TIMESTAMP | AUTO | ✅ Да | Последнее обновление |
| 14 | **is_active** | BOOLEAN | AUTO | ✅ Да | Активность |
| 15 | **price** | NUMERIC | `price.value` | ✅ Да | Цена (в listing_prices) |

### Примеры значений:

```json
{
  "id": 123456789,
  "url": "https://www.cian.ru/sale/flat/123456789/",
  "region": 1,
  "deal_type": "sale",
  "rooms": 2,
  "area_total": 65.5,
  "floor": 5,
  "address": "Москва, Тверская улица, 10",
  "seller_type": "owner",
  "lat": 55.751244,
  "lon": 37.618423,
  "first_seen": "2025-10-11T09:00:00",
  "last_seen": "2025-10-11T09:00:00",
  "is_active": true,
  "price": 15000000
}
```

---

## ❓ Копируется ли ссылка на объявление?

### ✅ ДА! Ссылка копируется в поле `url`

**Источник:** `seoUrl` из CIAN API

**Формат:** `https://www.cian.ru/sale/flat/{id}/`

**Пример:**
```
https://www.cian.ru/sale/flat/123456789/
https://www.cian.ru/rent/flat/987654321/
```

**Код маппинга:**
```python
# etl/collector_cian/mapper.py

def to_listing(offer: Dict[str, Any]) -> Listing:
    return Listing(
        id=offer.get("offerId"),
        url=str(offer.get("seoUrl") or offer.get("absoluteUrl") or ""),
        # ... other fields
    )
```

**SQL запрос для проверки:**
```sql
SELECT id, url FROM listings LIMIT 5;

-- Результат:
-- id        | url
-- 123456789 | https://www.cian.ru/sale/flat/123456789/
-- 987654321 | https://www.cian.ru/rent/flat/987654321/
```

**Использование в фронтенде:**
```html
<a href="{{ listing.url }}" target="_blank">
    Открыть на CIAN
</a>
```

---

## ❓ Каков статус фронтенда?

### Текущее состояние:

#### ✅ Metabase (Production Ready)

**URL:** https://realestate.ourdocs.org/

**Статус:** 🟢 **Работает**

**Возможности:**
- ✅ SQL-запросы к БД
- ✅ Визуализация данных
- ✅ Дашборды
- ✅ Графики и таблицы
- ✅ Экспорт в CSV/JSON/Excel

**Пример использования:**
```sql
-- В Metabase создать вопрос:
SELECT 
    l.id,
    l.url AS "Ссылка",
    l.rooms AS "Комнат",
    l.area_total AS "Площадь",
    l.address AS "Адрес",
    lp.price / 1000000 AS "Цена (млн ₽)",
    ROUND(lp.price / l.area_total, 0) AS "₽/м²"
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
LIMIT 100;
```

---

#### 🆕 Listings Browser (Только что создан!)

**Файлы:**
- ✅ `web/app.py` - Flask приложение
- ✅ `web/routes/listings.py` - API endpoints
- ✅ `web/templates/listings.html` - UI интерфейс

**Функции:**
- ✅ Просмотр объявлений (карточки)
- ✅ Фильтры (комнаты, цена, площадь)
- ✅ Пагинация
- ✅ Статистика
- ✅ Ссылки на CIAN
- ✅ Responsive design

**Запуск:**
```bash
cd /opt/realestate
source .venv/bin/activate
python web/app.py --port 5003

# Открыть в браузере:
# http://localhost:5003/
```

**Скриншот интерфейса:**
```
┌─────────────────────────────────────────────────────────────┐
│  CIAN Listings Browser                                      │
├─────────────────────────────────────────────────────────────┤
│  Статистика:                                                │
│  [Всего: 100,000] [Активных: 95,000] [Средняя: 15 млн ₽]  │
├─────────────────────────────────────────────────────────────┤
│  Фильтры:                                                   │
│  [Комнат: 2] [Цена от: 10млн] [до: 20млн] [Площадь: 50+]  │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────┐ │
│  │ 2-комн квартира, 65.5 м²          15.0 млн ₽         │ │
│  │ Москва, Тверская улица, 10        229,008 ₽/м²       │ │
│  │ Этаж: 5 | owner | 11.10.2025      [Открыть на CIAN] │ │
│  └───────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ 3-комн квартира, 85.0 м²          22.0 млн ₽         │ │
│  │ ...                                                    │ │
│  └───────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  [<] [1] [2] [3] ... [50] [>]                              │
└─────────────────────────────────────────────────────────────┘
```

---

#### ⏳ Дополнительные фичи (Планируются)

**Что можно добавить:**

1. **Карта объявлений**
   - Использовать lat/lon
   - Leaflet.js или Google Maps
   - Кластеризация

2. **Графики цен**
   - История изменений
   - Тренды по районам
   - Прогнозы

3. **Алерты**
   - Уведомления о падении цен
   - Новые объявления по фильтрам
   - Email/Telegram

4. **Экспорт**
   - CSV
   - Excel
   - JSON API

5. **Сравнение**
   - Сравнить несколько объявлений
   - Таблица характеристик

---

## 📊 Как обобщается информация?

### Уровень 1: Сырые данные

**Таблица:** `listings` + `listing_prices`

**Объем:** 100,000 записей в `listings`, ~100,000-200,000 в `listing_prices`

**Обновление:** Каждый запуск скрипта

---

### Уровень 2: Агрегированная статистика

**SQL Views (можно создать):**

#### View 1: Последние цены
```sql
CREATE VIEW v_listings_latest AS
SELECT 
    l.*,
    lp.price AS current_price,
    lp.seen_at AS price_updated_at,
    CASE WHEN l.area_total > 0 
        THEN ROUND(lp.price / l.area_total, 0)
        ELSE NULL 
    END AS price_per_sqm
FROM listings l
JOIN LATERAL (
    SELECT price, seen_at
    FROM listing_prices
    WHERE id = l.id
    ORDER BY seen_at DESC
    LIMIT 1
) lp ON true
WHERE l.is_active = TRUE;
```

#### View 2: Статистика по районам
```sql
CREATE VIEW v_stats_by_region AS
SELECT 
    region,
    COUNT(*) AS listings_count,
    AVG(area_total) AS avg_area,
    AVG(current_price) AS avg_price,
    AVG(price_per_sqm) AS avg_price_per_sqm
FROM v_listings_latest
WHERE area_total > 0
GROUP BY region;
```

#### View 3: Падения цен
```sql
CREATE VIEW v_price_drops AS
WITH price_changes AS (
    SELECT 
        id,
        price,
        LAG(price) OVER (PARTITION BY id ORDER BY seen_at) AS prev_price,
        seen_at
    FROM listing_prices
)
SELECT 
    l.id,
    l.url,
    l.address,
    pc.prev_price,
    pc.price,
    ROUND(((pc.price - pc.prev_price) / pc.prev_price * 100), 2) AS change_percent,
    pc.seen_at
FROM price_changes pc
JOIN listings l ON pc.id = l.id
WHERE pc.prev_price IS NOT NULL
    AND ((pc.price - pc.prev_price) / pc.prev_price) <= -0.05
ORDER BY change_percent ASC;
```

---

### Уровень 3: Бизнес-метрики

**Создать в Metabase:**

1. **Карточка: Всего объявлений**
   ```sql
   SELECT COUNT(*) FROM listings WHERE is_active = TRUE;
   ```

2. **Карточка: Средняя цена**
   ```sql
   SELECT AVG(current_price) / 1000000 AS avg_price_mln
   FROM v_listings_latest;
   ```

3. **График: Цены по комнатам**
   ```sql
   SELECT rooms, AVG(current_price) / 1000000 AS avg_price
   FROM v_listings_latest
   GROUP BY rooms
   ORDER BY rooms;
   ```

4. **Таблица: ТОП-10 падений цен**
   ```sql
   SELECT * FROM v_price_drops LIMIT 10;
   ```

---

## 📋 Полная структура данных

### Входные данные (CIAN API):

```json
{
  "data": {
    "offersSerialized": [
      {
        "offerId": 123456789,
        "seoUrl": "https://www.cian.ru/sale/flat/123456789/",
        "price": {"value": 15000000},
        "rooms": 2,
        "totalSquare": 65.5,
        "floor": 5,
        "address": "Москва, Тверская улица, 10",
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
    ]
  }
}
```

### Промежуточная обработка (Python):

```python
# etl/collector_cian/mapper.py

listing = Listing(
    id=123456789,
    url="https://www.cian.ru/sale/flat/123456789/",
    region=1,
    deal_type="sale",
    rooms=2,
    area_total=65.5,
    floor=5,
    address="Москва, Тверская улица, 10",
    seller_type="owner",
    lat=55.751244,
    lon=37.618423,
)

price = PricePoint(
    id=123456789,
    price=15000000,
    seen_at=datetime.now(),
)
```

### Выходные данные (PostgreSQL):

**Таблица `listings`:**
```
id          | 123456789
url         | https://www.cian.ru/sale/flat/123456789/
region      | 1
deal_type   | sale
rooms       | 2
area_total  | 65.5
floor       | 5
address     | Москва, Тверская улица, 10
seller_type | owner
lat         | 55.751244
lon         | 37.618423
first_seen  | 2025-10-11 09:00:00
last_seen   | 2025-10-11 09:00:00
is_active   | true
```

**Таблица `listing_prices`:**
```
id       | 123456789
seen_at  | 2025-10-11 09:00:00
price    | 15000000
```

---

## 🌐 Статус фронтенда - Детально

### Вариант 1: Metabase (УЖЕ РАБОТАЕТ)

**Статус:** 🟢 **Production Ready**

**URL:** https://realestate.ourdocs.org/

**Что можно делать:**
- ✅ Просматривать все объявления
- ✅ Фильтровать по любым полям
- ✅ Создавать дашборды
- ✅ Строить графики
- ✅ Экспортировать данные
- ✅ Делиться отчетами

**Преимущества:**
- ✅ Уже настроен и работает
- ✅ Мощный инструмент аналитики
- ✅ Не требует разработки
- ✅ Профессиональный вид

**Недостатки:**
- ❌ Не для конечных пользователей
- ❌ Требует знания SQL
- ❌ Нет кастомного дизайна

---

### Вариант 2: Custom Web Interface (СОЗДАН СЕЙЧАС)

**Статус:** 🟡 **MVP Ready** (требует тестирования)

**URL:** http://localhost:5003/

**Файлы:**
- ✅ `web/app.py` - Flask приложение
- ✅ `web/routes/listings.py` - API
- ✅ `web/templates/listings.html` - UI

**Функции:**
- ✅ Карточки объявлений
- ✅ Фильтры (комнаты, цена, площадь)
- ✅ Пагинация
- ✅ Статистика (всего, активных, средняя цена)
- ✅ Ссылки на CIAN
- ✅ Адаптивный дизайн

**Что показывается:**
```
Для каждого объявления:
- Тип (2-комн квартира)
- Площадь (65.5 м²)
- Адрес (Москва, Тверская, 10)
- Этаж (5)
- Тип продавца (owner)
- Цена (15.0 млн ₽)
- Цена за м² (229,008 ₽/м²)
- Дата обновления
- Кнопка "Открыть на CIAN" → ссылка на объявление
```

**Запуск:**
```bash
cd /opt/realestate
source .venv/bin/activate
python web/app.py --port 5003 --debug

# Откроется на http://localhost:5003/
```

**Что нужно добавить:**
- ⏳ Карта с объявлениями (lat/lon)
- ⏳ Графики истории цен
- ⏳ Сравнение объявлений
- ⏳ Экспорт в Excel
- ⏳ Избранное

---

### Вариант 3: API для внешних приложений

**Статус:** ✅ **Готов**

**Endpoints:**

```bash
# Список объявлений
GET /listings/api/list?page=1&per_page=20&rooms=2&min_price=10000000

# Статистика
GET /listings/api/stats

# Health check
GET /health
```

**Пример ответа:**
```json
{
  "listings": [
    {
      "id": 123456789,
      "url": "https://www.cian.ru/sale/flat/123456789/",
      "rooms": 2,
      "area_total": 65.5,
      "address": "Москва, Тверская, 10",
      "price": 15000000,
      "price_per_sqm": 229008
    }
  ],
  "total": 100000,
  "page": 1,
  "pages": 5000
}
```

---

## 🚀 Быстрый старт фронтенда

### Metabase (Рекомендуется для начала):

```bash
# 1. Открыть Metabase
open https://realestate.ourdocs.org/

# 2. Подключиться к БД
Host: localhost
Port: 5432
Database: realdb
User: realuser
Pass: strongpass

# 3. Создать SQL вопрос
SELECT * FROM v_listings_latest LIMIT 100;

# 4. Сохранить как дашборд
```

### Custom Web Interface:

```bash
# 1. Запустить Flask app
cd /opt/realestate
source .venv/bin/activate
python web/app.py --port 5003

# 2. Открыть в браузере
open http://localhost:5003/

# 3. Использовать фильтры
- Выбрать количество комнат
- Указать диапазон цен
- Нажать "Найти"

# 4. Просмотреть объявления
- Кликнуть "Открыть на CIAN" для деталей
```

---

## 📈 Roadmap фронтенда

### Фаза 1: MVP (✅ Готово)
- ✅ Просмотр объявлений
- ✅ Базовые фильтры
- ✅ Пагинация
- ✅ Ссылки на CIAN

### Фаза 2: Улучшения (1-2 недели)
- ⏳ Карта с объявлениями
- ⏳ Графики истории цен
- ⏳ Сохраненные поиски
- ⏳ Экспорт данных

### Фаза 3: Продвинутые фичи (1 месяц)
- ⏳ Алерты на изменения
- ⏳ Сравнение объявлений
- ⏳ Аналитика трендов
- ⏳ Рекомендации

---

## 💡 Рекомендации

### Для быстрого старта:
1. ✅ Используйте Metabase (уже работает)
2. ✅ Создайте 3-5 базовых дашбордов
3. ✅ Экспортируйте данные в Excel

### Для production:
1. ⏳ Протестируйте web interface
2. ⏳ Добавьте нужные фильтры
3. ⏳ Настройте автообновление
4. ⏳ Добавьте аналитику

---

**Document owner:** Cursor AI  
**Last updated:** 2025-10-11

