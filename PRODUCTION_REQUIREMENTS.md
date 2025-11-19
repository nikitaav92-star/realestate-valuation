# 🚀 Требования для Production Deployment

**Дата:** 2025-11-19  
**Проект:** Real Estate Data Platform  
**Статус:** ✅ Готово к развертыванию

---

## 📋 Содержание

1. [Системные требования](#системные-требования)
2. [Инфраструктура](#инфраструктура)
3. [Переменные окружения](#переменные-окружения)
4. [Зависимости](#зависимости)
5. [База данных](#база-данных)
6. [Веб-сервисы](#веб-сервисы)
7. [Безопасность](#безопасность)
8. [Мониторинг](#мониторинг)
9. [Пошаговая инструкция](#пошаговая-инструкция)

---

## 🖥️ Системные требования

### Минимальные требования

| Компонент | Минимум | Рекомендуется |
|-----------|---------|---------------|
| **CPU** | 2 ядра | 4+ ядра |
| **RAM** | 4 GB | 8+ GB |
| **Диск** | 50 GB SSD | 100+ GB SSD |
| **ОС** | Ubuntu 22.04+ | Ubuntu 22.04 LTS |
| **Python** | 3.11+ | 3.12+ |
| **Docker** | 20.10+ | Latest |
| **Docker Compose** | 2.0+ | Latest |

### Сетевое подключение

- **Входящий трафик:** Порты 80, 443, 5432 (опционально для внешнего доступа к БД)
- **Исходящий трафик:** Неограниченный (для сбора данных)
- **DNS:** Настроенная A-запись для домена (опционально)

---

## 🏗️ Инфраструктура

### Обязательные компоненты

1. **PostgreSQL 14+** (с PostGIS расширением)
   - Контейнер: `postgis/postgis:16-3.4`
   - Порт: `5432`
   - Данные: Volume mount для персистентности

2. **Docker & Docker Compose**
   - Для оркестрации контейнеров
   - Автоматический перезапуск сервисов

3. **Python 3.11+**
   - Виртуальное окружение (`venv`)
   - Все зависимости из `requirements.txt`

### Опциональные компоненты

4. **Metabase** (для аналитики)
   - Контейнер: `metabase/metabase:latest`
   - Порт: `3000`
   - Требует подключения к PostgreSQL

5. **Prefect** (для оркестрации задач)
   - Контейнер: `prefecthq/prefect:3-latest`
   - Порт: `4200`
   - Для автоматизации ETL процессов

6. **Nginx** (reverse proxy)
   - Для HTTPS и маршрутизации
   - SSL сертификаты (Let's Encrypt)

7. **Cloudflare Tunnel** (альтернатива Nginx)
   - Для безопасного доступа без открытых портов
   - Автоматический HTTPS

---

## 🔐 Переменные окружения

### Обязательные переменные

Создайте файл `.env` в корне проекта:

```bash
# PostgreSQL
POSTGRES_DB=realdb
POSTGRES_USER=realuser
POSTGRES_PASSWORD=<strong_password>  # ⚠️ Измените на безопасный пароль!
PG_DSN=postgresql://realuser:<password>@localhost:5432/realdb
PG_DSN_INTERNAL=postgresql://realuser:<password>@postgres:5432/realdb

# Компоненты PostgreSQL (для совместимости)
PG_HOST=localhost
PG_PORT=5432
PG_USER=realuser
PG_PASS=<password>
PG_DB=realdb
```

### Опциональные переменные (для расширенной функциональности)

```bash
# Anti-Captcha (для обхода капчи)
ANTICAPTCHA_KEY=<your_anticaptcha_key>

# Прокси сервисы (для обхода блокировок)
NODEMAVEN_PROXY_URL=http://username:password@gate.nodemaven.com:8080
BRIGHTDATA_PROXY_URL=http://username:password@brd.superproxy.io:33335
SMARTPROXY_URL=http://username:password@gate.smartproxy.com:10000

# DaData API (для нормализации адресов)
DADATA_API_KEY=<your_dadata_key>
DADATA_SECRET_KEY=<your_dadata_secret>

# Prefect (для оркестрации)
PREFECT_SERVER_HOST=0.0.0.0

# Cloudflare (для туннеля)
CLOUDFLARE_API_TOKEN=<your_token>

# Flask (если используется)
SECRET_KEY=<random_secret_key>
```

### Генерация безопасных паролей

```bash
# Генерация пароля для PostgreSQL
openssl rand -base64 32

# Генерация SECRET_KEY для Flask
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 📦 Зависимости

### Python зависимости

```bash
# Установка зависимостей
cd /home/ubuntu/realestate
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Playwright браузеры (для ETL)
playwright install chromium
```

**Основные зависимости:**
- `httpx` - HTTP клиент
- `tenacity` - Retry логика
- `pydantic` - Валидация данных
- `psycopg2-binary` - PostgreSQL драйвер
- `prefect` - Оркестрация задач
- `orjson` - Быстрый JSON
- `PyYAML` - YAML парсинг
- `python-dotenv` - Переменные окружения
- `playwright` - Браузерная автоматизация
- `anticaptchaofficial` - Решение капчи
- `fastapi` - API фреймворк (для веб-интерфейсов)
- `uvicorn` - ASGI сервер

### Системные зависимости

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y \
    python3-pip \
    python3-venv \
    docker.io \
    docker-compose \
    nginx \
    certbot \
    python3-certbot-nginx \
    postgresql-client

# Запуск Docker
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER  # Перелогиниться после этого
```

---

## 🗄️ База данных

### Инициализация PostgreSQL

```bash
# Запуск контейнера
cd /home/ubuntu/realestate
docker compose up -d postgres

# Ожидание готовности
sleep 10

# Применение схемы
PGPASSWORD=<password> psql -h localhost -U realuser -d realdb -f db/schema.sql

# Проверка
PGPASSWORD=<password> psql -h localhost -U realuser -d realdb -c "\dt"
```

### Резервное копирование

```bash
# Создание бэкапа
docker exec realestate-postgres-1 pg_dump -U realuser realdb > backup_$(date +%Y%m%d).sql

# Восстановление
cat backup_20251119.sql | docker exec -i realestate-postgres-1 psql -U realuser realdb
```

### Мониторинг БД

```bash
# Подключение к БД
docker exec -it realestate-postgres-1 psql -U realuser realdb

# Полезные запросы
SELECT COUNT(*) FROM listings;
SELECT COUNT(*) FROM listing_prices;
SELECT AVG(price)::bigint FROM listing_prices;
```

---

## 🌐 Веб-сервисы

### Вариант 1: FastAPI веб-интерфейс (рекомендуется)

```bash
cd /home/ubuntu/realestate
source venv/bin/activate

# Запуск web_viewer.py
python web_viewer.py
# Доступ: http://localhost:8000

# Или web_simple.py
python web_simple.py
# Доступ: http://localhost:8000
```

**Запуск через systemd:**

Создайте `/etc/systemd/system/realestate-web.service`:

```ini
[Unit]
Description=Real Estate Web Viewer
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/realestate
Environment="PATH=/home/ubuntu/realestate/venv/bin"
ExecStart=/home/ubuntu/realestate/venv/bin/python /home/ubuntu/realestate/web_viewer.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable realestate-web
sudo systemctl start realestate-web
```

### Вариант 2: API сервис

```bash
cd /home/ubuntu/realestate/api
docker build -t realestate-api .
docker run -d \
    --name realestate-api \
    --env-file ../.env \
    -p 8080:8080 \
    realestate-api
```

**Endpoints:**
- `GET /health` - Health check
- `GET /metrics/median-price` - Медианные цены
- `GET /metrics/dom` - Days on Market
- `GET /metrics/price-drops` - Падения цен

### Вариант 3: Metabase (аналитика)

```bash
# Запуск через docker-compose
cd /home/ubuntu/realestate
docker compose up -d metabase

# Доступ: http://localhost:3000
# Первый запуск: настройка администратора
```

### Вариант 4: Nginx + HTTPS

```bash
# Установка Nginx
sudo apt install -y nginx certbot python3-certbot-nginx

# Копирование конфигурации
sudo cp infra/nginx/conf.d/realestate.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/realestate.conf /etc/nginx/sites-enabled/

# Получение SSL сертификата
sudo certbot --nginx -d your-domain.com

# Перезапуск
sudo systemctl reload nginx
```

### Вариант 5: Cloudflare Tunnel (без открытых портов)

```bash
# Установка cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Настройка туннеля
cd infra/cloudflare
./setup-tunnel.sh

# Или вручную
cloudflared tunnel login
cloudflared tunnel create realestate
cloudflared tunnel route dns realestate your-domain.com
sudo cloudflared service install
```

---

## 🔒 Безопасность

### Обязательные меры безопасности

1. **Сильные пароли**
   ```bash
   # Используйте сложные пароли для всех сервисов
   openssl rand -base64 32
   ```

2. **Firewall (UFW)**
   ```bash
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   sudo ufw allow 22/tcp    # SSH
   sudo ufw allow 80/tcp    # HTTP
   sudo ufw allow 443/tcp   # HTTPS
   sudo ufw enable
   ```

3. **Ограничение доступа к PostgreSQL**
   ```bash
   # В docker-compose.yml убедитесь что порт 5432 не открыт наружу
   # Используйте только внутреннюю сеть Docker
   ```

4. **Регулярные обновления**
   ```bash
   sudo apt update && sudo apt upgrade -y
   docker compose pull
   docker compose up -d
   ```

5. **Резервное копирование**
   ```bash
   # Автоматический бэкап БД (cron)
   0 2 * * * docker exec realestate-postgres-1 pg_dump -U realuser realdb > /backups/db_$(date +\%Y\%m\%d).sql
   ```

6. **Мониторинг логов**
   ```bash
   # Проверка подозрительной активности
   sudo tail -f /var/log/auth.log
   docker compose logs -f
   ```

---

## 📊 Мониторинг

### Health checks

```bash
# Проверка статуса всех сервисов
cd /home/ubuntu/realestate
docker compose ps

# Проверка веб-интерфейса
curl http://localhost:8000/health

# Проверка API
curl http://localhost:8080/health

# Проверка БД
docker exec realestate-postgres-1 pg_isready -U realuser
```

### Логи

```bash
# Docker логи
docker compose logs -f

# Systemd логи
sudo journalctl -u realestate-web -f

# Nginx логи
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Метрики производительности

```bash
# Использование ресурсов
docker stats

# Использование диска
df -h
du -sh db/data/

# Использование памяти
free -h
```

---

## 📝 Пошаговая инструкция

### Шаг 1: Подготовка сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка базовых пакетов
sudo apt install -y \
    python3-pip \
    python3-venv \
    docker.io \
    docker-compose \
    git \
    curl \
    wget

# Настройка Docker
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
# ⚠️ Перелогиниться после этого!
```

### Шаг 2: Клонирование проекта

```bash
cd /home/ubuntu
git clone <repository_url> realestate
cd realestate
git checkout <branch>  # например, fix1 или main
```

### Шаг 3: Настройка переменных окружения

```bash
# Копирование примера
cp .env.example .env  # если есть
# или создание нового
nano .env

# ⚠️ ОБЯЗАТЕЛЬНО измените пароли!
```

### Шаг 4: Установка Python зависимостей

```bash
cd /home/ubuntu/realestate
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

### Шаг 5: Запуск базы данных

```bash
cd /home/ubuntu/realestate
docker compose up -d postgres

# Ожидание готовности (10-30 секунд)
sleep 15

# Применение схемы
PGPASSWORD=$(grep POSTGRES_PASSWORD .env | cut -d '=' -f2) \
psql -h localhost -U $(grep POSTGRES_USER .env | cut -d '=' -f2) \
     -d $(grep POSTGRES_DB .env | cut -d '=' -f2) \
     -f db/schema.sql
```

### Шаг 6: Тестирование системы

```bash
cd /home/ubuntu/realestate
source venv/bin/activate
python test_system.py
```

**Ожидаемый результат:** Все тесты должны пройти ✅

### Шаг 7: Запуск веб-сервисов

**Вариант A: FastAPI веб-интерфейс**

```bash
cd /home/ubuntu/realestate
source venv/bin/activate

# Создание systemd service
sudo tee /etc/systemd/system/realestate-web.service > /dev/null <<EOF
[Unit]
Description=Real Estate Web Viewer
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/realestate
Environment="PATH=/home/ubuntu/realestate/venv/bin"
EnvironmentFile=/home/ubuntu/realestate/.env
ExecStart=/home/ubuntu/realestate/venv/bin/python /home/ubuntu/realestate/web_viewer.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable realestate-web
sudo systemctl start realestate-web
sudo systemctl status realestate-web
```

**Вариант B: Docker Compose (все сервисы)**

```bash
cd /home/ubuntu/realestate
docker compose up -d
```

### Шаг 8: Настройка обратного прокси (опционально)

**Nginx + HTTPS:**

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo cp infra/nginx/conf.d/realestate.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/realestate.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo certbot --nginx -d your-domain.com
```

**Cloudflare Tunnel:**

```bash
cd /home/ubuntu/realestate/infra/cloudflare
./setup-tunnel.sh
```

### Шаг 9: Настройка автоматического сбора данных (опционально)

**Через cron:**

```bash
# Редактирование crontab
crontab -e

# Добавить строку (каждый день в 3:00)
0 3 * * * cd /home/ubuntu/realestate && source venv/bin/activate && python -m etl.collector_cian.cli to-db --pages 10
```

**Через Prefect:**

```bash
# Запуск Prefect сервера
docker compose up -d prefect

# Создание и запуск flow
cd /home/ubuntu/realestate
source venv/bin/activate
python -c "from etl.flows import daily_flow; daily_flow(pages=10)"
```

### Шаг 10: Проверка работоспособности

```bash
# Проверка всех сервисов
docker compose ps
sudo systemctl status realestate-web

# Проверка веб-интерфейса
curl http://localhost:8000

# Проверка API
curl http://localhost:8080/health

# Проверка БД
PGPASSWORD=$(grep POSTGRES_PASSWORD .env | cut -d '=' -f2) \
psql -h localhost -U $(grep POSTGRES_USER .env | cut -d '=' -f2) \
     -d $(grep POSTGRES_DB .env | cut -d '=' -f2) \
     -c "SELECT COUNT(*) FROM listings;"
```

---

## ✅ Чеклист готовности к production

- [ ] Сервер настроен (Ubuntu 22.04+, 4+ GB RAM)
- [ ] Docker и Docker Compose установлены
- [ ] Python 3.11+ и venv настроены
- [ ] Все зависимости установлены (`requirements.txt`)
- [ ] Файл `.env` создан с безопасными паролями
- [ ] PostgreSQL запущен и схема применена
- [ ] Тесты пройдены (`test_system.py`)
- [ ] Веб-интерфейс запущен и доступен
- [ ] Firewall настроен (UFW)
- [ ] Резервное копирование настроено
- [ ] Мониторинг настроен
- [ ] HTTPS настроен (Nginx или Cloudflare)
- [ ] Автоматический перезапуск сервисов настроен (systemd)

---

## 🆘 Troubleshooting

### Проблема: PostgreSQL не запускается

```bash
# Проверка логов
docker compose logs postgres

# Проверка порта
sudo lsof -i :5432

# Пересоздание контейнера
docker compose down postgres
docker volume rm realestate_db_data  # ⚠️ Удалит данные!
docker compose up -d postgres
```

### Проблема: Веб-интерфейс не доступен

```bash
# Проверка процесса
ps aux | grep python

# Проверка порта
sudo lsof -i :8000

# Проверка логов
sudo journalctl -u realestate-web -n 50

# Перезапуск
sudo systemctl restart realestate-web
```

### Проблема: Ошибки подключения к БД

```bash
# Проверка переменных окружения
cat .env | grep PG_

# Проверка подключения
PGPASSWORD=<password> psql -h localhost -U realuser -d realdb -c "SELECT 1;"

# Проверка Docker сети
docker network inspect realestate_services-net
```

---

## 📚 Дополнительные ресурсы

- **README.md** - Основная документация проекта
- **TEST_REPORT.md** - Результаты тестирования
- **FINAL_DEPLOYMENT_GUIDE.md** - Детальный гайд по деплою
- **infra/README.md** - Инфраструктурная документация
- **docs/** - Дополнительная документация

---

## 🎯 Итог

После выполнения всех шагов у вас будет:

✅ Работающая база данных PostgreSQL с данными  
✅ Веб-интерфейс для просмотра данных  
✅ API для интеграций  
✅ Система сбора данных (ETL)  
✅ Мониторинг и логирование  
✅ Безопасное HTTPS подключение  
✅ Автоматический перезапуск сервисов  

**Система готова к production использованию!** 🚀

