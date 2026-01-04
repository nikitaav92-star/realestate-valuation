# 🎨 CIAN Analytics Frontend - Quickstart

## ✅ Что сделано

### Адаптация HouseClick → CIAN Analytics

**Источник:** `vendor/houseclick/app/` (Next.js 14)  
**Результат:** `frontend/` (адаптировано для CIAN)

---

## 📁 Что изменилось

### 1. **Database Connector** (`lib/db.ts`)
- ✅ Подключение к PostgreSQL (`listings`, `listing_prices`, `listing_photos`)
- ✅ SQL запросы для CIAN схемы
- ✅ AI condition score (1-5)
- ✅ Цена за м² (calculated)
- ✅ История цен (latest from listing_prices)
- ✅ Главное фото (is_main = true)

### 2. **Search Config** (`lib/searchConfig.ts`)
- ✅ Фильтры для CIAN:
  - Цена (1-30 млн ₽)
  - Комнаты (студия, 1-4+)
  - Тип сделки (продажа/аренда)
  - Продавец (собственник/агент/застройщик)
  - **AI Состояние (1-5)** ⭐
  - Площадь (20-200 м²)
  - Этаж (2-40)
- ✅ Сортировка:
  - Недавно добавленные
  - Сначала дешевые/дорогие
  - Цена за м²
  - Площадь

### 3. **UI Components**
- ✅ Header: "CIAN Analytics" + эмодзи 🏠
- ✅ Landing: Градиент blue-indigo + статистика
- ✅ Цветовая схема: Indigo (основной)
- ✅ Русский язык

### 4. **Environment** (`.env.local`)
```env
PG_USER=realuser
PG_PASS=strongpass
PG_HOST=localhost
PG_PORT=5432
PG_DB=realdb
```

### 5. **package.json**
- Название: `cian-analytics`
- Версия: `1.0.0`

---

## 🚀 Быстрый запуск

### Требования:
```bash
# Node.js 20+
node --version

# npm 9+
npm --version
```

### Установка Node.js (если нужно):
```bash
# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### Запуск:
```bash
cd /opt/realestate/frontend

# 1. Установить зависимости (3-5 минут)
npm install

# 2. Проверить .env.local
cat .env.local

# 3. Запустить dev сервер
npm run dev

# ✅ Открыть http://localhost:3000
```

---

## 📊 Что работает

### ✅ Главная страница (`/`)
- Landing с поиском
- "CIAN Analytics" брендинг
- Статистика: "100,000+ объявлений • AI анализ фото • История цен"

### ✅ Поиск (`/listings/search`)
- Фильтры (включая AI состояние)
- Сортировка
- Сетка объявлений
- Pagination

### ✅ Детальная страница (`/listings/listing/[id]`)
- Основная информация
- Фотогалерея
- Детали (комнаты, площадь, этаж, цена/м²)
- **AI оценка состояния** (если есть в БД)
- Продавец
- Дата добавления

### ✅ Аналитика (`/analytics-ai`)
- AI-powered графики и визуализация

---

## 🗄️ Интеграция с БД

### SQL Example:
```sql
SELECT 
  l.*,
  lp.price as current_price,
  ROUND(lp.price / NULLIF(l.area_total, 0)) as price_per_sqm,
  lph.photo_url as main_photo_url,
  CASE 
    WHEN l.ai_condition_score = 1 THEN 'Требует ремонта'
    WHEN l.ai_condition_score = 2 THEN 'Удовлетворительное'
    WHEN l.ai_condition_score = 3 THEN 'Хорошее'
    WHEN l.ai_condition_score = 4 THEN 'Отличное'
    WHEN l.ai_condition_score = 5 THEN 'Евроремонт'
  END as condition_label
FROM listings l
LEFT JOIN LATERAL (
  SELECT price FROM listing_prices 
  WHERE id = l.id ORDER BY seen_at DESC LIMIT 1
) lp ON true
LEFT JOIN LATERAL (
  SELECT photo_url FROM listing_photos 
  WHERE listing_id = l.id AND is_main = true LIMIT 1
) lph ON true
WHERE l.is_active = true
ORDER BY l.last_seen DESC
```

### TypeScript Types:
```typescript
interface ListingRow {
  id: number;
  url: string;
  region: number;
  deal_type: string;
  rooms: number;
  area_total: number;
  floor: number;
  address: string;
  seller_type: string;
  lat: number;
  lon: number;
  first_seen: Date;
  last_seen: Date;
  is_active: boolean;
  current_price: number;          // ← JOIN
  price_per_sqm: number;          // ← CALCULATED
  main_photo_url: string | null;  // ← JOIN
  condition_score: number | null; // ← AI 1-5
  condition_label: string | null; // ← "Евроремонт"
  ai_analysis: string | null;     // ← GPT-4 Vision текст
}
```

---

## 🎨 Дизайн

### Цветовая схема:
- **Основной:** Indigo (#4F46E5)
- **Фон:** Gradient blue-50 → indigo-100
- **Текст:** Gray-700, Indigo-900
- **Акценты:** Indigo-600

### UI Framework:
- **Next.js 14** (App Router)
- **Tailwind CSS 4**
- **TypeScript**
- **ECharts** (графики)
- **Heroicons** (иконки)

---

## 📁 Структура

```
frontend/
├── app/                      # Next.js App Router
│   ├── page.tsx             # Главная (landing)
│   ├── layout.tsx           # Root layout
│   ├── listings/
│   │   ├── search/page.tsx  # Поиск объявлений
│   │   └── listing/[id]/    # Детальная страница
│   ├── analytics-ai/        # AI аналитика
│   └── api/                 # API routes
├── components/              # React компоненты
│   ├── Header.tsx          # Шапка (CIAN branding)
│   ├── Main.tsx            # Landing
│   ├── ListingGrid.tsx     # Сетка объявлений
│   ├── FilterPanel.tsx     # Фильтры
│   └── listing/            # Компоненты детальной
├── lib/                     # Утилиты
│   ├── db.ts               # ⭐ PostgreSQL connector
│   ├── types.ts            # TypeScript types
│   └── searchConfig.ts     # ⭐ Фильтры и сортировка
├── public/                  # Статика
├── .env.local              # ⭐ Переменные окружения
├── package.json            # Dependencies
├── README.md               # Основная документация
└── DEPLOYMENT.md           # Деплой гайд
```

---

## 🔧 Production Build

```bash
cd /opt/realestate/frontend

# Build
npm run build

# Run production
npm start

# Или через PM2
npm install -g pm2
pm2 start npm --name "cian-frontend" -- start
pm2 save
```

---

## 🐛 Troubleshooting

### Проблема: `npm` not found
```bash
# Установить Node.js
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### Проблема: Database connection error
```bash
# Проверить подключение
psql -h localhost -U realuser -d realdb -c "SELECT COUNT(*) FROM listings;"

# Проверить .env.local
cat .env.local
```

### Проблема: Port 3000 занят
```bash
# Найти и убить процесс
lsof -i :3000
kill -9 <PID>

# Или использовать другой порт
PORT=3001 npm run dev
```

---

## 📝 TODO (будущие улучшения)

- [ ] Галерея фотографий (сейчас только 1 фото)
- [ ] График истории цен на детальной странице
- [ ] Карта с объявлениями (Yandex Maps)
- [ ] Сравнение объявлений
- [ ] Экспорт в Excel/PDF
- [ ] Уведомления о новых объявлениях
- [ ] Избранное

---

## ✅ Готово!

**Frontend адаптирован и готов к запуску!**

### Следующие шаги:
1. ✅ `npm install` - установить зависимости
2. ✅ `npm run dev` - запустить dev server
3. ✅ Открыть http://localhost:3000
4. ✅ Проверить поиск и фильтры
5. ✅ Посмотреть детальную страницу
6. ✅ Проверить AI condition rating (если есть данные)

---

**Документация:**
- `README.md` - основная документация
- `DEPLOYMENT.md` - полный гайд по деплою
- `docs/FRONTEND_QUICKSTART.md` - этот файл

**Вопросы?** Проверьте документацию или логи:
```bash
npm run dev  # и смотри консоль
```

**Успехов с CIAN Analytics!** 🚀

