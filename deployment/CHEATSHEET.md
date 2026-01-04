# ⚡ Production Deployment - Шпаргалка

## 🚀 Быстрый деплой (одна команда!)

```bash
cd /home/ubuntu/realestate/deployment
./quick_deploy.sh your-domain.com YOUR_BOT_TOKEN
```

---

## 🎯 Основные команды

### Управление

```bash
./update.sh              # Обновить код
./backup.sh             # Создать бэкап
./health_check.sh       # Проверить систему
```

### Перезапуск

```bash
sudo systemctl restart valuation-api      # API
sudo systemctl restart valuation-bot      # Бот
sudo systemctl reload nginx               # Nginx
```

### Логи

```bash
sudo journalctl -u valuation-api -f       # API (realtime)
sudo journalctl -u valuation-bot -f       # Бот (realtime)
tail -f /var/log/nginx/valuation_access.log   # Nginx access
tail -f /var/log/nginx/valuation_error.log    # Nginx errors
```

### Статус

```bash
sudo systemctl status valuation-api       # API
sudo systemctl status valuation-bot       # Бот
sudo systemctl status nginx               # Nginx
sudo systemctl status postgresql          # БД
```

---

## 🆘 Troubleshooting

### API не отвечает
```bash
sudo systemctl restart valuation-api
sudo journalctl -u valuation-api -n 50
curl http://localhost:8001/
```

### 502 Bad Gateway
```bash
sudo systemctl restart valuation-api nginx
netstat -tlnp | grep 8001
```

### Бот не отвечает
```bash
sudo systemctl restart valuation-bot
sudo journalctl -u valuation-bot -n 50
```

### SSL проблемы
```bash
sudo certbot renew --force-renewal
sudo systemctl reload nginx
```

---

## 📊 Полезные проверки

```bash
# Использование диска
df -h

# Использование памяти
free -h

# Процессы API
ps aux | grep gunicorn

# Процессы бота
ps aux | grep bot.py

# Активные подключения
netstat -an | grep 8001

# Количество запросов
tail -1000 /var/log/nginx/valuation_access.log | wc -l

# Статистика БД
psql -U realuser realdb -c "SELECT COUNT(*) FROM listings;"
psql -U realuser realdb -c "SELECT COUNT(*) FROM valuation_history;"
```

---

## 🔧 Конфигурация

```bash
# Nginx
sudo nano /etc/nginx/sites-available/valuation
sudo nginx -t && sudo systemctl reload nginx

# API сервис
sudo nano /etc/systemd/system/valuation-api.service
sudo systemctl daemon-reload && sudo systemctl restart valuation-api

# Бот сервис
sudo nano /etc/systemd/system/valuation-bot.service
sudo systemctl daemon-reload && sudo systemctl restart valuation-bot
```

---

## 🔒 SSL

```bash
# Проверить сертификаты
sudo certbot certificates

# Обновить
sudo certbot renew

# Тест обновления
sudo certbot renew --dry-run
```

---

## 💾 Backup & Restore

### Backup
```bash
./backup.sh
# или вручную:
pg_dump -U realuser realdb | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Restore
```bash
gunzip -c backup_YYYYMMDD.sql.gz | psql -U realuser realdb
```

---

## 📈 Мониторинг

```bash
# Запустить мониторинг каждые 5 минут
crontab -e
# Добавить:
*/5 * * * * /home/ubuntu/realestate/deployment/health_check.sh >> /var/log/valuation/health.log

# Ежедневный бэкап в 3:00
0 3 * * * /home/ubuntu/realestate/deployment/backup.sh
```

---

## 🌐 URLs

```
https://your-domain.com/          # Веб-интерфейс
https://your-domain.com/docs      # API документация
https://your-domain.com/estimate  # API endpoint
```

---

## 📞 Экстренные команды

```bash
# Остановить все
sudo systemctl stop valuation-api valuation-bot nginx

# Запустить все
sudo systemctl start valuation-api valuation-bot nginx

# Полный рестарт
sudo systemctl restart valuation-api valuation-bot
sudo systemctl reload nginx

# Логи за последний час
sudo journalctl -u valuation-api --since "1 hour ago"

# Очистить логи (осторожно!)
sudo journalctl --vacuum-time=7d
```

---

**💡 Совет:** Сохраните эту шпаргалку и используйте для быстрого доступа к командам!
