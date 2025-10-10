# Проект ЦИАН (SCD2): глубокое исследование, риски и 4 пошаговых промта для полного автозапуска через Cursor AI

**Версия:** 08.10.2025 (MSK)  
**Роли:** Руководитель проекта · Системный аналитик · Сеньор разработчик  
**Цель:** Поднять полностью работоспособный проект «с нуля» (git init, Docker, схема БД, код ETL, Prefect-flow, витрины) силами Cursor AI, с максимальной автоматизацией в 4 этапа.

---

## 0) Вывод

1. **Модель данных:** применяем SCD Type 2 для сущности *объявление* (`listings`), историю цен храним в факт-таблице `listing_prices` (PK: `(id, seen_at)`), «мягкое удаление» — флаг `is_active=false` по тем, кто не встретился в свежем прогоне.  
2. **ETL-процесс:** `collect (CIAN API/JSON) → map (модели) → upsert (idempotent) → deactivate (daily) → витрины (DOM, ₽/м², падения ≥5%)`.  
3. **Архитектура:** Docker Compose (PostgreSQL + PostGIS, Metabase, Prefect 3). Код на Python 3.12: `httpx`, `tenacity`, `pydantic`, `psycopg2-binary`, `prefect`, `orjson`, `PyYAML`.  
4. **Запуск:** 4 промта для Cursor AI (см. раздел 5) — от пустой папки до рабочего прогона `daily_flow`.  
5. **Отказоустойчивость:** идемпотентные upsert-ы, `ON CONFLICT`, RPS-лимиты + backoff, отдельная деактивация, бэкапы.  
6. **Готовность к росту:** перенос витрин в ClickHouse при увеличении объёма, PostGIS для гео, интеграции ЕФРСБ/ГИС-Торги далее.

---

## 1) Доказательства / Обоснование решений

- **SCD2** фиксирует жизненный цикл объявления: `first_seen` — первое появление, `last_seen` — последняя встреча, `is_active` — отражает актуальность на текущий день. История цен — отдельный факт: каждое изменение цены — новая строка.  
- **CIAN JSON endpoint** (`/site/v1/offers/search/grouped/`) используется вместо парсинга HTML: это устойчивее к изменению верстки и проще для маппинга.  
- **Idempotent upsert** предотвращает дубли и обеспечивает безопасные повторные прогоны.  
- **Prefect 3** — лёгкая оркестрация без тяжёлой инфраструктуры Airflow: локальный сервер поднимается в контейнере.  
- **Metabase** — быстрый самообслуживаемый BI для DOM/₽/м² и простых витрин.

> Примечание по API/структуре CIAN: структура ответа и путь к массиву офферов в JSON периодически меняются. В код заложены стратегии извлечения с несколькими путями и «мягкой» деградацией. Если структура не подтверждается на момент запуска — в протоколе верификации следует зафиксировать «Не могу подтвердить это» и обновить `extract_offers()`.

---

## 2) Расчёты / Оценки (укрупнённо)

- **Нагрузка (Москва):** активных объявлений до ~100k. При RPS≈2 и пагинации 30–50 страниц/запрос цикл может занять 1–3 часа; допускается шардирование по районам/фильтрам.  
- **Объём БД:** `listings`: ~100k строк; `listing_prices`: при 1–2 изменениях/мес на объект ≈ 200–400k строк/мес. Индексы по `(id, seen_at)` и `id`.  
- **DOM:** `last_seen - first_seen`, агрегируем по сегментам.  
- **₽/м²:** `price/area_total`, медиана по срезам (регион × rooms × deal_type).  
- **Бэкапы:** nightly `pg_dump` в S3/R2, ретенция 30–90 дней.

Формулы и единицы:  
- `DOM_days = date_trunc('day', last_seen) - date_trunc('day', first_seen)`  
- `price_per_sqm = price / area_total` (руб./м², `area_total` > 0)

---

## 3) Риски / Альтернативы

- **Антибот и лимиты:** CAPTCHA/блокировки. Меры: RPS≤2, случайные задержки, `tenacity`-повторы, ротация UA/заголовков.  
- **Смена схемы JSON:** изолированный `mapper.py` + unit-тесты на ключевые поля + многоходовая `extract_offers()`.  
- **Правовые ограничения:** хранить только публичные факты объявлений; соблюдать условия использования площадки.  
- **Стабильность `id`:** контроль коллизий, вторичный аудит-хэш для расследований (не PK).  
- **Часовые зоны:** хранить UTC в БД; отчёты приводить к MSK.  
- **Рост:** возможен перенос витрин в ClickHouse; гео-обогащение через PostGIS; шардирование сборщика.

---

## 4) Чек-лист приёмки (MVP)

- Повторный прогон **не создаёт дублей**, `last_seen` обновляется.  
- История цен пишется **только при изменении**; запрос «падения ≥5%» возвращает корректные кейсы.  
- Суточная **деактивация** помечает `is_active=false` для не встреченных сегодня.  
- Метрики DOM и медианные ₽/м² доступны в Metabase.  
- Бэкап БД nightly выполняется и проверяется восстановление на стенде (еженедельно).

---

## 5) Четыре пошаговых промта для Cursor AI (копируйте по очереди, без изменений)

### ЭТАП 1 — ИНИЦИАЛИЗАЦИЯ РЕПО И DOCKER-ОКРУЖЕНИЯ

> Прогресс 2025-10-09: окружение поднято (`docker compose up -d`, `docker compose ps` — все три сервиса healthy после инициализации).

**Промт 1 (в Cursor AI, Devbox/SSH терминал):**
```
ДЕЙСТВУЙ СТРОГО ПО ШАГАМ. СОЗДАЙ С НУЛЯ СТРУКТУРУ ПРОЕКТА И ПОДНИМИ СЕРВИСЫ.

1) Создай каталоги и init git:
  - Рабочая папка: /opt/realestate
  - Команды:
      cd /opt
      mkdir -p realestate && cd realestate
      git init
      mkdir -p db etl/collector_cian/payloads reports scripts

2) Создай файл docker-compose.yml со следующим содержимым:
  ----8<---- docker-compose.yml ----
  version: "3.8"
  services:
    postgres:
      image: postgis/postgis:16-3.4
      environment:
        POSTGRES_DB: realdb
        POSTGRES_USER: realuser
        POSTGRES_PASSWORD: ${PG_PASS}
      volumes:
        - "./db/data:/var/lib/postgresql/data"
      ports:
        - "5432:5432"

    metabase:
      image: metabase/metabase:latest
      ports:
        - "3000:3000"

    prefect:
      image: prefecthq/prefect:3-latest
      command: prefect server start
      ports:
        - "4200:4200"
  ----8<----

3) Создай .env:
 ----8<---- .env ----
 PG_PASS=strongpass
 PG_DSN=postgresql://realuser:strongpass@localhost:5432/realdb
  PG_DSN_INTERNAL=postgresql://realuser:strongpass@postgres:5432/realdb
  POSTGRES_DB=realdb
  POSTGRES_USER=realuser
  POSTGRES_PASSWORD=strongpass
  PREFECT_API_URL=http://127.0.0.1:4200/api
  PREFECT_SERVER_HOST=0.0.0.0
  CIAN_COOKIES=
  ----8<----

4) Создай схему БД:
  ----8<---- db/schema.sql ----
  CREATE TABLE IF NOT EXISTS listings (
      id BIGINT PRIMARY KEY,
      url TEXT,
      region INT,
      deal_type TEXT,
      rooms INT,
      area_total NUMERIC,
      floor INT,
      address TEXT,
      seller_type TEXT,
      first_seen TIMESTAMPTZ NOT NULL,
      last_seen TIMESTAMPTZ NOT NULL,
      is_active BOOLEAN NOT NULL DEFAULT TRUE
  );
  CREATE TABLE IF NOT EXISTS listing_prices (
      id BIGINT REFERENCES listings(id),
      seen_at TIMESTAMPTZ NOT NULL,
      price NUMERIC NOT NULL,
      PRIMARY KEY (id, seen_at)
  );
  ----8<----

5) Создай db/deactivate.sql:
  ----8<---- db/deactivate.sql ----
  UPDATE listings
  SET is_active = FALSE
  WHERE last_seen::DATE < NOW()::DATE;
  ----8<----

6) Создай .gitignore:
  ----8<---- .gitignore ----
  __pycache__/
  .venv/
  venv/
  .env
  db/data/
  .DS_Store
  ----8<----

7) Подними Docker и применяй схему:
  docker compose up -d
  docker exec -i $(docker ps -qf "name=postgres") psql -U realuser -d realdb < db/schema.sql

8) Сообщи статус контейнеров и успешное применение схемы.
```

## 5.1) Детализированный план реализации для Cursor AI

Ниже — более мелкая декомпозиция проекта: каждый шаг занимает 5–15 минут, имеет осязаемый артефакт и проверку.

| Фаза | Шаг | Что делаем | Команда/действие | Проверка результата |
| --- | --- | --- | --- | --- |
| **F0. Подготовка** | F0.1 | Создаём папку `/opt/realestate`, включаем git | `mkdir -p /opt/realestate && cd /opt/realestate && git init` | `git status` пустой, директория создана |
|  | F0.2 | Фиксируем техническое задание | Скопировать этот README в `docs/blueprint.md` | Файл существует, `git diff` показывает добавление |
|  | F0.3 | Проверяем Docker/Compose | `docker --version`, `docker compose version` | Команды завершаются без ошибок |
| **F1. Инфраструктура** | F1.1 | Создаём базовую структуру каталогов | `mkdir -p db etl/collector_cian/payloads reports scripts` | `ls` отображает созданные директории |
|  | F1.2 | Создаём `docker-compose.yml` | как в промте 1 | `cat docker-compose.yml` совпадает с шаблоном |
|  | F1.3 | Создаём `.env` и `.gitignore` | как в промте 1 | `ls -a` показывает файлы, `cat` подтверждает содержимое |
|  | F1.4 | Пишем `db/schema.sql` и `db/deactivate.sql` | как в промте 1 | `psql -c "\dt"` после применения показывает таблицы |
|  | F1.5 | Поднимаем Compose | `docker compose up -d` | `docker compose ps` все контейнеры `Up` |
|  | F1.6 | Применяем схему | `docker exec ... < db/schema.sql` | `psql -c "SELECT count(*) FROM listings;"` возвращает `0` |
| **F2. Python окружение** | F2.1 | Создаём `requirements.txt` | как в промте 2 | `cat requirements.txt` совпадает |
|  | F2.2 | Разворачиваем venv | `python3 -m venv .venv && source .venv/bin/activate` | `which python` указывает на `.venv` |
|  | F2.3 | Устанавливаем зависимости | `pip install -r requirements.txt` | `pip list` содержит требуемые пакеты |
|  | F2.4 | Создаём `etl/models.py` | как в промте 2 | `python -m compileall etl/models.py` без ошибок |
|  | F2.5 | Создаём `etl/upsert.py` | как в промте 2 | `python -m compileall etl/upsert.py` без ошибок |
|  | F2.6 | Выполняем тестовую вставку | сценарий из промта 2 | В stdout «OK», в БД `count(*)=1` |
| **F3. Сбор данных** | F3.1 | Настраиваем базовый payload | создать `base.yaml` | `yamllint` (при наличии) проходит |
|  | F3.2 | Реализуем `fetcher.py` | как в промте 3 | `python -m compileall etl/collector_cian/fetcher.py` |
|  | F3.3 | Реализуем `mapper.py` | как в промте 3 | Временный тест `python -m compileall etl/collector_cian/mapper.py` |
|  | F3.4 | Реализуем `cli.py` | как в промте 3 | `python etl/collector_cian/cli.py --help` выводит команды |
|  | F3.5 | Делаем пробный `pull` | команда из промта 3 | stderr содержит `pulled_offers>0` или фиксируем «Не могу подтвердить это» + JSON |
|  | F3.6 | Прогоняем `pull → to-db` | конвейер из промта 3 | `listing_prices` увеличился, без дублей |
| **F4. Оркестрация** | F4.1 | Создаём `etl/flows.py` | как в промте 4 | `python -m compileall etl/flows.py` |
|  | F4.2 | Пишем SQL-репорты | `reports/queries.sql` | `psql -f reports/queries.sql` без ошибок |
|  | F4.3 | Запускаем `daily_flow` | скрипт из промта 4 | Prefect лог без исключений |
|  | F4.4 | Проверяем деактивацию | `SELECT id FROM listings WHERE is_active=false;` | Список соответствует ожиданию |
| **F5. Витрины/фронтенд** | F5.1 | Настраиваем Metabase | зайти на `http://localhost:3000` | Создано подключение к Postgres |
|  | F5.2 | Создаём карточки DOM/₽/падения | Через UI Metabase | Скриншоты карточек сохранены |
|  | F5.3 | Поднимаем внешний API (если нужно) | следовать разделу 11 | Endpoint `/api/listings/summary` возвращает JSON |
|  | F5.4 | Разворачиваем фронтенд на своём хостинге | Next.js/SSG по разделу 11 | Публичная страница доступна, lighthouse ≥80 |
| **F6. Контроль качества** | F6.1 | Прогоняем чек-лист из раздела 6 | ручной контроль | Все пункты отмечены |
|  | F6.2 | Ведём журнал багов | `docs/qa-log.md` + issues в git | У каждой записи есть дата, статус, ссылка на PR |
|  | F6.3 | Настраиваем автоматический бэкап | `scripts/backup.sh` + cron | В `db/backup_*.dump` появляется файл |

### Процесс фикса багов и контроль ошибок

1. **Детектор:** после каждого шага фиксируем `stdout`/`stderr` и SQL-снимки (`SELECT * FROM listings LIMIT 5`). Ошибка → сразу логируем в `docs/qa-log.md`.
2. **Реакция:** создаём git-ветку `fix/<issue>` и выполняем минимальный фикс; добавляем тест или SQL-проверку, которая ловит регрессию.
3. **Проверка:** повторяем только те шаги, которые затронуты фиксом, плюс smoke-тест `python etl/collector_cian/cli.py --help` и `psql -c "SELECT COUNT(*) FROM listings;"`.
4. **Документация:** обновляем разделы README/blueprint, если поведение изменилось (например, новый столбец или флаг).
5. **Автоматизация контроля:** по мере готовности добавляем `make lint`, `make test`, интегрируем в CI Cursor/Devbox (опционально GitHub Actions).

> Советы: держите размер шага маленьким — один логический файл или таблица. Каждый завершённый шаг фиксируйте отдельным коммитом, чтобы упростить откат и ревью.

---

### ЭТАП 2 — ЗАВИСИМОСТИ, БАЗОВЫЕ МОДЕЛИ И UPSERT-Ы

> Прогресс 2025-10-09: `db/schema.sql` расширён индексами и применён (`docker compose exec postgres psql -U realuser -d realdb < db/schema.sql`), `\dt` и `\di` подтверждают структуру; `etl/collector_cian/*` и `etl/upsert.py` переписаны, тесты `pytest` проходят целиком.

**Промт 2 (в Cursor AI):**
```
УСТАНОВИ ЗАВИСИМОСТИ, СОЗДАЙ Pydantic МОДЕЛИ, ФУНКЦИИ РАБОТЫ С БД И ТЕСТОВЫЙ ПРОГОН.

1) Создай requirements.txt:
  ----8<---- requirements.txt ----
  httpx
  tenacity
  pydantic
  psycopg2-binary
  prefect
  orjson
  PyYAML
  python-dotenv
  ----8<----

2) Создай и активируй виртуальное окружение, установи зависимости:
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt

3) Создай etl/models.py:
  ----8<---- etl/models.py ----
  from pydantic import BaseModel

  class Listing(BaseModel):
      id: int
      url: str = ""
      region: int = 0
      deal_type: str = ""
      rooms: int = 0
      area_total: float = 0.0
      floor: int = 0
      address: str = ""
      seller_type: str = ""

  class PricePoint(BaseModel):
      id: int
      price: float
  ----8<----

4) Создай etl/upsert.py (убедиcь, что импортируешь Listing):
  ----8<---- etl/upsert.py ----
  import os
  import psycopg2
  from etl.models import Listing

  def get_db_connection():
      dsn = os.getenv("PG_DSN")
      if not dsn:
          raise RuntimeError("PG_DSN is not set")
      return psycopg2.connect(dsn)

  def upsert_listing(conn, listing: Listing):
      with conn.cursor() as cur:
          cur.execute(
              """
              INSERT INTO listings (id, url, region, deal_type, rooms, area_total, floor, address, seller_type, first_seen, last_seen, is_active)
              VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), TRUE)
              ON CONFLICT (id) DO UPDATE SET
                url=EXCLUDED.url,
                region=EXCLUDED.region,
                deal_type=EXCLUDED.deal_type,
                rooms=EXCLUDED.rooms,
                area_total=EXCLUDED.area_total,
                floor=EXCLUDED.floor,
                address=EXCLUDED.address,
                seller_type=EXCLUDED.seller_type,
                last_seen=NOW(),
                is_active=TRUE;
              """,
              (listing.id, listing.url, listing.region, listing.deal_type, listing.rooms,
               listing.area_total, listing.floor, listing.address, listing.seller_type)
          )
          conn.commit()

  def upsert_price_if_changed(conn, listing_id: int, new_price: float):
      with conn.cursor() as cur:
          cur.execute(
              "SELECT price FROM listing_prices WHERE id = %s ORDER BY seen_at DESC LIMIT 1;",
              (listing_id,)
          )
          row = cur.fetchone()
          if row is None or row[0] != new_price:
              cur.execute(
                  "INSERT INTO listing_prices (id, seen_at, price) VALUES (%s, NOW(), %s);",
                  (listing_id, new_price)
              )
          conn.commit()
  ----8<----

5) Выполни тестовую вставку (проверка соединения и прав):
  python - <<'PY'
  import os
  from etl.upsert import get_db_connection, upsert_listing, upsert_price_if_changed
  from etl.models import Listing
  os.environ.setdefault("PG_DSN", "postgresql://realuser:strongpass@localhost:5432/realdb")
  conn = get_db_connection()
  upsert_listing(conn, Listing(id=1, url="https://example", region=77, deal_type="sale", rooms=2, area_total=45.0, floor=5, address="Москва", seller_type="owner"))
  upsert_price_if_changed(conn, 1, 10000000)
  print("OK")
  PY

6) Сообщи результат и содержимое таблиц (COUNT(*)) для listings и listing_prices.
```

---

### ЭТАП 3 — СБОР ДАННЫХ (CIAN), MAPPER И CLI

> Прогресс 2025-10-09: реализован HTTP-клиент + fallback на Playwright; при блокировке `/site/v1/offers/search/grouped/` скрипт автоматически запускает Chromium (см. `CIAN_HEADLESS`, `CIAN_SLOW_MO`). Payload формируется через `jsonQuery` в YAML.

**Промт 3 (в Cursor AI):**
```
СФОРМИРУЙ СБОРЩИК ДАННЫХ И КОНСОЛЬНЫЕ КОМАНДЫ PULL/TO-DB. НЕ ИСПОЛЬЗУЙ HTML-ПАРСИНГ. ТОЛЬКО JSON ЭНДПОИНТ.

1) Создай etl/collector_cian/payloads/base.yaml:
  ----8<---- etl/collector_cian/payloads/base.yaml ----
  jsonQuery:
    region:
      type: terms
      value: [1]        # 1 — Москва
    engine_version:
      type: term
      value: 2
    deal_type:
      type: term
      value: sale
    offer_type:
      type: term
      value: flat
    price:
      type: range
      value:
        gte: 1000000
        lte: 10000000
    area:
      type: range
      value:
        gte: 10
        lte: 200
    room:
      type: terms
      value: [1, 2, 3]
 limit: 20
 sort:
   type: term
   value: creation_date_desc
 ----8<----
  > Перед запуском `pull`/`daily_flow` откройте cian.ru в браузере, пройдите капчу, возьмите значение заголовка `Cookie` из DevTools и внесите его в `CIAN_COOKIES=` в `.env`.

2) Создай etl/collector_cian/fetcher.py (async httpx + tenacity, RPS<=2):
  ----8<---- etl/collector_cian/fetcher.py ----
  # см. актуальную версию в репозитории: используется эндпоинт
  # https://www.cian.ru/cms/api/search/v1/search-offers/, заголовки и cookies
  # читаются из окружения (CIAN_COOKIES), добавлены ретраи и throttle.
  ----8<----

3) Создай etl/collector_cian/mapper.py (извлечение офферов из разных возможных путей + преобразование в Listing/PricePoint):
  ----8<---- etl/collector_cian/mapper.py ----
  from typing import Iterable, List, Dict, Any
  from etl.models import Listing, PricePoint

  def extract_offers(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
      # Пытаемся найти массив офферов по нескольким известным путям.
      # Если не нашли — возвращаем пустой список.
      candidates = []
      # Известные варианты путей (могут меняться):
      paths = [
          ("data", "offersSerialized"),
          ("offersSerialized",),
          ("data", "offers"),
          ("result", "offers"),
      ]
      for path in paths:
          cur = resp
          ok = True
          for key in path:
              if isinstance(cur, dict) and key in cur:
                  cur = cur[key]
              else:
                  ok = False
                  break
          if ok and isinstance(cur, list):
              candidates = cur
              break
      return candidates if isinstance(candidates, list) else []

  def to_listing(o: Dict[str, Any]) -> Listing:
      return Listing(
          id=int(o.get("offerId") or o.get("id")),
          url=str(o.get("seoUrl") or o.get("url") or ""),
          region=int(o.get("region") or 0),
          deal_type=str(o.get("operationName") or o.get("dealType") or ""),
          rooms=int(o.get("roomsCount") or o.get("rooms") or 0),
          area_total=float(o.get("spaceTotal") or o.get("areaTotal") or 0.0),
          floor=int(o.get("floor") or 0),
          address=str(o.get("address") or ""),
          seller_type=str(o.get("sellerName") or o.get("sellerType") or "")
      )

  def to_price(o: Dict[str, Any]) -> PricePoint:
      price = o.get("price")
      if isinstance(price, dict):
          price = price.get("value") or price.get("rub") or price.get("amount")
      return PricePoint(
          id=int(o.get("offerId") or o.get("id")),
          price=float(price or 0.0)
      )
  ----8<----

4) Создай etl/collector_cian/cli.py (команды: pull → JSONL в stdout, to-db → читает JSONL из stdin):
  ----8<---- etl/collector_cian/cli.py ----
  import argparse, sys, json, asyncio, yaml, orjson
  from pathlib import Path
  from etl.collector_cian.fetcher import collect
  from etl.collector_cian.mapper import extract_offers, to_listing, to_price
  from etl.upsert import get_db_connection, upsert_listing, upsert_price_if_changed

  def command_pull(payload_path: str, pages: int):
      payload = yaml.safe_load(Path(payload_path).read_text())
      data = asyncio.run(collect(payload, pages))
      # Выводим JSONL: по одному офферу на строку (уже «сырые» поля)
      count = 0
      for resp in data:
          offers = extract_offers(resp)
          for o in offers:
              sys.stdout.write(orjson.dumps(o).decode() + "\n")
              count += 1
      sys.stderr.write(f"pulled_offers={count}\n")

  def command_to_db():
      conn = get_db_connection()
      count_l, count_p = 0, 0
      for line in sys.stdin:
          if not line.strip():
              continue
          o = json.loads(line)
          l = to_listing(o)
          p = to_price(o)
          upsert_listing(conn, l)
          upsert_price_if_changed(conn, l.id, p.price)
          count_l += 1
          count_p += 1
      sys.stderr.write(f"upserted_listings={count_l} upserted_prices={count_p}\n")

  def main():
      ap = argparse.ArgumentParser()
      sp = ap.add_subparsers(dest="cmd")
      p1 = sp.add_parser("pull")
      p1.add_argument("--payload", default="etl/collector_cian/payloads/base.yaml")
      p1.add_argument("--pages", type=int, default=1)
      sp.add_parser("to-db")
      args = ap.parse_args()
      if args.cmd == "pull":
          command_pull(args.payload, args.pages)
      elif args.cmd == "to-db":
          command_to_db()
      else:
          ap.print_help()

  if __name__ == "__main__":
      main()
  ----8<----

5) Выполни связку pull → to-db на 1–2 страницах:
  python etl/collector_cian/cli.py pull --payload etl/collector_cian/payloads/base.yaml --pages 1 | \
  python etl/collector_cian/cli.py to-db

6) Выведи COUNT(*) в listings и listing_prices. Если структура JSON у CIAN изменилась и офферы не извлекаются — зафиксируй «Не могу подтвердить это», покажи пример ответа и скорректируй extract_offers().
```

---

### ЭТАП 4 — PREFECT FLOW, ДЕАКТИВАЦИЯ, ВИТРИНЫ И ЗАПУСК

> Прогресс 2025-10-09: добавлен `etl/flows.py` с flow `daily_flow`, создан `reports/queries.sql`; локальный запуск `PREFECT_API_URL= python - <<'PY' ... daily_flow(pages=0)` завершился успешно (0 офферов, 0 деактиваций); Prefect и Metabase в Docker теперь проходят healthcheck, Metabase хранит метаданные в Postgres.

**Промт 4 (в Cursor AI):**
```
СОЗДАЙ FLOW В PREFECT, ДОБАВЬ SQL-ВИТРИНЫ И СДЕЛАЙ ТЕСТОВЫЙ ЕЖЕДНЕВНЫЙ ПРОГОН.

1) Создай etl/flows.py:
  ----8<---- etl/flows.py ----
  from prefect import flow, task
  import subprocess, json, os, sys
  from etl.upsert import get_db_connection, upsert_listing, upsert_price_if_changed
  from etl.models import Listing, PricePoint

  @task
  def collect_task(payload: str, pages: int) -> list[str]:
      cmd = [
          sys.executable, "etl/collector_cian/cli.py", "pull",
          "--payload", payload, "--pages", str(pages)
      ]
      proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
      out, err = proc.communicate()
      if proc.returncode != 0:
          raise RuntimeError(f"pull failed: {err}")
      return [ln for ln in out.splitlines() if ln.strip()]

  @task
  def to_db_task(lines: list[str]):
      conn = get_db_connection()
      for ln in lines:
          o = json.loads(ln)
          l = Listing.parse_obj({
              "id": int(o.get("offerId") or o.get("id")),
              "url": o.get("seoUrl") or o.get("url") or "",
              "region": int(o.get("region") or 0),
              "deal_type": o.get("operationName") or o.get("dealType") or "",
              "rooms": int(o.get("roomsCount") or o.get("rooms") or 0),
              "area_total": float(o.get("spaceTotal") or o.get("areaTotal") or 0.0),
              "floor": int(o.get("floor") or 0),
              "address": o.get("address") or "",
              "seller_type": o.get("sellerName") or o.get("sellerType") or ""
          })
          price = o.get("price")
          if isinstance(price, dict):
              price = price.get("value") or price.get("rub") or price.get("amount")
          p = PricePoint(id=l.id, price=float(price or 0.0))
          upsert_listing(conn, l)
          upsert_price_if_changed(conn, l.id, p.price)

  @task
  def deactivate_task():
      conn = get_db_connection()
      with conn.cursor() as cur:
          cur.execute(open("db/deactivate.sql").read())
          conn.commit()

  @flow
  def daily_flow(payload: str = "etl/collector_cian/payloads/base.yaml", pages: int = 2):
      lines = collect_task(payload, pages)
      to_db_task(lines)
      deactivate_task()
  ----8<----

2) Создай reports/queries.sql:
  ----8<---- reports/queries.sql ----
  -- Медиана ₽/м² по региону × комнатности × типу сделки
  SELECT region, rooms, deal_type,
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price/NULLIF(area_total,0)) AS median_price_per_sqm
  FROM listings l
  JOIN listing_prices p ON l.id = p.id
  GROUP BY region, rooms, deal_type;

  -- DOM: время с появления до "деактивации"
  SELECT id, (DATE_TRUNC('day', last_seen) - DATE_TRUNC('day', first_seen)) AS dom_days
  FROM listings
  WHERE is_active = FALSE;

  -- Падения цен ≥5%
  WITH seq AS (
    SELECT id, seen_at, price,
           LAG(price) OVER (PARTITION BY id ORDER BY seen_at) AS prev_price
    FROM listing_prices
  )
  SELECT id, seen_at, price
  FROM seq
  WHERE prev_price IS NOT NULL AND price <= 0.95 * prev_price;
  ----8<----

3) Запусти flow локально (без регистрации деплоймента):
  python - <<'PY'
  from etl.flows import daily_flow
  daily_flow()
  PY

4) Проверь, что:
  - В listings обновились last_seen и is_active=true для встреченных.
  - В listing_prices появилась запись, только если цена изменилась.
  - Скрипт db/deactivate.sql помечает отсутствующих как is_active=false (сравни last_seen::date).

5) Подключи Metabase к Postgres (порт 3000) и создай карточки:
  - Медиана ₽/м²
  - DOM
  - Падения ≥5%

6) Сообщи итоговые COUNT(*) и примеры строк из каждой таблицы (LIMIT 5).
```

---

## 6) Контроль качества и верификация (двухпроходная)

**Проход 1 (функциональность):**
- [ ] `pull → to-db` отрабатывает без ошибок.
- [ ] Повторный прогон **не создаёт дублей**, а продлевает `last_seen`.
- [ ] История цен добавляется **только при изменении**.

**Проход 2 (данные/отчёты):**
- [ ] Запрос «падения ≥5%» возвращает кейсы с корректными значениями.
- [ ] DOM рассчитывается без `NULL` из-за `area_total=0` (проверить входные).
- [ ] В Metabase карточки возвращают значения и фильтруются по сегментам.

**Протокол верификации:** входные → шаги → ожидаемый результат → фактический результат → решение.  
При несоответствиях фиксируем «Не могу подтвердить это» + ссылку на участок кода/ответ API и план фикса.

---

## 7) Мониторинг и бэкапы

- Логи ETL в stdout (JSON или текст) с метриками: `pulled_offers`, `upserted_listings`, `upserted_prices`, duration.  
- Nightly `pg_dump` в S3/R2, ретенция 30–90 дней. Скрипт:
  ```
  # scripts/backup.sh
  #!/usr/bin/env bash
  set -euo pipefail
  export PGPASSWORD="${PG_PASS:-strongpass}"
  ts="$(date +%Y%m%d_%H%M%S)"
  pg_dump -h 127.0.0.1 -U realuser -d realdb -F c -f "db/backup_${ts}.dump"
  ```
  Регулярный запуск через crontab/systemd-timer на хосте.

---

## 8) Известные слабые места и упущения (для последующей доработки)

1. **Точный формат ответа CIAN**: может отличаться от предположенного; `extract_offers()` покрывает несколько путей, но требуется быстрая коррекция при изменениях. *Статус:* «Не могу подтвердить это» до первого прогона.  
2. **Антибот-защита**: при росте объёма может потребоваться прокси-ротация, обновление заголовков, headless-обход.  
3. **Нормализация адресов/гео**: текущая версия не делает геокодирование и нормализацию адресов для районов → это нужно для корректных витрин по гео.  
4. **Единицы и валюта**: если CIAN вернёт цену в иной валюте/структуре, нужна нормализация (валюта → RUB).  
5. **Планировщик**: Prefect запускается вручную; продакшн-режим потребует деплоймента/агента либо cron-обвязки.  
6. **Гранулярные индексы**: при росте `listing_prices` добавить индекс по `(id, seen_at DESC)` и матвью для последних цен.  
7. **Юридический аспект**: требуется ревизия условий использования CIAN, чтобы исключить нарушения.  
8. **Качество данных**: контроль пустых `area_total`, некорректных `rooms`, `price=0`. Добавить валидаторы и отчёты о пропусках.  
9. **Метрики и алерты**: отсутствуют телеграм-нотификации о падениях/ошибках → добавить позже.

---

## 9) Полезные команды

```
# Поднять сервисы
docker compose up -d

# Применить схему
docker exec -i $(docker ps -qf "name=postgres") psql -U realuser -d realdb < db/schema.sql

# Виртуальное окружение и зависимости
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Тестовый пробег: pull → to-db
python etl/collector_cian/cli.py pull --payload etl/collector_cian/payloads/base.yaml --pages 1 | python etl/collector_cian/cli.py to-db

# Запуск Prefect flow
python -c "from etl.flows import daily_flow; daily_flow()"

# REST API (локально)
curl http://localhost:8080/metrics/median-price
```

---

## 10) Критерии готовности к демо

- [ ] Есть повторяемый запуск ETL с нуля (4 промта выполнены).
- [ ] Таблицы заполнены и запросы из `reports/queries.sql` возвращают результаты.
- [ ] Отчёты Metabase работают, есть 3 карточки: Медиана ₽/м², DOM, Падения ≥5%.
- [ ] Заведён скрипт бэкапа и проверено восстановление на стенде.

---

## 11) Дополнение: внешняя фронтенд-визуализация на собственном хостинге

> Цель: вынести пользовательские дашборды за пределы инфраструктуры Cursor/Devbox и опубликовать их на отдельном хостинге (VPS, bare metal, облако). Ниже — референсный план, который можно адаптировать под конкретный стек (Next.js/React, SvelteKit, Vue, Superset и т.д.).

### 11.1 Архитектурные варианты

1. **Public API + SPA (рекомендуемый базовый вариант)**
   - Добавляем к стэку лёгкий read-only API (FastAPI/Flask) поверх Postgres.
   - Front-end (Next.js/React) деплоится на отдельный хост (Docker/PM2/Vercel) и забирает данные через API.
   - Авторизация — токен по заголовку или OAuth2 через Reverse Proxy.

2. **Статическая публикация агрегатов**
   - Prefect flow генерирует JSON/CSV отчёты в `reports/public/` и складывает их в S3/R2.
   - На фронтенде (Nuxt/Next) они подхватываются как статические данные (ISR/SSG).
   - Подходит для витрин, которые обновляются раз в сутки.

3. **Metabase as-a-Service (альтернатива)**
   - Разворачиваем отдельный Metabase (или Superset) за reverse proxy с SSO.
   - Используем public/embedded dashboards для публикации на сайте.
   - Не требует кастомного фронтенда, но ограничивает UX и брендинг.

### 11.2 Минимальный API-слой (пример FastAPI)

> Статус: `api/main.py`, `api/Dockerfile` и сервис `api` в `docker-compose.yml` уже добавлены, `/metrics/median-price` отдаёт агрегаты (проверено локально через `curl http://localhost:8080/metrics/median-price`).

1. Создаём `api/requirements.txt`:
   ```txt
   fastapi
   uvicorn[standard]
   psycopg2-binary
   python-dotenv
   ```
2. Добавляем `api/main.py`:
   ```python
   from fastapi import FastAPI
   import os, psycopg2

   app = FastAPI()

   def get_conn():
       return psycopg2.connect(os.environ["PG_DSN"])

   @app.get("/metrics/median-price")
   def median_price():
       with get_conn() as conn, conn.cursor() as cur:
           cur.execute(
               """
               SELECT region, rooms, deal_type,
                      PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price/NULLIF(area_total,0)) AS median_price_per_sqm
               FROM listings l
               JOIN listing_prices p ON l.id = p.id
               GROUP BY region, rooms, deal_type
               """
           )
           columns = [c[0] for c in cur.description]
           return [dict(zip(columns, row)) for row in cur.fetchall()]
   ```
3. Обновляем `docker-compose.yml`, добавляя сервис `api`:
   ```yaml
   api:
     build: ./api
     environment:
       - PG_DSN=${PG_DSN}
     ports:
       - "8080:8080"
   ```
4. Dockerfile для API:
   ```dockerfile
   FROM python:3.12-slim
   WORKDIR /app
   COPY api/requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY api .
   CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
   ```

### 11.3 Front-end (пример Next.js на отдельном VPS)

1. Инициализируем проект:
   ```bash
   npx create-next-app@latest cian-analytics-frontend
   cd cian-analytics-frontend
   npm install @tanstack/react-query recharts axios
   ```
2. Создаём клиент для API (`lib/api.ts`):
   ```ts
   import axios from "axios";

   export const api = axios.create({
     baseURL: process.env.NEXT_PUBLIC_API_URL,
     timeout: 10_000,
   });
   ```
3. Страница с графиками (`app/page.tsx`):
   ```tsx
   import { useQuery } from "@tanstack/react-query";
   import { api } from "@/lib/api";

   export default function Dashboard() {
     const { data, isLoading } = useQuery({
       queryKey: ["median"],
       queryFn: async () => (await api.get("/metrics/median-price")).data,
     });

     if (isLoading) return <p>Загрузка…</p>;

     return (
       <main className="mx-auto max-w-5xl p-8">
         <h1 className="text-2xl font-semibold">Медиана ₽/м²</h1>
         {/* Пример: вывод таблицы/графика */}
         <table>
           <thead>
             <tr>
               <th>Регион</th>
               <th>Комнат</th>
               <th>Тип сделки</th>
               <th>Медиана ₽/м²</th>
             </tr>
           </thead>
           <tbody>
             {data.map((row: any) => (
               <tr key={`${row.region}-${row.rooms}-${row.deal_type}`}>
                 <td>{row.region}</td>
                 <td>{row.rooms}</td>
                 <td>{row.deal_type}</td>
                 <td>{Math.round(row.median_price_per_sqm).toLocaleString("ru-RU")}</td>
               </tr>
             ))}
           </tbody>
         </table>
       </main>
     );
   }
   ```
4. Секреты (API URL, токен) храним в `.env.production` на фронтенд-хосте.
5. Деплой:
   ```bash
   npm run build
   npm run start
   ```
   либо через Docker (`node:20-alpine`) и reverse proxy (Nginx/Caddy/Traefik) с HTTPS.

### 11.4 Безопасность и эксплуатация

- Read-only роль в Postgres для API (`GRANT SELECT ON ...`).
- Ограничение доступа к API по IP/токену, rate limiting (Traefik, Nginx, Cloudflare).
- Логи API и фронтенда отправляем в централизованный сборщик (Loki/ELK).
- CI/CD: GitHub Actions → docker build → деплой на VPS (SSH/rsync) или регистр (GHCR/Harbor).
- Мониторинг доступности (Uptime Kuma, Better Stack) и budget alerts на трафик.

### 11.5 Интеграция с текущим планом

1. **Prefect flow** дополняем шагом `export_public_metrics`, который агрегирует данные и складывает их в таблицы/JSON.
2. **Docker Compose**: `postgres`, `prefect`, `metabase`, `api`. Фронтенд выносим в отдельный деплой (может быть в том же Compose, но рекомендуется отдельный хост для DMZ).
3. **Документация**: добавляем инструкции по обновлению API/фронтенда, схему сети и список доменов/сертификатов.
4. **Инфраструктура**: резервный канал (Cloudflare Tunnel/Reverse Proxy) и бэкапы статики (S3).

Результат: ETL остаётся в исходном виде, а внешние пользователи получают доступ к витринам через брендированный веб-интерфейс с контролируемым API-слоем.

---

### Примечание о совместимости с Cursor

- Промты рассчитаны на использование **Cursor Devbox/SSH**.  
- Все пути абсолютные/относительные заданы для каталога `/opt/realestate`.  
- При необходимости запускать команды в *встроенном терминале Cursor* без изменения текста промтов.

---

**Конец файла.**
