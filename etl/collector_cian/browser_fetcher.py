"""Playwright-based HTML parser for CIAN with smart proxy strategy."""
from __future__ import annotations

import logging
import os
import re
import time
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from playwright.sync_api import BrowserContext, Browser, Playwright, Page, sync_playwright
from urllib.parse import urlencode

from .proxy_manager import get_validated_proxy, ProxyConfig, ProxyRotator

LOGGER = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when CIAN returns HTTP 429 (Too Many Requests)."""
    def __init__(self, url: str, status_code: int = 429):
        self.url = url
        self.status_code = status_code
        super().__init__(f"Rate limited (HTTP {status_code}) for URL: {url}")


CIAN_DOMAIN = ".cian.ru"
DEFAULT_STORAGE_PATH = "config/cian_browser_state.json"

DISTRICT_PATTERN = re.compile(
    r"\b("
    r"С[ВЗЮ]АО|ЦАО|НАО|ТАО|ЗАО|ВАО|ЮЗАО|ЮАО|ЮВАО|САО|СЗАО|СВАО"
    r"|р-?н|район|округ|мкр\.?|микрорайон|поселок|пос\.|поселение|деревня"
    r"|ЖК|жилой\s+комплекс|Новая\s+Москва"
    r")\b",
    re.IGNORECASE,
)

STREET_PATTERN = re.compile(
    r"\b("
    r"ул\.?|улица|проспект|пр\.|шоссе|ш\.|проезд|бульвар|наб\."
    r"|набережная|аллея|переулок|пер\.|площадь|пл\.|шос|тракт|дорога|жк"
    r")\b",
    re.IGNORECASE,
)

HOUSE_NUMBER_PATTERN = re.compile(r"\b\d{1,4}[кК]?\d?(?:[-/]\d+)?\b")
METRO_SEGMENT_PATTERN = re.compile(
    r"(?:,\s*)?(?:м\.|метро|станция)\s+[А-ЯЁ0-9][^,\.]*?(?:\d+\s*мин\.?(?:\s+[пп]ешком)?)?",
    re.IGNORECASE,
)
MINUTES_SEGMENT_PATTERN = re.compile(
    r"\b[А-ЯЁA-Z][^,]*?\d+\s*мин\.?(?:\s+[пп]ешком)?", re.IGNORECASE
)
ON_MAP_PATTERN = re.compile(r"\s*На\s+карте.*", re.IGNORECASE)
KM_FROM_MKAD_PATTERN = re.compile(r"\d+\s*км\s+от\s+МКАД", re.IGNORECASE)
HOUSE_EXTRA_PATTERN = re.compile(
    r"(?:дом|д\.|корпус|корп\.?|строение|стр\.?|лит\.?|литера|владение|вл\.?|секция|сек\.?|с\.?|к\.?|зд\.?|строит\.)\s*\d+[А-ЯA-Za-z0-9/-]*",
    re.IGNORECASE,
)
CARD_ADDRESS_FALLBACK_SELECTORS: tuple[str, ...] = (
    "[data-name='SpecialGeo']",
    "[data-name='Breadcrumbs']",
    ".geo-label",
    ".address-label",
    ".a10a3f92e9--address--wrapper",
    "[class*='--geo--']",
    "[class*='--address--']",
)
DETAIL_ADDRESS_SELECTORS: tuple[str, ...] = (
    "[data-name='Breadcrumbs']",
    "[data-name='Address']",
    "[data-name='Geo']",
    ".a10a3f92e9--address--wrapper",
    "[class*='--address--']",
)


def clean_address_text(raw: str | None) -> str:
    """Remove metro info, 'На карте' fragments and normalize whitespace/commas.
    
    More aggressive cleaning to handle various CIAN address formats.
    """
    if not raw:
        return ""

    text = raw.replace("\xa0", " ").replace("\n", " ").replace("\r", " ").strip()
    if not text:
        return ""

    # Step 1: Remove "На карте" and everything after (most aggressive)
    # Split by "На карте" and take only the first part
    if "На карте" in text or "на карте" in text:
        parts = re.split(r"[Нн]а\s+[Кк]арте", text, maxsplit=1)
        text = parts[0].strip() if parts else text

    # Remove explicit "На карте" fragments regardless of position (fallback)
    text = ON_MAP_PATTERN.sub("", text)

    # Step 2: Remove metro segments (м. ..., метро ...) - VERY aggressive
    text = METRO_SEGMENT_PATTERN.sub("", text)
    
    # Remove patterns like "м. Сокольники, 14 мин."
    text = re.sub(r"\s*м\.\s*[А-ЯЁ][^,]*?,\s*\d+\s*мин\.?\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*метро\s+[А-ЯЁ][^,]*?,\s*\d+\s*мин\.?\s*", " ", text, flags=re.IGNORECASE)
    
    # Remove standalone metro station names followed by time (e.g., "Сокольники 14 мин.")
    # This is tricky - we need to not remove district names
    # Pattern: single capitalized word followed by number and "мин."
    text = re.sub(r"\s+([А-ЯЁ][а-яё]+)\s+\d+\s*мин\.?(?:\s+пешком)?", lambda m: "" if len(m.group(1)) > 4 and "р-н" not in text[:m.start()] else m.group(0), text, flags=re.IGNORECASE)
    
    # Remove patterns like "Сокольники 14 мин. Электрозаводская 15 мин."  
    text = re.sub(r"\s+[А-ЯЁ][а-яё]+(?:ская|ский|ская|ский|ая|яя|ий)?\s+\d+\s*мин\.?(?:\s+пешком)?(?:\s+[А-ЯЁ][а-яё]+\s+\d+\s*мин\.?)?", "", text, flags=re.IGNORECASE)

    # Remove "[Station] 14 мин." fragments - more patterns
    text = MINUTES_SEGMENT_PATTERN.sub("", text)

    # Step 3: Remove distance markers like "20 км от МКАД"
    text = KM_FROM_MKAD_PATTERN.sub("", text)

    # Step 4: Remove "пешком" (on foot) mentions
    text = re.sub(r"\s+пешком\s*", " ", text, flags=re.IGNORECASE)

    # Step 5: Remove any remaining time patterns (X мин.)
    text = re.sub(r"\s+\d+\s*мин\.?\s*", " ", text, flags=re.IGNORECASE)

    # Step 6: Normalize whitespace prior to segment filtering
    text = re.sub(r"\s+", " ", text)

    segments = [segment.strip(" ,;-") for segment in text.split(",") if segment.strip(" .;-")]
    if segments:
        filtered = _filter_address_segments(segments)
        if filtered:
            segments = filtered
        text = ", ".join(segments)

    # Collapse whitespace and redundant commas
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"(,\s*){2,}", ", ", text)
    text = text.strip(" ,;.-")

    return text


def _is_noise_segment(segment: str) -> bool:
    """Return True if segment is clearly not part of the postal address."""
    if not segment:
        return True
    lowered = segment.lower()
    if "на карте" in lowered:
        return True
    if lowered.startswith(("посмотреть", "показать")):
        return True
    if re.search(r"\b\d+\s*мин", lowered):
        return True
    if re.match(r"^(?:м\.|метро|станция)\b", lowered):
        return True
    if "пешком" in lowered:
        return True
    if "км от мкад" in lowered:
        return True
    # Check for metro station names followed by numbers (likely time)
    if re.search(r"^[А-ЯЁ][а-яё]+\s+\d+", segment):
        return True
    if len(segment) <= 2 and not re.search(r"\d", lowered):
        return True
    return False


def _collect_address_parts(handle) -> List[str]:
    """Collect visible text fragments that could represent address components."""
    try:
        parts = handle.evaluate(
            """
            (el) => {
                const nodes = el.querySelectorAll('a, span, li, div');
                const parts = [];
                nodes.forEach(node => {
                    const text = (node.innerText || '').trim();
                    if (text) {
                        parts.push(text);
                    }
                });
                if (!parts.length) {
                    const fallback = (el.innerText || '').trim();
                    if (fallback) {
                        parts.push(fallback);
                    }
                }
                return parts;
            }
            """
        )
        if isinstance(parts, list):
            return [p for p in parts if isinstance(p, str)]
    except Exception:
        pass

    try:
        fallback_text = handle.inner_text().strip()
        return [fallback_text] if fallback_text else []
    except Exception:
        return []


def _normalize_segment_key(segment: str) -> str:
    return re.sub(r"[^0-9a-zа-яё]+", " ", segment.lower()).strip()


def _segment_is_redundant(candidate_key: str, seen_keys: List[str]) -> bool:
    if not candidate_key:
        return False
    for key in seen_keys:
        if len(candidate_key) >= 4 and candidate_key in key:
            return True
        if len(key) >= 4 and key in candidate_key:
            return True
    return False


def _segment_contains_house(segment: str) -> bool:
    if HOUSE_NUMBER_PATTERN.search(segment):
        return True
    if HOUSE_EXTRA_PATTERN.search(segment):
        return True
    return False


def _filter_address_segments(segments: List[str]) -> List[str]:
    filtered: List[str] = []
    seen_keys: List[str] = []
    house_found = False

    for raw_segment in segments:
        segment = raw_segment.strip(" ,;-")
        if not segment:
            continue
        if _is_noise_segment(segment):
            continue

        key = _normalize_segment_key(segment)
        if _segment_is_redundant(key, seen_keys):
            continue

        is_house = _segment_contains_house(segment)
        if house_found and not is_house:
            break

        filtered.append(segment)
        if key:
            seen_keys.append(key)

        if is_house:
            house_found = True

    return filtered


def _prepare_address_from_parts(parts: Iterable[str]) -> str:
    """Join, deduplicate and clean textual parts of an address."""
    seen = set()
    normalized_parts: List[str] = []

    for part in parts:
        candidate = re.sub(r"\s+", " ", part.strip(",; \n\t"))
        if not candidate:
            continue
        if _is_noise_segment(candidate):
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized_parts.append(candidate)

    filtered = _filter_address_segments(normalized_parts) if normalized_parts else []
    parts_to_join = filtered or normalized_parts
    combined = ", ".join(parts_to_join)
    return clean_address_text(combined)


def _address_is_valid(
    text: str,
    *,
    require_city: bool = False,
) -> bool:
    """Heuristic validation for extracted addresses.
    
    More lenient validation - accept if has Moscow/district + (street OR house OR district).
    """
    if not text:
        return False

    address = text.strip()
    if len(address) < 10:  # Minimum address length (more lenient)
        return False

    # Skip validation if address contains new construction indicators (will be filtered anyway)
    address_lower = address.lower()
    newbuilding_indicators = ["жилой комплекс", "жилой район", "жк ", "жк.", "новострой"]
    if any(indicator in address_lower for indicator in newbuilding_indicators):
        # Still validate basic structure but be more lenient
        has_city = "москва" in address_lower
        has_district = bool(DISTRICT_PATTERN.search(address))
        if has_city or has_district:
            return True
        return False

    has_city = "москва" in address_lower
    has_district = bool(DISTRICT_PATTERN.search(address))
    has_street = bool(STREET_PATTERN.search(address))
    has_house = bool(HOUSE_NUMBER_PATTERN.search(address))

    if require_city and not has_city:
        return False

    # MORE LENIENT: Accept if has Moscow OR district + at least one other indicator
    if has_city:
        # Has Moscow - accept if has any additional indicator
        if has_street or has_house or has_district:
            return True
    
    if has_district:
        # Has district - accept if has street or house
        if has_street or has_house:
            return True
    
    # Final fallback: if has both street and house, accept even without Moscow
    if has_street and has_house:
        return True

    return False


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _build_search_url(payload: Dict[str, Any]) -> str:
    """Build search URL from payload."""
    query: Dict[str, Any] = {}
    q = payload.get("jsonQuery", {})

    region = (q.get("region") or {}).get("value")
    if region:
        query["region"] = region[0] if isinstance(region, list) else region

    engine_version = (q.get("engine_version") or {}).get("value")
    if engine_version:
        query["engine_version"] = engine_version

    deal_type = (q.get("deal_type") or {}).get("value")
    if deal_type:
        query["deal_type"] = deal_type

    offer_type = (q.get("offer_type") or {}).get("value")
    if offer_type:
        query["offer_type"] = offer_type

    # Building status (secondary market)
    building_status = (q.get("building_status") or {}).get("value")
    if building_status:
        query["building_status"] = building_status
        normalized_status = str(building_status).lower()
        if normalized_status in {"secondary", "resale"}:
            query["resale"] = 1  # cat.php filter for вторичка
            # object_type[0]=1 - key CIAN filter for secondary market (excludes newbuildings)
            query["object_type[0]"] = 1
        elif normalized_status in {"new", "newbuilding"}:
            query["newobject"] = 1

    price = (q.get("price") or {}).get("value") or {}
    if price.get("gte"):
        query["minprice"] = price["gte"]
    if price.get("lte"):
        query["maxprice"] = price["lte"]

    area = (q.get("area") or {}).get("value") or {}
    if area.get("gte"):
        query["minarea"] = area["gte"]
    if area.get("lte"):
        query["maxarea"] = area["lte"]

    floor = (q.get("floor") or {}).get("value") or {}
    if floor.get("gte"):
        query["minfloor"] = floor["gte"]

    # Handle is_first_floor filter - if false, set minfloor=2
    is_first_floor = q.get("is_first_floor", {})
    if is_first_floor.get("type") == "term" and is_first_floor.get("value") is False:
        query["minfloor"] = max(query.get("minfloor", 2), 2)

    # Handle total_area filter (not just "area")
    total_area = (q.get("total_area") or {}).get("value") or {}
    if total_area.get("gte"):
        query["minarea"] = total_area["gte"]
    if total_area.get("lte"):
        query["maxarea"] = total_area["lte"]

    room_values = (q.get("room") or {}).get("value") or []
    for val in room_values:
        query.setdefault(f"room{val}", 1)

    # Sort order
    sort_value = (q.get("sort") or {}).get("value")
    if sort_value:
        query["sort"] = sort_value

    params = urlencode(query, doseq=True)
    return f"https://www.cian.ru/cat.php?{params}" if params else "https://www.cian.ru/cat.php"


def _storage_state_path() -> Path:
    """Get path to browser state file."""
    value = os.getenv("CIAN_STORAGE_STATE", DEFAULT_STORAGE_PATH)
    return Path(value).expanduser()


def _apply_cookies_from_env(context: BrowserContext) -> None:
    """Apply cookies from CIAN_COOKIES environment variable."""
    raw = os.getenv("CIAN_COOKIES")
    if not raw:
        return
    cookie_jar = SimpleCookie()
    try:
        cookie_jar.load(raw)
    except Exception as exc:
        LOGGER.warning("Failed to parse CIAN_COOKIES (%s); skipping", exc)
        return
    cookies = [
        {
            "name": morsel.key,
            "value": morsel.value,
            "domain": CIAN_DOMAIN,
            "path": "/",
        }
        for morsel in cookie_jar.values()
    ]
    if cookies:
        context.add_cookies(cookies)
        LOGGER.debug("Applied %s cookies to Playwright context", len(cookies))


def _create_browser_with_proxy(
    p: Playwright,
    proxy_url: str,
    headless: bool,
    slow_mo: int,
) -> Browser:
    """Create browser with proxy.

    ВАЖНО: Bypass на уровне браузера НЕ РАБОТАЕТ с wildcard!
    Блокировка делается через setup_route_blocking() на уровне контекста.
    """
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-gpu",
    ]

    proxy_config = ProxyConfig.from_url(proxy_url)

    # НЕ используем bypass - он не работает с wildcard паттернами!
    # Блокировка делается через setup_route_blocking() на контексте
    browser_kwargs = {
        "headless": headless,
        "slow_mo": slow_mo,
        "args": launch_args,
        "proxy": {
            "server": proxy_config.server,
            "username": proxy_config.username,
            "password": proxy_config.password,
        },
    }

    LOGGER.info(f"🌐 Creating browser with proxy: {proxy_config.server}")
    LOGGER.info(f"⚠️ ВАЖНО: Вызовите setup_route_blocking(context) после new_context()!")
    return p.chromium.launch(**browser_kwargs)


def setup_route_blocking(context) -> None:
    """СТРОГО блокировать ВСЕ запросы кроме www.cian.ru.

    ██████████████████████████████████████████████████████████████████████████████
    ██  КРИТИЧЕСКИ ВАЖНО!                                                       ██
    ██  Через прокси идёт ТОЛЬКО www.cian.ru                                    ██
    ██  ВСЁ остальное блокируется БЕЗ ИСКЛЮЧЕНИЙ!                               ██
    ██  CDN, картинки, аналитика, шрифты - ВСЁ БЛОКИРУЕТСЯ!                     ██
    ██                                                                          ██
    ██  ОБЯЗАТЕЛЬНО вызывать после browser.new_context() при работе с прокси!   ██
    ██  Без этого весь трафик пойдёт через прокси и сожрёт бюджет!              ██
    ██████████████████████████████████████████████████████████████████████████████
    """
    blocked_count = [0]  # Счётчик заблокированных запросов

    def route_handler(route):
        try:
            from urllib.parse import urlparse
            url = route.request.url
            domain = urlparse(url).netloc.lower()

            # Разрешаем все поддомены *.cian.ru (www, solnechnogorsk, podolsk и т.д.)
            if domain.endswith(".cian.ru") or domain == "cian.ru":
                route.continue_()
            else:
                # Блокируем АБСОЛЮТНО ВСЁ остальное (CDN, аналитика, и т.д.)
                blocked_count[0] += 1
                if blocked_count[0] <= 5:  # Логируем первые 5
                    LOGGER.debug(f"🚫 ЗАБЛОКИРОВАН: {domain}")
                route.abort("blockedbyclient")
        except Exception:
            # При любой ошибке - блокируем
            route.abort("blockedbyclient")

    context.route("**/*", route_handler)
    LOGGER.info("🛡️ БЛОКИРОВКА ВКЛЮЧЕНА: разрешены все *.cian.ru")
    LOGGER.info("🛡️ Все остальные домены (CDN, аналитика, картинки) - ЗАБЛОКИРОВАНЫ")


def create_proxy_context_safe(browser, context_kwargs: dict = None):
    """Создать контекст с ОБЯЗАТЕЛЬНОЙ блокировкой для прокси.

    ЭТА ФУНКЦИЯ ОБЯЗАТЕЛЬНА при работе с прокси!
    Она гарантирует что блокировка всегда включена.

    Пример:
        browser = p.chromium.launch(proxy={...})
        context = create_proxy_context_safe(browser, {"user_agent": "..."})
        page = context.new_page()
    """
    if context_kwargs is None:
        context_kwargs = {}

    context = browser.new_context(**context_kwargs)
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

    # ОБЯЗАТЕЛЬНО включаем блокировку!
    setup_route_blocking(context)

    return context


def _create_browser_without_proxy(
    p: Playwright,
    headless: bool,
    slow_mo: int,
) -> Browser:
    """Create browser without proxy."""
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-gpu",
    ]

    browser_kwargs = {
        "headless": headless,
        "slow_mo": slow_mo,
        "args": launch_args,
    }

    LOGGER.info(f"🔓 Creating browser WITHOUT proxy (using saved cookies)")
    return p.chromium.launch(**browser_kwargs)


def _parse_offers_from_html(page: Page) -> List[Dict[str, Any]]:
    """Extract offers from HTML page using selectors.

    Returns list of offer dictionaries with available data.
    """
    import re

    offers = []

    # Find all offer cards using the data-name attribute
    offer_elements = page.query_selector_all("[data-name='LinkArea']")

    LOGGER.debug(f"Found {len(offer_elements)} offer cards on page")

    for idx, element in enumerate(offer_elements):
        try:
            offer = {}

            # Try to get offer ID from link
            link = element.query_selector("a[href*='/sale/']")
            if link:
                href = link.get_attribute("href")
                if href:
                    offer["url"] = href if href.startswith("http") else f"https://www.cian.ru{href}"
                    # Extract ID from URL (e.g., /sale/flat/123456/)
                    match = re.search(r'/(\d+)/', href)
                    if match:
                        offer["offerId"] = int(match.group(1))

            # Get price - try multiple selectors
            price_elem = (
                element.query_selector("[data-testid='offer-discount-new-price']") or
                element.query_selector("[data-mark='DiscountPrice']") or
                element.query_selector("[data-mark='MainPrice']")
            )
            if price_elem:
                price_text = price_elem.inner_text().strip()
                # Remove "₽", spaces, and non-breaking spaces
                price_clean = price_text.replace("₽", "").replace(" ", "").replace("\xa0", "").replace("млн", "")
                try:
                    # If price contains "млн", multiply by 1,000,000
                    if "млн" in price_text:
                        offer["price"] = float(price_clean) * 1_000_000
                    else:
                        offer["price"] = float(price_clean)
                except ValueError:
                    pass

            # Get address from multiple selectors (fallback chain)
            address_parts: List[str] = []

            geo_labels = element.query_selector_all("[data-name='GeoLabel']")
            if geo_labels:
                for label in geo_labels:
                    address_parts.extend(_collect_address_parts(label))

            if not address_parts:
                for selector in CARD_ADDRESS_FALLBACK_SELECTORS:
                    fallback_node = element.query_selector(selector)
                    if not fallback_node:
                        continue
                    address_parts = _collect_address_parts(fallback_node)
                    if address_parts:
                        break

            if address_parts:
                address_text = _prepare_address_from_parts(address_parts)
                if address_text and _address_is_valid(address_text):
                    offer["address"] = address_text
                    LOGGER.debug(
                        "Offer %s: address detected (%s)",
                        offer.get("offerId", idx),
                        address_text,
                    )
                else:
                    LOGGER.warning(
                        "Offer %s: Invalid address candidate: %s",
                        offer.get("offerId", "unknown"),
                        address_text or "EMPTY",
                    )

            # Get title with params (rooms, area, floor)
            # FIXED: Check BOTH OfferSubtitle (preferred) and OfferTitle (fallback)
            # Reason: OfferTitle often contains promotional text ("Рассрочка 0%"),
            # while OfferSubtitle has actual property data ("2-комн. квартира, 60 м²")

            subtitle_elem = element.query_selector("[data-mark='OfferSubtitle']")
            title_elem = element.query_selector("[data-mark='OfferTitle']")

            # Determine which text contains property data
            text_to_parse = None
            data_source = None

            # Try OfferSubtitle first
            if subtitle_elem:
                subtitle_text = subtitle_elem.inner_text().strip()
                # Check if subtitle contains property info (rooms, area, floor)
                if re.search(r'\d+[-\s]*комн|м²|этаж|Студия', subtitle_text):
                    text_to_parse = subtitle_text
                    data_source = "OfferSubtitle"
                    offer["title"] = subtitle_text

            # Fallback to OfferTitle if subtitle is empty or doesn't have property data
            if not text_to_parse and title_elem:
                title_text = title_elem.inner_text().strip()
                # Check if title has property data (not just promo text)
                if re.search(r'\d+[-\s]*комн|м²|этаж|Студия', title_text):
                    text_to_parse = title_text
                    data_source = "OfferTitle"
                if "title" not in offer:
                    offer["title"] = title_text

            # Extract property data from chosen text
            if text_to_parse:
                # Extract rooms
                # Pattern 1: "1 комната", "2 комнаты", "3 комнаты"
                rooms_match = re.search(r'\b(\d+)\s+комнат', text_to_parse)
                if rooms_match:
                    offer["rooms"] = int(rooms_match.group(1))
                # Pattern 2: "2-комн.", "3-комн. квартира"
                elif re.search(r'\b(\d+)-комн', text_to_parse):
                    rooms_match = re.search(r'\b(\d+)-комн', text_to_parse)
                    offer["rooms"] = int(rooms_match.group(1))
                # Pattern 3: "Студия"
                elif "Студия" in text_to_parse or "студия" in text_to_parse:
                    offer["rooms"] = 0

                # Extract area (m²)
                area_match = re.search(r'(\d+(?:[.,]\d+)?)\s*м²', text_to_parse)
                if area_match:
                    offer["totalSquare"] = float(area_match.group(1).replace(",", "."))

                # Extract floor (format: "16/49 этаж")
                floor_match = re.search(r'(\d+)/(\d+)\s*этаж', text_to_parse)
                if floor_match:
                    offer["floor"] = int(floor_match.group(1))
                    offer["floorsCount"] = int(floor_match.group(2))

                # Log which source was used (helps debugging)
                if data_source:
                    LOGGER.debug(f"Offer {offer.get('offerId', idx)}: parsed from {data_source}")

            # Get seller type
            seller_elem = element.query_selector("[data-mark='OfferCardSeller']")
            if seller_elem:
                offer["userType"] = seller_elem.inner_text().strip()

            # Deduce property/building flags from card text to keep filters consistent
            flag_text_parts = []
            if subtitle_elem:
                try:
                    flag_text_parts.append(subtitle_elem.inner_text())
                except Exception:
                    pass
            if title_elem:
                try:
                    flag_text_parts.append(title_elem.inner_text())
                except Exception:
                    pass
            try:
                flag_text_parts.append(element.inner_text())
            except Exception:
                pass

            card_text_lower = " ".join(flag_text_parts).lower() if flag_text_parts else ""
            if card_text_lower:
                if any(token in card_text_lower for token in ("апартамент", "apartment")):
                    offer["propertyType"] = "apartment"
                elif any(token in card_text_lower for token in ("доля", "долев", "share")):
                    offer["propertyType"] = "share"

                # Enhanced newbuilding detection - catch more patterns
                # But allow if building is already completed (дом сдан)

                # First check if building is completed
                building_completed = False
                completed_patterns = ("дом сдан", "сдан в 20", "введён в эксплуатацию", "введен в эксплуатацию")
                if any(p in card_text_lower for p in completed_patterns):
                    building_completed = True

                # Check for future delivery dates (not completed)
                future_delivery = False
                if re.search(r"сдача\s+(в\s+)?202[5-9]|сдача\s+(в\s+)?203\d", card_text_lower):
                    future_delivery = True
                if re.search(r"срок\s+сдачи.*(202[5-9]|203\d)", card_text_lower):
                    future_delivery = True

                # Newbuilding indicators (строится, не сдан)
                under_construction_tokens = (
                    "строится", "в стадии строительства", "котлован",
                    "от застройщика", "переуступка дду"
                )
                under_construction = any(token in card_text_lower for token in under_construction_tokens)

                # ЖК indicators (may be completed or not)
                jk_tokens = ("жилой комплекс", "жилой район", "жк ", "жк.")
                has_jk = any(token in card_text_lower for token in jk_tokens)

                address_lower = (offer.get("address") or "").lower()
                has_jk_in_address = any(p in address_lower for p in jk_tokens)

                # Mark as newbuilding only if:
                # 1. Under construction OR future delivery
                # 2. OR has ЖК but NOT completed
                looks_newbuilding = False
                if under_construction or future_delivery:
                    looks_newbuilding = True
                elif (has_jk or has_jk_in_address) and not building_completed:
                    looks_newbuilding = True

                if looks_newbuilding:
                    offer["buildingStatus"] = "newbuilding"
                    offer["category"] = "newbuilding"

            # Add metadata
            offer["region"] = 1  # Moscow
            offer["dealType"] = "sale"
            offer["offerType"] = "flat"

            # Only add if we have at least ID and price
            if "offerId" in offer and "price" in offer:
                offers.append(offer)
                LOGGER.debug(f"Offer {offer['offerId']}: {offer.get('rooms')}комн, {offer.get('totalSquare')}м², {offer.get('floor')} этаж, {offer.get('address', 'N/A')[:50]}")
            else:
                LOGGER.debug(f"Skipping offer {idx} - missing required fields (ID or price)")

        except Exception as e:
            LOGGER.warning(f"Error parsing offer {idx}: {e}")
            continue

    LOGGER.info(f"✅ Extracted {len(offers)} valid offers from HTML")
    return offers


def parse_listing_detail(
    page: Page,
    listing_url: str,
    max_duration: int | None = None,
) -> Optional[Dict[str, Any]]:
    """Parse detailed information from individual listing page.

    Extracts:
    - Full address (complete address from page)
    - Full description text
    - All photos from gallery (URLs, order, dimensions)
    - Publication date
    - Building type and house details (year, material, series, elevator, parking)
    - Property type (flat, apartment, studio, share, newbuilding)
    - Apartment details (living area, kitchen area, balcony, loggia, renovation, layout)

    Parameters
    ----------
    page: Page
        Playwright page object
    listing_url: str
        Full URL to listing detail page

    Returns
    -------
    dict or None
        Dictionary with keys: address_full, description, published_at, building_type, property_type,
        photos, area_living, area_kitchen, balcony, loggia, renovation, rooms_layout,
        house_year, house_material, house_series, house_has_elevator, house_has_parking
        Returns None if page fails to load or parsing fails
    """
    import re
    from datetime import datetime

    try:
        if max_duration is None:
            env_timeout = os.getenv("CIAN_DETAIL_TIMEOUT")
            if env_timeout:
                try:
                    max_duration = int(env_timeout)
                except ValueError:
                    max_duration = None

        deadline = time.perf_counter() + max_duration if max_duration else None

        def _ensure_time_left(stage: str) -> None:
            if deadline is None:
                return
            if time.perf_counter() > deadline:
                raise TimeoutError(f"Detail parsing timeout while {stage}")

        def _remaining_timeout_ms(minimum: int = 500) -> Optional[int]:
            if deadline is None:
                return None
            remaining = int((deadline - time.perf_counter()) * 1000)
            if remaining <= 0:
                raise TimeoutError("Detail parsing timeout during browser operation")
            if remaining < minimum:
                raise TimeoutError("Detail parsing timeout during browser operation")
            return min(remaining, 60000)

        LOGGER.info(f"Parsing detail page: {listing_url}")

        # Navigate to listing page
        # Use domcontentloaded instead of networkidle to save proxy traffic (~70-80% less)
        # networkidle waits for ALL resources (images, CSS, JS, fonts) - very heavy on proxy
        # domcontentloaded waits only for HTML + DOM - much faster and lighter
        goto_timeout = _remaining_timeout_ms(1000) if deadline else 60000
        response = page.goto(
            listing_url,
            wait_until="domcontentloaded",
            timeout=goto_timeout or 60000,
        )

        if not response or response.status >= 400:
            status_code = response.status if response else None
            LOGGER.warning(f"Failed to load {listing_url}: HTTP {status_code}")
            # Raise special exception for rate limiting (429) to trigger proxy rotation
            if status_code == 429:
                raise RateLimitError(listing_url, status_code)
            return None

        # Wait for content to load and render
        # Give DOM time to render after domcontentloaded
        wait_duration = min(2000, (_remaining_timeout_ms() or 2000))
        page.wait_for_timeout(wait_duration)
        _ensure_time_left("post-load wait")

        # Then wait for description element (or timeout silently if not present)
        try:
            desc_timeout = _remaining_timeout_ms(1000) if deadline else 5000
            page.wait_for_selector(
                "[data-name='Description']", timeout=desc_timeout or 5000
            )
        except:
            pass  # Description might not exist on all pages

        result = {
            "address_full": None,
            "description": None,
            "description_hash": None,  # MD5 hash for duplicate detection
            "published_at": None,
            "building_type": None,
            "property_type": None,
            "photos": [],
            # Coordinates (from CIAN JSON data)
            "lat": None,
            "lon": None,
            # Floor info (for valuation)
            "floor": None,
            "total_floors": None,
            # Apartment details
            "area_living": None,
            "area_kitchen": None,
            "balcony": None,
            "loggia": None,
            "renovation": None,
            "rooms_layout": None,
            # House details
            "house_year": None,
            "house_material": None,
            "house_series": None,
            "house_has_elevator": None,
            "house_has_parking": None,
            # Price history (for exposure/discount analysis)
            "price_history": [],  # List of {price, date} dicts
            "initial_price": None,  # First known price
            "price_change_pct": None,  # Total change in %
            "days_on_market": None,  # Days since publication
        }

        # Extract full address - comprehensive scan of entire page
        # Strategy: Multiple methods starting from most reliable to least reliable
        try:
            address_source = None
            import re
            import json
            
            LOGGER.debug(f"🔍 Starting comprehensive address extraction for {listing_url}")
            
            # Method 0: Try to find address from <title> tag (FASTEST and MOST RELIABLE)
            # CIAN title format: "Продажа 2-комн. квартиры 60 м² по адресу Москва, ВАО, р-н ..."
            try:
                page_title = page.title()
                if page_title and "адрес" in page_title.lower():
                    # Extract address after "адресу" or "адрес"
                    match = re.search(r'адрес[уе]?\s+([^—\-|]+)', page_title, re.IGNORECASE)
                    if match:
                        address_candidate = match.group(1).strip()
                        cleaned = clean_address_text(address_candidate)
                        if cleaned and _address_is_valid(cleaned, require_city=False):
                            result["address_full"] = cleaned
                            address_source = "title_tag"
                            LOGGER.info(f"✅ Full address from title tag: {cleaned[:150]}")
                            # Skip other methods if we found address in title
                            if result["address_full"]:
                                pass  # Continue to other extractions
            except Exception as e:
                LOGGER.debug(f"Title tag address extraction failed: {e}")
            
            # Method 1: Try JSON-LD structured data (most reliable, priority)
            if not result["address_full"]:
                try:
                    json_ld_scripts = page.query_selector_all("script[type='application/ld+json']")
                    LOGGER.debug(f"Found {len(json_ld_scripts)} JSON-LD scripts")
                    for script in json_ld_scripts:
                        try:
                            json_text = script.inner_text()
                            data = json.loads(json_text)
                            
                            # Recursive function to find address in JSON-LD
                            def find_address_in_json(obj):
                                if isinstance(obj, dict):
                                    # Check common address fields
                                    for key in ['address', 'streetAddress', 'addressLocality', 'addressRegion', 'addressCountry']:
                                        if key in obj and isinstance(obj[key], str):
                                            if "Москва" in obj[key] or len(obj[key]) > 20:
                                                return obj[key]
                                    # Recursively search nested objects
                                    for value in obj.values():
                                        result = find_address_in_json(value)
                                        if result:
                                            return result
                                elif isinstance(obj, list):
                                    for item in obj:
                                        result = find_address_in_json(item)
                                        if result:
                                            return result
                                return None
                            
                            address_from_json = find_address_in_json(data)
                            if address_from_json and len(address_from_json) > 15:
                                cleaned = clean_address_text(address_from_json.strip())
                                if cleaned and _address_is_valid(cleaned, require_city=False):
                                    result["address_full"] = cleaned
                                    address_source = "json-ld"
                                    LOGGER.info(f"✅ Full address from JSON-LD: {cleaned[:100]}")
                                    # Don't return yet, continue to extract other fields
                        except (json.JSONDecodeError, Exception) as e:
                            LOGGER.debug(f"JSON-LD parsing failed: {e}")
                            continue
                except Exception as e:
                    LOGGER.debug(f"JSON-LD extraction failed: {e}")
            
            # Method 2: Extract address right after H1 title (most common location)
            # Address appears immediately after "Продается 2-комн. квартира, 43,2 м²"
            if not result["address_full"]:
                try:
                    h1 = page.query_selector("h1")
                    if h1:
                        try:
                            # Get the next sibling element after H1 which usually contains the address
                            # Enhanced: look not just in siblings but also in parent container
                            address_from_h1 = page.evaluate(
                                r"""
                                (h1) => {
                                    if (!h1) return null;
                                    
                                    // Helper function to check if text looks like Moscow address
                                    function looksLikeAddress(text) {
                                        if (!text || text.length < 15 || text.length > 300) return false;
                                        
                                        // Must contain "Москва" or district abbreviation
                                        const hasMoscow = text.includes('Москва');
                                        const hasDistrict = /[СЦЮВЗ][ВАЮЗО]АО|ЦАО|НАО|ТАО/i.test(text);
                                        
                                        if (!hasMoscow && !hasDistrict) return false;
                                        
                                        // Check for street indicators (more permissive)
                                        const hasStreet = /ул\.|улица|пр\.|проспект|шоссе|ш\.|пер\.|переулок|бульвар|наб\.|площадь|пл\./i.test(text);
                                        const hasHouseNumber = /\d+[кК]?\d*/.test(text);
                                        const hasDistrict2 = /р-?н\s|район|округ|мкр\.|микрорайон/i.test(text);
                                        
                                        // More lenient: accept if has Moscow + (street OR house number OR district)
                                        return hasMoscow && (hasStreet || hasHouseNumber || hasDistrict2);
                                    }
                                    
                                    // Method 1: Look for address in next sibling elements
                                    let sibling = h1.nextElementSibling;
                                    let checked = 0;
                                    while (sibling && sibling !== null && checked < 8) {  // Check more siblings
                                        checked++;
                                        const text = (sibling.textContent || sibling.innerText || '').trim();
                                        
                                        // Check if it looks like an address
                                        if (looksLikeAddress(text)) {
                                            // Remove "На карте" link if present
                                            let cleaned = text.replace(/На\s+карте.*/i, '').trim();
                                            // Remove metro station info if present  
                                            cleaned = cleaned.replace(/м\.[^,]*,\s*\d+\s*мин\..*/i, '').trim();
                                            // More aggressive metro cleaning
                                            cleaned = cleaned.replace(/[А-ЯЁ][а-яё]+\s+\d+\s*мин\.?\s*/g, '').trim();
                                            if (cleaned.length > 15 && cleaned.length < 300) {
                                                return cleaned;
                                            }
                                        }
                                        
                                        // Stop if we hit another heading or major section
                                        if (sibling.tagName === 'H2' || sibling.tagName === 'H3' || 
                                            sibling.classList.contains('section') ||
                                            sibling.querySelector('h2, h3')) {
                                            break;
                                        }
                                        
                                        sibling = sibling.nextElementSibling;
                                    }
                                    
                                    // Method 2: Look in parent container for address elements right after H1
                                    const parent = h1.parentElement;
                                    if (parent) {
                                        // Get all child nodes and find address after H1
                                        const children = Array.from(parent.children);
                                        const h1Index = children.indexOf(h1);
                                        
                                        // Check next few elements after H1
                                        for (let i = h1Index + 1; i < Math.min(h1Index + 6, children.length); i++) {
                                            const elem = children[i];
                                            const text = (elem.textContent || elem.innerText || '').trim();
                                            
                                            if (looksLikeAddress(text)) {
                                                let cleaned = text.replace(/На\s+карте.*/i, '').trim();
                                                cleaned = cleaned.replace(/м\.[^,]*,\s*\d+\s*мин\..*/i, '').trim();
                                                cleaned = cleaned.replace(/[А-ЯЁ][а-яё]+\s+\d+\s*мин\.?\s*/g, '').trim();
                                                if (cleaned.length > 15) {
                                                    return cleaned;
                                                }
                                            }
                                        }
                                        
                                        // Also check for links and spans in parent that might contain address
                                        const candidates = parent.querySelectorAll('a, span, div, p');
                                        for (let elem of candidates) {
                                            const text = (elem.textContent || elem.innerText || '').trim();
                                            if (looksLikeAddress(text)) {
                                                // Check if it's positioned after H1 (more lenient)
                                                try {
                                                    const h1Rect = h1.getBoundingClientRect();
                                                    const elemRect = elem.getBoundingClientRect();
                                                    
                                                    // Element should be near H1 (below or same level)
                                                    if (elemRect.top >= h1Rect.top - 50 && elemRect.top <= h1Rect.bottom + 200) {
                                                        let cleaned = text.replace(/На\s+карте.*/i, '').trim();
                                                        cleaned = cleaned.replace(/м\.[^,]*,\s*\d+\s*мин\..*/i, '').trim();
                                                        cleaned = cleaned.replace(/[А-ЯЁ][а-яё]+\s+\d+\s*мин\.?\s*/g, '').trim();
                                                        if (cleaned.length > 15) {
                                                            return cleaned;
                                                        }
                                                    }
                                                } catch (e) {
                                                    // getBoundingClientRect might fail, try without position check
                                                    let cleaned = text.replace(/На\s+карте.*/i, '').trim();
                                                    cleaned = cleaned.replace(/м\.[^,]*,\s*\d+\s*мин\..*/i, '').trim();
                                                    cleaned = cleaned.replace(/[А-ЯЁ][а-яё]+\s+\d+\s*мин\.?\s*/g, '').trim();
                                                    if (cleaned.length > 15) {
                                                        return cleaned;
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    
                                    return null;
                                }
                                """,
                                h1
                            )
                            
                            if address_from_h1:
                                cleaned = clean_address_text(address_from_h1.strip())
                                if cleaned and _address_is_valid(cleaned, require_city=False):
                                    result["address_full"] = cleaned
                                    address_source = "h1_sibling"
                                    LOGGER.info(f"✅ Full address from H1 sibling: {cleaned[:150]}")
                        except Exception as h1_error:
                            LOGGER.debug(f"H1-based address extraction failed: {h1_error}")
                except Exception as e:
                    LOGGER.debug(f"H1 extraction failed: {e}")
            
            # Method 3: Extract address from map links (Яндекс карты)
            # Links like "На карте" or map anchors contain address
            if not result["address_full"]:
                try:
                    # Look for map links and extract address from href or nearby text
                    map_link_address = page.evaluate(
                        r"""
                        () => {
                            // Find all links and check for map-related ones
                            const allLinks = document.querySelectorAll('a');
                            
                            for (let link of allLinks) {
                                const linkText = (link.textContent || link.innerText || '').trim();
                                const href = link.getAttribute('href') || '';
                                
                                // Check if link text contains "карте" or "карта" or href contains map
                                const isMapLink = linkText.toLowerCase().includes('карте') || 
                                                 linkText.toLowerCase().includes('карта') ||
                                                 href.includes('yandex.ru/maps') ||
                                                 href.includes('yandex.ru/map') ||
                                                 href.includes('2gis.ru') ||
                                                 href.includes('google.com/maps');
                                
                                if (isMapLink) {
                                    // Check previous sibling (address often comes before "На карте" link)
                                    let prevSibling = link.previousElementSibling;
                                    if (prevSibling) {
                                        const prevText = (prevSibling.textContent || '').trim();
                                        if (prevText.includes('Москва') && prevText.length > 20 && prevText.length < 200) {
                                            const cleaned = prevText.replace(/На\s+карте.*/i, '').trim();
                                            if (cleaned.length > 15) {
                                                return cleaned;
                                            }
                                        }
                                    }
                                    
                                    // Check parent element (address might be in same container)
                                    let parent = link.parentElement;
                                    if (parent) {
                                        const parentText = (parent.textContent || '').trim();
                                        // Extract address part before "На карте"
                                        const match = parentText.match(/^([^Н]*Москва[^Н]*?)(?:На\s+карте|на\s+карте)/i);
                                        if (match && match[1]) {
                                            const addr = match[1].trim();
                                            if (addr.length > 15 && addr.length < 200) {
                                                return addr;
                                            }
                                        }
                                        
                                        // Also try to get text before the link within parent
                                        const fullText = parentText;
                                        if (fullText.includes('Москва') && fullText.length > 20 && fullText.length < 300) {
                                            // Split by "На карте" and take first part
                                            const parts = fullText.split(/На\s+карте/i);
                                            if (parts.length > 1 && parts[0]) {
                                                const addr = parts[0].trim();
                                                if (addr.length > 15 && addr.length < 200) {
                                                    return addr;
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            
                            // Also check for text nodes containing "На карте" and get preceding address
                            const walker = document.createTreeWalker(
                                document.body,
                                NodeFilter.SHOW_TEXT,
                                null,
                                false
                            );
                            
                            let node;
                            while (node = walker.nextNode()) {
                                const text = node.textContent.trim();
                                if (text.includes('На карте') || text.includes('на карте')) {
                                    // Get parent element and look for address before this text
                                    let parent = node.parentElement;
                                    if (parent) {
                                        const fullText = (parent.textContent || '').trim();
                                        // Extract address part before "На карте"
                                        const match = fullText.match(/^([^Н]*Москва[^Н]*?)(?:На\s+карте|на\s+карте)/i);
                                        if (match && match[1]) {
                                            const addr = match[1].trim();
                                            if (addr.length > 15 && addr.length < 200) {
                                                return addr;
                                            }
                                        }
                                    }
                                }
                            }
                            
                            return null;
                        }
                        """
                    )
                    
                    if map_link_address:
                        cleaned = clean_address_text(map_link_address.strip())
                        if cleaned and _address_is_valid(cleaned, require_city=False):
                            result["address_full"] = cleaned
                            address_source = "map_link"
                            LOGGER.info(f"✅ Full address from map link: {cleaned[:150]}")
                except Exception as e:
                    LOGGER.debug(f"Map link extraction failed: {e}")
            
            # Method 4: Specific CIAN selectors (breadcrumbs, dedicated address blocks)
            if not result["address_full"]:
                try:
                    for selector in DETAIL_ADDRESS_SELECTORS:
                        _ensure_time_left(f"evaluating selector {selector}")
                        node = page.query_selector(selector)
                        if not node:
                            continue
                        parts = _collect_address_parts(node)
                        candidate = _prepare_address_from_parts(parts)
                        if candidate and _address_is_valid(candidate, require_city=False):
                            result["address_full"] = candidate
                            address_source = f"selector:{selector}"
                            LOGGER.info(f"✅ Full address from selector {selector}: {candidate[:100]}")
                            break
                except Exception as selector_error:
                    LOGGER.debug(f"Selector-based address extraction failed: {selector_error}")

            # Method 3: Comprehensive DOM scan - find all elements containing address parts
            if not result["address_full"]:
                try:
                    LOGGER.debug("Scanning DOM for address elements...")
                    
                    # Get all text elements and links on the page
                    all_elements = page.query_selector_all("a, span, div, p, li")
                    address_candidates = []
                    
                    for elem in all_elements:
                        _ensure_time_left("scanning DOM elements")
                        try:
                            elem_text = elem.inner_text().strip()
                            if not elem_text or len(elem_text) < 5:
                                continue
                            
                            # Skip common non-address elements
                            skip_patterns = [
                                r'^Фотографи',
                                r'^Описани',
                                r'^Расположени',
                                r'^Похожие',
                                r'^Недвижимость',
                                r'^Цена',
                                r'^Площадь',
                                r'^Комнат',
                                r'^Этаж',
                            ]
                            
                            should_skip = any(re.match(pattern, elem_text, re.I) for pattern in skip_patterns)
                            if should_skip:
                                continue
                            
                            # Check if element contains address indicators
                            has_moscow = "Москва" in elem_text
                            has_street = bool(re.search(r'(ул\.|улица|проспект|пр\.|переулок|пер\.)', elem_text, re.I))
                            has_number = bool(re.search(r'\d+', elem_text))
                            has_district = bool(re.search(r'(СВАО|САО|СЗАО|ЮАО|ЮВАО|ВАО|ЗАО|ЦАО|р-н|район)', elem_text, re.I))
                            
                            # Must have Москва to be considered
                            if not has_moscow and not has_district:
                                continue
                            
                            # Score element based on address indicators
                            score = 0
                            if has_moscow:
                                score += 4
                            if has_street:
                                score += 3
                            if has_district:
                                score += 2
                            if has_number:
                                score += 1
                            
                            if score >= 5 and len(elem_text) > 15:
                                address_candidates.append((score, elem_text, elem))
                        except Exception:
                            continue
                    
                    # Sort candidates by score (highest first)
                    address_candidates.sort(key=lambda x: x[0], reverse=True)
                    LOGGER.debug(f"Found {len(address_candidates)} address candidates")
                    
                    # Try to find complete address from candidates
                    for score, candidate_text, elem in address_candidates[:12]:  # Check top candidates
                        candidate_clean = clean_address_text(candidate_text.strip())
                        if not candidate_clean:
                            continue

                        if not _address_is_valid(candidate_clean, require_city=False):
                            continue

                        result["address_full"] = candidate_clean
                        address_source = f"dom_scan(score={score})"
                        LOGGER.info(f"✅ Full address from DOM scan (score={score}): {candidate_clean[:100]}")
                        break
                    
                    # If no single element has complete address, try to combine nearby elements
                    if not result["address_full"] and address_candidates:
                        LOGGER.debug("Trying to combine address parts from multiple elements...")
                        # Get elements near H1
                        h1 = page.query_selector("h1")
                        if h1:
                            # Find parent container
                            try:
                                parent = h1.evaluate("(el) => el.parentElement")
                                if parent:
                                    # Get all text from parent container
                                    parts = page.evaluate(
                                        """
                                        (el) => {
                                            if (!el) return [];
                                            const parts = [];
                                            el.querySelectorAll('a, span').forEach(node => {
                                                const text = (node.innerText || '').trim();
                                                if (text) {
                                                    parts.push(text);
                                                }
                                            });
                                            return parts;
                                        }
                                        """,
                                        parent,
                                    )
                                    candidate = _prepare_address_from_parts(parts or [])
                                    if candidate and _address_is_valid(candidate, require_city=False):
                                        result["address_full"] = candidate
                                        address_source = "combined_breadcrumbs"
                                        LOGGER.info(f"✅ Full address from combined elements: {candidate[:100]}")
                            except Exception as e:
                                LOGGER.debug(f"Combining elements failed: {e}")
                except Exception as e:
                    LOGGER.warning(f"DOM scan failed: {e}")
            
            # Method 3: Full page text scan with regex patterns
            if not result["address_full"]:
                try:
                    LOGGER.debug("Scanning full page text with regex patterns...")
                    page_text = page.inner_text() if hasattr(page, 'inner_text') else page.evaluate("() => document.body.innerText")
                    
                    # More comprehensive patterns
                    address_patterns = [
                        r'Москва[^\\n]*?ул\.?[^\\n]*?\\d+',  # Москва ... ул. ... число
                        r'Москва[^\\n]*?улица[^\\n]*?\\d+',  # Москва ... улица ... число
                        r'Москва[^,]*,[^,]*,[^,]*,[^,]*,[^\\n]*\\d+',  # Москва, ..., ..., ..., ..., число
                        r'Москва[^,]*,[^,]*,[^,]*,[^,]*,[^,]*,[^\\n]*\\d+',  # Москва, ..., ..., ..., ..., ..., число
                        r'Москва[^,]*,[^,]*,[^,]*ул\.?[^,]*,[^\\n]*\\d+',  # Москва, ..., ..., ул. ..., число
                    ]
                    
                    for pattern in address_patterns:
                        _ensure_time_left("regex scan")
                        matches = re.findall(pattern, page_text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                        if matches:
                            LOGGER.debug(f"Pattern {pattern} found {len(matches)} matches")
                            for match in matches:
                                match_clean = clean_address_text(" ".join(match.split()))
                                if match_clean and _address_is_valid(match_clean, require_city=False):
                                    result["address_full"] = match_clean
                                    address_source = "regex"
                                    LOGGER.info(f"✅ Full address from regex pattern: {match_clean[:100]}")
                                    break
                            if result["address_full"]:
                                break
                except Exception as e:
                    LOGGER.warning(f"Regex pattern scan failed: {e}")
            
            # Method 4: Try to get address from page HTML directly
            if not result["address_full"]:
                try:
                    LOGGER.debug("Trying to extract from page HTML...")
                    page_html = page.content()
                    
                    # Look for address in HTML attributes or data attributes
                    html_address_patterns = [
                        r'data-address=["\']([^"\']*Москва[^"\']*)["\']',
                        r'itemprop=["\']address["\'][^>]*>([^<]*Москва[^<]*)<',
                        r'class=["\'][^"\']*address[^"\']*["\'][^>]*>([^<]*Москва[^<]*)<',
                    ]
                    
                    for pattern in html_address_patterns:
                        _ensure_time_left("html attribute scan")
                        matches = re.findall(pattern, page_html, re.IGNORECASE)
                        if matches:
                            for match in matches:
                                match_clean = clean_address_text(" ".join(match.split()))
                                if match_clean and _address_is_valid(match_clean, require_city=False):
                                    result["address_full"] = match_clean
                                    address_source = "html_attr"
                                    LOGGER.info(f"✅ Full address from HTML attributes: {match_clean[:100]}")
                                    break
                            if result["address_full"]:
                                break
                except Exception as e:
                    LOGGER.debug(f"HTML extraction failed: {e}")
                    
        except Exception as e:
            LOGGER.warning(f"Failed to extract full address: {e}")
        
        # Log final result
        if result["address_full"]:
            source_label = f" ({address_source})" if address_source else ""
            address_preview = result['address_full'][:150] if len(result['address_full']) > 150 else result['address_full']
            address_len = len(result['address_full'])
            LOGGER.info(f"✅ Full address saved{source_label} ({address_len} chars): {address_preview}")
        else:
            LOGGER.warning(f"⚠️ Full address NOT extracted for {listing_url} - all methods failed")
            # Log page structure for debugging
            try:
                h1_exists = bool(page.query_selector("h1"))
                links_count = len(page.query_selector_all("a"))
                LOGGER.debug(f"Page structure: H1={h1_exists}, Links={links_count}")
            except Exception:
                pass

        # Extract coordinates from CIAN page JavaScript data
        try:
            coords = page.evaluate(
                """
                () => {
                    // Method 1: Try window.__initialState or __cianInitialState
                    const stateVars = ['__initialState__', '__cianInitialState__', '_cianGeoSearchFrontend_Data'];
                    for (const varName of stateVars) {
                        if (window[varName]) {
                            const findCoords = (obj, depth = 0) => {
                                if (depth > 10 || !obj) return null;
                                if (typeof obj === 'object') {
                                    // Direct geo coordinates
                                    if (obj.coordinates && obj.coordinates.lat && obj.coordinates.lng) {
                                        return {lat: obj.coordinates.lat, lon: obj.coordinates.lng};
                                    }
                                    if (obj.coordinates && obj.coordinates.lat && obj.coordinates.lon) {
                                        return {lat: obj.coordinates.lat, lon: obj.coordinates.lon};
                                    }
                                    if (obj.geo && obj.geo.coordinates) {
                                        return {lat: obj.geo.coordinates.lat, lon: obj.geo.coordinates.lng || obj.geo.coordinates.lon};
                                    }
                                    if (obj.lat && obj.lng) {
                                        return {lat: obj.lat, lon: obj.lng};
                                    }
                                    if (obj.lat && obj.lon) {
                                        return {lat: obj.lat, lon: obj.lon};
                                    }
                                    // Search nested
                                    for (const key of Object.keys(obj)) {
                                        const result = findCoords(obj[key], depth + 1);
                                        if (result) return result;
                                    }
                                }
                                return null;
                            };
                            const coords = findCoords(window[varName]);
                            if (coords) return coords;
                        }
                    }

                    // Method 2: Parse script tags for JSON with coordinates
                    const scripts = document.querySelectorAll('script:not([src])');
                    for (const script of scripts) {
                        const text = script.textContent || '';
                        // Look for coordinate patterns
                        const coordMatch = text.match(/"coordinates"\\s*:\\s*\\{\\s*"lat"\\s*:\\s*([\\d.]+)\\s*,\\s*"l(?:ng|on)"\\s*:\\s*([\\d.]+)/);
                        if (coordMatch) {
                            return {lat: parseFloat(coordMatch[1]), lon: parseFloat(coordMatch[2])};
                        }
                        const geoMatch = text.match(/"geo"\\s*:\\s*\\{[^}]*"lat"\\s*:\\s*([\\d.]+)[^}]*"l(?:ng|on)"\\s*:\\s*([\\d.]+)/);
                        if (geoMatch) {
                            return {lat: parseFloat(geoMatch[1]), lon: parseFloat(geoMatch[2])};
                        }
                    }

                    // Method 3: Check for map links with coordinates
                    const mapLinks = document.querySelectorAll('a[href*="maps"], a[href*="yandex"], a[href*="google"]');
                    for (const link of mapLinks) {
                        const href = link.href;
                        const llMatch = href.match(/ll=([\\d.]+),([\\d.]+)/);
                        if (llMatch) {
                            return {lat: parseFloat(llMatch[1]), lon: parseFloat(llMatch[2])};
                        }
                        const ptMatch = href.match(/pt=([\\d.]+),([\\d.]+)/);
                        if (ptMatch) {
                            return {lat: parseFloat(ptMatch[2]), lon: parseFloat(ptMatch[1])};
                        }
                    }

                    return null;
                }
                """
            )
            if coords and coords.get('lat') and coords.get('lon'):
                result["lat"] = float(coords['lat'])
                result["lon"] = float(coords['lon'])
                LOGGER.info(f"✅ Coordinates extracted: lat={result['lat']}, lon={result['lon']}")
        except Exception as e:
            LOGGER.debug(f"Coordinates extraction failed: {e}")

        # Extract description (full text, not truncated)
        try:
            # Try multiple selectors for description (ordered by reliability)
            desc_selectors = [
                "[data-name='Description']",
                "[data-name='OfferDescription']",  # Added
                "[data-name='ObjectDescription']",
                "[itemprop='description']",
                ".object-description",
                ".offer-description",
                ".description",
                "[class*='description']",
                "[class*='Description']",
                "[data-testid='description']",  # Added
                "#description",  # Added
            ]
            
            for selector in desc_selectors:
                try:
                    desc_elem = page.query_selector(selector)
                    if desc_elem:
                        # Get full text including all paragraphs
                        desc_text = desc_elem.inner_text().strip()
                        # Preserve paragraph breaks but clean up extra whitespace
                        desc_text = "\n".join([p.strip() for p in desc_text.split("\n") if p.strip()])
                        if desc_text and len(desc_text) > 20:  # Valid description should be substantial
                            result["description"] = desc_text
                            LOGGER.info(f"✅ Description extracted via {selector}: {len(desc_text)} chars")
                            break
                except Exception:
                    continue
            
            # If still no description, try JavaScript-based extraction (more comprehensive)
            if not result["description"]:
                try:
                    # Use JavaScript to find description more aggressively
                    desc_from_js = page.evaluate(
                        """
                        () => {
                            // Method 1: Try known CIAN description containers
                            const containers = [
                                '[data-name="Description"]',
                                '[itemprop="description"]',
                                '.object-description',
                                '.offer-description',
                                '.description'
                            ];
                            
                            for (const selector of containers) {
                                const elem = document.querySelector(selector);
                                if (elem) {
                                    const text = (elem.textContent || elem.innerText || '').trim();
                                    if (text.length > 30) {
                                        return text;
                                    }
                                }
                            }
                            
                            // Method 2: Look for description by heading
                            // Find "Описание" or "Description" heading and get text after it
                            const allElements = document.querySelectorAll('h2, h3, h4, div, span, p');
                            for (let i = 0; i < allElements.length; i++) {
                                const elem = allElements[i];
                                const text = (elem.textContent || '').trim();
                                
                                if (text === 'Описание' || text === 'Description' || text.includes('Описание объявления')) {
                                    // Found heading, look for description in next siblings
                                    let sibling = elem.nextElementSibling;
                                    let checked = 0;
                                    while (sibling && checked < 5) {
                                        checked++;
                                        const siblingText = (sibling.textContent || sibling.innerText || '').trim();
                                        // Description should be substantial (>100 chars) and not be a heading
                                        if (siblingText.length > 100 && !['H1','H2','H3','H4','H5','H6'].includes(sibling.tagName)) {
                                            return siblingText;
                                        }
                                        sibling = sibling.nextElementSibling;
                                    }
                                }
                            }
                            
                            // Method 3: Look for long text blocks that might be description
                            // (paragraphs or divs with substantial text)
                            const longTexts = [];
                            const candidates = document.querySelectorAll('p, div');
                            for (const elem of candidates) {
                                // Get only direct text content (not nested)
                                let text = '';
                                for (const node of elem.childNodes) {
                                    if (node.nodeType === Node.TEXT_NODE) {
                                        text += node.textContent;
                                    }
                                }
                                text = text.trim();
                                
                                // Consider as description if:
                                // - Length > 150 chars (substantial text)
                                // - Contains sentences (has periods or exclamation marks)
                                // - Not a navigation/menu item
                                if (text.length > 150 && (text.includes('.') || text.includes('!')) && !text.includes('©')) {
                                    longTexts.push({text: text, length: text.length});
                                }
                            }
                            
                            // Return the longest text found (most likely description)
                            if (longTexts.length > 0) {
                                longTexts.sort((a, b) => b.length - a.length);
                                return longTexts[0].text;
                            }
                            
                            return null;
                        }
                        """
                    )
                    
                    if desc_from_js and len(desc_from_js) > 20:
                        # Clean up the description
                        desc_text = "\n".join([p.strip() for p in desc_from_js.split("\n") if p.strip()])
                        result["description"] = desc_text
                        LOGGER.debug(f"✅ Description from JavaScript extraction: {len(desc_text)} chars")
                except Exception as js_error:
                    LOGGER.debug(f"JavaScript description extraction failed: {js_error}")
            
            # If STILL no description, try textarea or content divs
            if not result["description"]:
                try:
                    # Some pages have description in textarea or content divs
                    content_elem = page.query_selector("textarea[name='description'], .content-text, .offer-text")
                    if content_elem:
                        desc_text = content_elem.inner_text().strip()
                        desc_text = "\n".join([p.strip() for p in desc_text.split("\n") if p.strip()])
                        if desc_text and len(desc_text) > 20:
                            result["description"] = desc_text
                            LOGGER.debug(f"✅ Description from content: {len(desc_text)} chars")
                except Exception:
                    pass
            
            if not result["description"]:
                LOGGER.warning(f"⚠️  No description found for {listing_url}")
            else:
                LOGGER.info(f"✅ Description extracted: {len(result['description'])} chars")
                # Calculate description hash for duplicate detection
                import hashlib
                normalized_desc = ' '.join(result["description"].lower().split())
                result["description_hash"] = hashlib.md5(normalized_desc.encode()).hexdigest()

        except Exception as e:
            LOGGER.warning(f"Failed to extract description: {e}")

        # Extract photos from gallery
        try:
            # CIAN stores photos at: https://images.cdn-cian.ru/images/XXXXXX-1.jpg
            # Photos can be in:
            # - img[src], img[data-src], img[srcset]
            # - picture > source[srcset]
            # - style="background-image: url(...)"
            
            photo_urls = []
            
            # Method 1: Extract from img tags (src, data-src, srcset)
            all_images = page.query_selector_all("img")
            for img in all_images:
                # Try multiple attributes
                src = (
                    img.get_attribute("src") or 
                    img.get_attribute("data-src") or 
                    img.get_attribute("data-lazy-src") or
                    ""
                )
                
                # Also check srcset attribute (might contain multiple URLs)
                srcset = img.get_attribute("srcset") or img.get_attribute("data-srcset") or ""
                if srcset:
                    # Parse srcset format: "url1 1x, url2 2x" or "url1 100w, url2 200w"
                    srcset_urls = [part.split()[0] for part in srcset.split(",") if part.strip()]
                    # Use the first (usually highest quality) URL
                    if srcset_urls:
                        src = srcset_urls[0]
                
                # Filter: only CIAN photo images from images.cdn-cian.ru
                if src and "images.cdn-cian.ru/images/" in src:
                    # Ensure URL ends with image extension (or contains it)
                    if any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                        # Extract dimensions if available
                        width = img.get_attribute("width")
                        height = img.get_attribute("height")
                        photo_urls.append({
                            "url": src,
                            "width": int(width) if width and width.isdigit() else None,
                            "height": int(height) if height and height.isdigit() else None
                        })
            
            # Method 2: Extract from picture > source elements
            picture_sources = page.query_selector_all("picture > source")
            for source in picture_sources:
                srcset = source.get_attribute("srcset") or ""
                if srcset and "images.cdn-cian.ru/images/" in srcset:
                    # Parse srcset
                    srcset_urls = [part.split()[0] for part in srcset.split(",") if part.strip()]
                    for url in srcset_urls:
                        if any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                            photo_urls.append({
                                "url": url,
                                "width": None,
                                "height": None
                            })
            
            # Method 3: Use JavaScript to find more images (lazy-loaded, background-image, etc.)
            if len(photo_urls) < 3:  # If we found less than 3 photos, try JavaScript extraction
                try:
                    photos_from_js = page.evaluate(
                        """
                        () => {
                            const photos = [];
                            
                            // Find all img elements
                            const images = document.querySelectorAll('img');
                            images.forEach(img => {
                                const src = img.src || img.getAttribute('data-src') || img.getAttribute('data-lazy-src') || '';
                                if (src && src.includes('images.cdn-cian.ru/images/')) {
                                    photos.push({
                                        url: src,
                                        width: img.width || null,
                                        height: img.height || null
                                    });
                                }
                            });
                            
                            // Find elements with background-image
                            const allElements = document.querySelectorAll('*');
                            allElements.forEach(elem => {
                                const style = window.getComputedStyle(elem);
                                const bgImage = style.backgroundImage;
                                if (bgImage && bgImage !== 'none') {
                                    const match = bgImage.match(/url\\(["']?(.*?)["']?\\)/);
                                    if (match && match[1] && match[1].includes('images.cdn-cian.ru/images/')) {
                                        photos.push({
                                            url: match[1],
                                            width: null,
                                            height: null
                                        });
                                    }
                                }
                            });
                            
                            return photos;
                        }
                        """
                    )
                    
                    if photos_from_js:
                        photo_urls.extend(photos_from_js)
                        LOGGER.debug(f"Found {len(photos_from_js)} additional photos via JavaScript")
                except Exception as js_error:
                    LOGGER.debug(f"JavaScript photo extraction failed: {js_error}")

            # Deduplicate photos by URL (normalize URLs first)
            seen_urls = set()
            unique_photos = []
            for idx, photo in enumerate(photo_urls):
                # Normalize URL (remove query parameters for deduplication, but keep original URL)
                url_for_comparison = photo["url"].split("?")[0]
                
                if url_for_comparison not in seen_urls:
                    seen_urls.add(url_for_comparison)
                    unique_photos.append({
                        "url": photo["url"],
                        "order": len(unique_photos),  # Order by discovery order
                        "width": photo.get("width"),
                        "height": photo.get("height")
                    })

            result["photos"] = unique_photos
            if unique_photos:
                LOGGER.info(f"✅ Photos: {len(unique_photos)} images extracted")
            else:
                LOGGER.warning(f"⚠️  No photos found for {listing_url}")
                # Try one more time with a more aggressive search
                try:
                    LOGGER.debug("Trying aggressive photo search...")
                    aggressive_photos = page.evaluate(
                        """
                        () => {
                            const photos = new Set();
                            
                            // Search all elements for image URLs
                            document.querySelectorAll('*').forEach(elem => {
                                // Check src attributes
                                ['src', 'data-src', 'data-lazy-src', 'data-original'].forEach(attr => {
                                    const val = elem.getAttribute(attr);
                                    if (val && val.includes('cdn-cian.ru') && /\\.(jpg|jpeg|png|webp)/i.test(val)) {
                                        photos.add(val);
                                    }
                                });
                                
                                // Check srcset
                                const srcset = elem.getAttribute('srcset') || elem.getAttribute('data-srcset');
                                if (srcset) {
                                    srcset.split(',').forEach(part => {
                                        const url = part.trim().split(' ')[0];
                                        if (url && url.includes('cdn-cian.ru') && /\\.(jpg|jpeg|png|webp)/i.test(url)) {
                                            photos.add(url);
                                        }
                                    });
                                }
                                
                                // Check background-image in style
                                const style = window.getComputedStyle(elem);
                                const bgImage = style.backgroundImage;
                                if (bgImage && bgImage !== 'none') {
                                    const match = bgImage.match(/url\\(["']?(.*?)["']?\\)/);
                                    if (match && match[1] && match[1].includes('cdn-cian.ru')) {
                                        photos.add(match[1]);
                                    }
                                }
                            });
                            
                            return Array.from(photos).map((url, idx) => ({
                                url: url,
                                order: idx,
                                width: null,
                                height: null
                            }));
                        }
                        """
                    )
                    
                    if aggressive_photos:
                        result["photos"] = aggressive_photos
                        LOGGER.info(f"✅ Photos (aggressive search): {len(aggressive_photos)} images extracted")
                except Exception as e:
                    LOGGER.debug(f"Aggressive photo search failed: {e}")

        except Exception as e:
            LOGGER.warning(f"Failed to extract photos: {e}")

        # Extract publication date
        try:
            # Look for date in metadata or page content
            # CIAN typically shows "Опубликовано: 15 октября"
            date_patterns = [
                r'Опубликовано[:\s]+(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+(\d{4}))?',
                r'(\d{1,2})\.(\d{1,2})\.(\d{4})',  # DD.MM.YYYY
            ]

            page_content = page.content()

            for pattern in date_patterns:
                match = re.search(pattern, page_content, re.IGNORECASE)
                if match:
                    if "Опубликовано" in pattern:
                        # Russian month name format
                        day = int(match.group(1))
                        month_name = match.group(2).lower()
                        year = int(match.group(3)) if match.group(3) else datetime.now().year

                        months = {
                            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
                            'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
                            'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
                        }
                        month = months.get(month_name)

                        if month:
                            result["published_at"] = datetime(year, month, day)
                            LOGGER.debug(f"Publication date: {result['published_at']}")
                            break
                    else:
                        # DD.MM.YYYY format
                        try:
                            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                            # Validate before creating datetime
                            if 1 <= day <= 31 and 1 <= month <= 12 and 2000 <= year <= 2030:
                                result["published_at"] = datetime(year, month, day)
                                LOGGER.debug(f"Publication date: {result['published_at']}")
                                break
                        except (ValueError, IndexError):
                            continue

        except Exception as e:
            LOGGER.warning(f"Failed to extract publication date: {e}")

        # Extract price history and discount info
        # CIAN shows "Динамика цены" block if price changed
        try:
            price_history_data = page.evaluate('''
                () => {
                    const result = {
                        history: [],
                        currentPrice: null,
                        initialPrice: null,
                        daysOnMarket: null,
                        priceChangePct: null
                    };

                    const text = document.body.innerText;

                    // Extract current price from page
                    // Look for price in RUB (e.g., "9 500 000 ₽" or "9,5 млн ₽")
                    const priceMatch = text.match(/([\d\s]+)\s*₽/);
                    if (priceMatch) {
                        const priceStr = priceMatch[1].replace(/\s/g, '');
                        result.currentPrice = parseInt(priceStr);
                    }

                    // Look for "Цена снижена" or discount info
                    // Pattern: "Цена снижена на X%" or "−X%"
                    const discountMatch = text.match(/[Цц]ена\\s+снижена\\s+на\\s+(\\d+)\\s*%/i);
                    if (discountMatch) {
                        result.priceChangePct = -parseInt(discountMatch[1]);
                    }

                    // Alternative: "−15%" near price
                    const negPctMatch = text.match(/[−-](\\d+)\\s*%/);
                    if (negPctMatch && !result.priceChangePct) {
                        result.priceChangePct = -parseInt(negPctMatch[1]);
                    }

                    // Look for "Динамика цены" block
                    // This block contains price history chart/data
                    const dynamicsMatch = text.match(/[Дд]инамика\\s+цены/i);
                    if (dynamicsMatch) {
                        // Try to extract price changes
                        // CIAN shows dates and prices like "15 окт — 10 000 000 ₽"
                        const historyPattern = /(\\d{1,2})\\s+(янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек)[а-я]*\\s*[—-]?\\s*([\\d\\s]+)\\s*₽/gi;
                        let match;
                        while ((match = historyPattern.exec(text)) !== null) {
                            const day = parseInt(match[1]);
                            const monthStr = match[2].toLowerCase().substring(0, 3);
                            const priceStr = match[3].replace(/\\s/g, '');
                            const price = parseInt(priceStr);

                            const monthMap = {
                                'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4,
                                'мая': 5, 'июн': 6, 'июл': 7, 'авг': 8,
                                'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12
                            };
                            const month = monthMap[monthStr] || 1;
                            const year = new Date().getFullYear();

                            if (price && price > 100000) {
                                result.history.push({
                                    price: price,
                                    date: `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
                                });
                            }
                        }
                    }

                    // Calculate initial price from history
                    if (result.history.length > 0) {
                        // Sort by date ascending
                        result.history.sort((a, b) => a.date.localeCompare(b.date));
                        result.initialPrice = result.history[0].price;

                        // Calculate total change if we have current price
                        if (result.currentPrice && result.initialPrice) {
                            result.priceChangePct = ((result.currentPrice - result.initialPrice) / result.initialPrice * 100).toFixed(1);
                        }
                    }

                    // Look for days on market / exposure time
                    // "Объявление опубликовано 45 дней назад" or "на сайте 30 дней"
                    const daysMatch = text.match(/(\\d+)\\s*дн[а-я]*\\s*(на\\s*сайте|назад|в\\s*продаже)/i);
                    if (daysMatch) {
                        result.daysOnMarket = parseInt(daysMatch[1]);
                    }

                    // Alternative: "опубликовано X дней"
                    const pubDaysMatch = text.match(/опубликовано\\s*(\\d+)\\s*дн/i);
                    if (pubDaysMatch && !result.daysOnMarket) {
                        result.daysOnMarket = parseInt(pubDaysMatch[1]);
                    }

                    return result;
                }
            ''')

            if price_history_data:
                if price_history_data.get('history'):
                    result["price_history"] = price_history_data['history']
                    LOGGER.info(f"💰 Price history: {len(result['price_history'])} records")
                if price_history_data.get('initialPrice'):
                    result["initial_price"] = price_history_data['initialPrice']
                    LOGGER.debug(f"Initial price: {result['initial_price']:,}")
                if price_history_data.get('priceChangePct'):
                    result["price_change_pct"] = float(price_history_data['priceChangePct'])
                    LOGGER.info(f"📉 Price change: {result['price_change_pct']}%")
                if price_history_data.get('daysOnMarket'):
                    result["days_on_market"] = price_history_data['daysOnMarket']
                    LOGGER.debug(f"Days on market: {result['days_on_market']}")

        except Exception as e:
            LOGGER.warning(f"Failed to extract price history: {e}")

        # Extract building type
        try:
            # Look for building type in property details
            # Typically in a list like "Тип дома: Панельный"
            building_types = {
                'панельный': 'panel',
                'кирпичный': 'brick',
                'монолитный': 'monolithic',
                'блочный': 'block',
                'деревянный': 'wood'
            }

            page_content_lower = page.content().lower()
            for russian, english in building_types.items():
                if russian in page_content_lower:
                    result["building_type"] = english
                    LOGGER.debug(f"Building type: {english}")
                    break

        except Exception as e:
            LOGGER.warning(f"Failed to extract building type: {e}")

        # Extract property type - check for apartments, newbuildings, shares
        try:
            page_content = page.content()
            page_content_lower = page_content.lower()
            
            # PRIORITY 0: Check "Размер доли" field - if exists and != 1/1, it's a share
            share_size = None
            try:
                # Extract "Размер доли" field from page
                share_size_value = page.evaluate(
                    """
                    () => {
                        // Look for "Размер доли" text in the page
                        const walker = document.createTreeWalker(
                            document.body,
                            NodeFilter.SHOW_TEXT,
                            null,
                            false
                        );
                        
                        let node;
                        while (node = walker.nextNode()) {
                            const text = node.textContent.trim();
                            if (text.includes('Размер доли') || text.includes('Размер доли:')) {
                                // Found the label, now find the value
                                let parent = node.parentElement;
                                
                                // Try to find value in the same parent element
                                const parentText = parent.textContent || '';
                                const match = parentText.match(/Размер\\s+доли[:\\s]+([\\d\\/]+)/i);
                                if (match && match[1]) {
                                    return match[1].trim();
                                }
                                
                                // Try next sibling
                                let sibling = parent.nextElementSibling;
                                if (sibling) {
                                    const siblingText = (sibling.textContent || '').trim();
                                    // Check if it matches fraction pattern (e.g., "1/2", "1/8")
                                    if (/^\\d+\\/\\d+$/.test(siblingText)) {
                                        return siblingText;
                                    }
                                }
                                
                                // Try parent's parent
                                if (parent.parentElement) {
                                    const grandParentText = parent.parentElement.textContent || '';
                                    const match2 = grandParentText.match(/Размер\\s+доли[:\\s]+([\\d\\/]+)/i);
                                    if (match2 && match2[1]) {
                                        return match2[1].trim();
                                    }
                                }
                            }
                        }
                        
                        return null;
                    }
                    """
                )
                
                # Also try regex search in page content as fallback
                if not share_size_value:
                    share_match = re.search(r'Размер\s+доли[:\s]+([\d\/]+)', page_content, re.IGNORECASE)
                    if share_match:
                        share_size_value = share_match.group(1).strip()
                
                if share_size_value:
                    share_size = share_size_value
                    LOGGER.info(f"📊 Размер доли: {share_size}")
                    
                    # Check if it's a partial share (not full ownership)
                    # Full ownership: "1/1" or no field at all
                    # Partial share: "1/2", "1/3", "1/4", "1/8", etc.
                    if share_size and share_size != "1/1":
                        # This is a share, not full ownership
                        result["property_type"] = 'share'
                        LOGGER.info(f"⚠️  Detected share ownership: {share_size} - marking as 'share'")
                        # No need to continue - we know it's a share
                        return result
                    
            except Exception as e:
                LOGGER.debug(f"Failed to extract 'Размер доли': {e}")
            
            # PRIORITY 1: Parse structured "О квартире" section with "Тип жилья" field
            # This is the most reliable source for property type
            try:
                # Method 1: Try to find "Тип жилья" using JavaScript evaluation
                # This searches for the label and extracts the value from the same container
                property_type_value = page.evaluate(
                    """
                    () => {
                        // Look for "Тип жилья" text in the page
                        const walker = document.createTreeWalker(
                            document.body,
                            NodeFilter.SHOW_TEXT,
                            null,
                            false
                        );
                        
                        let node;
                        while (node = walker.nextNode()) {
                            const text = node.textContent.trim();
                            if (text.includes('Тип жилья') || text.includes('Тип жилья:')) {
                                // Found the label, now find the value
                                let parent = node.parentElement;
                                
                                // Try to find value in the same parent element
                                const parentText = parent.textContent || '';
                                const match = parentText.match(/Тип\\s+жилья[:\\s]+([^\\n\\r<]+)/i);
                                if (match && match[1]) {
                                    const value = match[1].trim();
                                    if (value.length > 0 && value.length < 100) {
                                        return value;
                                    }
                                }
                                
                                // Try next sibling
                                let sibling = parent.nextElementSibling;
                                if (sibling) {
                                    const siblingText = (sibling.textContent || '').trim();
                                    if (siblingText.length > 0 && siblingText.length < 100) {
                                        return siblingText;
                                    }
                                }
                                
                                // Try parent's parent (for table rows or list items)
                                if (parent.parentElement) {
                                    const grandParentText = parent.parentElement.textContent || '';
                                    const match2 = grandParentText.match(/Тип\\s+жилья[:\\s]+([^\\n\\r<]+)/i);
                                    if (match2 && match2[1]) {
                                        const value = match2[1].trim();
                                        if (value.length > 0 && value.length < 100) {
                                            return value;
                                        }
                                    }
                                }
                            }
                        }
                        
                        return null;
                    }
                    """
                )
                
                # Method 2: Regex search in page content for "Тип жилья: Новостройка" pattern
                if not property_type_value:
                    type_match = re.search(r'Тип\s+жилья[:\s]+([^\n\r<]+)', page_content, re.IGNORECASE)
                    if type_match:
                        property_type_value = type_match.group(1).strip().lower()
                    else:
                        property_type_value = None
                else:
                    property_type_value = property_type_value.lower() if isinstance(property_type_value, str) else None
                
                # Map extracted value to property_type
                if property_type_value:
                    if 'новостройка' in property_type_value or 'newbuilding' in property_type_value:
                        result["property_type"] = 'newbuilding'
                        LOGGER.info(f"✅ Property type from 'Тип жилья': новостройка")
                    elif 'апартамент' in property_type_value or 'apartment' in property_type_value:
                        result["property_type"] = 'apartment'
                        LOGGER.info(f"✅ Property type from 'Тип жилья': апартаменты")
                    elif 'вторичка' in property_type_value or 'вторичный' in property_type_value:
                        result["property_type"] = 'flat'
                        LOGGER.info(f"✅ Property type from 'Тип жилья': вторичка")
                    elif 'доля' in property_type_value or 'share' in property_type_value:
                        result["property_type"] = 'share'
                        LOGGER.info(f"✅ Property type from 'Тип жилья': доля")
                    elif 'комната' in property_type_value or 'room' in property_type_value:
                        result["property_type"] = 'room'
                        LOGGER.info(f"✅ Property type from 'Тип жилья': комната")
                    elif 'студия' in property_type_value or 'studio' in property_type_value:
                        result["property_type"] = 'studio'
                        LOGGER.info(f"✅ Property type from 'Тип жилья': студия")
            except Exception as e:
                LOGGER.debug(f"Failed to parse 'Тип жилья' section: {e}")

            # PRIORITY 1.5: Override for rooms - check if description indicates this is a room, not a flat
            # Rooms can be listed under "Вторичка" but are actually rooms (комнаты)
            # This check should happen BEFORE other fallbacks
            if result.get("property_type") == "flat" or not result.get("property_type"):
                room_indicators = ['продается комната', 'продаётся комната', 'продаю комнату',
                                   'комната в коммунальной', 'комната в общежитии']
                if any(indicator in page_content_lower for indicator in room_indicators) or '/room/' in listing_url.lower():
                    result["property_type"] = 'room'
                    LOGGER.info(f"⚠️  Override: Detected room listing from description/URL (was: flat/Вторичка)")

            # PRIORITY 2: Enhanced newbuilding detection - check multiple indicators
            # Only if property_type not set from structured data
            if not result.get("property_type"):
                newbuilding_indicators = [
                    'новостройка', 'newbuilding', '/newbuilding/', '/new/',
                    'жилой комплекс', 'жилой район', 'жк ', 'жк.', 'жк,',
                    'микрорайон', 'новый дом', 'новый район', 'застройщик',
                    'строится', 'в стадии строительства', 'сдача', 'сдач'
                ]
                
                # Check for "Тип жилья" section which shows: Вторичка / Апартаменты or Новостройка
                # Look for property type indicators
                if 'апартамент' in page_content_lower or 'apartment' in page_content_lower:
                    result["property_type"] = 'apartment'
                elif any(indicator in page_content_lower for indicator in newbuilding_indicators):
                    result["property_type"] = 'newbuilding'
                elif 'доля' in page_content_lower or 'share' in page_content_lower or '/share/' in listing_url.lower():
                    result["property_type"] = 'share'
                elif '/room/' in listing_url.lower() or 'продается комната' in page_content_lower or 'продаётся комната' in page_content_lower:
                    result["property_type"] = 'room'
                    LOGGER.info(f"⚠️  Detected room listing from URL/description")
                elif 'студия' in page_content_lower or 'studio' in page_content_lower:
                    result["property_type"] = 'studio'
                elif 'квартира' in page_content_lower:
                    result["property_type"] = 'flat'
                
                # Also check title and address_full for newbuilding indicators
                title = page.title()
                address_full_lower = (result.get("address_full") or "").lower()
                
                if title and not result.get("property_type"):
                    title_lower = title.lower()
                    if 'апартамент' in title_lower:
                        result["property_type"] = 'apartment'
                    elif any(indicator in title_lower for indicator in newbuilding_indicators):
                        result["property_type"] = 'newbuilding'
                    elif 'студия' in title_lower:
                        result["property_type"] = 'studio'
                    elif 'квартира' in title_lower:
                        result["property_type"] = 'flat'
                
                # Check address_full if property_type still not determined
                if address_full_lower and not result.get("property_type"):
                    if any(indicator in address_full_lower for indicator in newbuilding_indicators):
                        result["property_type"] = 'newbuilding'
            
            LOGGER.debug(f"Property type: {result.get('property_type', 'unknown')}")

        except Exception as e:
            LOGGER.warning(f"Failed to extract property type: {e}")

        # Extract apartment details (living area, kitchen area, balcony, loggia, renovation, layout)
        try:
            page_content = page.content()

            # Extract areas from ObjectFactoidsItem elements (more reliable than regex)
            try:
                factoid_items = page.query_selector_all('[data-name="ObjectFactoidsItem"]')
                for item in factoid_items:
                    text = item.inner_text().lower()
                    # Extract living area: "Жилая площадь\n40,5 м²"
                    if 'жилая' in text and 'площадь' in text:
                        match = re.search(r'(\d+(?:[.,]\d+)?)', text)
                        if match:
                            result["area_living"] = float(match.group(1).replace(",", "."))
                    # Extract kitchen area: "Площадь кухни\n11,9 м²"
                    elif 'кухни' in text or 'кухня' in text:
                        match = re.search(r'(\d+(?:[.,]\d+)?)', text)
                        if match:
                            result["area_kitchen"] = float(match.group(1).replace(",", "."))
            except Exception as e:
                LOGGER.debug(f"Could not extract areas from factoids: {e}")

            # Check for balcony
            result["balcony"] = bool(re.search(r'балкон', page_content, re.IGNORECASE))

            # Check for loggia
            result["loggia"] = bool(re.search(r'лоджия', page_content, re.IGNORECASE))

            # Extract renovation type
            renovation_types = {
                'без ремонта': 'без ремонта',
                'требуется ремонт': 'требуется ремонт',
                'косметический': 'косметический',
                'евроремонт': 'евроремонт',
                'евро': 'евроремонт',
                'дизайнерский': 'дизайнерский',
                'хороший': 'хороший',
            }
            for ru_name, value in renovation_types.items():
                if re.search(ru_name, page_content, re.IGNORECASE):
                    result["renovation"] = value
                    break

            # Extract room layout
            if re.search(r'смежн', page_content, re.IGNORECASE):
                result["rooms_layout"] = 'смежные'
            elif re.search(r'раздельн', page_content, re.IGNORECASE):
                result["rooms_layout"] = 'раздельные'
            elif re.search(r'свободная', page_content, re.IGNORECASE):
                result["rooms_layout"] = 'свободная планировка'

        except Exception as e:
            LOGGER.warning(f"Failed to extract apartment details: {e}")

        # Extract house details (year, material, series, elevator, parking)
        # AND floor/total_floors using JavaScript for better extraction
        try:
            page_content = page.content()

            # IMPROVED: Extract floor and total_floors using JavaScript
            # This is more reliable than regex on rendered page
            try:
                floor_year_data = page.evaluate('''
                    () => {
                        const text = document.body.innerText;
                        const result = {};

                        // Floor extraction - CIAN format: "Этаж\\n42 из 56" or "42 из 56 этаж"
                        // Pattern 1: "Этаж" followed by "N из M" (with possible newlines/spaces)
                        let floorMatch = text.match(/[Ээ]таж[\\s\\n]*(\\d+)\\s*из\\s*(\\d+)/);
                        if (floorMatch) {
                            result.floor = parseInt(floorMatch[1]);
                            result.total_floors = parseInt(floorMatch[2]);
                        }

                        // Pattern 2: "N из M этаж"
                        if (!result.floor) {
                            floorMatch = text.match(/(\\d+)\\s*из\\s*(\\d+)\\s*[эЭ]таж/);
                            if (floorMatch) {
                                result.floor = parseInt(floorMatch[1]);
                                result.total_floors = parseInt(floorMatch[2]);
                            }
                        }

                        // Pattern 3: "N/M этаж" (legacy format)
                        if (!result.floor) {
                            floorMatch = text.match(/(\\d+)\\s*\\/\\s*(\\d+)\\s*[эЭ]таж/);
                            if (floorMatch) {
                                result.floor = parseInt(floorMatch[1]);
                                result.total_floors = parseInt(floorMatch[2]);
                            }
                        }

                        // Year of construction - multiple patterns
                        // Pattern 1: "Год постройки 1969" or "Год постройки: 1969"
                        let yearMatch = text.match(/[Гг]од\\s*постройки[\\s:]*?(\\d{4})/);
                        if (yearMatch) {
                            const year = parseInt(yearMatch[1]);
                            if (year >= 1900 && year <= 2030) {
                                result.house_year = year;
                            }
                        }

                        // Pattern 2: "построен в 1969" or "построено в 1969"
                        if (!result.house_year) {
                            yearMatch = text.match(/[Пп]острое?н[ао]?\\s*в?\\s*(\\d{4})/);
                            if (yearMatch) {
                                const year = parseInt(yearMatch[1]);
                                if (year >= 1900 && year <= 2030) {
                                    result.house_year = year;
                                }
                            }
                        }

                        return result;
                    }
                ''')

                if floor_year_data:
                    if floor_year_data.get('floor'):
                        result["floor"] = floor_year_data['floor']
                        LOGGER.debug(f"✅ Floor from JS: {result['floor']}")
                    if floor_year_data.get('total_floors'):
                        result["total_floors"] = floor_year_data['total_floors']
                        LOGGER.debug(f"✅ Total floors from JS: {result['total_floors']}")
                    if floor_year_data.get('house_year'):
                        result["house_year"] = floor_year_data['house_year']
                        LOGGER.debug(f"✅ House year from JS: {result['house_year']}")

            except Exception as e:
                LOGGER.debug(f"JS floor/year extraction failed: {e}")

            # Fallback: Extract year of construction from HTML if not found via JS
            if not result.get("house_year"):
                year_match = re.search(r'год[а]?\s*постройки[:\s]*(\d{4})', page_content, re.IGNORECASE)
                if year_match:
                    year = int(year_match.group(1))
                    if 1900 <= year <= 2030:
                        result["house_year"] = year

            # Extract house material (already extracted as building_type, but keep for consistency)
            # building_type is already set above

            # Extract house series (e.g., П-44, КОПЭ, И-209А)
            series_match = re.search(r'серия[:\s]+([А-ЯЁ0-9\-]+)', page_content, re.IGNORECASE)
            if series_match:
                result["house_series"] = series_match.group(1).strip()

            # Check for elevator
            result["house_has_elevator"] = bool(re.search(r'лифт', page_content, re.IGNORECASE))

            # Check for parking
            result["house_has_parking"] = bool(re.search(r'парковк[аи]|паркинг', page_content, re.IGNORECASE))

            # Detect newbuilding resale: no year + high-rise building (>25 floors)
            # These are apartments in new residential complexes sold on secondary market
            if not result.get("house_year") and result.get("total_floors"):
                total_floors = result.get("total_floors")
                if total_floors and total_floors > 25:
                    result["is_newbuilding_resale"] = True
                    LOGGER.info(f"⚠️ Detected newbuilding resale: {total_floors} floors, no year")

        except Exception as e:
            LOGGER.warning(f"Failed to extract house details: {e}")

        return result

    except RateLimitError:
        # Re-raise rate limit errors to trigger proxy rotation
        raise
    except Exception as e:
        LOGGER.error(f"Failed to parse detail page {listing_url}: {e}")
        return None


def collect_with_playwright(
    payload: Dict[str, Any],
    pages: int,
    *,
    headless: bool | None = None,
    slow_mo: int | None = None,
    use_smart_proxy: bool = False,  # КРИТИЧНО: По умолчанию БЕЗ прокси! Прокси дорогой!
    start_page: int = 1,
) -> List[Dict[str, Any]]:
    """Fetch pages via Playwright HTML parsing.

    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║  ПРОКСИ ЗАПРЕЩЁН ПО УМОЛЧАНИЮ! use_smart_proxy=False                        ║
    ║  Прокси только для обновления cookies (отдельный скрипт)                    ║
    ╚══════════════════════════════════════════════════════════════════════════════╝

    Strategy (when use_smart_proxy=False - DEFAULT):
    1. Use saved cookies for authentication
    2. Direct connection to CIAN (no proxy)
    3. On rate limit - stop and ask to refresh cookies

    Legacy Strategy (when use_smart_proxy=True - NOT RECOMMENDED):
    1. Validate proxy before starting (check CIAN API accessibility)
    2. If proxy invalid, refresh proxy pool automatically
    3. First page: Authorize with proxy, save cookies
    4. Following pages: Use proxy with saved cookies (faster, no re-auth)
    5. Automatic proxy rotation on errors (auto-refresh and retry)
    6. Parse HTML instead of API requests (works when API is blocked)

    Parameters
    ----------
    payload: dict
        Base payload (jsonQuery, limit, etc.)
    pages: int
        Number of pages to fetch sequentially.
    headless: bool
        Launch browser in headless mode
    slow_mo: int
        Optional delay (ms) for troubleshooting
    use_smart_proxy: bool
        Use smart proxy strategy (validate, authorize, periodic refresh)
    """
    if headless is None:
        headless = _env_bool("CIAN_HEADLESS", True)
    if slow_mo is None:
        slow_mo = int(os.getenv("CIAN_SLOW_MO", "0") or 0)

    results: List[Dict[str, Any]] = []
    storage_path = _storage_state_path()
    storage_exists = storage_path.exists()
    search_url = _build_search_url(payload)

    # Step 1 & 2: Get validated proxy (with auto-refresh if needed)
    proxy_url: Optional[str] = None
    if use_smart_proxy:
        LOGGER.info("🔍 Step 1-2: Validating proxy and refreshing if needed...")
        proxy_url = get_validated_proxy(auto_refresh=True, max_attempts=3)

        if not proxy_url:
            LOGGER.error("❌ No valid proxy available! Cannot proceed.")
            raise RuntimeError("No valid proxy available")

        LOGGER.info("✅ Proxy validated and ready")

    with sync_playwright() as p:
        # Step 3: First run - authorize with proxy and save cookies
        if not storage_exists and use_smart_proxy:
            LOGGER.info("🆕 Step 3: First run - authorizing with proxy and saving cookies...")

            browser = _create_browser_with_proxy(p, proxy_url, headless, slow_mo)

            try:
                context_kwargs: dict[str, Any] = {
                    "user_agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                }

                context = browser.new_context(**context_kwargs)
                context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

                # CRITICAL: Block all non-cian.ru requests to save proxy traffic
                setup_route_blocking(context)

                _apply_cookies_from_env(context)

                page = context.new_page()
                page.set_default_timeout(60000)
                page.goto(search_url, wait_until="load", timeout=60000)

                # Wait for content to load
                time.sleep(2)

                # Save cookies
                storage_path.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(storage_path))
                LOGGER.info(f"💾 Initial cookies saved to {storage_path}")

                context.close()
            finally:
                browser.close()

        # Step 4: Collect data WITHOUT proxy (using saved cookies)
        # CRITICAL: Proxy is EXPENSIVE! Only use for getting cookies, then go direct!
        LOGGER.info(f"📥 Step 4: Collecting {pages} pages WITHOUT proxy (using saved cookies)...")
        LOGGER.info(f"💰 Proxy saved - all traffic goes DIRECT (cookies provide access)")

        browser = _create_browser_without_proxy(p, headless, slow_mo)

        try:
            context_kwargs: dict[str, Any] = {
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            }

            # Load saved cookies
            if storage_path.exists():
                context_kwargs["storage_state"] = str(storage_path)

            context = browser.new_context(**context_kwargs)
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

            page = context.new_page()
            page.set_default_timeout(60000)

            consecutive_failures = 0
            max_consecutive_failures = 3
            
            end_page = start_page + pages - 1
            for page_number in range(start_page, end_page + 1):
                # Build URL with page number
                if page_number == 1:
                    page_url = search_url
                else:
                    page_url = f"{search_url}&p={page_number}"

                LOGGER.info(f"📄 Fetching page {page_number}/{end_page}...")

                try:
                    # Navigate to page
                    response = page.goto(page_url, wait_until="load", timeout=60000)

                    if not response or response.status != 200:
                        consecutive_failures += 1
                        LOGGER.error(f"❌ Page {page_number}: Bad response {response.status if response else 'None'}")

                        # If too many failures, maybe cookies expired - try refreshing them
                        if consecutive_failures >= max_consecutive_failures:
                            LOGGER.warning(f"⚠️  {consecutive_failures} consecutive failures - cookies may have expired")
                            LOGGER.info("💡 Try running: python config/get_cookies_with_proxy.py")
                            break

                        continue

                    # Reset failure counter on success
                    consecutive_failures = 0

                    # Wait for offers to load
                    time.sleep(2)

                    # Parse offers from HTML
                    offers = _parse_offers_from_html(page)

                    if offers:
                        # Wrap in API-like response format for compatibility with mapper
                        result = {
                            "data": {
                                "offersSerialized": offers
                            },
                            "page": page_number,
                            "source": "html_parsing"
                        }
                        results.append(result)
                        LOGGER.info(f"✅ Page {page_number}/{end_page}: {len(offers)} offers extracted")
                    else:
                        LOGGER.warning(f"⚠️  Page {page_number}/{end_page}: No offers found")

                    # Save updated cookies
                    context.storage_state(path=str(storage_path))

                    # Small delay between pages
                    time.sleep(0.6)

                except Exception as e:
                    consecutive_failures += 1
                    LOGGER.error(f"❌ Error on page {page_number}: {e}")

                    # If too many failures, cookies may have expired
                    if consecutive_failures >= max_consecutive_failures:
                        LOGGER.warning(f"⚠️  {consecutive_failures} consecutive failures - cookies may have expired")
                        LOGGER.info("💡 Try running: python config/get_cookies_with_proxy.py")
                        break

                    continue

            context.close()
        finally:
            browser.close()

    LOGGER.info(f"🎉 Successfully collected {len(results)} pages with {sum(len(r.get('data', {}).get('offersSerialized', [])) for r in results)} total offers")
    return results
