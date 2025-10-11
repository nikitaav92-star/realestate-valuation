## AI-оценка состояния квартир по фотографиям

**Date:** 2025-10-11  
**Goal:** Анализ 50,000+ фото с минимальными затратами

---

## 🎯 Цель

Использовать GPT-4 Vision или Claude для оценки состояния квартир по фотографиям и присвоения рейтинга 1-5 для более точной оценки цены.

---

## 📊 Стратегия минимальных затрат

### Вариант 1: OpenAI GPT-4 Vision (РЕКОМЕНДУЕТСЯ)

**API:** GPT-4 Turbo with Vision

**Цены:**
- Input: $0.01 / 1K tokens
- **Images:** $0.01275 per image (high detail)
- **Images:** $0.00425 per image (low detail)

**Для 50,000 объявлений:**
- Объявлений: 50,000
- Фото на объявление: 1 (главное фото)
- Режим: low detail
- **Стоимость: 50,000 × $0.00425 = $212.50**

**Оптимизация:**
- Использовать low detail mode
- Анализировать только 1 главное фото
- Batch processing (50 фото за раз)
- Кэширование результатов

---

### Вариант 2: Claude 3.5 Sonnet (АЛЬТЕРНАТИВА)

**API:** Claude 3.5 Sonnet with vision

**Цены:**
- Input: $3 / 1M tokens
- **Images:** Считаются как ~1,600 tokens (~$0.0048)

**Для 50,000 объявлений:**
- **Стоимость: 50,000 × $0.0048 = $240**

**Преимущества:**
- Лучшее качество анализа
- Более детальные описания
- Понимание русского языка

---

### Вариант 3: Hybrid (ОПТИМАЛЬНЫЙ)

**Подход:**
1. GPT-4 Vision (low detail) для bulk оценки
2. Claude 3.5 для спорных случаев
3. Кэширование повторных оценок

**Для 50,000 объявлений:**
- GPT-4 Vision: 48,000 × $0.00425 = $204
- Claude 3.5: 2,000 × $0.0048 = $9.60
- **Итого: $213.60**

---

## 🏗️ Архитектура решения

### Этап 1: Сбор фотографий

```
CIAN API → Extract photo URLs → Save to DB
```

### Этап 2: Скачивание фото

```
DB (URLs) → Download images → Save locally/S3
```

### Этап 3: AI оценка

```
Images → GPT-4 Vision API → Condition rating (1-5) → Save to DB
```

### Этап 4: Использование в аналитике

```
Listings + Condition → Price adjustment → Better estimates
```

---

## 📋 Расширение схемы БД

### Новые таблицы:

```sql
-- Фотографии объявлений
CREATE TABLE listing_photos (
    id BIGSERIAL PRIMARY KEY,
    listing_id BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    photo_url TEXT NOT NULL,
    photo_order INT DEFAULT 0,  -- Порядок (0 = главное фото)
    is_main BOOLEAN DEFAULT FALSE,
    downloaded BOOLEAN DEFAULT FALSE,
    local_path TEXT,  -- Путь к скачанному файлу
    s3_url TEXT,  -- URL в S3 (если используется)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(listing_id, photo_url)
);

CREATE INDEX idx_listing_photos_listing ON listing_photos(listing_id);
CREATE INDEX idx_listing_photos_main ON listing_photos(listing_id, is_main) WHERE is_main;
CREATE INDEX idx_listing_photos_downloaded ON listing_photos(downloaded) WHERE NOT downloaded;

-- AI оценка состояния
CREATE TABLE listing_condition_ratings (
    id BIGSERIAL PRIMARY KEY,
    listing_id BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    condition_score INT NOT NULL CHECK (condition_score BETWEEN 1 AND 5),
    condition_label TEXT NOT NULL,  -- excellent, good, fair, poor, very_poor
    ai_model TEXT NOT NULL,  -- gpt-4-vision, claude-3.5-sonnet
    ai_analysis TEXT,  -- Детальное описание от AI
    confidence NUMERIC(3,2),  -- Уверенность (0.00-1.00)
    analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    cost_usd NUMERIC(10,4),  -- Стоимость анализа
    
    -- Детали анализа
    repair_quality TEXT,  -- excellent, good, average, poor
    furniture_condition TEXT,
    cleanliness TEXT,
    modern_design BOOLEAN,
    needs_renovation BOOLEAN,
    
    UNIQUE(listing_id)  -- Одна оценка на объявление
);

CREATE INDEX idx_condition_ratings_listing ON listing_condition_ratings(listing_id);
CREATE INDEX idx_condition_ratings_score ON listing_condition_ratings(condition_score);
CREATE INDEX idx_condition_ratings_analyzed ON listing_condition_ratings(analyzed_at DESC);

COMMENT ON TABLE listing_photos IS 'Photos from CIAN listings';
COMMENT ON TABLE listing_condition_ratings IS 'AI-based condition ratings (1-5 scale)';
COMMENT ON COLUMN listing_condition_ratings.condition_score IS '1=very poor, 2=poor, 3=fair, 4=good, 5=excellent';
```

---

## 🔧 Реализация

### Шаг 1: Извлечение URL фотографий

**Обновить mapper:**

```python
# etl/collector_cian/mapper_v2.py

def extract_photo_urls(offer: Dict[str, Any]) -> List[str]:
    """Extract photo URLs from offer.
    
    Returns
    -------
    list[str]
        List of photo URLs (ordered, main photo first)
    """
    photo_urls = []
    
    # Try different possible paths in API response
    for key in ("photos", "images", "photoUrls", "photo"):
        photos = offer.get(key)
        
        if isinstance(photos, list):
            for photo in photos:
                if isinstance(photo, dict):
                    # Extract URL from dict
                    url = photo.get("fullUrl") or photo.get("url") or photo.get("link")
                    if url:
                        photo_urls.append(str(url))
                elif isinstance(photo, str):
                    photo_urls.append(photo)
        elif isinstance(photos, dict):
            url = photos.get("fullUrl") or photos.get("url")
            if url:
                photo_urls.append(str(url))
    
    return photo_urls
```

---

### Шаг 2: Скачивание фотографий (опционально)

**Два подхода:**

#### A. Хранить только URLs (РЕКОМЕНДУЕТСЯ)

**Преимущества:**
- Нет затрат на хранение
- Быстрый сбор данных
- Фото всегда актуальные

**Недостатки:**
- Зависимость от CIAN CDN
- Фото могут удалиться

#### B. Скачивать и хранить локально/S3

**Преимущества:**
- Независимость от CIAN
- Постоянный доступ

**Недостатки:**
- Затраты на хранение (~10 GB для 50k)
- Медленнее

**Рекомендация:** Начать с URLs, скачивать по необходимости

---

### Шаг 3: AI оценка

#### Минимальный промпт для GPT-4 Vision:

```python
import openai
import base64

def analyze_apartment_condition(image_url: str) -> dict:
    """Analyze apartment condition using GPT-4 Vision.
    
    Parameters
    ----------
    image_url : str
        URL of apartment photo
        
    Returns
    -------
    dict
        {
            'condition_score': 1-5,
            'condition_label': 'excellent' | 'good' | 'fair' | 'poor' | 'very_poor',
            'analysis': 'Detailed description',
            'repair_quality': 'excellent' | 'good' | 'average' | 'poor',
            'needs_renovation': True | False,
            'confidence': 0.0-1.0
        }
    """
    
    prompt = """Оцени состояние квартиры по фотографии по шкале от 1 до 5:

1 - Очень плохое (требует капитального ремонта, старая отделка, видимые дефекты)
2 - Плохое (требует ремонта, устаревшая отделка, износ)
3 - Удовлетворительное (жилое состояние, но не новое)
4 - Хорошее (современный ремонт, качественная отделка)
5 - Отличное (новый ремонт, премиум отделка, дизайнерский интерьер)

Ответь в формате JSON:
{
  "condition_score": 1-5,
  "condition_label": "excellent/good/fair/poor/very_poor",
  "repair_quality": "excellent/good/average/poor",
  "cleanliness": "excellent/good/average/poor",
  "modern_design": true/false,
  "needs_renovation": true/false,
  "confidence": 0.0-1.0,
  "analysis": "Краткое описание (1-2 предложения)"
}"""
    
    response = openai.ChatCompletion.create(
        model="gpt-4-vision-preview",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url,
                            "detail": "low"  # ВАЖНО: low для экономии!
                        }
                    }
                ]
            }
        ],
        max_tokens=300,  # Ограничить ответ
        temperature=0.3,  # Консистентность
    )
    
    # Parse JSON response
    import json
    result = json.loads(response.choices[0].message.content)
    return result
```

---

## 💰 Оптимизация затрат

### Стратегия 1: Batch Processing (РЕКОМЕНДУЕТСЯ)

**Подход:** Обрабатывать по 100 объявлений за раз

```python
async def analyze_batch(photo_urls: List[str]) -> List[dict]:
    """Analyze multiple photos in parallel."""
    import asyncio
    
    # Use async to process 10 at a time
    semaphore = asyncio.Semaphore(10)
    
    async def analyze_one(url):
        async with semaphore:
            return analyze_apartment_condition(url)
    
    tasks = [analyze_one(url) for url in photo_urls]
    results = await asyncio.gather(*tasks)
    
    return results
```

**Экономия:** Параллельная обработка ускоряет в 10x

---

### Стратегия 2: Кэширование

**Подход:** Не анализировать повторно

```python
def get_or_analyze_condition(listing_id: int, photo_url: str):
    """Get cached rating or analyze if new."""
    
    # Check if already analyzed
    cached = get_cached_rating(listing_id)
    if cached:
        return cached
    
    # Analyze and cache
    rating = analyze_apartment_condition(photo_url)
    cache_rating(listing_id, rating)
    
    return rating
```

**Экономия:** 0% на повторные запуски

---

### Стратегия 3: Выборочный анализ

**Подход:** Анализировать только важные объявления

```python
def should_analyze(listing):
    """Decide if listing needs AI analysis."""
    
    # Analyze if:
    # 1. Price anomaly (too high/low for area)
    # 2. New listing (first_seen today)
    # 3. Price changed recently
    # 4. Missing manual rating
    
    if listing.price / listing.area_total > 300000:  # >300k per sqm
        return True
    
    if (datetime.now() - listing.first_seen).days < 1:
        return True
    
    return False
```

**Экономия:** Анализировать только 20-30% → **$42-64 вместо $212**

---

### Стратегия 4: Hybrid (GPT-4 + Claude)

**Подход:**
1. Быстрая оценка GPT-4 Vision (low detail) - $0.00425
2. Если confidence < 0.7 → Claude 3.5 - $0.0048
3. Если цена >20 млн → Claude 3.5 (точнее)

**Для 50,000:**
- GPT-4 (80%): 40,000 × $0.00425 = $170
- Claude (20%): 10,000 × $0.0048 = $48
- **Итого: $218**

**Преимущества:**
- Оптимальное качество/цена
- Точность для дорогих квартир
- Экономия на простых случаях

---

## 🏗️ Полная реализация

### 1. Расширение схемы БД

```sql
-- Apply: db/schema_v3_with_photos.sql
psql -h localhost -U realuser -d realdb -f db/schema_v3_with_photos.sql
```

### 2. Обновление mapper

```python
# etl/collector_cian/mapper_v3.py

from etl.models_v3 import Listing, ListingPhoto

def to_listing_with_photos(offer: Dict) -> tuple[Listing, List[ListingPhoto]]:
    """Extract listing and photos."""
    
    listing = to_listing(offer)
    
    photo_urls = extract_photo_urls(offer)
    photos = [
        ListingPhoto(
            listing_id=listing.id,
            photo_url=url,
            photo_order=i,
            is_main=(i == 0),
        )
        for i, url in enumerate(photo_urls)
    ]
    
    return listing, photos
```

### 3. AI модуль

```python
# etl/ai_evaluator/photo_analyzer.py

class PhotoAnalyzer:
    """AI-based photo analysis."""
    
    def __init__(self, provider: str = "openai"):
        self.provider = provider
        if provider == "openai":
            self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        elif provider == "anthropic":
            self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    def analyze_condition(
        self,
        photo_url: str,
        *,
        detail: str = "low",
    ) -> ConditionRating:
        """Analyze apartment condition."""
        
        if self.provider == "openai":
            return self._analyze_openai(photo_url, detail)
        else:
            return self._analyze_claude(photo_url)
```

### 4. Batch processor

```python
# etl/ai_evaluator/batch_processor.py

class BatchProcessor:
    """Process photos in batches for cost efficiency."""
    
    def __init__(self, batch_size: int = 50):
        self.batch_size = batch_size
        self.analyzer = PhotoAnalyzer("openai")
    
    async def process_listings(
        self,
        listing_ids: List[int],
    ) -> dict:
        """Process multiple listings."""
        
        total_cost = 0
        total_analyzed = 0
        
        for i in range(0, len(listing_ids), self.batch_size):
            batch = listing_ids[i:i + self.batch_size]
            
            # Analyze batch
            for listing_id in batch:
                rating = await self.analyze_listing(listing_id)
                total_cost += rating.cost_usd
                total_analyzed += 1
            
            # Progress
            print(f"Analyzed {total_analyzed}/{len(listing_ids)} "
                  f"(${total_cost:.2f})")
            
            # Rate limit
            await asyncio.sleep(1)
        
        return {
            "total_analyzed": total_analyzed,
            "total_cost": total_cost,
            "avg_cost": total_cost / total_analyzed,
        }
```

---

## 💡 Минимальные затраты - Пошаговый план

### План A: URL-only + On-demand анализ (МИНИМУМ)

**Подход:**
1. Собирать только URLs фотографий (бесплатно)
2. Анализировать AI только по запросу пользователя
3. Кэшировать результаты

**Затраты:**
- Сбор URLs: $0
- AI анализ: $0.00425 за объявление (только по запросу)
- Для 1000 объявлений: $4.25

**Реализация:**
```python
# В веб-интерфейсе
@app.route('/listings/<int:listing_id>/analyze')
def analyze_listing(listing_id):
    """Analyze listing condition on demand."""
    
    # Check cache
    rating = get_cached_rating(listing_id)
    if rating:
        return jsonify(rating)
    
    # Get main photo
    photo_url = get_main_photo_url(listing_id)
    
    # Analyze
    rating = analyzer.analyze_condition(photo_url)
    
    # Cache
    save_rating(listing_id, rating)
    
    return jsonify(rating)
```

---

### План B: Pre-analyze важные (ОПТИМАЛЬНЫЙ)

**Подход:**
1. Собрать URLs всех фотографий
2. AI анализ только для:
   - Цена >15 млн (премиум сегмент)
   - Аномалии цены (слишком дешево/дорого)
   - Новые объявления

**Затраты:**
- 30% от 50,000 = 15,000 объявлений
- 15,000 × $0.00425 = **$63.75**

**ROI:**
- Фокус на важных объявлениях
- Экономия 70%
- Лучшая точность оценки

---

### План C: Полный анализ с оптимизацией (МАКСИМУМ)

**Подход:**
1. Анализировать все 50,000
2. Low detail mode
3. Batch processing
4. Кэширование

**Затраты:**
- 50,000 × $0.00425 = **$212.50**

**Дополнительная экономия:**
- Использовать GPT-4o-mini (дешевле): $85
- Или только 1-2 фото вместо всех: $106

---

## 🎯 Рекомендуемая стратегия

### Фаза 1: URL Collection (Сейчас)

**Что делать:**
```python
# 1. Обновить mapper
def to_listing_with_photos(offer):
    listing = to_listing(offer)
    photo_urls = extract_photo_urls(offer)
    return listing, photo_urls

# 2. Сохранять URLs в БД
for offer in offers:
    listing, photo_urls = to_listing_with_photos(offer)
    save_listing(listing)
    save_photo_urls(listing.id, photo_urls)
```

**Стоимость:** $0  
**Время:** +0 (в рамках текущего сбора)

---

### Фаза 2: Selective AI Analysis (Позже)

**Что делать:**
```python
# Отфильтровать важные
important_listings = """
SELECT id FROM listings 
WHERE price > 15000000 
   OR price / area_total > 250000
   OR first_seen > NOW() - INTERVAL '1 day'
LIMIT 15000
"""

# Запустить batch анализ
python -m etl.ai_evaluator.cli analyze \
    --batch-size 50 \
    --model gpt-4-vision \
    --detail low \
    --filter important
```

**Стоимость:** $63.75  
**Время:** ~4 часа

---

### Фаза 3: Price Adjustment (Использование)

**Формула корректировки цены:**

```python
def adjust_price_by_condition(
    base_price: float,
    condition_score: int,
) -> float:
    """Adjust price based on condition rating.
    
    Adjustments:
    - Score 5 (excellent): +10%
    - Score 4 (good): +5%
    - Score 3 (fair): 0%
    - Score 2 (poor): -10%
    - Score 1 (very poor): -20%
    """
    
    adjustments = {
        5: 1.10,  # +10%
        4: 1.05,  # +5%
        3: 1.00,  # 0%
        2: 0.90,  # -10%
        1: 0.80,  # -20%
    }
    
    multiplier = adjustments.get(condition_score, 1.0)
    return base_price * multiplier
```

**SQL View:**

```sql
CREATE VIEW v_listings_adjusted_price AS
SELECT 
    l.*,
    lp.price AS original_price,
    lcr.condition_score,
    CASE 
        WHEN lcr.condition_score = 5 THEN lp.price * 1.10
        WHEN lcr.condition_score = 4 THEN lp.price * 1.05
        WHEN lcr.condition_score = 3 THEN lp.price * 1.00
        WHEN lcr.condition_score = 2 THEN lp.price * 0.90
        WHEN lcr.condition_score = 1 THEN lp.price * 0.80
        ELSE lp.price
    END AS adjusted_price
FROM listings l
JOIN LATERAL (...) lp ON true
LEFT JOIN listing_condition_ratings lcr ON l.id = lcr.listing_id;
```

---

## 📊 Сравнение подходов

| Подход | Объявлений | Стоимость | Время | Качество |
|--------|------------|-----------|-------|----------|
| **URL only** | 50,000 | $0 | 0ч | - |
| **On-demand** | ~1,000 | $4 | 1ч | Высокое |
| **Selective (30%)** | 15,000 | $64 | 4ч | Высокое |
| **Full (low detail)** | 50,000 | $213 | 12ч | Среднее |
| **Full (high detail)** | 50,000 | $637 | 12ч | Максимальное |

---

## 🎯 Итоговая рекомендация

### Этап 1: Сейчас (Бесплатно)

```bash
1. Собрать URLs фотографий (добавить в mapper)
2. Сохранить в БД (listing_photos table)
3. Стоимость: $0
```

### Этап 2: Через неделю ($64)

```bash
1. Выбрать важные объявления (30%)
2. Запустить batch AI анализ
3. Сохранить оценки в БД
4. Стоимость: $64
```

### Этап 3: Использование

```bash
1. Показывать рейтинг в UI
2. Корректировать цены
3. Фильтр по состоянию
4. Рекомендации для покупателей
```

---

## 🛠️ Implementation Files

### Создам следующие файлы:

1. `db/schema_v3_with_photos.sql` - Схема с фото
2. `etl/models_v3.py` - Модели с фото
3. `etl/collector_cian/mapper_v3.py` - Извлечение фото
4. `etl/ai_evaluator/__init__.py` - AI модуль
5. `etl/ai_evaluator/photo_analyzer.py` - Анализатор
6. `etl/ai_evaluator/batch_processor.py` - Batch обработка
7. `etl/ai_evaluator/cli.py` - CLI для анализа
8. `scripts/analyze_conditions.py` - Production скрипт

---

## 💰 Итоговые затраты

### Минимальная стратегия:

```
Сбор данных + URLs: $0.50
AI анализ (30%):     $64
───────────────────────
ИТОГО:               $64.50

ROI:
- Более точные оценки цен
- Рекомендации для покупателей
- Конкурентное преимущество
```

### Оптимальная стратегия:

```
Фаза 1: Собрать URLs           $0
Фаза 2: Анализ важных (15k)    $64
Фаза 3: On-demand анализ       $4 (по запросу)
───────────────────────────────────
ИТОГО первый запуск:           $64
Поддержка (месяц):            $10-20
```

---

## 🚀 Следующие шаги

### Немедленно:
1. ⏳ Обновить mapper для извлечения URLs фотографий
2. ⏳ Расширить схему БД (listing_photos)
3. ⏳ Протестировать извлечение

### На этой неделе:
1. ⏳ Реализовать AI модуль (GPT-4 Vision)
2. ⏳ Создать batch processor
3. ⏳ Протестировать на 100 объявлениях

### В этом месяце:
1. ⏳ Запустить анализ 15,000 важных объявлений
2. ⏳ Интегрировать оценки в UI
3. ⏳ Создать систему рекомендаций

---

**Document owner:** Cursor AI  
**Last updated:** 2025-10-11  
**Status:** Strategy Defined, Ready to Implement

