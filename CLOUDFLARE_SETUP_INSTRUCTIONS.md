# Настройка Cloudflare Tunnel для Realestate Viewer

## Текущее состояние

- ✅ cloudflared установлен (версия 2025.10.1)
- ✅ Веб-сервер работает на localhost:8000
- ✅ Скрипт setup-tunnel.sh готов
- ⏳ Требуется аутентификация в Cloudflare

---

## Быстрая установка (рекомендуется)

Выполните на сервере:

```bash
cd ~/realestate/infra/cloudflare
./setup-tunnel.sh
```

Скрипт автоматически:
1. Запросит аутентификацию через браузер
2. Создаст туннель "realestate"
3. Настроит DNS для realestate.ourdocs.org
4. Запустит туннель как systemd service

---

## Ручная установка (если скрипт не работает)

### Шаг 1: Аутентификация

```bash
cloudflared tunnel login
```

Откроется URL вида:
```
https://dash.cloudflare.com/argotunnel?...
```

Откройте его в браузере, войдите в Cloudflare и разрешите доступ.

### Шаг 2: Создание туннеля

```bash
cloudflared tunnel create realestate
```

Получите TUNNEL_ID из вывода.

### Шаг 3: Конфигурация

Создайте файл `~/.cloudflared/config.yml`:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /home/ubuntu/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: realestate.ourdocs.org
    service: http://localhost:8000
  - service: http_status:404
```

### Шаг 4: DNS routing

```bash
cloudflared tunnel route dns realestate realestate.ourdocs.org
```

### Шаг 5: Запуск как service

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

---

## Проверка работы

```bash
# Статус service
sudo systemctl status cloudflared

# Логи в реальном времени
sudo journalctl -u cloudflared -f

# Проверка DNS
nslookup realestate.ourdocs.org

# Проверка HTTPS
curl -I https://realestate.ourdocs.org
```

---

## Доступ к веб-интерфейсу

После настройки откройте в браузере:

**https://realestate.ourdocs.org**

Вы должны увидеть:
- Статистику: 1,558 объявлений
- Таблицу с квартирами
- Фильтры по комнатам, цене
- Ссылки на CIAN.ru

---

## Troubleshooting

### Туннель не запускается

```bash
# Проверьте конфигурацию
cat ~/.cloudflared/config.yml

# Проверьте credentials
ls -la ~/.cloudflared/*.json

# Запустите вручную для отладки
cloudflared tunnel run realestate
```

### DNS не резолвится

```bash
# Проверьте routes
cloudflared tunnel route dns list

# Добавьте route вручную
cloudflared tunnel route dns realestate realestate.ourdocs.org
```

### 502 Bad Gateway

Проверьте что веб-сервер работает:
```bash
curl http://localhost:8000
ps aux | grep web_simple
```

---

## Управление

### Перезапуск туннеля

```bash
sudo systemctl restart cloudflared
```

### Остановка туннеля

```bash
sudo systemctl stop cloudflared
```

### Удаление туннеля

```bash
sudo systemctl stop cloudflared
sudo systemctl disable cloudflared
cloudflared tunnel delete realestate
```

---

## Безопасность

1. **Credentials файл:**
   - Хранится в `~/.cloudflared/<UUID>.json`
   - НЕ коммитить в Git!
   - Сделать backup в безопасное место

2. **Cloudflare Access (опционально):**
   - Добавьте аутентификацию через Cloudflare Access
   - Ограничьте доступ по email домену
   - Настройте через dashboard.cloudflare.com

3. **Rate Limiting:**
   - Настройте в Cloudflare Dashboard
   - Защита от DDoS включена автоматически

---

## Следующие шаги

После успешного деплоя:

1. ✅ Проверить доступ через https://realestate.ourdocs.org
2. ✅ Протестировать все функции веб-интерфейса
3. ✅ Добавить в .gitignore: `.cloudflared/*.json`
4. ✅ Сделать backup credentials файла
5. ✅ Настроить мониторинг (Uptime Robot, Cloudflare Analytics)
6. Обновить README.md с новым URL
7. Настроить Cloudflare Access для защиты (если нужно)

---

## Контакты для поддержки

- Cloudflare Docs: https://developers.cloudflare.com/cloudflare-one/
- GitHub Issues: https://github.com/cloudflare/cloudflared/issues
- Cloudflare Community: https://community.cloudflare.com/
