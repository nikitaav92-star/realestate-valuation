# 🌐 Доступ к веб-интерфейсу

**Дата:** 2025-11-19  
**Статус:** ⚠️ Требуется запуск сервиса

---

## 📍 Адреса веб-интерфейсов

### 1. Cloudflare Tunnel (Production) ⭐
**URL:** https://realestate.ourdocs.org

**Статус:** ✅ **РАБОТАЕТ**

**Доступен:**
- Веб-сервис запущен на localhost:8000
- Cloudflare Tunnel настроен и работает
- Сайт доступен из интернета

---

### 2. Локальный доступ
**URL:** http://localhost:8000

**Статус:** ✅ **РАБОТАЕТ** (через systemd service)

**Для запуска:**
```bash
cd /home/ubuntu/realestate
source venv/bin/activate
python web_viewer.py
```

---

### 3. Прямой IP доступ (если настроен)
**URL:** http://51.75.16.178:8000

**Статус:** ⚠️ Требуется проверка firewall и запуск сервиса

---

## 🚀 Быстрый запуск

### Вариант 1: Запуск вручную (для тестирования)

```bash
cd /home/ubuntu/realestate
source venv/bin/activate
python web_viewer.py
```

**Доступ:** http://localhost:8000

---

### Вариант 2: Запуск через systemd (production)

```bash
# Проверить статус
sudo systemctl status realestate-web

# Если не запущен, запустить
sudo systemctl start realestate-web

# Включить автозапуск
sudo systemctl enable realestate-web

# Проверить логи
sudo journalctl -u realestate-web -f
```

**Доступ:** http://localhost:8000

---

### Вариант 3: Запуск через Docker (если настроен)

```bash
cd /home/ubuntu/realestate
docker compose up -d api
```

**Доступ:** http://localhost:8080

---

## 🔧 Настройка Cloudflare Tunnel

Если нужно настроить доступ через Cloudflare Tunnel:

```bash
cd /home/ubuntu/realestate/infra/cloudflare
./setup-tunnel.sh
```

После настройки доступ будет: **https://realestate.ourdocs.org**

---

## 📊 Доступные веб-интерфейсы

### 1. Web Viewer (FastAPI)
**Файл:** `web_viewer.py`  
**Порт:** 8000  
**Функции:**
- Просмотр объявлений
- Фильтры (комнаты, цена, площадь)
- Сортировка
- Статистика

**Endpoints:**
- `GET /` - Главная страница с таблицей
- `GET /api/stats` - Статистика (JSON)

---

### 2. Web Simple (FastAPI)
**Файл:** `web_simple.py`  
**Порт:** 8000 (если запущен)  
**Функции:**
- Упрощенный интерфейс
- Таблица объявлений
- Фильтры

---

### 3. API Service (FastAPI)
**Файл:** `api/main.py`  
**Порт:** 8080  
**Endpoints:**
- `GET /health` - Health check
- `GET /metrics/median-price` - Медианные цены
- `GET /metrics/dom` - Days on Market
- `GET /metrics/price-drops` - Падения цен

---

### 4. Metabase (Analytics)
**Порт:** 3000  
**Доступ:** http://localhost:3000 (если запущен через docker-compose)

**Запуск:**
```bash
docker compose up -d metabase
```

---

## ✅ Проверка работоспособности

### Проверить, запущен ли сервис:

```bash
# Проверка systemd
sudo systemctl status realestate-web

# Проверка процесса
ps aux | grep web_viewer

# Проверка порта
curl http://localhost:8000/health
```

### Если сервис не запущен:

```bash
# Запустить вручную
cd /home/ubuntu/realestate
source venv/bin/activate
python web_viewer.py

# Или через systemd
sudo systemctl start realestate-web
```

---

## 🌐 Текущий статус

**Cloudflare Tunnel:** https://realestate.ourdocs.org  
- ✅ **РАБОТАЕТ** - Сайт доступен

**Локальный:** http://localhost:8000  
- ✅ **РАБОТАЕТ** - Веб-сервис запущен через systemd

**Статус:** Все сервисы работают корректно

---

## 📝 Команды для запуска

### Быстрый запуск (тестирование):
```bash
cd /home/ubuntu/realestate
source venv/bin/activate
python web_viewer.py
# Открыть: http://localhost:8000
```

### Production запуск:
```bash
sudo systemctl start realestate-web
sudo systemctl enable realestate-web
# Открыть: http://localhost:8000
# Или через Cloudflare: https://realestate.ourdocs.org
```

---

**Последнее обновление:** 2025-11-19

