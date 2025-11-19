# ⚡ Production Quick Start

**Быстрый запуск в production за 10 минут**

---

## 🎯 Минимальные требования

- **Сервер:** Ubuntu 22.04+, 4GB RAM, 50GB диск
- **Порты:** 80, 443 (для веб), 5432 (для БД, опционально)
- **Доступ:** SSH с sudo правами

---

## 🚀 Быстрая установка

### 1. Подготовка (2 минуты)

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка зависимостей
sudo apt install -y python3-pip python3-venv docker.io docker-compose git

# Настройка Docker
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
# ⚠️ Перелогиниться!
```

### 2. Клонирование проекта (1 минута)

```bash
cd /home/ubuntu
git clone <repository_url> realestate
cd realestate
```

### 3. Настройка окружения (2 минуты)

```bash
# Создание .env файла
cat > .env <<EOF
POSTGRES_DB=realdb
POSTGRES_USER=realuser
POSTGRES_PASSWORD=$(openssl rand -base64 32)
PG_DSN=postgresql://realuser:$(grep POSTGRES_PASSWORD .env | cut -d '=' -f2)@localhost:5432/realdb
PG_DSN_INTERNAL=postgresql://realuser:$(grep POSTGRES_PASSWORD .env | cut -d '=' -f2)@postgres:5432/realdb
PG_HOST=localhost
PG_PORT=5432
PG_USER=realuser
PG_PASS=$(grep POSTGRES_PASSWORD .env | cut -d '=' -f2)
PG_DB=realdb
EOF

# Или отредактировать вручную
nano .env
```

### 4. Установка Python зависимостей (2 минуты)

```bash
cd /home/ubuntu/realestate
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

### 5. Запуск базы данных (1 минута)

```bash
cd /home/ubuntu/realestate
docker compose up -d postgres
sleep 15  # Ожидание запуска

# Применение схемы
export PGPASSWORD=$(grep POSTGRES_PASSWORD .env | cut -d '=' -f2)
psql -h localhost -U realuser -d realdb -f db/schema.sql
```

### 6. Тестирование (1 минута)

```bash
cd /home/ubuntu/realestate
source venv/bin/activate
python test_system.py
```

**Ожидаемый результат:** ✅ Все тесты пройдены

### 7. Запуск веб-интерфейса (1 минута)

```bash
cd /home/ubuntu/realestate
source venv/bin/activate

# Создание systemd service
sudo tee /etc/systemd/system/realestate-web.service > /dev/null <<'EOF'
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
```

### 8. Проверка (30 секунд)

```bash
# Проверка статуса
sudo systemctl status realestate-web
docker compose ps

# Проверка доступности
curl http://localhost:8000
```

---

## 🌐 Настройка доступа извне

### Вариант 1: Cloudflare Tunnel (рекомендуется, 3 минуты)

```bash
# Установка cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Настройка
cd /home/ubuntu/realestate/infra/cloudflare
./setup-tunnel.sh
```

### Вариант 2: Nginx + HTTPS (5 минут)

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo cp infra/nginx/conf.d/realestate.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/realestate.conf /etc/nginx/sites-enabled/
sudo certbot --nginx -d your-domain.com
```

---

## ✅ Проверка работоспособности

```bash
# Все сервисы запущены
docker compose ps
sudo systemctl status realestate-web

# Веб-интерфейс доступен
curl http://localhost:8000

# База данных работает
export PGPASSWORD=$(grep POSTGRES_PASSWORD .env | cut -d '=' -f2)
psql -h localhost -U realuser -d realdb -c "SELECT COUNT(*) FROM listings;"
```

---

## 📊 Что получилось

✅ PostgreSQL база данных с данными  
✅ Веб-интерфейс на порту 8000  
✅ Автоматический перезапуск при сбоях  
✅ HTTPS доступ (если настроен)  

---

## 🔧 Полезные команды

```bash
# Просмотр логов
sudo journalctl -u realestate-web -f
docker compose logs -f

# Перезапуск сервисов
sudo systemctl restart realestate-web
docker compose restart

# Остановка
sudo systemctl stop realestate-web
docker compose down

# Обновление
cd /home/ubuntu/realestate
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart realestate-web
```

---

## 📚 Полная документация

Для детальной информации см. **PRODUCTION_REQUIREMENTS.md**

---

**Готово! Система запущена в production.** 🎉

