# Real Estate Valuation Platform

Платформа для оценки недвижимости в Санкт-Петербурге с автоматическим парсингом CIAN, обнаружением обременений и Telegram-ботом для мониторинга.

---

## Ключевые возможности

| Функция | Описание |
|---------|----------|
| **Оценка недвижимости** | Гибридный KNN + Grid алгоритм с точностью ±3-5% |
| **Парсинг CIAN** | Автономный сбор 100K+ объявлений с anti-captcha |
| **Детекция дубликатов** | Обнаружение перепостов по hash описания и параметрам |
| **Обнаружение обременений** | AI-анализ описаний через Claude API |
| **FIAS нормализация** | Стандартизация адресов через DaData Suggest API |
| **Telegram бот** | Оценка, алерты, управление парсерами |
| **Автомониторинг** | Автоматические действия при проблемах |

---

## Быстрый старт

### Требования

- Python 3.11+
- PostgreSQL 16+ с PostGIS 3.4
- Docker (опционально)
- Node.js 18+ (для Playwright)

### 1. Установка

```bash
git clone https://github.com/USERNAME/realestate-platform.git
cd realestate-platform

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. База данных

```bash
# Docker (рекомендуется)
docker-compose up -d

# Или локальный PostgreSQL
psql -h localhost -U realuser -d realdb -f db/schema.sql
```

### 3. Конфигурация

```bash
cp .env.example .env
# Заполнить переменные (см. раздел Конфигурация)
```

### 4. Запуск

```bash
# API (FastAPI :8000)
bash START.sh

# Web интерфейс (Flask :5001)
python web_viewer.py

# Telegram бот
python telegram_bot/bot.py
```

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                        TELEGRAM BOT                              │
│   Оценка | Алерты | Admin панель | Управление парсерами         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                      VALUATION API                               │
│                     (FastAPI :8000)                              │
├──────────────────────────────────────────────────────────────────┤
│  /estimate  │  /investment/calculate  │  /report/generate        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    VALUATION ENGINE                              │
├──────────────────────────────────────────────────────────────────┤
│  KNN Searcher  │  Grid Estimator  │  Hybrid Engine               │
│  (аналоги)     │  (сегменты)      │  (комбинация)                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                   ETL PIPELINE                                   │
├──────────────────────────────────────────────────────────────────┤
│  CIAN Parser  │  Enricher  │  Geocoder  │  Encumbrance Detector  │
│  (Playwright) │  (детали)  │  (DaData)  │  (Claude AI)           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                  PostgreSQL + PostGIS                            │
│           listings | valuations | segments | photos              │
└──────────────────────────────────────────────────────────────────┘
```

### Технологии

| Компонент | Технология |
|-----------|------------|
| Backend API | FastAPI, Pydantic |
| Web Interface | Flask, Jinja2, Leaflet |
| Frontend | Next.js (новая архитектура) |
| Telegram | python-telegram-bot, APScheduler |
| Парсинг | Playwright, AntiCaptcha |
| База данных | PostgreSQL 16 + PostGIS 3.4 |
| AI | Claude API (Anthropic) |
| Геокодинг | DaData API |
| Прокси | NodeMaven (только для cookies) |

---

## Компоненты

### 1. ETL Pipeline

**Парсеры запускаются через systemd таймеры:**

| Сервис | Расписание | Описание |
|--------|-----------|----------|
| `cian-scraper` | каждые 90 мин | Основной сбор объявлений + детекция дубликатов |
| `cian-enrich` | каждые 60 мин | Загрузка описаний + hash |
| `cian-alerts` | каждые 10 мин | Проверка обременений |
| `fias-normalizer` | 4 раза в день | FIAS нормализация через DaData |

> **Примечание:** `cian-fast-scan` отключён (дублирует функционал cian-scraper)

**Управление:**

```bash
# Статус всех парсеров
sudo systemctl list-timers 'cian-*'

# Запустить вручную
sudo systemctl start cian-scraper.service

# Логи
journalctl -u cian-scraper -f
```

### 2. Telegram Bot (@NevskyDeals_bot)

**Команды пользователя:**

| Команда | Описание |
|---------|----------|
| `/start` | Начать диалог |
| `/eval` | Оценить объект (ввод адреса и площади) |
| `/status` | Статус системы |

**Admin команды:**

| Команда | Описание |
|---------|----------|
| `/manage` | Панель управления парсерами |
| `/proxy` | Статус прокси и cookies |
| `/logs [service]` | Просмотр логов сервиса |
| `/restart [service]` | Перезапуск сервиса |

**Автоматические алерты:**

| Алерт | Условие | Действие |
|-------|---------|----------|
| Зависший процесс | >1 день | Auto-kill + restart |
| Долгий процесс | >4 часа | Auto-kill + restart |
| Устаревшие cookies | >24ч | Auto-refresh |
| Критично мало трафика | <0.1 GB | Stop parsers |
| Прокси для парсинга | >2 conn | Kill processes |

### 3. API

**Valuation API (FastAPI :8000):**

```bash
# Оценка объекта
curl -X POST http://localhost:8000/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "lat": 59.93,
    "lon": 30.31,
    "area_total": 65,
    "rooms": 2,
    "floor": 5,
    "total_floors": 12
  }'

# Инвестиционный расчёт
curl -X POST http://localhost:8000/investment/calculate \
  -d '{"purchase_price": 8000000, "project_type": "partner_flip"}'
```

---

## Конфигурация

### Переменные окружения (.env)

```bash
# === База данных ===
PG_DSN=postgresql://realuser:password@localhost:5432/realdb

# === Telegram ===
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ADMIN_CHAT_ID=your_admin_id
TELEGRAM_CHAT_ID=your_channel_id

# === API ключи ===
DADATA_API_KEY=your_dadata_key
DADATA_SECRET_KEY=your_dadata_secret
ANTHROPIC_API_KEY=your_claude_key

# === Прокси (только для cookies!) ===
# Credentials в etl/collector_cian/nodemaven_proxy.py
# NODEMAVEN_API_KEY=your_api_key  # для мониторинга трафика
```

### Прокси

**КРИТИЧЕСКИ ВАЖНО:** Прокси используется ТОЛЬКО для получения cookies, НИКОГДА для парсинга!

- Парсеры идут напрямую к CIAN без прокси
- Прокси используется только в `get_cookies_with_proxy.py`
- Это экономит трафик NodeMaven

**Конфигурация прокси:**

```python
# etl/collector_cian/nodemaven_proxy.py
PROXY_USER = "nikita_a_v_92_gmail_com"
PROXY_HOST = "gate.nodemaven.com"
PROXY_PORT = 8080
```

---

## Мониторинг

### Health Checks

Бот проверяет систему каждые 5 минут:

1. **Процессы** - время работы, зависания
2. **Cookies** - возраст файла (живут 24ч)
3. **Прокси** - тест соединения, время отклика
4. **Трафик** - остаток на подписке

### Автодействия

При обнаружении проблем бот автоматически:

- Убивает зависшие процессы (>4ч)
- Перезапускает соответствующие таймеры
- Обновляет cookies при истечении
- Останавливает парсеры при критическом трафике
- Отправляет отчёт админу

### Просмотр статуса

```bash
# Telegram
/status

# CLI
python scripts/health_check.py
```

---

## Алгоритм оценки

### BOTTOM-3 Strategy

1. **Поиск аналогов** - KNN в радиусе 2 км, похожие параметры
2. **IQR фильтрация** - удаление выбросов (±1.5 IQR)
3. **Коррекции:**
   - Площадь: ±0.1% за каждый м² разницы
   - Возраст: -1% за каждые 30 дней на рынке
   - Этаж: -2% последний, -5% первый
4. **Расчёт** - среднее по 3 самым дешёвым
5. **Торг** - автоматическая скидка 7%

### Confidence Score

| Score | Диапазон | Условие |
|-------|----------|---------|
| ≥70% | ±5% | Много качественных аналогов |
| 50-69% | ±10% | Среднее количество |
| <50% | ±15% | Мало аналогов |

---

## Структура проекта

```
realestate/
├── api/                      # FastAPI Backend
│   ├── valuation.py          # Оценка
│   ├── investment_calculator.py
│   └── report_generator.py
│
├── etl/                      # ETL Pipeline
│   ├── collector_cian/       # CIAN парсер
│   │   ├── cli.py            # Точка входа
│   │   ├── nodemaven_proxy.py # Прокси модуль
│   │   └── antibot/          # Anti-captcha
│   ├── valuation/            # Алгоритмы оценки
│   └── ai_evaluator/         # AI анализ
│
├── telegram_bot/             # Telegram бот
│   ├── bot.py                # Основная логика
│   ├── admin_commands.py     # Admin функции
│   └── egrn_parser.py        # EGRN парсер
│
├── web/                      # Flask Web App
├── frontend/                 # Next.js (новая архитектура)
├── db/                       # Схемы PostgreSQL
│
├── .speckit/                 # SpecKit документация
│   ├── PROJECT-MAP.md        # Карта проекта
│   ├── CLAUDE-CONTEXT.md     # Контекст для Claude Code
│   ├── specifications/       # Спецификации
│   └── tasks/                # Задачи
│
├── config/                   # Конфигурация
│   ├── cian_browser_state.json  # Cookies (автообновление)
│   └── get_cookies_with_proxy.py
│
└── logs/                     # Логи парсеров
```

---

## Деплой

### Systemd сервисы

```bash
# Бот
sudo systemctl enable realestate-bot
sudo systemctl start realestate-bot

# Таймеры парсеров
sudo systemctl enable cian-scraper.timer
sudo systemctl enable cian-enrich.timer
sudo systemctl start cian-scraper.timer
```

### Docker

```bash
docker-compose up -d
```

---

## Разработка

### Тестирование

```bash
pytest tests/
python scripts/test_valuation.py
```

### SpecKit документация

Проект использует SpecKit для стратегической документации:

- `.speckit/PROJECT-MAP.md` - карта проекта
- `.speckit/CLAUDE-CONTEXT.md` - контекст для Claude Code
- `.speckit/specifications/` - спецификации фич
- `.speckit/tasks/` - текущие задачи

---

## Лицензия

Внутренний проект. Все права защищены.

---

**Версия:** 2.2.1
**Последнее обновление:** 7 Января 2026
