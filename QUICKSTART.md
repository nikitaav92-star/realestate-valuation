# 🚀 БЫСТРЫЙ СТАРТ - Система оценки недвижимости

## ✅ ЧТО УЖЕ ГОТОВО

```
✓ База данных: 13,928 объявлений
✓ Цены: 10,976 (78.8%)
✓ Координаты: 7,440 (53.4%)
✓ Сегментация: 61 сегмент
✓ Агрегаты: 16 активных
```

---

## 📋 ШАГ 1: Подготовка данных

### 1.1 Обновить агрегаты (один раз в день)

```bash
cd /home/ubuntu/realestate
source venv/bin/activate
python3 scripts/run_aggregation.py
```

**Результат:**
```
📊 Aggregating for 2025-12-11...
✅ Inserted 16 aggregates
```

---

## 🔥 ШАГ 2: Запустить API сервер

```bash
cd /home/ubuntu/realestate
source venv/bin/activate
uvicorn api.v1.valuation:app --host 0.0.0.0 --port 8000
```

**Проверка:** Откройте в браузере `http://localhost:8000`

---

## 🧪 ШАГ 3: Протестировать систему

### Вариант А: Через curl

```bash
curl -X POST http://localhost:8000/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "lat": 55.7558,
    "lon": 37.6173,
    "area_total": 65.0,
    "rooms": 2,
    "floor": 5,
    "total_floors": 9,
    "building_type": "panel"
  }'
```

### Вариант Б: Через Python

Создайте файл `test.py`:

```python
import requests

data = {
    "lat": 55.7558,
    "lon": 37.6173,
    "area_total": 65.0,
    "rooms": 2,
    "floor": 5,
    "total_floors": 9,
    "building_type": "panel"
}

response = requests.post("http://localhost:8000/estimate", json=data)
result = response.json()

print(f"💰 Цена: {result['estimated_price']:,.0f} ₽")
print(f"📊 Цена/м²: {result['estimated_price_per_sqm']:,.0f} ₽")
print(f"🎯 Уверенность: {result['confidence']}%")
print(f"🔧 Метод: {result['method_used']}")
print(f"📈 Диапазон: {result['price_range_low']:,.0f} - {result['price_range_high']:,.0f} ₽")
```

Запустите:
```bash
python3 test.py
```

---

## 📊 ПРИМЕР ОТВЕТА

```json
{
  "estimated_price": 15250000,
  "estimated_price_per_sqm": 234615,
  "price_range_low": 13725000,
  "price_range_high": 16775000,
  "confidence": 75,
  "method_used": "hybrid_knn_heavy",
  "grid_weight": 0.2,
  "knn_weight": 0.8,
  "comparables_count": 10,
  "timestamp": "2025-12-10T12:00:00"
}
```

---

## 🔄 ЕЖЕДНЕВНОЕ ОБСЛУЖИВАНИЕ

### Автоматическая агрегация через cron

```bash
crontab -e
```

Добавьте:
```
# Ежедневная агрегация в 2:00
0 2 * * * cd /home/ubuntu/realestate && source venv/bin/activate && python3 scripts/run_aggregation.py >> logs/aggregation.log 2>&1
```

---

## 🛠️ КОМАНДЫ ДЛЯ РАБОТЫ

### Посмотреть статистику базы

```bash
psql postgresql://realuser:strongpass123@localhost:5432/realdb -c "
SELECT 
    COUNT(*) as total,
    COUNT(initial_price) as with_price,
    COUNT(lat) as with_coords,
    COUNT(property_segment_id) as with_segment
FROM listings;
"
```

### Проверить агрегаты

```bash
psql postgresql://realuser:strongpass123@localhost:5432/realdb -c "
SELECT 
    COUNT(*) as segments,
    SUM(total_listings) as total_listings,
    AVG(confidence_score)::int as avg_confidence
FROM multidim_aggregates
WHERE date = CURRENT_DATE;
"
```

### Запустить дополнительное геокодирование

```bash
cd /home/ubuntu/realestate
source venv/bin/activate
python3 scripts/geocode_all_listings.py
```

---

## 🎯 ПАРАМЕТРЫ API

### Обязательные:
- `area_total` - площадь (м²)

### Опциональные:
- `lat`, `lon` - координаты (для KNN)
- `district_id` - ID района (для Grid)
- `rooms` - количество комнат (1-10)
- `floor` - этаж
- `total_floors` - всего этажей
- `building_type` - тип дома: `panel`, `brick`, `monolithic`, `block`, `wood`, `other`
- `has_elevator` - наличие лифта (true/false)
- `has_parking` - наличие парковки (true/false)

### Query параметры:
- `k` - количество сопоставимых объектов (по умолчанию: 10)
- `max_distance_km` - макс. радиус поиска (по умолчанию: 5.0)
- `max_age_days` - макс. возраст объявлений (по умолчанию: 90)

---

## 🌐 SWAGGER ДОКУМЕНТАЦИЯ

После запуска API откройте:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

---

## ❓ TROUBLESHOOTING

### API не запускается

```bash
# Проверить, занят ли порт
sudo lsof -i :8000

# Убить процесс
sudo kill -9 <PID>
```

### База данных недоступна

```bash
# Проверить PostgreSQL
sudo systemctl status postgresql

# Проверить подключение
psql postgresql://realuser:strongpass123@localhost:5432/realdb -c "SELECT 1;"
```

### Мало данных для оценки

```bash
# Запустить парсер CIAN (если еще не запущен)
cd /home/ubuntu/realestate
source venv/bin/activate
python3 -m etl.collector_cian.main
```

---

## 📞 ПОДДЕРЖКА

Все файлы системы:
```
etl/valuation/         - движок оценки
api/v1/valuation.py    - REST API
scripts/               - утилиты
db/migrations/         - миграции БД
```

**Логи API:** `api.log` в корне проекта

**Все готово! Запускайте! 🚀**

