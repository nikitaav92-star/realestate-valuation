# Контекст для Claude Code

Этот документ содержит критическую информацию для Claude Code при работе с проектом.

---

## Критические правила

### 1. ПРОКСИ

**ПРОКСИ ИСПОЛЬЗУЕТСЯ ТОЛЬКО ДЛЯ COOKIES, НИКОГДА ДЛЯ ПАРСИНГА!**

- Парсеры (`cian-scraper`, `cian-enrich`, `cian-fast-scan`) идут НАПРЯМУЮ к CIAN
- Прокси используется ТОЛЬКО в `config/get_cookies_with_proxy.py`
- Это экономит трафик NodeMaven (платный, ограниченный)

```
ПРАВИЛЬНО:
  get_cookies_with_proxy.py → NodeMaven proxy → CIAN → cookies
  cian_parser.py → НАПРЯМУЮ к CIAN (с cookies)

НЕПРАВИЛЬНО:
  cian_parser.py → proxy → CIAN  ← НЕ ДЕЛАТЬ!
```

### 2. Cookies

- Файл: `/home/ubuntu/realestate/config/cian_browser_state.json`
- Живут ~24 часа
- Автообновление через бота при истечении
- Нужны для обхода rate limits CIAN

### 3. База данных

```bash
# Всегда использовать PG_DSN из .env
PG_DSN=postgresql://realuser:strongpass123@localhost:5432/realdb
```

---

## Архитектура системы

```
┌────────────────────────────────────────────────────────────┐
│                     TELEGRAM BOT                            │
│              (realestate-bot.service)                       │
│  - Оценка объектов (/eval)                                 │
│  - Статус системы (/status)                                │
│  - Управление парсерами (/manage)                          │
│  - Автоалерты каждые 5 мин                                 │
└──────────────────────────┬─────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────┐
│                    SYSTEMD TIMERS                           │
├─────────────────────────────────────────────────────────────┤
│  cian-scraper.timer   │ каждые 90 мин  │ Сбор объявлений   │
│  cian-fast-scan.timer │ каждые 30 мин  │ Срочные           │
│  cian-enrich.timer    │ каждые 60 мин  │ Описания          │
│  cian-alerts.timer    │ каждые 10 мин  │ Обременения       │
│  fias-normalizer.timer│ 4 раза/день    │ Геокодинг         │
└──────────────────────────┬─────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────┐
│                    PostgreSQL + PostGIS                     │
│                     (localhost:5432)                        │
├─────────────────────────────────────────────────────────────┤
│  listings        │ Объявления CIAN (~100K)                  │
│  listing_photos  │ Фото объявлений                          │
│  valuations      │ История оценок                           │
│  segments        │ Grid-сегменты для оценки                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Ключевые файлы

| Компонент | Файл | Описание |
|-----------|------|----------|
| Telegram бот | `telegram_bot/bot.py` | Основная логика бота |
| Admin функции | `telegram_bot/admin_commands.py` | Управление парсерами |
| Прокси модуль | `etl/collector_cian/nodemaven_proxy.py` | NodeMaven интеграция |
| Получение cookies | `config/get_cookies_with_proxy.py` | Единственное место с прокси |
| CIAN парсер | `etl/collector_cian/cli.py` | Точка входа парсера |
| Оценка | `api/valuation.py` | Алгоритм оценки |

---

## Переменные окружения

```bash
# Обязательные
PG_DSN=postgresql://...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ADMIN_CHAT_ID=...

# API ключи
DADATA_API_KEY=...
ANTHROPIC_API_KEY=...

# Прокси (credentials в коде, НЕ в .env)
# NODEMAVEN_API_KEY=...  # только для мониторинга трафика
```

---

## Автодействия при алертах

Бот автоматически выполняет действия при проблемах:

| Проблема | Условие | Действие |
|----------|---------|----------|
| Зависший процесс | runtime > 1 day | `auto_fix_stuck_process()` → kill + restart timer |
| Долгий процесс | runtime > 4h | `auto_fix_stuck_process()` → kill + restart timer |
| Устаревшие cookies | age > 24h | `refresh_cookies()` → stop parsers → refresh → start |
| Мало трафика | < 0.1 GB | `stop_parsers()` |
| Прокси для парсинга | > 2 connections | `kill_proxy_using_processes()` |

**Код:** `telegram_bot/bot.py` → `check_and_alert()`

---

## Ограничения

1. **NodeMaven трафик** - платный, экономить
2. **CIAN rate limits** - не более 100 запросов/мин
3. **Cookies** - живут 24 часа, потом блокировка
4. **AntiCaptcha баланс** - следить за остатком

---

## Частые задачи

### Перезапуск парсера

```bash
sudo systemctl restart cian-scraper.timer
```

### Обновление cookies

```bash
cd /home/ubuntu/realestate
source venv/bin/activate
python config/get_cookies_with_proxy.py --force
```

### Проверка логов

```bash
journalctl -u cian-scraper -f
tail -f /home/ubuntu/realestate/logs/cian-scraper.log
```

### Статус системы

```bash
# Или через Telegram: /status
python scripts/health_check.py
```

---

## Ссылки

- [PROJECT-MAP.md](PROJECT-MAP.md) - Карта проекта
- [specifications/](specifications/) - Спецификации фич
- [tasks/](tasks/) - Текущие задачи
- [NodeMaven Dashboard](https://dashboard.nodemaven.com/) - Остаток трафика
