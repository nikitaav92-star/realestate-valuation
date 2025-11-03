"""Playwright-based HTML parser for CIAN with smart proxy strategy."""
from __future__ import annotations

import logging
import os
import time
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import BrowserContext, Browser, Playwright, Page, sync_playwright
from urllib.parse import urlencode

from .proxy_manager import get_validated_proxy, ProxyConfig

LOGGER = logging.getLogger(__name__)
CIAN_DOMAIN = ".cian.ru"
DEFAULT_STORAGE_PATH = "config/cian_browser_state.json"


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
    """Create browser with proxy."""
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-gpu",
    ]

    proxy_config = ProxyConfig.from_url(proxy_url)
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
    return p.chromium.launch(**browser_kwargs)


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

            # Get address from multiple GeoLabel elements
            geo_labels = element.query_selector_all("[data-name='GeoLabel']")
            if geo_labels:
                # Combine all geo labels into address (e.g., "Москва, ЮАО, р-н Даниловский")
                address_parts = [label.inner_text().strip() for label in geo_labels if label.inner_text().strip()]
                if address_parts:
                    offer["address"] = ", ".join(address_parts[:4])  # Limit to first 4 parts

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


def parse_listing_detail(page: Page, listing_url: str) -> Optional[Dict[str, Any]]:
    """Parse detailed information from individual listing page.

    Extracts:
    - Full description text
    - All photos from gallery (URLs, order, dimensions)
    - Publication date
    - Building type
    - Property type

    Parameters
    ----------
    page: Page
        Playwright page object
    listing_url: str
        Full URL to listing detail page

    Returns
    -------
    dict or None
        Dictionary with keys: description, published_at, building_type, property_type, photos
        Returns None if page fails to load or parsing fails
    """
    import re
    from datetime import datetime

    try:
        LOGGER.info(f"Parsing detail page: {listing_url}")

        # Navigate to listing page
        # Use domcontentloaded instead of networkidle to save proxy traffic (~70-80% less)
        # networkidle waits for ALL resources (images, CSS, JS, fonts) - very heavy on proxy
        # domcontentloaded waits only for HTML + DOM - much faster and lighter
        response = page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)

        if not response or response.status >= 400:
            LOGGER.warning(f"Failed to load {listing_url}: HTTP {response.status if response else 'None'}")
            return None

        # Wait for content to load and render
        # Give DOM time to render after domcontentloaded
        page.wait_for_timeout(2000)  # 2 sec for dynamic content

        # Then wait for description element (or timeout silently if not present)
        try:
            page.wait_for_selector("[data-name='Description']", timeout=5000)
        except:
            pass  # Description might not exist on all pages

        result = {
            "description": None,
            "published_at": None,
            "building_type": None,
            "property_type": None,
            "photos": []
        }

        # Extract description
        try:
            desc_elem = page.query_selector("[data-name='Description']")
            if desc_elem:
                result["description"] = desc_elem.inner_text().strip()
                LOGGER.debug(f"Description: {len(result['description'])} chars")
        except Exception as e:
            LOGGER.warning(f"Failed to extract description: {e}")

        # Extract photos from gallery
        try:
            # CIAN stores photos at: https://images.cdn-cian.ru/images/XXXXXX-1.jpg
            # Find all img tags and filter by URL pattern
            all_images = page.query_selector_all("img")
            photo_urls = []

            for img in all_images:
                src = img.get_attribute("src") or img.get_attribute("data-src") or ""

                # Filter: only CIAN photo images from images.cdn-cian.ru
                if "images.cdn-cian.ru/images/" in src and src.endswith((".jpg", ".jpeg", ".png")):
                    # Extract dimensions if available
                    width = img.get_attribute("width")
                    height = img.get_attribute("height")
                    photo_urls.append({
                        "url": src,
                        "width": int(width) if width and width.isdigit() else None,
                        "height": int(height) if height and height.isdigit() else None
                    })

            # Deduplicate photos by URL
            seen_urls = set()
            unique_photos = []
            for idx, photo in enumerate(photo_urls):
                if photo["url"] not in seen_urls:
                    seen_urls.add(photo["url"])
                    unique_photos.append({
                        "url": photo["url"],
                        "order": idx,
                        "width": photo["width"],
                        "height": photo["height"]
                    })

            result["photos"] = unique_photos
            LOGGER.debug(f"Photos: {len(unique_photos)} images")

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

        # Extract property type (usually from title or metadata)
        try:
            title = page.title()
            if title:
                title_lower = title.lower()
                if 'квартира' in title_lower:
                    result["property_type"] = 'flat'
                elif 'апартамент' in title_lower:
                    result["property_type"] = 'apartment'
                elif 'студия' in title_lower:
                    result["property_type"] = 'studio'
                LOGGER.debug(f"Property type: {result.get('property_type', 'unknown')}")

        except Exception as e:
            LOGGER.warning(f"Failed to extract property type: {e}")

        return result

    except Exception as e:
        LOGGER.error(f"Failed to parse detail page {listing_url}: {e}")
        return None


def collect_with_playwright(
    payload: Dict[str, Any],
    pages: int,
    *,
    headless: bool | None = None,
    slow_mo: int | None = None,
    use_smart_proxy: bool = True,
) -> List[Dict[str, Any]]:
    """Fetch pages via Playwright HTML parsing with smart proxy strategy.

    Smart Strategy:
    1. Validate proxy before starting (check CIAN API accessibility)
    2. If proxy invalid, refresh proxy pool automatically
    3. First page: Authorize with proxy, save cookies
    4. Following pages: Use proxy with saved cookies (faster, no re-auth)
    5. Parse HTML instead of API requests (works when API is blocked)

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
        proxy_url = get_validated_proxy(auto_refresh=True)

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

        # Step 4: Collect data WITH proxy (using saved cookies to avoid captcha)
        LOGGER.info(f"📥 Step 4: Collecting {pages} pages WITH proxy (HTML parsing)...")

        browser = _create_browser_with_proxy(p, proxy_url, headless, slow_mo) if use_smart_proxy else _create_browser_without_proxy(p, headless, slow_mo)

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

            for page_number in range(1, pages + 1):
                # Build URL with page number
                if page_number == 1:
                    page_url = search_url
                else:
                    page_url = f"{search_url}&p={page_number}"

                LOGGER.info(f"📄 Fetching page {page_number}/{pages}...")

                try:
                    # Navigate to page
                    response = page.goto(page_url, wait_until="load", timeout=60000)

                    if not response or response.status != 200:
                        LOGGER.error(f"❌ Page {page_number}: Bad response {response.status if response else 'None'}")
                        continue

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
                        LOGGER.info(f"✅ Page {page_number}/{pages}: {len(offers)} offers extracted")
                    else:
                        LOGGER.warning(f"⚠️  Page {page_number}/{pages}: No offers found")

                    # Save updated cookies
                    context.storage_state(path=str(storage_path))

                    # Small delay between pages
                    time.sleep(0.6)

                except Exception as e:
                    LOGGER.error(f"❌ Error on page {page_number}: {e}")
                    continue

            context.close()
        finally:
            browser.close()

    LOGGER.info(f"🎉 Successfully collected {len(results)} pages with {sum(len(r.get('data', {}).get('offersSerialized', [])) for r in results)} total offers")
    return results
