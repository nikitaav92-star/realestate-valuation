# Code Analysis Report

> **Дата:** 2025-01-03
> **Проанализировано:** web/, telegram_bot/, api/, etl/

---

## Критические проблемы (SECURITY)

### Hardcoded Credentials

| Файл | Строка | Проблема |
|------|--------|----------|
| web/api.py | 15 | Password в DSN |
| web/api_map.py | 17 | Password "strongpass123" |
| web/routes/auctions.py | 28 | Password hardcoded |
| web/routes/encumbrances.py | 19 | Password hardcoded |
| web/routes/listings.py | 14 | Password hardcoded |
| telegram_bot/smart_params.py | 17 | Password в DSN |
| telegram_bot/admin_commands.py | 32 | Password в get_db() |

**Рекомендация:** Использовать только `os.environ.get('DATABASE_URL')` без fallback с паролями.

---

## Высокий приоритет

### Missing Error Handling

| Файл | Строка | Проблема |
|------|--------|----------|
| telegram_bot/bot.py | 377 | bare except |
| telegram_bot/admin_commands.py | 169, 194, 206 | bare except |
| telegram_bot/admin_commands.py | 556, 563, 582 | bare except |
| web/api_map.py | 114-117 | Generic exception handler |

**Рекомендация:** Заменить `except:` на `except Exception as e:` с логированием.

---

## Средний приоритет

### Дублирование кода

**get_db() функции (5 копий):**
- web/api.py:13-16
- web/api_map.py:15-18
- web/routes/listings.py:10-19
- web/routes/encumbrances.py:15-24
- web/routes/auctions.py:21-33

**Рекомендация:** Создать `web/utils/db.py` с единой функцией.

**Дублирование логики расчёта цены:**
- web/api.py:72
- web/api_map.py:189
- web/routes/listings.py:84-87

**Дублирование estimate_rooms:**
- telegram_bot/bot.py:64-108
- telegram_bot/smart_params.py:121-207

---

### Resource Leaks

| Файл | Проблема |
|------|----------|
| web/api.py:47-104 | Connection не закрывается при exception |
| web/api_map.py:50-117 | Нет try/finally |
| web/routes/auctions.py:64-163 | Нет cleanup |

**Рекомендация:** Использовать context managers везде.

---

## Низкий приоритет

### Inconsistent Query Placeholders

- PostgreSQL style: `$1, $2` (auctions.py)
- Dict style: `%(name)s` (listings.py)
- Tuple style: `%s` (api.py)

**Рекомендация:** Унифицировать на один стиль.

### Missing Input Validation

- web/routes/auctions.py:61 - limit/offset
- web/api.py:44-45 - int() conversion

---

## Рекомендуемые действия

### Фаза 1 (Критическое)
1. [ ] Убрать все hardcoded credentials
2. [ ] Создать .env.example
3. [ ] Проверить что приложение падает без DATABASE_URL

### Фаза 2 (При рефакторинге)
1. [ ] Создать web/utils/db.py
2. [ ] Заменить bare except
3. [ ] Добавить context managers

### Фаза 3 (Улучшения)
1. [ ] Унифицировать query placeholders
2. [ ] Добавить input validation
3. [ ] Убрать дублирование estimate_rooms

---

**Статус:** Для информации
**Действия:** По желанию владельца
