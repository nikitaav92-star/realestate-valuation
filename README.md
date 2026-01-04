# Real Estate Valuation Platform

Платформа оценки стоимости недвижимости с гибридным алгоритмом KNN + Grid.

---

## Ключевые возможности

| Функция | Описание |
|---------|----------|
| **Оценка недвижимости** | Гибридный KNN + Grid алгоритм с точностью ±3-5% |
| **Инвестиционный калькулятор** | 4 типа проектов: своё жильё, партнёрский, flip, bank flip |
| **Telegram бот** | EGRN парсинг, уведомления об оценках |
| **Интерактивная карта** | Leaflet + PostGIS кластеризация |
| **Отчёты** | PDF и HTML генерация отчётов об оценке |

---

## Быстрый старт

### 1. Установка зависимостей

```bash
# Клонировать репозиторий
git clone https://github.com/USERNAME/realestate-valuation.git
cd realestate-valuation

# Создать виртуальное окружение
python -m venv venv
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt
playwright install chromium
```

### 2. База данных

```bash
# Запустить PostgreSQL + PostGIS
docker-compose up -d

# Применить схему
psql -h localhost -U realuser -d realdb -f db/schema.sql
```

### 3. Настройка окружения

```bash
cp .env.example .env
# Отредактировать .env с вашими значениями
```

### 4. Запуск сервисов

```bash
# Valuation API (FastAPI, порт 8000)
bash START.sh

# Web интерфейс (Flask, порт 5001)
python web_viewer.py

# Telegram бот
cd telegram_bot && bash START_BOT.sh
```

### 5. Тестирование API

```bash
curl -X POST http://localhost:8000/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "lat": 55.75,
    "lon": 37.62,
    "area_total": 65,
    "rooms": 2,
    "floor": 5,
    "total_floors": 12
  }'
```

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                      Web Interface                          │
│              (Flask :5001 / static/index.html)              │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                    Valuation API                            │
│                    (FastAPI :8000)                          │
├─────────────────────────────────────────────────────────────┤
│  /estimate           │  /investment/calculate               │
│  /estimate/comparables│  /report/generate                   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  Valuation Engine                           │
├─────────────────────────────────────────────────────────────┤
│  KNN Searcher   │  Grid Estimator  │  Hybrid Engine        │
│  (похожие       │  (агрегаты по    │  (комбинация          │
│   объекты)      │   сегментам)     │   методов)            │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│               PostgreSQL + PostGIS                          │
│            (listings, valuations, segments)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Алгоритм оценки

### BOTTOM-3 Strategy

1. **Поиск аналогов** - KNN поиск похожих объектов в радиусе 2 км
2. **Фильтрация** - IQR фильтр выбросов (±1.5 IQR от медианы)
3. **Коррекции:**
   - Площадь: ±0.1% за каждый м² разницы
   - Возраст объявления: -1% за каждые 30 дней
   - Этаж: -2% последний этаж, -5% первый этаж
4. **Расчёт** - среднее по 3 самым дешёвым аналогам
5. **Торг** - автоматическая скидка 7%

### Confidence Score

| Confidence | Диапазон цен | Условие |
|------------|--------------|---------|
| ≥70% | ±5% | Много качественных аналогов |
| 50-69% | ±10% | Среднее количество аналогов |
| <50% | ±15% | Мало аналогов, низкое качество |

---

## Инвестиционный калькулятор

### Типы проектов

| Тип | Описание | Целевая доходность |
|-----|----------|-------------------|
| `own` | Покупка для себя | — |
| `partner` | Партнёрский проект | Делится пополам |
| `partner_flip` | Партнёрский flip | 24% годовых |
| `bank_flip` | Flip с ипотекой | 24% + проценты банка |

### Учитываемые расходы

- Риэлторская комиссия (3%)
- Налог на покупку
- Ремонт (ROI 1.8x)
- ЖКУ за период владения
- Ипотечные платежи (для bank_flip)

---

## API Endpoints

### Valuation API (FastAPI :8000)

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/estimate` | POST | Оценка стоимости объекта |
| `/estimate/comparables` | POST | Получить аналоги |
| `/investment/calculate` | POST | Расчёт инвестиционных метрик |
| `/report/generate` | POST | Генерация PDF отчёта |
| `/health` | GET | Health check |

### Web API (Flask :5001)

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/` | GET | Главная страница (оценка) |
| `/listings` | GET | Список объявлений |
| `/api/map/clusters` | GET | Кластеры для карты |
| `/api/valuations/history` | GET | История оценок |

---

## Структура проекта

```
realestate/
├── api/                          # FastAPI Backend
│   └── v1/
│       ├── valuation.py          # Оценка недвижимости
│       ├── investment_calculator.py  # Инвест. калькулятор
│       ├── report_generator.py   # PDF отчёты
│       └── claude_parser.py      # AI парсер
│
├── etl/                          # ETL Pipeline
│   ├── collector_cian/           # CIAN парсер
│   ├── valuation/                # Алгоритмы оценки
│   │   ├── knn_searcher.py       # KNN поиск
│   │   ├── grid_estimator.py     # Grid оценка
│   │   ├── hybrid_engine.py      # Гибридный движок
│   │   └── rosreestr_searcher.py # Данные Росреестра
│   ├── geocoder.py               # DaData геокодинг
│   └── upsert.py                 # Работа с БД
│
├── web/                          # Flask Web App
│   ├── app.py                    # Flask entry point
│   └── routes/                   # Роуты
│
├── telegram_bot/                 # Telegram бот
│   ├── bot.py                    # Основная логика
│   └── egrn_parser.py            # EGRN парсер
│
├── static/                       # Статика для web
│   └── index.html                # SPA интерфейс
│
├── db/                           # Схемы БД
│   └── schema.sql
│
├── .speckit/                     # SpecKit документация
│   ├── PROJECT-MAP.md            # Карта проекта
│   ├── specifications/           # Спецификации
│   ├── bugs/                     # Баг-репорты
│   └── ideas/                    # Бэклог идей
│
├── docker-compose.yml            # Docker stack
├── requirements.txt              # Python зависимости
├── START.sh                      # Запуск API
└── .env.example                  # Пример конфига
```

---

## Переменные окружения

```bash
# База данных
DATABASE_URL=postgresql://realuser:password@localhost:5432/realdb

# Или отдельные переменные
PG_HOST=localhost
PG_PORT=5432
PG_USER=realuser
PG_PASS=password
PG_DB=realdb

# DaData (геокодинг)
DADATA_API_KEY=your_api_key
DADATA_SECRET_KEY=your_secret_key

# Telegram бот
TELEGRAM_BOT_TOKEN=your_bot_token

# Anti-captcha (для парсера CIAN)
ANTICAPTCHA_KEY=your_key

# Прокси (опционально)
NODEMAVEN_PROXY_URL=http://user:pass@proxy:8080
```

---

## Деплой

### Systemd сервисы

```bash
# Valuation API
sudo cp deployment/realestate-api.service /etc/systemd/system/
sudo systemctl enable realestate-api
sudo systemctl start realestate-api

# Web интерфейс
sudo cp deployment/realestate-web.service /etc/systemd/system/
sudo systemctl enable realestate-web
sudo systemctl start realestate-web
```

### Nginx

```bash
sudo cp infra/nginx/realestate.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/realestate.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## Тестирование

```bash
# Unit тесты
pytest tests/

# Тест валюации
python scripts/test_valuation.py

# Тест API
bash TEST_API.sh
```

---

## Недавние улучшения

### Январь 2025

- **IQR фильтрация** - удаление выбросов из аналогов
- **Aging discount** - учёт возраста объявлений (-1% за 30 дней)
- **Confidence-based range** - диапазон цен зависит от уверенности
- **Дисконт последнего этажа** - снижен с 5% до 2%
- **Кнопка "Переоценить"** - в истории оценок

### Декабрь 2024

- **Инвестиционный калькулятор** - 4 типа проектов
- **Telegram отчёты** - отправка PDF в бот
- **Интерактивная карта** - PostGIS кластеризация

---

## Документация

- [QUICKSTART.md](QUICKSTART.md) - Быстрый старт
- [.speckit/PROJECT-MAP.md](.speckit/PROJECT-MAP.md) - Карта проекта
- [.speckit/specifications/](.speckit/specifications/) - Спецификации

---

## Лицензия

Внутренний проект. Все права защищены.

---

**Версия:** 2.1.0
**Последнее обновление:** Январь 2025
