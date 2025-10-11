# 🚀 Vercel Deployment - Полная инструкция

## ✅ Что уже сделано

- [x] Vercel CLI установлен (версия 48.2.9)
- [x] `vercel.json` создан
- [x] Frontend готов к деплою

---

## 📋 Пошаговая инструкция

### Вариант 1: GitHub Integration (⭐ Рекомендуется)

Это самый простой способ - не требует работы с сервером!

#### Шаги:

1. **Перейти на Vercel**
   - Открыть https://vercel.com/new
   - Залогиниться (GitHub, GitLab, или Email)

2. **Import Repository**
   - Нажать "Import Git Repository"
   - Выбрать или вставить: `github.com/nikitaav92-star/realestate`
   - Дать доступ Vercel к репозиторию (если первый раз)

3. **Configure Project**
   ```
   Project Name: cian-analytics
   Framework Preset: Next.js (автоопределится)
   Root Directory: frontend
   Build Command: npm run build (автоматически)
   Output Directory: .next (автоматически)
   Install Command: npm install (автоматически)
   ```

4. **Environment Variables**
   
   Добавить следующие переменные (все для Production):
   
   | Name | Value |
   |------|-------|
   | `PG_USER` | `realuser` |
   | `PG_PASS` | `strongpass` |
   | `PG_HOST` | `91.103.252.36` |
   | `PG_PORT` | `5432` |
   | `PG_DB` | `realdb` |
   | `POSTGRES_USER` | `realuser` |
   | `POSTGRES_PASSWORD` | `strongpass` |
   | `POSTGRES_HOST` | `91.103.252.36` |
   | `POSTGRES_PORT` | `5432` |
   | `POSTGRES_DATABASE` | `realdb` |

5. **Deploy**
   - Нажать "Deploy"
   - Подождать 3-5 минут
   - ✅ Готово!

#### Результат:
```
Preview URL:    https://cian-analytics-git-fix1-username.vercel.app
Production URL: https://cian-analytics.vercel.app
```

---

### Вариант 2: CLI Deployment

Если хотите деплоить через командную строку.

#### Шаги:

```bash
# 1. Логин
cd /opt/realestate/frontend
vercel login
# Выбрать Email или GitHub
# Подтвердить через браузер или почту

# 2. Первый деплой (preview)
vercel
# Ответить на вопросы:
# ? Set up and deploy? → Y
# ? Which scope? → Выбрать ваш аккаунт
# ? Link to existing project? → N
# ? What's your project's name? → cian-analytics
# ? In which directory is your code? → ./

# 3. Production deployment
vercel --prod
```

#### Добавить Environment Variables через CLI:

```bash
vercel env add PG_USER production
vercel env add PG_PASS production
vercel env add PG_HOST production
vercel env add PG_PORT production
vercel env add PG_DB production
```

Или через Dashboard: https://vercel.com/dashboard → Settings → Environment Variables

---

## 🗄️ Настройка PostgreSQL для внешних подключений

⚠️ **Важно:** PostgreSQL должен принимать подключения от Vercel!

### На сервере выполнить:

```bash
# 1. Найти конфиг PostgreSQL
sudo find /etc/postgresql -name postgresql.conf

# 2. Редактировать postgresql.conf
sudo nano /etc/postgresql/14/main/postgresql.conf
# Или: sudo nano $(find /etc/postgresql -name postgresql.conf | head -1)

# Найти и изменить:
listen_addresses = '*'

# 3. Редактировать pg_hba.conf
sudo nano /etc/postgresql/14/main/pg_hba.conf

# Добавить в конец:
host    realdb    realuser    0.0.0.0/0    md5

# 4. Перезапустить PostgreSQL
sudo systemctl restart postgresql

# 5. Проверить статус
sudo systemctl status postgresql

# 6. Открыть порт в firewall (если есть)
sudo ufw allow 5432/tcp
```

### Проверить подключение:

```bash
# С другого компьютера или через curl
psql -h 91.103.252.36 -U realuser -d realdb -c "SELECT COUNT(*) FROM listings;"
```

---

## 🔒 Безопасность (для Production)

### Ограничить доступ только для Vercel IP

1. **Получить IP ranges Vercel:**
   - Документация: https://vercel.com/docs/security/deployment-ip-ranges
   - Примерные ranges: `76.76.0.0/16`, `76.223.0.0/16` и др.

2. **Обновить pg_hba.conf:**
   ```bash
   # Вместо 0.0.0.0/0 использовать конкретные IP:
   host    realdb    realuser    76.76.0.0/16     md5
   host    realdb    realuser    76.223.0.0/16    md5
   # и т.д. для всех Vercel ranges
   ```

3. **Создать отдельного пользователя для Vercel:**
   ```sql
   CREATE USER vercel_user WITH PASSWORD 'secure_password_here';
   GRANT CONNECT ON DATABASE realdb TO vercel_user;
   GRANT SELECT ON ALL TABLES IN SCHEMA public TO vercel_user;
   GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO vercel_user;
   ```

4. **Использовать SSL (опционально):**
   - Настроить SSL для PostgreSQL
   - В Vercel environment добавить: `PGSSLMODE=require`

---

## 🌐 После успешного деплоя

### URLs:

```
Production: https://cian-analytics.vercel.app
Preview:    https://cian-analytics-git-fix1-xxx.vercel.app
```

### Автоматический CI/CD:

✅ При каждом push в GitHub → автоматический деплой  
✅ Branch preview (каждая ветка получает свой URL)  
✅ Rollback за 1 клик  
✅ Analytics и мониторинг встроены

### Проверка работы:

1. Открыть https://cian-analytics.vercel.app
2. Проверить главную страницу
3. Попробовать поиск
4. Открыть детальную страницу объявления
5. Проверить аналитику

---

## 📊 Мониторинг и логи

### В Vercel Dashboard:

- **Deployments** - история деплоев
- **Analytics** - статистика посещений
- **Logs** - логи приложения в реальном времени
- **Functions** - статистика API routes
- **Settings** - настройки проекта

### CLI команды:

```bash
# Список деплоев
vercel ls

# Логи последнего деплоя
vercel logs

# Информация о проекте
vercel inspect

# Удалить проект
vercel rm cian-analytics
```

---

## 🔄 Обновления

### Автоматические (через Git):

1. Внести изменения в код
2. Закоммитить: `git commit -m "update"`
3. Запушить: `git push origin fix1`
4. ✅ Vercel автоматически задеплоит!

### Ручные (через CLI):

```bash
cd /opt/realestate/frontend
vercel --prod
```

---

## ❓ Troubleshooting

### Build Failed

**Проблема:** Build падает с ошибкой

**Решение:**
1. Проверить логи в Vercel Dashboard
2. Проверить Environment Variables
3. Локально запустить: `npm run build`
4. Проверить версии Node.js (18-20)

### Database Connection Error

**Проблема:** Не подключается к PostgreSQL

**Решение:**
1. Проверить что PostgreSQL принимает внешние подключения
2. Проверить что порт 5432 открыт
3. Проверить Environment Variables в Vercel
4. Попробовать подключиться вручную:
   ```bash
   psql -h 91.103.252.36 -U realuser -d realdb
   ```

### Empty Data

**Проблема:** Сайт открывается но нет данных

**Решение:**
1. Проверить что в БД есть данные:
   ```sql
   SELECT COUNT(*) FROM listings;
   ```
2. Проверить логи в Vercel
3. Проверить что пользователь БД имеет права SELECT

---

## 💰 Pricing

### Free Tier (Hobby):
- ✅ Unlimited deployments
- ✅ 100 GB bandwidth
- ✅ Автоматический HTTPS
- ✅ CDN
- ✅ Analytics (basic)
- ⚠️ Только для некоммерческих проектов

### Pro ($20/month):
- Все из Free +
- Больше bandwidth
- Advanced analytics
- Team collaboration
- Password protection
- Коммерческое использование

Для CIAN Analytics: **Free tier достаточно!**

---

## ✅ Преимущества Vercel

| Функция | Описание |
|---------|----------|
| 🚀 **Скорость** | Global CDN, edge network |
| 🔒 **HTTPS** | Автоматический SSL |
| 📦 **CI/CD** | Автодеплой из Git |
| 🌍 **Preview URLs** | Каждая ветка = свой URL |
| 📊 **Analytics** | Встроенная аналитика |
| 🔄 **Rollback** | Откат за 1 клик |
| 💰 **Бесплатно** | Для личных проектов |
| ⚡ **Fast** | Serverless functions |

---

## 🎯 Итог

### Что нужно сделать:

1. ✅ Перейти на https://vercel.com/new
2. ✅ Подключить GitHub репозиторий
3. ✅ Выбрать Root Directory: `frontend`
4. ✅ Добавить Environment Variables (PostgreSQL)
5. ✅ Настроить PostgreSQL для внешних подключений
6. ✅ Нажать Deploy
7. ✅ Подождать 3-5 минут
8. ✅ **Готово!** 🎉

### Результат:

```
🌐 https://cian-analytics.vercel.app

✅ HTTPS
✅ CDN
✅ Автодеплой
✅ Мониторинг
✅ Логи
```

---

**Удачного деплоя!** 🚀

*Документация Vercel: https://vercel.com/docs*  
*Support: https://vercel.com/support*

