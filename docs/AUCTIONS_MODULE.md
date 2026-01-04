# Модуль торгов и аукционов

## Обзор

Модуль для сбора и анализа лотов с торгов по недвижимости из различных источников:

1. **ФССП** - Торги по исполнительным производствам (torgi.gov.ru)
2. **Банкротство** - Торги по банкротству (bankrot.fedresurs.ru, lot-online.ru)
3. **Залоговое имущество банков** - Витрины залогов (Сбербанк, ВТБ, Альфа-Банк)
4. **ДГИ Москвы** - Торги городской недвижимости (investmoscow.ru)

## Важно!

**Данные торгов хранятся в ОТДЕЛЬНОЙ базе данных!**

Причина: торги имеют иное ценообразование (обычно с дисконтом 20-40% от рынка).
Смешивание с основной базой CIAN исказит расчёты рыночной стоимости.

## Архитектура

```
etl/auctions/
├── __init__.py           # Экспорт модулей
├── models.py             # Pydantic модели (AuctionLot, etc.)
├── base_parser.py        # Базовый класс парсера
├── db.py                 # Работа с БД аукционов
├── cli.py                # CLI команды
└── parsers/
    ├── fssp_parser.py       # Парсер ФССП (torgi.gov.ru API)
    ├── fedresurs_parser.py  # Парсер Федресурс (Playwright)
    ├── bank_parser.py       # Парсер залогов банков
    └── dgi_parser.py        # Парсер ДГИ Москвы

web/routes/auctions.py    # Flask роуты для веб-интерфейса
web/templates/auctions.html # HTML шаблон интерфейса

db/schema_auctions.sql    # Схема БД для аукционов
```

## Установка

### 1. Запуск БД аукционов

```bash
cd /home/ubuntu/realestate
docker-compose up -d postgres-auctions
```

БД будет доступна на порту **5433** (основная CIAN на 5432).

### 2. Инициализация схемы

```bash
# Через CLI
python -m etl.auctions.cli init_db

# Или вручную
psql -h localhost -p 5433 -U realuser -d auctionsdb -f db/schema_auctions.sql
```

### 3. Переменные окружения

Добавьте в `.env`:

```bash
# Отдельная БД для аукционов
AUCTIONS_POSTGRES_DB=auctionsdb
AUCTIONS_POSTGRES_USER=realuser
AUCTIONS_POSTGRES_PASSWORD=strongpass123
AUCTIONS_DATABASE_URL=postgresql://realuser:strongpass123@localhost:5433/auctionsdb
```

## Использование

### CLI команды

```bash
# Сбор лотов со всех источников
python -m etl.auctions.cli collect --source all --city Москва

# Сбор только с ФССП
python -m etl.auctions.cli collect --source fssp --max-pages 5

# Сбор из Федресурса (банкротство)
python -m etl.auctions.cli collect --source bankrupt

# Сбор залогового имущества банков
python -m etl.auctions.cli collect --source bank_pledge

# Сбор с ДГИ Москвы
python -m etl.auctions.cli collect --source dgi_moscow

# Просмотр статистики
python -m etl.auctions.cli stats

# Список активных лотов
python -m etl.auctions.cli list --source fssp --limit 20

# Сравнение с рыночными ценами
python -m etl.auctions.cli compare-market --all
```

### Веб-интерфейс

Доступен по адресу: `http://localhost:5003/auctions`

Функции:
- Просмотр всех лотов с фильтрацией по источнику
- Статистика по источникам и дисконтам
- Сравнение цен торгов с рыночной оценкой
- Сортировка по дате, цене, дисконту

### API endpoints

```bash
# Получить лоты с фильтрами
GET /auctions/api/lots?source=fssp&status=active&limit=20

# Детали лота
GET /auctions/api/lots/{id}

# Статистика
GET /auctions/api/stats

# Сравнение с рынком
POST /auctions/api/compare/{id}
```

## Фильтрация лотов

Модуль автоматически фильтрует:

- **Доли** - пропускаются (не собираем доли в праве)
- **Не жильё** - пропускаются (земельные участки, коммерция, паркинги)
- **Собираем**: квартиры, комнаты, дома (включая новостройки)

## Схема БД

Основные таблицы:

| Таблица | Назначение |
|---------|------------|
| `auction_platforms` | Площадки торгов (ФССП, Федресурс, банки) |
| `auction_lots` | Основная таблица лотов |
| `auction_price_history` | История изменения цен |
| `auction_bids` | История ставок (если доступно) |
| `auction_market_comparison` | Сравнение с рыночной ценой |
| `auction_scrape_stats` | Статистика сбора данных |

## Интеграция с оценкой

Модуль интегрирован с Valuation API для расчёта дисконта:

```python
# Автоматическое сравнение при сборе
python -m etl.auctions.cli compare-market --all

# Результат сохраняется в auction_market_comparison
# discount_from_market показывает % дисконта от рыночной цены
```

## Источники данных

### torgi.gov.ru (ФССП)

- API: `https://torgi.gov.ru/new/api/public/lotcards/search`
- Метод: HTTP GET (без браузера)
- Фильтры: регион, категория, статус
- Обновление: ежедневно

### bankrot.fedresurs.ru

- Требует Playwright (сильная анти-бот защита)
- Парсинг HTML страниц
- Обновление: ежедневно

### Сбербанк Витрина Залогов

- API: `https://www.sberbank.ru/proxy/services/zalog-services/api/lots`
- Метод: HTTP GET
- Обновление: еженедельно

### investmoscow.ru (ДГИ)

- Требует Playwright
- Парсинг тендерных карточек
- Обновление: еженедельно

## Мониторинг

Статистика сбора данных сохраняется в `auction_scrape_stats`:

```sql
SELECT * FROM v_daily_scrape_stats;
```

## TODO

- [ ] Добавить парсер lot-online.ru
- [ ] Добавить парсер ВТБ залогов
- [ ] Добавить уведомления о новых лотах с высоким дисконтом
- [ ] Интеграция с Telegram ботом
- [ ] Автоматический ежедневный сбор через Prefect
