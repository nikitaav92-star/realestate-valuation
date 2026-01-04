# 🚀 Deployment Scripts

Автоматизированные скрипты для развертывания системы оценки на production.

---

## 📋 Быстрый старт

### 1️⃣ Развернуть на домене (один скрипт!)

```bash
cd /home/ubuntu/realestate/deployment
./quick_deploy.sh your-domain.com YOUR_BOT_TOKEN
```

**Например:**
```bash
./quick_deploy.sh valuation.example.com 123456:ABC-DEF1234ghIkl
```

**Что делает:**
- ✅ Устанавливает Nginx
- ✅ Настраивает SSL (Let's Encrypt)
- ✅ Создает systemd сервисы
- ✅ Запускает API и бота
- ✅ Настраивает автозапуск

**Время:** ~5 минут

---

## 🛠️ Управление системой

### Обновить код

```bash
./update.sh
```

- Обновляет код (git pull)
- Устанавливает зависимости
- Перезапускает сервисы

---

### Создать бэкап

```bash
./backup.sh
```

- Бэкап базы данных
- Бэкап истории оценок
- Бэкап логов
- Хранит последние 7 дней

**Автоматический бэкап:**
```bash
crontab -e
# Добавьте:
0 3 * * * /home/ubuntu/realestate/deployment/backup.sh
```

---

### Проверить здоровье системы

```bash
./health_check.sh
```

**Проверяет:**
- ✅ API доступность
- ✅ Статус сервисов
- ✅ База данных
- ✅ Диск и память
- ✅ Логи ошибок
- ✅ Статистика оценок

**Автоматический мониторинг:**
```bash
crontab -e
# Добавьте:
*/5 * * * * /home/ubuntu/realestate/deployment/health_check.sh >> /var/log/valuation/health.log
```

---

## 📊 Мониторинг

### Просмотр логов в реальном времени

```bash
# API логи
sudo journalctl -u valuation-api -f

# Бот логи
sudo journalctl -u valuation-bot -f

# Nginx логи
tail -f /var/log/nginx/valuation_access.log
tail -f /var/log/nginx/valuation_error.log

# Все сразу
sudo journalctl -u valuation-api -u valuation-bot -f
```

---

### Перезапуск сервисов

```bash
# Перезапустить API
sudo systemctl restart valuation-api

# Перезапустить бота
sudo systemctl restart valuation-bot

# Перезапустить Nginx
sudo systemctl reload nginx

# Всё сразу
sudo systemctl restart valuation-api valuation-bot && sudo systemctl reload nginx
```

---

### Проверка статуса

```bash
# API
sudo systemctl status valuation-api

# Бот
sudo systemctl status valuation-bot

# Nginx
sudo systemctl status nginx
```

---

## 🔧 Настройка

### Переменные окружения

#### API сервис:
```bash
sudo nano /etc/systemd/system/valuation-api.service
```

#### Бот сервис:
```bash
sudo nano /etc/systemd/system/valuation-bot.service
```

После изменений:
```bash
sudo systemctl daemon-reload
sudo systemctl restart valuation-api valuation-bot
```

---

### Nginx конфигурация

```bash
sudo nano /etc/nginx/sites-available/valuation
sudo nginx -t  # Проверка
sudo systemctl reload nginx  # Применить
```

---

## 🆘 Troubleshooting

### API не отвечает

```bash
# Проверить статус
sudo systemctl status valuation-api

# Посмотреть логи
sudo journalctl -u valuation-api -n 100

# Перезапустить
sudo systemctl restart valuation-api

# Проверить напрямую
curl http://localhost:8001/
```

---

### 502 Bad Gateway

```bash
# API запущен?
sudo systemctl status valuation-api

# Nginx запущен?
sudo systemctl status nginx

# Перезапустить API
sudo systemctl restart valuation-api

# Проверить порт
netstat -tlnp | grep 8001
```

---

### SSL проблемы

```bash
# Проверить сертификат
sudo certbot certificates

# Обновить вручную
sudo certbot renew --force-renewal

# Перезагрузить Nginx
sudo systemctl reload nginx
```

---

### База данных недоступна

```bash
# Проверить PostgreSQL
sudo systemctl status postgresql

# Проверить подключение
psql -U realuser -d realdb

# Рестарт
sudo systemctl restart postgresql
```

---

## 📁 Структура файлов

```
deployment/
├── PRODUCTION_SETUP.md    # Полная инструкция
├── README.md              # Этот файл
├── quick_deploy.sh        # Автоматический деплой
├── update.sh              # Обновление кода
├── backup.sh              # Бэкап БД и логов
└── health_check.sh        # Проверка здоровья
```

---

## 🔗 Полезные ссылки

- [PRODUCTION_SETUP.md](./PRODUCTION_SETUP.md) - Детальная инструкция
- [Nginx docs](https://nginx.org/ru/docs/)
- [Let's Encrypt](https://letsencrypt.org/)
- [Systemd](https://www.freedesktop.org/wiki/Software/systemd/)

---

## 📞 Быстрые команды

```bash
# Полная переустановка
./quick_deploy.sh your-domain.com bot-token

# Обновить код
./update.sh

# Бэкап
./backup.sh

# Проверка
./health_check.sh

# Посмотреть логи
sudo journalctl -u valuation-api -f

# Перезапуск
sudo systemctl restart valuation-api valuation-bot

# Статус всего
systemctl status valuation-api valuation-bot nginx postgresql
```

---

## ✅ Чек-лист production

- [ ] DNS настроен (A-запись)
- [ ] Деплой выполнен (`quick_deploy.sh`)
- [ ] SSL сертификат получен
- [ ] API доступен по HTTPS
- [ ] Бот отвечает в Telegram
- [ ] Настроен автобэкап (cron)
- [ ] Настроен health check (cron)
- [ ] Логи ротируются
- [ ] Firewall настроен

---

**Готово! Ваша система работает на production! 🎉**
