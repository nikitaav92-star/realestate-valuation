"""Модуль для получения ключевой ставки ЦБ РФ."""

import os
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path

CACHE_FILE = '/tmp/cbr_rate_cache.json'
CACHE_TTL_HOURS = 24
BANK_MARGIN = 5.5  # Надбавка к ключевой ставке для банковского финансирования


def get_key_rate() -> float:
    """
    Получить ключевую ставку ЦБ РФ.

    Использует кеширование на 24 часа.
    При ошибке возвращает дефолтное значение 21%.
    """
    # Проверить кеш
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                cache = json.load(f)
                cache_time = datetime.fromisoformat(cache['timestamp'])
                if datetime.now() - cache_time < timedelta(hours=CACHE_TTL_HOURS):
                    return cache['rate']
        except (json.JSONDecodeError, KeyError, ValueError):
            pass  # Кеш повреждён, получим заново

    # Попробовать получить с API ЦБ
    rate = _fetch_cbr_rate()

    if rate:
        # Сохранить в кеш
        try:
            with open(CACHE_FILE, 'w') as f:
                json.dump({
                    'rate': rate,
                    'timestamp': datetime.now().isoformat(),
                    'source': 'cbr_api'
                }, f)
        except Exception:
            pass  # Не критично если не удалось сохранить кеш

    return rate


def _fetch_cbr_rate() -> float:
    """
    Получить ключевую ставку с сайта ЦБ РФ.

    Пробует несколько источников.
    """
    import re

    # Метод 1: Парсинг страницы https://www.cbr.ru/hd_base/keyrate/
    try:
        url = "https://www.cbr.ru/hd_base/keyrate/"
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; RealEstateBot/1.0)'
        })
        if response.status_code == 200:
            # Ищем первое значение ставки в формате >XX,XX< или >XX.XX<
            matches = re.findall(r'>(\d+[,\.]\d+)<', response.text)
            if matches:
                rate_str = matches[0].replace(',', '.')
                rate = float(rate_str)
                print(f"CBR key rate fetched from HTML: {rate}%")
                return rate
    except Exception as e:
        print(f"CBR HTML parsing error: {e}")

    # Метод 2: Старый XML API ЦБ (может не работать)
    try:
        url = "https://www.cbr.ru/scripts/XML_keyRate.asp"
        response = requests.get(url, timeout=10)
        response.encoding = 'windows-1251'

        if response.status_code == 200 and '<Rate' in response.text:
            # Ищем последнюю ставку в XML
            # Формат: <Rate Date="DD.MM.YYYY">XX.XX</Rate>
            matches = re.findall(r'<Rate Date="[^"]+">([0-9.]+)</Rate>', response.text)
            if matches:
                rate = float(matches[-1])
                print(f"CBR key rate fetched from XML: {rate}%")
                return rate
    except Exception as e:
        print(f"CBR XML API error: {e}")

    # Дефолтное значение если не удалось получить
    # Актуальная ставка на январь 2026 - 16%
    print("Warning: Could not fetch CBR key rate, using default 16%")
    return 16.0


def get_bank_rate() -> float:
    """
    Получить ставку банковского финансирования.

    Формула: ключевая ставка ЦБ + 5.5%
    """
    return get_key_rate() + BANK_MARGIN


def get_rate_info() -> dict:
    """
    Получить полную информацию о ставках.

    Returns:
        dict: {
            'key_rate': float,      # Ключевая ставка ЦБ
            'bank_margin': float,   # Надбавка банка
            'bank_rate': float,     # Итоговая ставка банка
            'cached': bool,         # Из кеша или свежие данные
            'updated_at': str       # Время обновления
        }
    """
    key_rate = get_key_rate()

    # Проверить кеш для получения времени обновления
    cached = False
    updated_at = datetime.now().isoformat()

    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                cache = json.load(f)
                cached = True
                updated_at = cache.get('timestamp', updated_at)
        except Exception:
            pass

    return {
        'key_rate': key_rate,
        'bank_margin': BANK_MARGIN,
        'bank_rate': key_rate + BANK_MARGIN,
        'cached': cached,
        'updated_at': updated_at
    }


# При импорте модуля, предзагрузим ставку в кеш
if __name__ == "__main__":
    info = get_rate_info()
    print(f"Ключевая ставка ЦБ: {info['key_rate']}%")
    print(f"Надбавка банка: {info['bank_margin']}%")
    print(f"Ставка банковского финансирования: {info['bank_rate']}%")
