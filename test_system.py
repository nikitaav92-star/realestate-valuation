#!/usr/bin/env python3
"""
Системный тест работоспособности Real Estate Platform
Проверяет все основные компоненты системы
"""
import os
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Тест импорта зависимостей"""
    print("🔍 Тест 1: Проверка зависимостей...")
    required = ['psycopg2', 'fastapi', 'uvicorn', 'httpx', 'playwright', 'pydantic', 'orjson', 'yaml', 'dotenv']
    optional = ['flask', 'psycopg']
    missing_required = []
    missing_optional = []
    
    for module in required:
        try:
            __import__(module)
        except ImportError:
            missing_required.append(module)
    
    for module in optional:
        try:
            __import__(module)
        except ImportError:
            missing_optional.append(module)
    
    if missing_required:
        print(f"   ❌ Отсутствуют обязательные модули: {', '.join(missing_required)}")
        return False
    
    if missing_optional:
        print(f"   ⚠️  Отсутствуют опциональные модули: {', '.join(missing_optional)}")
    
    print("   ✅ Все обязательные зависимости установлены")
    return True

def test_database():
    """Тест подключения к базе данных"""
    print("\n🔍 Тест 2: Подключение к PostgreSQL...")
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        dsn = os.getenv('PG_DSN', 'postgresql://realuser:strongpass123@localhost:5432/realdb')
        import psycopg2
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        
        # Проверка таблиц
        cur.execute("SELECT COUNT(*) FROM listings")
        listings_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM listing_prices")
        prices_count = cur.fetchone()[0]
        
        cur.execute("SELECT AVG(price)::bigint, MIN(price)::bigint, MAX(price)::bigint FROM listing_prices")
        avg_price, min_price, max_price = cur.fetchone()
        
        conn.close()
        
        print(f"   ✅ Подключение успешно")
        print(f"   📊 Объявлений: {listings_count:,}")
        print(f"   📊 Записей цен: {prices_count:,}")
        print(f"   💰 Средняя цена: {avg_price:,} ₽")
        print(f"   💰 Диапазон: {min_price:,} - {max_price:,} ₽")
        return True
    except Exception as e:
        print(f"   ❌ Ошибка БД: {e}")
        return False

def test_etl_cli():
    """Тест ETL CLI"""
    print("\n🔍 Тест 3: ETL CLI команды...")
    try:
        from etl.collector_cian.cli import command_pull, command_to_db
        print("   ✅ CLI модули импортированы")
        
        # Проверка наличия payload файлов
        payload_path = Path("etl/collector_cian/payloads/base.yaml")
        if payload_path.exists():
            print(f"   ✅ Payload файл найден: {payload_path}")
        else:
            print(f"   ⚠️  Payload файл не найден: {payload_path}")
        
        return True
    except Exception as e:
        print(f"   ❌ Ошибка ETL: {e}")
        return False

def test_web_interfaces():
    """Тест веб-интерфейсов"""
    print("\n🔍 Тест 4: Веб-интерфейсы...")
    results = []
    
    # Проверка Flask приложения (опционально)
    try:
        from web.app import app as flask_app
        print("   ✅ Flask приложение загружено")
        results.append(True)
    except ImportError:
        print("   ⚠️  Flask не установлен (опционально)")
        results.append(None)
    except Exception as e:
        print(f"   ⚠️  Flask ошибка: {e}")
        results.append(None)
    
    # Проверка FastAPI приложений
    try:
        from web_simple import app as fastapi_app_simple
        print("   ✅ FastAPI (web_simple.py) загружен")
        results.append(True)
    except Exception as e:
        print(f"   ❌ FastAPI (web_simple) ошибка: {e}")
        results.append(False)
    
    try:
        from web_viewer import app as fastapi_app_viewer
        print("   ✅ FastAPI (web_viewer.py) загружен")
        results.append(True)
    except Exception as e:
        print(f"   ❌ FastAPI (web_viewer) ошибка: {e}")
        results.append(False)
    
    # Требуем чтобы хотя бы один FastAPI работал
    fastapi_results = [r for r in results if r is not None]
    return any(fastapi_results) and all(r for r in fastapi_results if r is not None)

def test_antibot_toolkit():
    """Тест anti-bot toolkit"""
    print("\n🔍 Тест 5: Anti-bot toolkit...")
    try:
        from etl.antibot import captcha, proxy, retry, fingerprint, user_agent
        print("   ✅ Anti-bot модули импортированы")
        return True
    except Exception as e:
        print(f"   ❌ Ошибка anti-bot: {e}")
        return False

def test_product_scraper():
    """Тест product scraper"""
    print("\n🔍 Тест 6: Product scraper...")
    try:
        from etl.product_scraper import queue, worker, fetcher, cli
        print("   ✅ Product scraper модули импортированы")
        return True
    except Exception as e:
        print(f"   ❌ Ошибка product scraper: {e}")
        return False

def test_docker_containers():
    """Тест Docker контейнеров"""
    print("\n🔍 Тест 7: Docker контейнеры...")
    try:
        import subprocess
        result = subprocess.run(
            ['docker', 'ps', '--format', '{{.Names}}\t{{.Status}}'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            containers = result.stdout.strip().split('\n')
            postgres_running = any('postgres' in c.lower() for c in containers)
            if postgres_running:
                print("   ✅ PostgreSQL контейнер запущен")
                for container in containers:
                    if container.strip():
                        print(f"      - {container}")
            else:
                print("   ⚠️  PostgreSQL контейнер не найден")
            return postgres_running
        else:
            print("   ⚠️  Docker не доступен или команда не выполнена")
            return False
    except Exception as e:
        print(f"   ⚠️  Docker проверка пропущена: {e}")
        return None

def main():
    """Запуск всех тестов"""
    print("=" * 60)
    print("🧪 ТЕСТИРОВАНИЕ СИСТЕМЫ Real Estate Platform")
    print("=" * 60)
    
    tests = [
        ("Зависимости", test_imports),
        ("База данных", test_database),
        ("ETL CLI", test_etl_cli),
        ("Веб-интерфейсы", test_web_interfaces),
        ("Anti-bot toolkit", test_antibot_toolkit),
        ("Product scraper", test_product_scraper),
        ("Docker контейнеры", test_docker_containers),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"   ❌ Критическая ошибка в тесте '{name}': {e}")
            results.append((name, False))
    
    # Итоги
    print("\n" + "=" * 60)
    print("📊 ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r is True)
    failed = sum(1 for _, r in results if r is False)
    skipped = sum(1 for _, r in results if r is None)
    
    for name, result in results:
        if result is True:
            status = "✅ PASSED"
        elif result is False:
            status = "❌ FAILED"
        else:
            status = "⚠️  SKIPPED"
        print(f"{status:12} - {name}")
    
    print(f"\nВсего: {len(results)} | Успешно: {passed} | Ошибок: {failed} | Пропущено: {skipped}")
    
    if failed == 0:
        print("\n🎉 Все критические тесты пройдены! Система готова к работе.")
        return 0
    else:
        print(f"\n⚠️  Обнаружено {failed} ошибок. Проверьте детали выше.")
        return 1

if __name__ == '__main__':
    sys.exit(main())

