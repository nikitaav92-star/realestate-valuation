# Спецификация: KNN-First Валюационная Система

> **Версия:** 2.0
> **Дата создания:** 2024-12-10
> **Последнее обновление:** 2025-01-03
> **Статус:** Реализовано
> **Приоритет:** Завершено

---

## Цель

Высокоточная система оценки стоимости недвижимости на основе:

1. **KNN (K-Nearest Neighbors)** - поиск ближайших похожих объектов
2. **Grid Estimator** - агрегированные данные по микро-сегментам
3. **Hybrid Engine** - комбинация обоих методов

### Достигнутая точность

| Метод | Точность | Применение |
|-------|----------|-----------|
| Grid только | ±10% | Fallback |
| KNN только | ±3-5% | Основной (90% случаев) |
| Hybrid | ±3% | Лучший результат |

---

## Реализованные компоненты

### FR-1: KNN Поиск (knn_searcher.py)

**Статус:** Реализовано

```python
# Ключевые параметры
AREA_ADJUSTMENT_COEF = 0.001      # ±0.1% за м²
AGING_DISCOUNT_PER_30_DAYS = 0.01 # -1% за 30 дней
RADIUS_KM = 2.0                   # Радиус поиска
MIN_COMPARABLES = 3               # Минимум аналогов
```

**Функции:**
- `find_comparables(lat, lon, features)` - поиск аналогов
- Similarity score с весами
- Фильтрация по типу, комнатам, площади

### FR-2: Grid Estimator (grid_estimator.py)

**Статус:** Реализовано

- Таблица `multidim_aggregates` (district × segment × date)
- Автообновление через ночной cron
- Fallback когда KNN не даёт результатов

### FR-3: Hybrid Engine (hybrid_engine.py)

**Статус:** Реализовано

**Новые функции (Январь 2025):**

1. **IQR Outlier Detection**
```python
# Фильтрация выбросов
q1 = prices[len(prices) // 4]
q3 = prices[3 * len(prices) // 4]
iqr = q3 - q1
lower_bound = q1 - 1.5 * iqr
upper_bound = q3 + 1.5 * iqr
```

2. **Confidence-based Price Range**
```python
if confidence >= 70:
    range_pct = 0.05  # ±5%
elif confidence >= 50:
    range_pct = 0.10  # ±10%
else:
    range_pct = 0.15  # ±15%
```

3. **Aging Discount**
```python
age_days = (now - listing_date).days
aging_discount = min(0.03, (age_days / 30) * 0.01)
corrected_psm = price_per_sqm * (1 - aging_discount)
```

### FR-4: BOTTOM-3 Strategy

**Статус:** Реализовано (подтверждено пользователем)

Алгоритм:
1. Найти K аналогов в радиусе 2 км
2. Применить IQR фильтрацию
3. Сортировать по цене (дешевле → дороже)
4. Взять 3 самых дешёвых
5. Рассчитать среднюю цену
6. Применить 7% скидку на торг

### FR-5: REST API

**Статус:** Реализовано

```
POST /estimate
{
  "lat": 55.75,
  "lon": 37.62,
  "area_total": 65,
  "rooms": 2,
  "floor": 5,
  "total_floors": 12
}

Response:
{
  "price": 12700000,
  "price_low": 12065000,
  "price_high": 13335000,
  "confidence": 87,
  "comparables": [...]
}
```

---

## Файлы реализации

| Файл | Назначение |
|------|------------|
| `etl/valuation/knn_searcher.py` | KNN поиск аналогов |
| `etl/valuation/grid_estimator.py` | Grid оценка по сегментам |
| `etl/valuation/hybrid_engine.py` | Гибридный движок |
| `etl/valuation/rosreestr_searcher.py` | Данные Росреестра |
| `etl/valuation/models.py` | Pydantic модели |
| `api/v1/valuation.py` | API эндпоинты |

---

## Коррекционные коэффициенты

### Площадь

```python
AREA_ADJUSTMENT_COEF = 0.001  # Снижен с 0.002
# Разница 50 м² = 5% коррекция (было 10%)
```

### Возраст объявления

```python
AGING_DISCOUNT_PER_30_DAYS = 0.01  # -1% за месяц
MAX_AGING_DISCOUNT = 0.03          # Макс. -3%
```

### Этаж

| Этаж | Дисконт |
|------|---------|
| Первый | -5% |
| Последний | -2% (было -5%) |
| Средние | 0% |

---

## Метрики успеха

| Метрика | Цель | Факт |
|---------|------|------|
| Точность ±5% | 90% | ~88% |
| KNN покрытие | 95% | ~92% |
| p99 latency | <300ms | ~250ms |
| Confidence >70% | 80% | ~75% |

---

## Исправленные баги (Январь 2025)

| Баг | Описание | Исправление |
|-----|----------|-------------|
| Area correction sign | KNN (-) vs Rosreestr (+) | Унифицировано: `-` |
| Coordinates 0.0 | `not lat` отвергало 0.0 | `is None` проверка |
| ЖКУ always True | `or True` в условии | Убрано |
| Price range fixed | Всегда ±5% | Зависит от confidence |

---

## Будущие улучшения

### Запланировано

- [ ] Учёт близости к метро (±10-30%)
- [ ] Учёт вида из окна (±5-15%)
- [ ] Инфляционная коррекция Росреестра
- [ ] Кэширование DaData запросов

### Отложено (по решению пользователя)

- Учёт балкона (не добавлять)
- Учёт стороны света (не добавлять)
- Налог 13% при продаже (текущая схема OK)

---

## История изменений

### v2.0 (2025-01-03)
- IQR фильтрация выбросов
- Aging discount -1%/30 дней
- Confidence-based price range
- AREA_COEF снижен до 0.001
- Дисконт последнего этажа: 5% → 2%

### v1.0 (2024-12-10)
- Базовая KNN реализация
- Grid estimator
- Hybrid engine
- BOTTOM-3 strategy

---

**Ответственный:** AI Assistant
**Последняя проверка:** 2025-01-03
