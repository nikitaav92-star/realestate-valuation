# 🚀 Деплой CIAN Analytics Frontend

## Требования

### Минимальные требования:
- Node.js 18+ или 20+
- npm 9+ или yarn
- PostgreSQL 14+ (с заполненной БД CIAN)
- 512MB RAM (минимум)
- 2GB свободного места

### Рекомендуемые требования:
- Node.js 20 LTS
- 2GB+ RAM
- 10GB свободного места
- Reverse proxy (nginx)

## 🎯 Варианты деплоя

### 1️⃣ Локальная разработка (Development)

#### Шаг 1: Установка Node.js

**Ubuntu/Debian:**
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

**Проверка:**
```bash
node --version  # должно быть v20.x.x
npm --version   # должно быть 9.x.x+
```

#### Шаг 2: Установка зависимостей

```bash
cd /opt/realestate/frontend
npm install
```

**Время:** 3-5 минут  
**Размер node_modules:** ~500MB

#### Шаг 3: Настройка переменных окружения

Файл `.env.local` уже создан, но проверьте настройки:

```bash
cat .env.local
```

Убедитесь что параметры соответствуют вашей БД:
```env
PG_USER=realuser
PG_PASS=strongpass
PG_HOST=localhost
PG_PORT=5432
PG_DB=realdb
```

#### Шаг 4: Запуск dev сервера

```bash
npm run dev
```

✅ **Доступ:** http://localhost:3000

---

### 2️⃣ Production на VPS (Ubuntu)

#### A. Подготовка сервера

```bash
# 1. Обновление системы
sudo apt update && sudo apt upgrade -y

# 2. Установка Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# 3. Установка PM2 (process manager)
sudo npm install -g pm2

# 4. Установка nginx (опционально, для reverse proxy)
sudo apt install -y nginx
```

#### B. Клонирование и установка

```bash
# 1. Переход в директорию проекта
cd /opt/realestate/frontend

# 2. Установка зависимостей
npm install --production

# 3. Настройка .env.production
cp .env.local .env.production
nano .env.production  # настроить под production БД
```

#### C. Build и запуск

```bash
# 1. Production build
npm run build

# 2. Запуск через PM2
pm2 start npm --name "cian-frontend" -- start

# 3. Автозапуск при перезагрузке
pm2 startup
pm2 save

# 4. Мониторинг
pm2 logs cian-frontend
pm2 status
```

#### D. Nginx reverse proxy (опционально)

```bash
sudo nano /etc/nginx/sites-available/cian-analytics
```

Содержимое:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Активация:
```bash
sudo ln -s /etc/nginx/sites-available/cian-analytics /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

✅ **Доступ:** http://your-domain.com

---

### 3️⃣ Docker

#### Создание Dockerfile

```bash
cd /opt/realestate/frontend
cat > Dockerfile << 'DOCKER_EOF'
FROM node:20-alpine AS builder

WORKDIR /app

# Копируем package files
COPY package*.json ./

# Установка зависимостей
RUN npm ci --only=production

# Копируем исходники
COPY . .

# Build
RUN npm run build

# Production image
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV production

# Создание non-root пользователя
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Копируем build artifacts
COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/public ./public

USER nextjs

EXPOSE 3000

ENV PORT 3000

CMD ["npm", "start"]
DOCKER_EOF
```

#### docker-compose.yml

```bash
cat > docker-compose.yml << 'COMPOSE_EOF'
version: '3.8'

services:
  frontend:
    build: .
    ports:
      - "3000:3000"
    environment:
      - PG_USER=realuser
      - PG_PASS=strongpass
      - PG_HOST=postgres
      - PG_PORT=5432
      - PG_DB=realdb
    depends_on:
      - postgres
    restart: unless-stopped

  postgres:
    image: postgres:14-alpine
    environment:
      - POSTGRES_USER=realuser
      - POSTGRES_PASSWORD=strongpass
      - POSTGRES_DB=realdb
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ../db/schema_v3_with_photos.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    restart: unless-stopped

volumes:
  postgres_data:
COMPOSE_EOF
```

#### Запуск

```bash
# Build и запуск
docker-compose up -d

# Логи
docker-compose logs -f frontend

# Остановка
docker-compose down
```

✅ **Доступ:** http://localhost:3000

---

### 4️⃣ Vercel (самый простой)

#### A. Установка Vercel CLI

```bash
npm install -g vercel
```

#### B. Деплой

```bash
cd /opt/realestate/frontend

# Первый деплой (интерактивный)
vercel

# Production деплой
vercel --prod
```

#### C. Настройка переменных окружения в Vercel

Через веб-интерфейс:
1. Перейти на vercel.com
2. Выбрать проект
3. Settings → Environment Variables
4. Добавить:
   - `PG_USER`
   - `PG_PASS`
   - `PG_HOST` (внешний IP вашего PostgreSQL)
   - `PG_PORT`
   - `PG_DB`

⚠️ **Важно:** PostgreSQL должен принимать внешние подключения!

```sql
-- Разрешить подключения от Vercel
-- В pg_hba.conf добавить:
host    realdb    realuser    0.0.0.0/0    md5
```

✅ **Доступ:** https://your-project.vercel.app

---

## 🔒 Безопасность

### 1. Защита PostgreSQL

```bash
# Firewall для PostgreSQL
sudo ufw allow from <vercel-ip-range> to any port 5432
sudo ufw enable
```

### 2. Environment Variables

**Никогда не коммитьте:**
- `.env.local`
- `.env.production`
- `database credentials`

Используйте:
- Vercel Environment Variables
- Docker Secrets
- Vault / AWS Secrets Manager

### 3. HTTPS

**Production должен использовать HTTPS:**
```bash
# Let's Encrypt с certbot
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## 📊 Мониторинг

### PM2 Monitoring

```bash
# CPU, Memory, logs
pm2 monit

# Detailed info
pm2 show cian-frontend

# Restart on memory limit
pm2 start npm --name "cian-frontend" --max-memory-restart 1G -- start
```

### Logs

```bash
# PM2
pm2 logs cian-frontend --lines 100

# Docker
docker-compose logs -f --tail=100 frontend

# Nginx
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

---

## 🐛 Troubleshooting

### Проблема: npm install fails

```bash
# Очистить кеш
npm cache clean --force
rm -rf node_modules package-lock.json
npm install
```

### Проблема: Database connection error

```bash
# Проверить подключение к PostgreSQL
psql -h localhost -U realuser -d realdb -c "SELECT COUNT(*) FROM listings;"

# Проверить переменные окружения
cat .env.local
```

### Проблема: Port 3000 already in use

```bash
# Найти процесс
lsof -i :3000

# Убить процесс
kill -9 <PID>

# Или использовать другой порт
PORT=3001 npm run dev
```

### Проблема: Build fails

```bash
# Проверить версию Node.js
node --version  # должно быть 18+

# Обновить зависимости
npm update

# Пересобрать
rm -rf .next
npm run build
```

---

## 📈 Performance

### 1. Static Site Generation (SSG)

Для лучшей производительности используйте ISR (Incremental Static Regeneration):

```typescript
// app/listings/listing/[id]/page.tsx
export const revalidate = 3600; // Обновлять каждый час
```

### 2. CDN

Используйте CDN для статики:
- Vercel (встроенный CDN)
- CloudFlare
- AWS CloudFront

### 3. Database Connection Pooling

В `lib/db.ts` уже настроен connection pool:
```typescript
const pool = new Pool({
  max: 20,              // Максимум подключений
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 2000,
});
```

---

## ✅ Чеклист деплоя

- [ ] Node.js 20+ установлен
- [ ] npm install выполнен успешно
- [ ] .env.local настроен
- [ ] PostgreSQL доступен и заполнен данными
- [ ] npm run build прошел без ошибок
- [ ] npm start работает локально
- [ ] PM2 или Docker настроены (для production)
- [ ] Nginx reverse proxy настроен (опционально)
- [ ] Firewall настроен
- [ ] HTTPS сертификат установлен (для production)
- [ ] Логи доступны и мониторятся
- [ ] Backup PostgreSQL настроен

---

**🎉 Готово!** Ваш CIAN Analytics frontend развернут и работает!

Вопросы? Проверьте README.md или обратитесь к документации Next.js.
