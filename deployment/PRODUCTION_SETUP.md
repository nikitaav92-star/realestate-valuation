# 🚀 Production Deployment Guide

## Размещение системы оценки на домене

Эта инструкция поможет разместить систему оценки недвижимости на вашем домене с SSL, автозапуском и мониторингом.

---

## 📋 Что будет настроено

✅ **Nginx** - reverse proxy с SSL  
✅ **SSL сертификат** (Let's Encrypt) - HTTPS  
✅ **Systemd services** - автозапуск при перезагрузке  
✅ **Gunicorn** - production WSGI сервер  
✅ **Мониторинг** - логи и статус сервисов  

---

## 🌐 Предварительные требования

1. **Домен** - например: `valuation.yourdomain.com`
2. **DNS настроен** - A-запись указывает на ваш сервер
3. **Порты открыты**: 80 (HTTP), 443 (HTTPS)
4. **Root доступ** к серверу

---

## 1️⃣ Установка Nginx

```bash
sudo apt update
sudo apt install -y nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

Проверка:
```bash
sudo systemctl status nginx
```

---

## 2️⃣ Настройка Nginx для вашего домена

### Создайте конфигурацию сайта:

```bash
sudo nano /etc/nginx/sites-available/valuation
```

Вставьте конфигурацию:

```nginx
# HTTP - редирект на HTTPS
server {
    listen 80;
    server_name valuation.yourdomain.com;  # ← Замените на ваш домен
    
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS - основная конфигурация
server {
    listen 443 ssl http2;
    server_name valuation.yourdomain.com;  # ← Замените на ваш домен
    
    # SSL сертификаты (будут созданы позже)
    ssl_certificate /etc/letsencrypt/live/valuation.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/valuation.yourdomain.com/privkey.pem;
    
    # SSL настройки безопасности
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Логи
    access_log /var/log/nginx/valuation_access.log;
    error_log /var/log/nginx/valuation_error.log;
    
    # Статические файлы
    location /static/ {
        alias /home/ubuntu/realestate/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
    
    # API (FastAPI/Uvicorn)
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        
        # Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # WebSocket support (если понадобится)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    
    # Ограничение размера загружаемых файлов (для ЕГРН)
    client_max_body_size 10M;
}
```

### Активируйте конфигурацию:

```bash
sudo ln -s /etc/nginx/sites-available/valuation /etc/nginx/sites-enabled/
sudo nginx -t  # Проверка конфигурации
```

**Пока не перезагружайте Nginx!** (сначала нужен SSL сертификат)

---

## 3️⃣ Установка SSL сертификата (Let's Encrypt)

### Установите Certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx
```

### Получите SSL сертификат:

```bash
sudo certbot certonly --nginx -d valuation.yourdomain.com
```

Следуйте инструкциям:
1. Введите email для уведомлений
2. Согласитесь с условиями (Yes)
3. Сертификат будет получен автоматически

### Настройте автообновление:

```bash
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

Проверка:
```bash
sudo certbot renew --dry-run
```

### Теперь перезагрузите Nginx:

```bash
sudo systemctl reload nginx
```

---

## 4️⃣ Создание Systemd сервисов

### 4.1. Сервис для Valuation API

```bash
sudo nano /etc/systemd/system/valuation-api.service
```

```ini
[Unit]
Description=Real Estate Valuation API (FastAPI)
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/realestate

# Environment
Environment="PATH=/home/ubuntu/realestate/venv/bin"
Environment="PG_DSN=postgresql://realuser:strongpass123@localhost:5432/realdb"
Environment="PYTHONPATH=/home/ubuntu/realestate"

# Start command (Gunicorn для production)
ExecStart=/home/ubuntu/realestate/venv/bin/gunicorn \
    api.v1.valuation:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 127.0.0.1:8001 \
    --timeout 120 \
    --access-logfile /var/log/valuation/access.log \
    --error-logfile /var/log/valuation/error.log \
    --log-level info

# Restart policy
Restart=always
RestartSec=10

# Security
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

### 4.2. Сервис для Telegram бота

```bash
sudo nano /etc/systemd/system/valuation-bot.service
```

```ini
[Unit]
Description=Real Estate Valuation Telegram Bot
After=network.target valuation-api.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/realestate/telegram_bot

# Environment
Environment="PATH=/home/ubuntu/realestate/venv/bin"
Environment="TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE"
Environment="VALUATION_API_URL=http://localhost:8001"
Environment="PG_DSN=postgresql://realuser:strongpass123@localhost:5432/realdb"

# Start command
ExecStart=/home/ubuntu/realestate/venv/bin/python3 bot.py

# Restart policy
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Создайте директорию для логов:

```bash
sudo mkdir -p /var/log/valuation
sudo chown ubuntu:ubuntu /var/log/valuation
```

### Установите Gunicorn:

```bash
cd /home/ubuntu/realestate
source venv/bin/activate
pip install gunicorn
```

### Активируйте и запустите сервисы:

```bash
# Перезагрузка systemd
sudo systemctl daemon-reload

# Включение автозапуска
sudo systemctl enable valuation-api
sudo systemctl enable valuation-bot

# Запуск сервисов
sudo systemctl start valuation-api
sudo systemctl start valuation-bot

# Проверка статуса
sudo systemctl status valuation-api
sudo systemctl status valuation-bot
```

---

## 5️⃣ Проверка работы

### Проверьте API:

```bash
curl https://valuation.yourdomain.com/
```

Должен вернуться JSON с информацией об API.

### Проверьте веб-интерфейс:

Откройте в браузере:
```
https://valuation.yourdomain.com
```

### Проверьте Telegram бота:

Напишите боту в Telegram - он должен отвечать.

---

## 6️⃣ Мониторинг и логи

### Просмотр логов API:

```bash
# Realtime
sudo journalctl -u valuation-api -f

# Последние 100 строк
sudo journalctl -u valuation-api -n 100

# Логи Gunicorn
tail -f /var/log/valuation/access.log
tail -f /var/log/valuation/error.log
```

### Просмотр логов бота:

```bash
sudo journalctl -u valuation-bot -f
```

### Просмотр логов Nginx:

```bash
tail -f /var/log/nginx/valuation_access.log
tail -f /var/log/nginx/valuation_error.log
```

### Перезапуск сервисов:

```bash
sudo systemctl restart valuation-api
sudo systemctl restart valuation-bot
sudo systemctl reload nginx
```

---

## 7️⃣ Обновление кода

### Скрипт для быстрого обновления:

```bash
nano /home/ubuntu/realestate/deployment/update.sh
```

```bash
#!/bin/bash
# Quick update script for production

echo "🔄 Updating Real Estate Valuation System..."

cd /home/ubuntu/realestate

# Pull latest code (if using git)
# git pull origin main

# Activate venv
source venv/bin/activate

# Install/update dependencies
pip install -r requirements.txt
pip install -r telegram_bot/requirements.txt

# Restart services
echo "♻️  Restarting services..."
sudo systemctl restart valuation-api
sudo systemctl restart valuation-bot

# Check status
echo "✅ Checking status..."
sudo systemctl status valuation-api --no-pager
sudo systemctl status valuation-bot --no-pager

echo "✅ Update complete!"
```

```bash
chmod +x /home/ubuntu/realestate/deployment/update.sh
```

---

## 8️⃣ Firewall настройки

### Настройте UFW (если используется):

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp  # SSH
sudo ufw enable
sudo ufw status
```

---

## 9️⃣ Backup скрипт

```bash
nano /home/ubuntu/realestate/deployment/backup.sh
```

```bash
#!/bin/bash
# Backup script for database and logs

BACKUP_DIR="/home/ubuntu/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup database
echo "💾 Backing up database..."
pg_dump -U realuser realdb | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"

# Backup logs
echo "📋 Backing up logs..."
tar -czf "$BACKUP_DIR/logs_$DATE.tar.gz" /var/log/valuation/

# Keep only last 7 backups
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +7 -delete
find $BACKUP_DIR -name "logs_*.tar.gz" -mtime +7 -delete

echo "✅ Backup complete: $BACKUP_DIR"
```

```bash
chmod +x /home/ubuntu/realestate/deployment/backup.sh

# Добавьте в cron для ежедневного бэкапа
crontab -e
# Добавьте строку:
0 3 * * * /home/ubuntu/realestate/deployment/backup.sh
```

---

## 🔟 Health Check скрипт

```bash
nano /home/ubuntu/realestate/deployment/health_check.sh
```

```bash
#!/bin/bash
# Health check script

echo "🏥 Health Check Report"
echo "====================="

# Check API
echo -n "API: "
if curl -f -s https://valuation.yourdomain.com/ > /dev/null; then
    echo "✅ OK"
else
    echo "❌ DOWN"
    sudo systemctl restart valuation-api
fi

# Check Bot
echo -n "Bot: "
if sudo systemctl is-active --quiet valuation-bot; then
    echo "✅ Running"
else
    echo "❌ Stopped"
    sudo systemctl start valuation-bot
fi

# Check Nginx
echo -n "Nginx: "
if sudo systemctl is-active --quiet nginx; then
    echo "✅ Running"
else
    echo "❌ Stopped"
fi

# Check Database
echo -n "PostgreSQL: "
if sudo systemctl is-active --quiet postgresql; then
    echo "✅ Running"
else
    echo "❌ Stopped"
fi

# Check disk space
echo ""
echo "💾 Disk Space:"
df -h / | tail -1

# Check memory
echo ""
echo "🧠 Memory Usage:"
free -h | grep Mem

echo ""
echo "📊 Last 5 API requests:"
tail -5 /var/log/valuation/access.log 2>/dev/null || echo "No logs yet"
```

```bash
chmod +x /home/ubuntu/realestate/deployment/health_check.sh

# Запуск каждые 5 минут
crontab -e
# Добавьте:
*/5 * * * * /home/ubuntu/realestate/deployment/health_check.sh >> /var/log/valuation/health.log
```

---

## ✅ Чек-лист для production

- [ ] DNS настроен (A-запись на ваш IP)
- [ ] Nginx установлен и настроен
- [ ] SSL сертификат получен (Let's Encrypt)
- [ ] Systemd сервисы созданы и запущены
- [ ] Firewall настроен (порты 80, 443)
- [ ] Логи пишутся в `/var/log/valuation/`
- [ ] Автообновление SSL работает
- [ ] Backup скрипт настроен
- [ ] Health check работает
- [ ] Сайт доступен по HTTPS
- [ ] Telegram бот отвечает

---

## 🔗 Полезные команды

```bash
# Перезапуск всего стека
sudo systemctl restart valuation-api valuation-bot nginx

# Просмотр всех логов
sudo journalctl -u valuation-api -u valuation-bot -f

# Проверка конфигурации Nginx
sudo nginx -t

# Обновление системы
./deployment/update.sh

# Проверка здоровья
./deployment/health_check.sh

# Бэкап
./deployment/backup.sh
```

---

## 🆘 Troubleshooting

### API не отвечает:

```bash
sudo systemctl status valuation-api
sudo journalctl -u valuation-api -n 50
```

### 502 Bad Gateway:

```bash
# Проверьте, запущен ли API
curl http://localhost:8001/

# Перезапустите
sudo systemctl restart valuation-api
```

### SSL ошибки:

```bash
# Обновите сертификат
sudo certbot renew --force-renewal
sudo systemctl reload nginx
```

---

## 📊 Мониторинг производительности

### Установите htop для мониторинга:

```bash
sudo apt install htop
htop
```

### Мониторинг запросов:

```bash
# Количество запросов в минуту
watch -n 1 'tail -100 /var/log/nginx/valuation_access.log | wc -l'
```

---

**Готово! Ваша система оценки теперь работает на production домене!** 🚀
