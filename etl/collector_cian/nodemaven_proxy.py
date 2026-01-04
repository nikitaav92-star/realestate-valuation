"""
NodeMaven Proxy Helper
Модуль для интеграции прокси NodeMaven в парсер

Использование:
    from nodemaven_proxy import get_proxy, get_proxies_dict, get_session

    # Простой запрос с прокси
    import requests
    response = requests.get(url, proxies=get_proxies_dict("us"))

    # Сессия с прокси
    session = get_session("ru")
    response = session.get(url)

    # Sticky session (один IP на время сессии)
    proxy = get_proxy("us", session_id="my_session_123")
"""

import random
import string
from typing import Optional, Dict, List

import requests

# === CREDENTIALS from environment ===
import os

PROXY_USER = os.getenv("NODEMAVEN_USER", "")
PROXY_PASS = os.getenv("NODEMAVEN_PASS", "")
PROXY_HOST = os.getenv("NODEMAVEN_HOST", "gate.nodemaven.com")
PROXY_PORT_HTTP = int(os.getenv("NODEMAVEN_PORT_HTTP", "8080"))
PROXY_PORT_SOCKS = int(os.getenv("NODEMAVEN_PORT_SOCKS", "1080"))


def _check_credentials():
    """Check that proxy credentials are configured."""
    if not PROXY_USER or not PROXY_PASS:
        raise ValueError(
            "NodeMaven proxy credentials not configured. "
            "Set NODEMAVEN_USER and NODEMAVEN_PASS in .env file."
        )


def get_proxy(
    country: str = "us",
    session_id: Optional[str] = None,
    protocol: str = "http"
) -> str:
    """
    Получить URL прокси для указанной страны.

    Args:
        country: Код страны (us, ru, de, gb, etc.)
        session_id: ID сессии для sticky proxy (один IP).
                   Если None - rotating proxy (новый IP каждый запрос)
        protocol: http или socks5

    Returns:
        Строка прокси: http://user:pass@host:port

    Raises:
        ValueError: If proxy credentials are not configured.

    Examples:
        get_proxy("us")                    # rotating US proxy
        get_proxy("ru", session_id="s1")   # sticky RU proxy
        get_proxy("de", protocol="socks5") # SOCKS5 DE proxy
    """
    _check_credentials()
    # Формируем username с параметрами
    username = f"{PROXY_USER}-country-{country.lower()}"

    if session_id:
        username += f"-session-{session_id}"

    port = PROXY_PORT_SOCKS if protocol == "socks5" else PROXY_PORT_HTTP
    proto = "socks5" if protocol == "socks5" else "http"

    return f"{proto}://{username}:{PROXY_PASS}@{PROXY_HOST}:{port}"


def get_proxies_dict(
    country: str = "us",
    session_id: Optional[str] = None
) -> Dict[str, str]:
    """
    Получить dict прокси для requests.

    Args:
        country: Код страны
        session_id: ID сессии для sticky proxy

    Returns:
        Dict для параметра proxies в requests

    Example:
        response = requests.get(url, proxies=get_proxies_dict("us"))
    """
    proxy_url = get_proxy(country, session_id)
    return {
        "http": proxy_url,
        "https": proxy_url
    }


def get_session(
    country: str = "us",
    session_id: Optional[str] = None,
    sticky: bool = False
) -> requests.Session:
    """
    Создать requests.Session с настроенным прокси.

    Args:
        country: Код страны
        session_id: ID сессии (если sticky=True и не указан, генерируется автоматически)
        sticky: Использовать sticky session (один IP на всю сессию)

    Returns:
        requests.Session с настроенным прокси

    Example:
        session = get_session("ru", sticky=True)
        response = session.get(url)  # все запросы через один IP
    """
    if sticky and not session_id:
        session_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

    session = requests.Session()
    session.proxies = get_proxies_dict(country, session_id)
    return session


def generate_session_id() -> str:
    """Сгенерировать уникальный ID сессии для sticky proxy."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))


class ProxyRotator:
    """
    Ротатор прокси по списку стран.

    Example:
        rotator = ProxyRotator(["us", "ru", "de", "gb"])

        for url in urls:
            proxy = rotator.next()
            response = requests.get(url, proxies=proxy)
    """

    def __init__(self, countries: List[str], sticky: bool = False):
        """
        Args:
            countries: Список кодов стран для ротации
            sticky: Использовать sticky sessions
        """
        self.countries = countries
        self.sticky = sticky
        self.index = 0
        self.session_ids = {c: generate_session_id() for c in countries} if sticky else {}

    def next(self) -> Dict[str, str]:
        """Получить следующий прокси из ротации."""
        country = self.countries[self.index % len(self.countries)]
        self.index += 1

        session_id = self.session_ids.get(country) if self.sticky else None
        return get_proxies_dict(country, session_id)

    def random(self) -> Dict[str, str]:
        """Получить случайный прокси."""
        country = random.choice(self.countries)
        session_id = self.session_ids.get(country) if self.sticky else None
        return get_proxies_dict(country, session_id)

    def reset(self):
        """Сбросить счётчик и сгенерировать новые session IDs."""
        self.index = 0
        if self.sticky:
            self.session_ids = {c: generate_session_id() for c in self.countries}


def test_proxy(country: str = "ru", timeout: int = 15) -> dict:
    """
    Тестировать прокси и получить внешний IP.

    Args:
        country: Код страны для теста
        timeout: Таймаут в секундах

    Returns:
        {'ok': True, 'ip': '...', 'country': 'RU', 'response_time': 1.23}
        или
        {'ok': False, 'error': '...'}

    Example:
        result = test_proxy("ru")
        if result['ok']:
            print(f"Proxy IP: {result['ip']}, time: {result['response_time']}s")
    """
    import time
    start = time.time()

    try:
        response = requests.get(
            "https://api.ipify.org?format=json",
            proxies=get_proxies_dict(country),
            timeout=timeout
        )
        elapsed = time.time() - start

        if response.status_code == 200:
            data = response.json()
            return {
                'ok': True,
                'ip': data.get('ip', 'unknown'),
                'country': country.upper(),
                'response_time': round(elapsed, 2)
            }
        else:
            return {
                'ok': False,
                'error': f'HTTP {response.status_code}'
            }

    except requests.Timeout:
        return {'ok': False, 'error': 'Таймаут'}
    except requests.ConnectionError:
        return {'ok': False, 'error': 'Нет соединения'}
    except Exception as e:
        return {'ok': False, 'error': str(e)[:50]}


# === Быстрый тест ===
if __name__ == "__main__":
    print("=== NodeMaven Proxy Helper ===\n")

    # Примеры
    print("Rotating proxy (US):")
    print(f"  {get_proxy('us')}\n")

    print("Sticky proxy (RU):")
    print(f"  {get_proxy('ru', session_id='test123')}\n")

    print("SOCKS5 proxy (DE):")
    print(f"  {get_proxy('de', protocol='socks5')}\n")

    print("Proxies dict:")
    print(f"  {get_proxies_dict('us')}\n")

    print("Rotator example:")
    rotator = ProxyRotator(["us", "ru", "de"])
    for i in range(3):
        print(f"  {i+1}: {list(rotator.next().values())[0]}")
