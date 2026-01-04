# Исправленные баги валюации (Январь 2025)

> **Дата исправления:** 2025-01-03
> **Статус:** Закрыто

---

## BUG-101: ЖКУ всегда включались

**Файл:** `api/v1/investment_calculator.py:150`

**Проблема:**
```python
# До исправления
if params.include_utilities or True:  # BUG! Всегда True
    expenses += utilities_cost
```

**Решение:**
```python
# После исправления
if params.include_utilities:
    expenses += utilities_cost
```

**Влияние:** Расходы на ЖКУ добавлялись даже когда пользователь их отключал.

---

## BUG-102: Координаты 0.0 отвергались как invalid

**Файл:** `api/v1/valuation.py:311`

**Проблема:**
```python
# До исправления
if not property_data.lat or not property_data.lon:
    # 0.0 трактуется как False!
    raise ValueError("Invalid coordinates")
```

**Решение:**
```python
# После исправления
if property_data.lat is None or property_data.lon is None:
    raise ValueError("Invalid coordinates")
```

**Влияние:** Объекты на экваторе/нулевом меридиане (теоретически) не могли быть оценены.

---

## BUG-103: Противоречие в коррекции площади

**Файлы:**
- `etl/valuation/knn_searcher.py:228-230`
- `etl/valuation/rosreestr_searcher.py:273`

**Проблема:**
```python
# KNN: ВЫЧИТАНИЕ
correction_factor = 1.0 - (AREA_ADJUSTMENT_COEF * area_diff)

# Rosreestr: СЛОЖЕНИЕ (противоположный знак!)
correction_factor = 1.0 + (AREA_ADJUSTMENT_COEF * area_diff)
```

**Решение:**
Унифицирована формула с вычитанием:
```python
correction_factor = 1.0 - (AREA_ADJUSTMENT_COEF * area_diff)
```

**Влияние:** При комбинировании источников оценки были несовместимы.

---

## BUG-104: Диапазон цен всегда ±5%

**Файл:** `etl/valuation/hybrid_engine.py:73-75`

**Проблема:**
```python
# До исправления
price_low = estimated_price * 0.95   # Всегда ±5%
price_high = estimated_price * 1.05
```

**Решение:**
```python
# После исправления
if confidence >= 70:
    range_pct = 0.05
elif confidence >= 50:
    range_pct = 0.10
else:
    range_pct = 0.15

price_low = estimated_price * (1 - range_pct)
price_high = estimated_price * (1 + range_pct)
```

**Влияние:** При низкой уверенности пользователь получал слишком узкий диапазон.

---

## BUG-105: Fallback фильтрации возвращал всё

**Файл:** `etl/valuation/knn_searcher.py:161-163`

**Проблема:**
```python
# До исправления
if len(filtered) < 3 and len(candidates) >= 3:
    return candidates  # Возвращал ВСЁ, включая отфильтрованное!
```

**Решение:**
```python
# После исправления
if len(filtered) < 3 and len(candidates) >= 3:
    remaining = [c for c in candidates if c not in filtered]
    remaining_sorted = sorted(remaining, key=lambda x: x.get('distance_km', 999))
    needed = min(5 - len(filtered), len(remaining_sorted))
    filtered.extend(remaining_sorted[:needed])
return filtered if filtered else candidates[:5]
```

**Влияние:** Несопоставимые объекты попадали в расчёт.

---

## Связанные улучшения

В рамках исправления багов также добавлены:

1. **IQR фильтрация** - удаление ценовых выбросов
2. **Aging discount** - учёт возраста объявлений (-1%/30 дней)
3. **Коэффициент площади** - снижен с 0.002 до 0.001
4. **interest_price > 0** - валидация в инвест. калькуляторе

---

**Исправил:** AI Assistant
**Проверено:** Пользователь
