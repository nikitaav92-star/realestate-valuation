# Инфраструктура: публикация Metabase и Prefect

## DNS
- Настройте A-запись `realestate.ourdocs.org` → публичный IP VPS.

## Установка зависимостей
```bash
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx
```

## Фаервол
```bash
sudo ufw allow 80/tcp || true
sudo ufw allow 443/tcp || true
```

## Развёртывание конфигурации Nginx
```bash
sudo install -m 644 /opt/realestate/infra/nginx/conf.d/realestate.conf /etc/nginx/sites-available/realestate.conf
sudo ln -sf /etc/nginx/sites-available/realestate.conf /etc/nginx/sites-enabled/realestate.conf
sudo nginx -t
sudo systemctl reload nginx
```

## Выпуск TLS-сертификата
```bash
sudo certbot --nginx -d realestate.ourdocs.org --redirect -m admin@ourdocs.org -n --agree-tos
```

## Автопродление сертификата
Добавьте cron-задание:
```bash
echo '0 3 * * * root certbot renew --quiet && systemctl reload nginx' | sudo tee /etc/cron.d/certbot_renew >/dev/null
```

## Доступ
- Metabase: https://realestate.ourdocs.org/
- Prefect: https://realestate.ourdocs.org/prefect/

## Быстрый деплой
Выполните на сервере с правами sudo:
```bash
apt update && apt install -y nginx certbot python3-certbot-nginx
ufw allow 80/tcp || true && ufw allow 443/tcp || true
install -m 644 /opt/realestate/infra/nginx/conf.d/realestate.conf /etc/nginx/sites-available/realestate.conf
ln -sf /etc/nginx/sites-available/realestate.conf /etc/nginx/sites-enabled/realestate.conf
nginx -t && systemctl reload nginx
certbot --nginx -d realestate.ourdocs.org --redirect -m admin@ourdocs.org -n --agree-tos
printf '0 3 * * * root certbot renew --quiet && systemctl reload nginx\n' | tee /etc/cron.d/certbot_renew >/dev/null
```
