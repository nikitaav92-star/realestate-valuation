#!/usr/bin/env python3
"""Диагностика проблемы с CIAN - почему не извлекаются данные."""

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

def analyze_original_script():
    """Анализирует оригинальный скрипт и находит проблемы."""
    
    script_path = Path("scripts/test_captcha_strategy.py")
    
    if not script_path.exists():
        LOGGER.error("❌ Оригинальный скрипт не найден")
        return
    
    LOGGER.info("🔍 АНАЛИЗ ОРИГИНАЛЬНОГО СКРИПТА test_captcha_strategy.py")
    LOGGER.info("=" * 60)
    
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем проблемные места
    lines = content.split('\n')
    
    LOGGER.info("📋 НАЙДЕННЫЕ ПРОБЛЕМЫ:")
    
    # 1. Поиск извлечения данных
    data_extraction_found = False
    for i, line in enumerate(lines, 1):
        if "query_selector_all" in line and "LinkArea" in line:
            LOGGER.info(f"   Строка {i}: {line.strip()}")
            LOGGER.info(f"   ❌ ПРОБЛЕМА: Только подсчет элементов, НЕТ извлечения данных!")
            
            # Показываем следующие строки
            for j in range(i, min(i+5, len(lines))):
                if j < len(lines) and lines[j].strip():
                    LOGGER.info(f"      {j+1}: {lines[j].strip()}")
            data_extraction_found = True
    
    if not data_extraction_found:
        LOGGER.warning("   ❌ НЕ НАЙДЕНО: Извлечение данных объявлений")
    
    # 2. Поиск сохранения в БД
    db_save_found = False
    for i, line in enumerate(lines, 1):
        if any(keyword in line.lower() for keyword in ["insert", "save", "database", "postgres"]):
            LOGGER.info(f"   Строка {i}: {line.strip()}")
            db_save_found = True
    
    if not db_save_found:
        LOGGER.warning("   ❌ НЕ НАЙДЕНО: Сохранение в базу данных")
    
    # 3. Поиск извлечения содержимого
    content_extraction_found = False
    for i, line in enumerate(lines, 1):
        if any(keyword in line.lower() for keyword in ["textcontent", "innerhtml", "evaluate", "extract"]):
            LOGGER.info(f"   Строка {i}: {line.strip()}")
            content_extraction_found = True
    
    if not content_extraction_found:
        LOGGER.warning("   ❌ НЕ НАЙДЕНО: Извлечение содержимого элементов")
    
    LOGGER.info("\n🎯 ЗАКЛЮЧЕНИЕ:")
    LOGGER.info("   Оригинальный скрипт:")
    LOGGER.info("   ✅ Успешно обходит анти-бот защиту")
    LOGGER.info("   ✅ Загружает страницы CIAN")
    LOGGER.info("   ✅ Считает элементы на странице")
    LOGGER.info("   ❌ НЕ извлекает данные объявлений")
    LOGGER.info("   ❌ НЕ сохраняет в базу данных")

def check_database_status():
    """Проверяет статус базы данных."""
    
    LOGGER.info("\n🗄️ СТАТУС БАЗЫ ДАННЫХ:")
    LOGGER.info("=" * 60)
    
    try:
        import subprocess
        
        # Проверяем количество записей
        result = subprocess.run([
            "docker", "exec", "realestate-postgres-1", "psql", 
            "-U", "realuser", "-d", "realdb", "-c", 
            "SELECT COUNT(*) as total_listings FROM listings;"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            count_line = result.stdout.strip().split('\n')[-2]
            count = count_line.strip()
            LOGGER.info(f"   📊 Записей в БД: {count}")
            
            if int(count) <= 2:
                LOGGER.warning("   ⚠️  Только тестовые данные в БД")
                LOGGER.warning("   ❌ Реальные объявления НЕ сохраняются")
        else:
            LOGGER.error(f"   ❌ Ошибка БД: {result.stderr}")
            
    except Exception as e:
        LOGGER.error(f"   ❌ Ошибка проверки БД: {e}")

def check_logs():
    """Проверяет логи на предмет реального извлечения данных."""
    
    LOGGER.info("\n📋 АНАЛИЗ ЛОГОВ:")
    LOGGER.info("=" * 60)
    
    log_file = Path("logs/captcha_strategy.log")
    if not log_file.exists():
        LOGGER.warning("   ❌ Лог файл не найден")
        return
    
    with open(log_file, 'r') as f:
        lines = f.readlines()
    
    # Ищем упоминания извлечения данных
    extraction_mentions = 0
    for line in lines:
        if any(keyword in line.lower() for keyword in ["extract", "parse", "title", "price", "address"]):
            if "offers" not in line.lower() or "count" not in line.lower():
                extraction_mentions += 1
                if extraction_mentions <= 3:  # Показываем только первые 3
                    LOGGER.info(f"   {line.strip()}")
    
    if extraction_mentions == 0:
        LOGGER.warning("   ❌ В логах НЕТ упоминаний извлечения данных")
        LOGGER.warning("   ❌ Только подсчет элементов, но НЕ их содержимого")
    else:
        LOGGER.info(f"   ✅ Найдено {extraction_mentions} упоминаний извлечения данных")

def create_fix_recommendations():
    """Создает рекомендации по исправлению."""
    
    LOGGER.info("\n🛠️ РЕКОМЕНДАЦИИ ПО ИСПРАВЛЕНИЮ:")
    LOGGER.info("=" * 60)
    
    recommendations = [
        "1. ЗАМЕНИТЬ подсчет элементов на извлечение данных:",
        "   БЫЛО: offers = page.query_selector_all('[data-name=\"LinkArea\"]')",
        "   ДОЛЖНО БЫТЬ: offers_data = page.evaluate('() => { /* извлечение данных */ }')",
        "",
        "2. ДОБАВИТЬ извлечение содержимого:",
        "   - title = card.querySelector('[data-mark=\"OfferTitle\"]').textContent",
        "   - price = card.querySelector('[data-mark=\"MainPrice\"]').textContent", 
        "   - address = card.querySelector('[data-mark=\"GeoLabel\"]').textContent",
        "",
        "3. ДОБАВИТЬ сохранение в базу данных:",
        "   - Подключение к PostgreSQL",
        "   - INSERT запросы для listings и listing_prices",
        "   - Обработка ошибок и дубликатов",
        "",
        "4. ИСПРАВИТЬ структуру данных:",
        "   - Парсинг цен (убрать пробелы, ₽)",
        "   - Парсинг комнат (студия = 0)",
        "   - Парсинг площади (убрать м²)",
        "",
        "5. ДОБАВИТЬ валидацию:",
        "   - Проверка обязательных полей",
        "   - Проверка форматов данных",
        "   - Обработка ошибок парсинга"
    ]
    
    for rec in recommendations:
        LOGGER.info(f"   {rec}")

def show_real_vs_fake_data():
    """Показывает разницу между реальными и фейковыми данными."""
    
    LOGGER.info("\n🔍 СРАВНЕНИЕ: РЕАЛЬНЫЕ vs ФЕЙКОВЫЕ ДАННЫЕ:")
    LOGGER.info("=" * 60)
    
    LOGGER.info("📊 ФЕЙКОВЫЕ ДАННЫЕ (logs/demo_cian_data.json):")
    LOGGER.info("   ❌ ID: 1000000, 1000001, 1000002... (искусственные)")
    LOGGER.info("   ❌ URL: https://www.cian.ru/sale/flat/1000000/ (не существуют)")
    LOGGER.info("   ❌ Адреса: Москва, Арбат, 15 (сгенерированы)")
    LOGGER.info("   ❌ Цены: 8,786,145 ₽ (случайные)")
    LOGGER.info("   ❌ AI анализ: 'Евроремонт (3/5)' (фейковый)")
    
    LOGGER.info("\n✅ РЕАЛЬНЫЕ ДАННЫЕ (что должно быть):")
    LOGGER.info("   ✅ ID: 12345678, 87654321... (реальные ID с CIAN)")
    LOGGER.info("   ✅ URL: https://www.cian.ru/sale/flat/12345678/ (работающие ссылки)")
    LOGGER.info("   ✅ Адреса: Москва, ул. Ленина, 45, кв. 12 (реальные)")
    LOGGER.info("   ✅ Цены: 15 500 000 ₽ (актуальные)")
    LOGGER.info("   ✅ AI анализ: 'Хорошее состояние, нужен косметический ремонт'")

if __name__ == "__main__":
    LOGGER.info("🔍 ДИАГНОСТИКА ПРОБЛЕМЫ С CIAN")
    LOGGER.info("=" * 60)
    
    analyze_original_script()
    check_database_status()
    check_logs()
    create_fix_recommendations()
    show_real_vs_fake_data()
    
    LOGGER.info("\n🎯 ИТОГОВЫЙ ВЫВОД:")
    LOGGER.info("   Оригинальный скрипт test_captcha_strategy.py")
    LOGGER.info("   УСПЕШНО обходит анти-бот защиту, но")
    LOGGER.info("   НЕ извлекает реальные данные объявлений!")
    LOGGER.info("   ")
    LOGGER.info("   Демо-данные - это ИСКУССТВЕННО созданные примеры,")
    LOGGER.info("   показывающие как ДОЛЖНЫ выглядеть реальные данные.")

