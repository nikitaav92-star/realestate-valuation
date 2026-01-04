#!/usr/bin/env python3
"""Admin commands for parser monitoring and control."""

import os
import sys
import subprocess
import psutil
from datetime import datetime, timedelta
from typing import Optional
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# Admin user IDs (can execute admin commands)
ADMIN_IDS = [1435579369]  # @bruckbond


def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    return user_id in ADMIN_IDS


def get_db():
    """Get database connection."""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'realdb'),
        user=os.getenv('DB_USER', 'realuser'),
        password=os.getenv('DB_PASSWORD', 'strongpass123')
    )


def get_db_stats() -> dict:
    """Get database statistics."""
    conn = get_db()
    cur = conn.cursor()

    stats = {}

    # Total listings
    cur.execute("SELECT COUNT(*) FROM listings WHERE is_active = true")
    stats['total_active'] = cur.fetchone()[0]

    # With descriptions
    cur.execute("SELECT COUNT(*) FROM listings WHERE is_active = true AND description IS NOT NULL")
    stats['with_description'] = cur.fetchone()[0]

    # With encumbrances
    cur.execute("SELECT COUNT(*) FROM listings WHERE is_active = true AND has_encumbrances = true")
    stats['with_encumbrances'] = cur.fetchone()[0]

    # Added today
    cur.execute("SELECT COUNT(*) FROM listings WHERE first_seen_at::date = CURRENT_DATE")
    stats['added_today'] = cur.fetchone()[0]

    # Added in last hour
    cur.execute("SELECT COUNT(*) FROM listings WHERE first_seen_at > NOW() - INTERVAL '1 hour'")
    stats['added_last_hour'] = cur.fetchone()[0]

    # Stats at 12:00 MSK (09:00 UTC)
    cur.execute("""
        SELECT COUNT(*) FROM listings
        WHERE first_seen_at < DATE_TRUNC('day', NOW()) + INTERVAL '9 hours'
          AND is_active = true
    """)
    stats['at_noon_msk'] = cur.fetchone()[0]

    # Photos count
    cur.execute("SELECT COUNT(*) FROM listing_photos")
    stats['photos'] = cur.fetchone()[0]

    # By rooms
    cur.execute("""
        SELECT COALESCE(rooms, 0) as r, COUNT(*)
        FROM listings WHERE is_active = true
        GROUP BY rooms ORDER BY rooms
    """)
    stats['by_rooms'] = dict(cur.fetchall())

    cur.close()
    conn.close()
    return stats


def get_parser_status() -> dict:
    """Get parser processes status."""
    status = {
        'running': [],
        'total_count': 0,
        'memory_mb': 0,
        'cpu_percent': 0
    }

    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info', 'cpu_percent', 'create_time']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'collector_cian' in cmdline or 'enrich_details' in cmdline:
                runtime = datetime.now() - datetime.fromtimestamp(proc.info['create_time'])
                status['running'].append({
                    'pid': proc.info['pid'],
                    'cmd': cmdline[:60],
                    'memory_mb': proc.info['memory_info'].rss / 1024 / 1024,
                    'runtime': str(runtime).split('.')[0]
                })
                status['total_count'] += 1
                status['memory_mb'] += proc.info['memory_info'].rss / 1024 / 1024
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return status


def get_timer_status() -> dict:
    """Get systemd timer status."""
    timers = ['cian-scraper', 'cian-enrich', 'cian-fast-scan', 'cian-alerts', 'health-check']
    status = {}

    for timer in timers:
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', f'{timer}.timer'],
                capture_output=True, text=True
            )
            is_active = result.stdout.strip() == 'active'

            # Get next run time
            result = subprocess.run(
                ['systemctl', 'show', f'{timer}.timer', '--property=NextElapseUSecRealtime'],
                capture_output=True, text=True
            )
            next_run = result.stdout.strip().split('=')[1] if '=' in result.stdout else 'N/A'

            status[timer] = {
                'active': is_active,
                'next_run': next_run[:19] if len(next_run) > 19 else next_run
            }
        except Exception as e:
            status[timer] = {'active': False, 'error': str(e)}

    return status


def get_system_stats() -> dict:
    """Get system resource stats."""
    return {
        'cpu_percent': psutil.cpu_percent(interval=1),
        'memory_percent': psutil.virtual_memory().percent,
        'memory_available_gb': psutil.virtual_memory().available / 1024 / 1024 / 1024,
        'disk_percent': psutil.disk_usage('/').percent,
        'disk_free_gb': psutil.disk_usage('/').free / 1024 / 1024 / 1024
    }


def restart_parsers() -> str:
    """Restart all parser services."""
    results = []

    # Kill existing processes
    killed = 0
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'collector_cian' in cmdline or 'enrich_details' in cmdline:
                proc.kill()
                killed += 1
        except:
            pass

    results.append(f"Убито процессов: {killed}")

    # Restart timers
    for timer in ['cian-scraper', 'cian-enrich', 'cian-fast-scan']:
        try:
            subprocess.run(['sudo', 'systemctl', 'restart', f'{timer}.timer'], check=True)
            results.append(f"✅ {timer}.timer перезапущен")
        except Exception as e:
            results.append(f"❌ {timer}.timer: {e}")

    return '\n'.join(results)


def stop_parsers() -> str:
    """Stop all parser processes and timers."""
    results = []

    # Stop timers
    for timer in ['cian-scraper', 'cian-enrich', 'cian-fast-scan']:
        try:
            subprocess.run(['sudo', 'systemctl', 'stop', f'{timer}.timer'], check=True)
            subprocess.run(['sudo', 'systemctl', 'stop', f'{timer}.service'], check=True, timeout=5)
        except:
            pass
        results.append(f"⏹ {timer} остановлен")

    # Kill processes
    killed = 0
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'collector_cian' in cmdline or 'enrich_details' in cmdline:
                proc.kill()
                killed += 1
        except:
            pass

    results.append(f"Убито процессов: {killed}")
    return '\n'.join(results)


def start_parsers() -> str:
    """Start all parser timers."""
    results = []

    for timer in ['cian-scraper', 'cian-enrich', 'cian-fast-scan']:
        try:
            subprocess.run(['sudo', 'systemctl', 'start', f'{timer}.timer'], check=True)
            results.append(f"▶️ {timer}.timer запущен")
        except Exception as e:
            results.append(f"❌ {timer}.timer: {e}")

    return '\n'.join(results)


def check_proxy_connections() -> dict:
    """Check if any connections go through proxy."""
    # Check for nodemaven connections
    result = subprocess.run(
        ['ss', '-tnp'],
        capture_output=True, text=True
    )

    proxy_connections = 0
    cian_connections = 0

    for line in result.stdout.split('\n'):
        if 'nodemaven' in line.lower():
            proxy_connections += 1
        if 'cian' in line.lower() or '89.108' in line or '51.250' in line:
            cian_connections += 1

    return {
        'proxy_connections': proxy_connections,
        'cian_connections': cian_connections,
        'proxy_used': proxy_connections > 0
    }


def get_nodemaven_traffic() -> dict:
    """Get NodeMaven traffic usage from API.

    Requires NODEMAVEN_API_KEY in environment.
    NodeMaven API: https://api.nodemaven.com/v1/account/usage
    """
    import httpx

    api_key = os.getenv('NODEMAVEN_API_KEY')
    if not api_key:
        return {
            'error': 'NODEMAVEN_API_KEY не настроен',
            'configured': False
        }

    try:
        # NodeMaven API endpoint for usage
        response = httpx.get(
            'https://api.nodemaven.com/v1/account/usage',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            # Typical response format:
            # {
            #   "data_used_gb": 6.56,
            #   "data_limit_gb": 10.0,
            #   "data_remaining_gb": 3.44,
            #   "requests_count": 12345,
            #   "period_start": "2025-01-01",
            #   "period_end": "2025-01-31"
            # }
            return {
                'configured': True,
                'used_gb': data.get('data_used_gb', 0),
                'limit_gb': data.get('data_limit_gb', 0),
                'remaining_gb': data.get('data_remaining_gb', 0),
                'requests': data.get('requests_count', 0),
                'period_start': data.get('period_start'),
                'period_end': data.get('period_end'),
            }
        elif response.status_code == 401:
            return {'error': 'Неверный API ключ', 'configured': True}
        else:
            return {'error': f'API error: {response.status_code}', 'configured': True}

    except httpx.TimeoutException:
        return {'error': 'API timeout', 'configured': True}
    except Exception as e:
        return {'error': str(e), 'configured': True}


def format_status_message() -> str:
    """Format full status message."""
    db = get_db_stats()
    parsers = get_parser_status()
    timers = get_timer_status()
    system = get_system_stats()
    proxy = check_proxy_connections()

    now_msk = datetime.utcnow() + timedelta(hours=3)

    msg = f"""📊 <b>Статус системы</b>
<i>{now_msk.strftime('%d.%m.%Y %H:%M')} МСК</i>

<b>📦 База данных:</b>
• Активных: <b>{db['total_active']:,}</b>
• С описанием: {db['with_description']:,} ({db['with_description']*100//max(db['total_active'],1)}%)
• С обременениями: {db['with_encumbrances']}
• Добавлено сегодня: +{db['added_today']}
• За последний час: +{db['added_last_hour']}
• Фото: {db['photos']:,}

<b>🤖 Парсеры ({parsers['total_count']} активных):</b>
• Память: {parsers['memory_mb']:.0f} MB
"""

    for p in parsers['running'][:5]:
        msg += f"• PID {p['pid']}: {p['runtime']}\n"

    if parsers['total_count'] > 5:
        msg += f"• ... и ещё {parsers['total_count'] - 5}\n"

    msg += f"""
<b>⏱ Таймеры:</b>
"""
    for name, t in timers.items():
        status = "✅" if t.get('active') else "❌"
        msg += f"• {status} {name}\n"

    msg += f"""
<b>💻 Система:</b>
• CPU: {system['cpu_percent']:.0f}%
• RAM: {system['memory_percent']:.0f}% ({system['memory_available_gb']:.1f} GB свободно)
• Диск: {system['disk_percent']:.0f}% ({system['disk_free_gb']:.0f} GB свободно)

<b>🔒 Прокси:</b>
• Соединений через прокси: {proxy['proxy_connections']}
• Соединений к CIAN: {proxy['cian_connections']}
• Статус: {'⚠️ ПРОКСИ ИСПОЛЬЗУЕТСЯ!' if proxy['proxy_used'] else '✅ Прокси НЕ используется'}
"""

    return msg


def format_short_status() -> str:
    """Format short status for periodic updates."""
    db = get_db_stats()
    parsers = get_parser_status()

    now_msk = datetime.utcnow() + timedelta(hours=3)

    return f"""📊 {now_msk.strftime('%H:%M')} МСК
Объявлений: {db['total_active']:,} (+{db['added_last_hour']} за час)
Парсеров: {parsers['total_count']}
Обременений: {db['with_encumbrances']}"""


# ============= НОВЫЕ ФУНКЦИИ ДЛЯ ИНДИВИДУАЛЬНОГО УПРАВЛЕНИЯ =============

# Маппинг имён парсеров на systemd сервисы
PARSER_SERVICES = {
    'scraper': 'cian-scraper',
    'fastscan': 'cian-fast-scan',
    'enrich': 'cian-enrich',
    'alerts': 'cian-alerts',
    'geocoding': 'fias-normalizer',
}

# Маппинг на файлы логов
LOG_FILES = {
    'scraper': '/home/ubuntu/realestate/logs/cian-scraper.log',
    'fastscan': '/home/ubuntu/realestate/logs/fast-scan.log',
    'enrich': '/home/ubuntu/realestate/logs/enrich.log',
    'alerts': '/home/ubuntu/realestate/logs/alerts.log',
    'geocoding': '/home/ubuntu/realestate/logs/fias-normalizer.log',
    'health': '/home/ubuntu/realestate/logs/health_check.log',
}

# Описания что делает каждый процесс
SERVICE_DESCRIPTIONS = {
    'scraper': '🔍 Основной парсер - сбор новых объявлений с CIAN (каждые 90 мин)',
    'fastscan': '⚡ Быстрый скан - поиск срочных объявлений (каждые 30 мин)',
    'enrich': '📝 Обогащение - загрузка описаний и деталей (каждые 60 мин)',
    'alerts': '🔔 Алерты - уведомления об обременениях (каждые 10 мин)',
    'geocoding': '📍 Геокодинг - нормализация адресов через ФИАС (4 раза в день)',
    'health': '💓 Health Check - мониторинг здоровья системы (каждые 15 мин)',
}

COOKIES_FILE = '/home/ubuntu/realestate/config/cian_browser_state.json'


def get_service_status(service: str) -> dict:
    """Получить детальный статус конкретного сервиса.

    Parameters
    ----------
    service : str
        Имя сервиса (scraper, fastscan, enrich, alerts)

    Returns
    -------
    dict
        Статус сервиса с полями: active, running, runtime, next_run, memory_mb
    """
    systemd_name = PARSER_SERVICES.get(service, service)
    status = {
        'name': service,
        'systemd_name': systemd_name,
        'active': False,
        'running': False,
        'runtime': None,
        'next_run': None,
        'memory_mb': 0,
        'pid': None,
    }

    try:
        # Проверить статус таймера
        result = subprocess.run(
            ['systemctl', 'is-active', f'{systemd_name}.timer'],
            capture_output=True, text=True
        )
        status['active'] = result.stdout.strip() == 'active'

        # Проверить статус сервиса (работает ли сейчас)
        result = subprocess.run(
            ['systemctl', 'is-active', f'{systemd_name}.service'],
            capture_output=True, text=True
        )
        status['running'] = result.stdout.strip() == 'active'

        # Получить следующее время запуска
        result = subprocess.run(
            ['systemctl', 'show', f'{systemd_name}.timer', '--property=NextElapseUSecRealtime'],
            capture_output=True, text=True
        )
        if '=' in result.stdout:
            next_run = result.stdout.strip().split('=')[1]
            if next_run and next_run != 'n/a':
                status['next_run'] = next_run[:16]  # YYYY-MM-DD HH:MM

        # Найти процесс и его время работы
        for proc in psutil.process_iter(['pid', 'cmdline', 'memory_info', 'create_time']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                # Проверяем соответствие процесса сервису
                if service == 'scraper' and 'collector_cian' in cmdline and 'autonomous' in cmdline:
                    status['running'] = True
                    status['pid'] = proc.info['pid']
                    status['memory_mb'] = proc.info['memory_info'].rss / 1024 / 1024
                    runtime = datetime.now() - datetime.fromtimestamp(proc.info['create_time'])
                    status['runtime'] = str(runtime).split('.')[0]
                    break
                elif service == 'fastscan' and 'collector_cian' in cmdline and 'fast' in cmdline.lower():
                    status['running'] = True
                    status['pid'] = proc.info['pid']
                    status['memory_mb'] = proc.info['memory_info'].rss / 1024 / 1024
                    runtime = datetime.now() - datetime.fromtimestamp(proc.info['create_time'])
                    status['runtime'] = str(runtime).split('.')[0]
                    break
                elif service == 'enrich' and 'enrich_details' in cmdline:
                    status['running'] = True
                    status['pid'] = proc.info['pid']
                    status['memory_mb'] = proc.info['memory_info'].rss / 1024 / 1024
                    runtime = datetime.now() - datetime.fromtimestamp(proc.info['create_time'])
                    status['runtime'] = str(runtime).split('.')[0]
                    break
                elif service == 'alerts' and 'alert_new_encumbrances' in cmdline:
                    status['running'] = True
                    status['pid'] = proc.info['pid']
                    status['memory_mb'] = proc.info['memory_info'].rss / 1024 / 1024
                    runtime = datetime.now() - datetime.fromtimestamp(proc.info['create_time'])
                    status['runtime'] = str(runtime).split('.')[0]
                    break
                elif service == 'geocoding' and 'fias_normalizer' in cmdline:
                    status['running'] = True
                    status['pid'] = proc.info['pid']
                    status['memory_mb'] = proc.info['memory_info'].rss / 1024 / 1024
                    runtime = datetime.now() - datetime.fromtimestamp(proc.info['create_time'])
                    status['runtime'] = str(runtime).split('.')[0]
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    except Exception as e:
        status['error'] = str(e)

    return status


def start_service(service: str) -> str:
    """Запустить конкретный сервис.

    Parameters
    ----------
    service : str
        Имя сервиса (scraper, fastscan, enrich, alerts)

    Returns
    -------
    str
        Результат операции
    """
    systemd_name = PARSER_SERVICES.get(service)
    if not systemd_name:
        return f"❌ Неизвестный сервис: {service}"

    try:
        # Запустить таймер (он запустит сервис по расписанию)
        subprocess.run(['sudo', 'systemctl', 'start', f'{systemd_name}.timer'], check=True)
        # Также сразу запустить сервис
        subprocess.run(['sudo', 'systemctl', 'start', f'{systemd_name}.service'], check=True)
        return f"✅ {systemd_name} запущен"
    except subprocess.CalledProcessError as e:
        return f"❌ Ошибка запуска {systemd_name}: {e}"
    except Exception as e:
        return f"❌ Ошибка: {e}"


def stop_service(service: str) -> str:
    """Остановить конкретный сервис.

    Parameters
    ----------
    service : str
        Имя сервиса (scraper, fastscan, enrich, alerts)

    Returns
    -------
    str
        Результат операции
    """
    systemd_name = PARSER_SERVICES.get(service)
    if not systemd_name:
        return f"❌ Неизвестный сервис: {service}"

    results = []

    try:
        # Остановить таймер
        subprocess.run(['sudo', 'systemctl', 'stop', f'{systemd_name}.timer'], check=True)
        results.append(f"⏹ {systemd_name}.timer остановлен")
    except:
        pass

    try:
        # Остановить сервис
        subprocess.run(['sudo', 'systemctl', 'stop', f'{systemd_name}.service'], check=True, timeout=10)
        results.append(f"⏹ {systemd_name}.service остановлен")
    except:
        pass

    # Убить процессы если остались
    killed = 0
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            should_kill = False
            if service == 'scraper' and 'collector_cian' in cmdline:
                should_kill = True
            elif service == 'enrich' and 'enrich_details' in cmdline:
                should_kill = True
            elif service == 'alerts' and 'alert_new_encumbrances' in cmdline:
                should_kill = True

            if should_kill:
                proc.kill()
                killed += 1
        except:
            pass

    if killed:
        results.append(f"Убито процессов: {killed}")

    return '\n'.join(results) if results else f"⏹ {systemd_name} остановлен"


def restart_service(service: str) -> str:
    """Перезапустить конкретный сервис.

    Parameters
    ----------
    service : str
        Имя сервиса (scraper, fastscan, enrich, alerts)

    Returns
    -------
    str
        Результат операции
    """
    systemd_name = PARSER_SERVICES.get(service)
    if not systemd_name:
        return f"❌ Неизвестный сервис: {service}"

    # Сначала остановить
    stop_result = stop_service(service)

    # Подождать немного
    import time
    time.sleep(1)

    # Запустить
    try:
        subprocess.run(['sudo', 'systemctl', 'start', f'{systemd_name}.timer'], check=True)
        subprocess.run(['sudo', 'systemctl', 'start', f'{systemd_name}.service'], check=True)
        return f"🔄 {systemd_name} перезапущен\n{stop_result}"
    except Exception as e:
        return f"❌ Ошибка перезапуска: {e}\n{stop_result}"


def get_service_logs(service: str, lines: int = 50) -> str:
    """Получить последние строки лога сервиса.

    Parameters
    ----------
    service : str
        Имя сервиса (scraper, fastscan, enrich, alerts, health)
    lines : int
        Количество строк (по умолчанию 50)

    Returns
    -------
    str
        Последние строки лога
    """
    log_file = LOG_FILES.get(service)
    if not log_file:
        return f"❌ Неизвестный сервис: {service}"

    if not os.path.exists(log_file):
        return f"❌ Файл лога не найден: {log_file}"

    try:
        result = subprocess.run(
            ['tail', '-n', str(lines), log_file],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode == 0:
            log_content = result.stdout
            # Ограничить длину для Telegram (макс 4096 символов)
            if len(log_content) > 3800:
                log_content = "...(обрезано)...\n" + log_content[-3800:]
            return log_content
        else:
            return f"❌ Ошибка чтения лога: {result.stderr}"

    except subprocess.TimeoutExpired:
        return "❌ Таймаут чтения лога"
    except Exception as e:
        return f"❌ Ошибка: {e}"


def get_cookies_status() -> dict:
    """Получить статус файла cookies.

    Returns
    -------
    dict
        Статус cookies: exists, age_hours, size_kb, file_path
    """
    status = {
        'exists': False,
        'age_hours': None,
        'size_kb': 0,
        'file_path': COOKIES_FILE,
    }

    if os.path.exists(COOKIES_FILE):
        status['exists'] = True
        stat = os.stat(COOKIES_FILE)
        status['size_kb'] = stat.st_size / 1024
        age_seconds = datetime.now().timestamp() - stat.st_mtime
        status['age_hours'] = age_seconds / 3600

    return status


def get_cookies_age_hours() -> Optional[float]:
    """Получить возраст cookies в часах.

    Returns
    -------
    float or None
        Возраст в часах или None если файл не существует
    """
    if os.path.exists(COOKIES_FILE):
        stat = os.stat(COOKIES_FILE)
        age_seconds = datetime.now().timestamp() - stat.st_mtime
        return age_seconds / 3600
    return None


def refresh_cookies() -> tuple[bool, str]:
    """Обновить cookies через прокси.

    Returns
    -------
    tuple[bool, str]
        (успех, сообщение)
    """
    script_path = '/home/ubuntu/realestate/config/get_cookies_with_proxy.py'
    venv_python = '/home/ubuntu/realestate/venv/bin/python'

    if not os.path.exists(script_path):
        return False, "❌ Скрипт не найден"

    try:
        result = subprocess.run(
            [venv_python, script_path, '--force'],
            capture_output=True, text=True, timeout=180,
            cwd='/home/ubuntu/realestate'
        )

        if result.returncode == 0:
            # Получить информацию о новом файле
            cookies = get_cookies_status()
            return True, (
                f"✅ Cookies обновлены!\n"
                f"📁 Размер: {cookies['size_kb']:.1f} KB\n"
                f"🕐 Возраст: только что"
            )
        else:
            # Извлечь ошибку из вывода
            error_lines = result.stderr.split('\n')[-5:] if result.stderr else ['Неизвестная ошибка']
            return False, f"❌ Ошибка обновления:\n" + '\n'.join(error_lines)

    except subprocess.TimeoutExpired:
        return False, "❌ Таймаут (>3 мин)"
    except Exception as e:
        return False, f"❌ Ошибка: {e}"


def format_compact_status() -> str:
    """Форматировать компактный статус для дашборда.

    Returns
    -------
    str
        Компактный HTML-статус
    """
    db = get_db_stats()
    parsers = get_parser_status()
    proxy = check_proxy_connections()
    traffic = get_nodemaven_traffic()
    system = get_system_stats()
    cookies = get_cookies_status()

    now_msk = datetime.utcnow() + timedelta(hours=3)

    # Статус ВСЕХ сервисов с описаниями
    all_services = ['scraper', 'fastscan', 'enrich', 'alerts', 'geocoding']
    parser_lines = []

    for name in all_services:
        status = get_service_status(name)
        if status['running']:
            icon = "🟢"
            info = f"работает {status['runtime']}" if status['runtime'] else "активен"
        elif status['active']:
            icon = "🟡"
            info = "ожидает"
        else:
            icon = "🔴"
            info = "выключен"

        # Короткое имя для компактности
        short_names = {
            'scraper': 'Scraper',
            'fastscan': 'FastScan',
            'enrich': 'Enrich',
            'alerts': 'Alerts',
            'geocoding': 'Geocoding',
        }
        parser_lines.append(f"  {icon} <b>{short_names[name]}</b>: {info}")

    # Traffic bar
    if not traffic.get('error'):
        used = traffic.get('used_gb', 0)
        limit = traffic.get('limit_gb', 10)
        percent = (used / limit * 100) if limit > 0 else 0
        bar_filled = int(percent / 10)
        bar_empty = 10 - bar_filled
        traffic_bar = '█' * bar_filled + '░' * bar_empty
        traffic_line = f"{traffic_bar} {used:.1f}/{limit:.0f} GB ({percent:.0f}%)"
    else:
        traffic_line = f"⚠️ {traffic.get('error', 'N/A')}"

    # Cookies status
    if cookies['exists']:
        age = cookies['age_hours']
        if age < 12:
            cookies_icon = "✅"
        elif age < 20:
            cookies_icon = "🟡"
        else:
            cookies_icon = "🔴"
        cookies_line = f"{cookies_icon} {age:.1f}ч ({cookies['size_kb']:.1f} KB)"
    else:
        cookies_line = "❌ Не найдены!"

    # Proxy status
    proxy_icon = "⚠️" if proxy['proxy_used'] else "✅"
    proxy_status = "ИСПОЛЬЗУЕТСЯ!" if proxy['proxy_used'] else "не используется"

    msg = f"""📊 <b>СТАТУС</b> ({now_msk.strftime('%H:%M')} МСК)
{'━' * 28}

<b>📦 БАЗА:</b> {db['total_active']:,} объявлений
   +{db['added_last_hour']} за час │ +{db['added_today']} сегодня
   Описания: {db['with_description']*100//max(db['total_active'],1)}% │ Фото: {db['photos']//1000}K

<b>🤖 СЕРВИСЫ:</b> ({parsers['total_count']} активных)
{chr(10).join(parser_lines)}

<b>🔒 ПРОКСИ:</b> {proxy_icon} {proxy_status}
   Трафик: {traffic_line}
   Cookies: {cookies_line}

<b>💻 СЕРВЕР:</b>
   CPU {system['cpu_percent']:.0f}% │ RAM {system['memory_percent']:.0f}% │ Disk {system['disk_percent']:.0f}%"""

    return msg


def format_services_help() -> str:
    """Форматировать справку по сервисам с описаниями.

    Returns
    -------
    str
        Справка по всем сервисам
    """
    lines = ["<b>📋 ОПИСАНИЕ СЕРВИСОВ:</b>\n"]

    for service_id, description in SERVICE_DESCRIPTIONS.items():
        if service_id == 'health':
            continue  # health не управляется
        status = get_service_status(service_id)
        if status['running']:
            icon = "🟢"
        elif status['active']:
            icon = "🟡"
        else:
            icon = "🔴"
        lines.append(f"{icon} {description}")

    return '\n'.join(lines)


# ============= АВТОМАТИЧЕСКИЕ ДЕЙСТВИЯ ПРИ АЛЕРТАХ =============

def identify_service_by_cmdline(cmdline: str) -> Optional[str]:
    """Определить сервис по командной строке процесса.

    Parameters
    ----------
    cmdline : str
        Командная строка процесса

    Returns
    -------
    str or None
        Идентификатор сервиса (scraper, fastscan, enrich, alerts, geocoding) или None
    """
    cmdline_lower = cmdline.lower()

    if 'collector_cian' in cmdline:
        if 'autonomous' in cmdline_lower:
            return 'scraper'
        elif 'fast' in cmdline_lower:
            return 'fastscan'
        else:
            return 'scraper'  # по умолчанию
    elif 'enrich_details' in cmdline:
        return 'enrich'
    elif 'alert_new_encumbrances' in cmdline:
        return 'alerts'
    elif 'fias_normalizer' in cmdline:
        return 'geocoding'

    return None


def auto_fix_stuck_process(pid: int, cmdline: str = '') -> str:
    """Убить зависший процесс и перезапустить соответствующий сервис.

    Parameters
    ----------
    pid : int
        PID процесса для завершения
    cmdline : str
        Командная строка процесса (для определения сервиса)

    Returns
    -------
    str
        Отчёт о выполненных действиях
    """
    results = []

    # Определить сервис
    service = identify_service_by_cmdline(cmdline)

    # Убить процесс
    try:
        proc = psutil.Process(pid)
        proc.kill()
        results.append(f"✅ Убит процесс PID {pid}")
    except psutil.NoSuchProcess:
        results.append(f"⚠️ Процесс {pid} уже не существует")
    except Exception as e:
        results.append(f"❌ Ошибка kill {pid}: {e}")

    # Перезапустить сервис если определён
    if service:
        try:
            systemd_name = PARSER_SERVICES.get(service)
            if systemd_name:
                subprocess.run(['sudo', 'systemctl', 'restart', f'{systemd_name}.timer'], check=True, timeout=30)
                results.append(f"🔄 Перезапущен {systemd_name}.timer")
        except Exception as e:
            results.append(f"❌ Ошибка рестарта {service}: {e}")
    else:
        results.append("⚠️ Сервис не определён, рестарт не выполнен")

    return '\n'.join(results)


def kill_proxy_using_processes() -> tuple[int, str]:
    """Найти и убить процессы, использующие прокси для парсинга.

    Returns
    -------
    tuple[int, str]
        (количество убитых, отчёт)
    """
    killed = 0
    results = []

    # Получить список соединений через ss
    try:
        result = subprocess.run(['ss', '-tnp'], capture_output=True, text=True)

        # Найти PID процессов использующих nodemaven
        proxy_pids = set()
        for line in result.stdout.split('\n'):
            if 'nodemaven' in line.lower() or 'proxy' in line.lower():
                # Извлечь PID из строки вида: ... users:(("python",pid=12345,fd=3))
                import re
                match = re.search(r'pid=(\d+)', line)
                if match:
                    proxy_pids.add(int(match.group(1)))

        # Убить только парсерные процессы (не бота!)
        for pid in proxy_pids:
            try:
                proc = psutil.Process(pid)
                cmdline = ' '.join(proc.cmdline())

                # Проверить что это парсер, а не бот
                if any(x in cmdline for x in ['collector_cian', 'enrich_details', 'get_cookies']):
                    proc.kill()
                    killed += 1
                    results.append(f"Убит: PID {pid} ({cmdline[:50]}...)")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    except Exception as e:
        results.append(f"❌ Ошибка: {e}")

    report = '\n'.join(results) if results else "Процессов через прокси не найдено"
    return killed, report


def parse_runtime_hours(runtime: str) -> float:
    """Преобразовать строку времени работы в часы.

    Parameters
    ----------
    runtime : str
        Время в формате "H:MM:SS" или "D days, H:MM:SS" или "D day, H:MM:SS"

    Returns
    -------
    float
        Количество часов
    """
    if not runtime:
        return 0

    hours = 0.0

    try:
        # Проверить наличие дней
        if 'day' in runtime:
            parts = runtime.split(',')
            day_part = parts[0].strip()
            days = int(day_part.split()[0])
            hours += days * 24

            if len(parts) > 1:
                time_part = parts[1].strip()
            else:
                return hours
        else:
            time_part = runtime

        # Парсить H:MM:SS
        time_parts = time_part.split(':')
        if len(time_parts) >= 1:
            hours += int(time_parts[0])
        if len(time_parts) >= 2:
            hours += int(time_parts[1]) / 60
        if len(time_parts) >= 3:
            hours += int(time_parts[2]) / 3600

    except (ValueError, IndexError):
        pass

    return hours
