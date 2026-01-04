# CIAN Analytics - Next.js Frontend

Современный веб-интерфейс для аналитики недвижимости с AI оценкой состояния квартир.

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
npm install
```

### 2. Настройка переменных окружения

Файл `.env.local` уже создан со стандартными настройками для локальной БД:

```env
PG_USER=realuser
PG_PASS=strongpass
PG_HOST=localhost
PG_PORT=5432
PG_DB=realdb
```

### 3. Запуск в режиме разработки

```bash
npm run dev
```

Откройте [http://localhost:3000](http://localhost:3000) в браузере.

### 4. Production build

```bash
npm run build
npm start
```

## 📊 Функционал

### Главная страница
- Поиск объявлений по адресу
- Красивый landing с градиентом
- Статистика: 100,000+ объявлений

### Страница поиска (`/listings/search`)
- Фильтры:
  - Цена (1-30 млн ₽)
  - Количество комнат (студия, 1-4+)
  - Тип сделки (продажа/аренда)
  - Продавец (собственник/агент/застройщик)
  - **AI состояние** (1-5 баллов)
  - Площадь (20-200 м²)
  - Этаж (2-40)

- Сортировка:
  - Недавно добавленные
  - По цене (дешевые/дорогие)
  - По цене за м²
  - По площади

### Детальная страница объявления (`/listings/listing/[id]`)
- Основная информация
- Фотогалерея
- История цен
- **AI оценка состояния** (1-5 баллов + описание)
- Цена за м²
- Геолокация

### Аналитика (`/analytics-ai`)
- Графики и визуализация
- AI аналитика

## 🗄️ База данных

Фронтенд работает с PostgreSQL через следующие таблицы:

```sql
listings              -- Объявления
listing_prices        -- История цен
listing_photos        -- Фотографии
```

### SQL запросы включают:
- AI condition score (1-5)
- Актуальная цена (последняя из listing_prices)
- Цена за м² (calculated)
- Главное фото (is_main = true)

## 🎨 Дизайн

- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS 4
- **Charts**: ECharts
- **Icons**: Heroicons
- **Typography**: Inter, Noto Sans

### Цветовая схема:
- Основной: Indigo (синий)
- Фон: Градиент blue-50 → indigo-100
- Текст: Gray-700, Indigo-900
- Акценты: Indigo-600

## 📁 Структура проекта

```
frontend/
├── app/                      # Next.js 14 App Router
│   ├── page.tsx             # Главная страница
│   ├── listings/
│   │   ├── search/page.tsx  # Поиск
│   │   └── listing/[id]/    # Детальная страница
│   ├── analytics-ai/        # AI аналитика
│   └── api/                 # API routes
├── components/              # React компоненты
│   ├── Header.tsx          # Шапка сайта
│   ├── Main.tsx            # Landing
│   ├── ListingGrid.tsx     # Сетка объявлений
│   ├── FilterPanel.tsx     # Фильтры
│   └── listing/            # Компоненты детальной страницы
├── lib/                     # Утилиты
│   ├── db.ts               # PostgreSQL connector
│   ├── types.ts            # TypeScript types
│   └── searchConfig.ts     # Конфигурация фильтров
├── public/                  # Статика
└── .env.local              # Переменные окружения
```

## 🔧 Технические детали

### TypeScript Types

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
  current_price: number;          // JOIN с listing_prices
  price_per_sqm: number;          // Calculated
  main_photo_url: string | null;  // JOIN с listing_photos
  condition_score: number | null; // AI оценка 1-5
  condition_label: string | null; // "Евроремонт", "Хорошее" и т.д.
  ai_analysis: string | null;     // Текст AI анализа
}
```

### SQL Example

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
```

## 🚀 Деплой

### Option 1: Vercel (рекомендуется)
```bash
vercel deploy
```

### Option 2: Docker
```bash
docker build -t cian-frontend .
docker run -p 3000:3000 cian-frontend
```

### Option 3: VPS
```bash
npm run build
pm2 start npm --name "cian-frontend" -- start
```

## 📝 TODO

- [ ] Добавить галерею фотографий (сейчас только одно фото)
- [ ] График истории цен на детальной странице
- [ ] Карта с объявлениями
- [ ] Сравнение объявлений
- [ ] Экспорт в Excel/PDF
- [ ] Уведомления о новых объявлениях
- [ ] Избранное

## 🤝 Интеграция с Backend

Фронтенд полностью интегрирован с:
- ✅ PostgreSQL (CIAN database)
- ✅ Таблицы: listings, listing_prices, listing_photos
- ✅ AI condition scores (1-5)
- ✅ Фильтры согласно production критериям
- ✅ Responsive design

---

**Версия**: 1.0.0  
**Адаптировано из**: HouseClick template  
**Для**: CIAN Analytics Platform
