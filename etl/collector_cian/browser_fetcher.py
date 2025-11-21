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

            # Get address from multiple selectors (fallback chain)
            # TASK-002: Improved address extraction with multiple selectors
            address_parts = []
            
            # Try primary selector: GeoLabel
            geo_labels = element.query_selector_all("[data-name='GeoLabel']")
            if geo_labels:
                address_parts = [label.inner_text().strip() for label in geo_labels if label.inner_text().strip()]
            
            # Fallback 1: SpecialGeo
            if not address_parts:
                special_geo = element.query_selector("[data-name='SpecialGeo']")
                if special_geo:
                    address_parts = [special_geo.inner_text().strip()]
            
            # Fallback 2: Any element with geo-related classes
            if not address_parts:
                geo_fallback = element.query_selector(".geo-label, .address-label, [class*='geo']")
                if geo_fallback:
                    address_parts = [geo_fallback.inner_text().strip()]
            
            # Validate address: must contain "Москва" or metro station name
            if address_parts:
                address_text = ", ".join(address_parts[:4])  # Limit to first 4 parts
                # Validate address contains location indicator
                if "Москва" in address_text or any(
                    metro in address_text for metro in 
                    ["метро", "ст.", "станция", "м.", "мкр", "район", "р-н"]
                ):
                    offer["address"] = address_text
                else:
                    # Log warning for missing/invalid address
                    LOGGER.warning(f"Offer {offer.get('offerId', 'unknown')}: Invalid address format: {address_text}")

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
            "address_full": None,
            "description": None,
            "published_at": None,
            "building_type": None,
            "property_type": None,
            "photos": [],
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
        }

        # Extract full address - comprehensive scan of entire page
        # Strategy: Scan entire page DOM for address patterns using multiple methods
        try:
            import re
            import json
            
            LOGGER.debug(f"🔍 Starting comprehensive address extraction for {listing_url}")
            
            # Method 1: Try JSON-LD structured data (most reliable, priority)
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
                            result["address_full"] = address_from_json.strip()
                            LOGGER.info(f"✅ Full address from JSON-LD: {address_from_json[:100]}")
                            return result
                    except (json.JSONDecodeError, Exception) as e:
                        LOGGER.debug(f"JSON-LD parsing failed: {e}")
                        continue
            except Exception as e:
                LOGGER.debug(f"JSON-LD extraction failed: {e}")
            
            # Method 2: Comprehensive DOM scan - find all elements containing address parts
            if not result["address_full"]:
                try:
                    LOGGER.debug("Scanning DOM for address elements...")
                    
                    # Get all text elements and links on the page
                    all_elements = page.query_selector_all("a, span, div, p, li")
                    address_candidates = []
                    
                    for elem in all_elements:
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
                            if not has_moscow:
                                continue
                            
                            # Score element based on address indicators
                            score = 0
                            if has_moscow:
                                score += 5  # Москва is mandatory
                            if has_street:
                                score += 3  # Street is very important
                            if has_district:
                                score += 2  # District is important
                            if has_number and re.search(r'\d{1,3}', elem_text):  # House number (1-3 digits)
                                score += 2
                            
                            # Must have at least Москва + street or district
                            if score >= 7 and len(elem_text) > 20:
                                # Additional validation: should contain comma-separated parts
                                if ',' in elem_text or 'ул.' in elem_text or 'улица' in elem_text:
                                    address_candidates.append((score, elem_text, elem))
                        except Exception:
                            continue
                    
                    # Sort candidates by score (highest first)
                    address_candidates.sort(key=lambda x: x[0], reverse=True)
                    LOGGER.debug(f"Found {len(address_candidates)} address candidates")
                    
                    # Try to find complete address from candidates
                    for score, candidate_text, elem in address_candidates[:10]:  # Check top 10
                        # Strict validation: must be a real address
                        candidate_clean = candidate_text.strip()
                        
                        # Must have Москва
                        if "Москва" not in candidate_clean:
                            continue
                        
                        # Must have street indicator
                        if not re.search(r'(ул\.|улица|проспект|пр\.|переулок|пер\.)', candidate_clean, re.I):
                            continue
                        
                        # Must have house number (not just any number)
                        if not re.search(r'(дом|д\.|,)\s*\d{1,3}', candidate_clean, re.I):
                            # Try alternative: number after street name
                            if not re.search(r'ул\.?\s+[^,]+,\s*\d+', candidate_clean, re.I):
                                continue
                        
                        # Exclude common non-address words
                        exclude_words = [
                            r'мебель', r'цена', r'₽', r'рубл', r'только', r'циан',
                            r'фотографи', r'описани', r'расположени', r'похожие',
                            r'хорош', r'плох', r'новый', r'старый'
                        ]
                        if any(re.search(word, candidate_clean, re.I) for word in exclude_words):
                            LOGGER.debug(f"Skipping candidate (contains excluded word): {candidate_clean[:50]}")
                            continue
                        
                        # Clean up: remove common prefixes that are not part of address
                        # Remove things like "Продается X-комн. квартира..." before "Москва"
                        if "Москва" in candidate_clean:
                            moscow_index = candidate_clean.find("Москва")
                            if moscow_index > 0:
                                # Check if there's address-like content before Москва
                                before_moscow = candidate_clean[:moscow_index].strip()
                                # If before Москва contains "Продается", "квартира", etc., remove it
                                if re.search(r'(Продается|квартира|м²|ЖК|в\s+ЖК|комн\.|комнат)', before_moscow, re.I):
                                    candidate_clean = candidate_clean[moscow_index:].strip()
                        
                        # Additional cleanup: remove common prefixes at the start
                        # Patterns to remove from the beginning
                        prefix_patterns = [
                            r'^Продается\s+[\d\-комн\.\s]+квартира[^,]*,\s*',
                            r'^[\d\-комн\.\s]+квартира[^,]*,\s*',
                            r'^в\s+ЖК[^,]*,\s*',
                            r'^ЖК[^,]*,\s*',
                            r'^[\d,\.]+\s*м²[^,]*,\s*',
                        ]
                        for pattern in prefix_patterns:
                            candidate_clean = re.sub(pattern, '', candidate_clean, flags=re.I).strip()
                        
                        # Remove text after house number (like "На карте", metro stations, etc.)
                        # Pattern: number followed by "На карте" or metro station names
                        candidate_clean = re.sub(r'(\d+[кК]?\d*)\s*На\s+карте.*$', r'\1', candidate_clean, flags=re.I)
                        candidate_clean = re.sub(r'(\d+[кК]?\d*)\s*\d+\s*мин\..*$', r'\1', candidate_clean, flags=re.I)
                        
                        # Remove newlines and extra whitespace
                        candidate_clean = re.sub(r'\s+', ' ', candidate_clean).strip()
                        
                        # If address starts with something that's not Москва or district, try to find Москва
                        if not candidate_clean.startswith(('Москва', 'СВАО', 'САО', 'СЗАО', 'ЮАО', 'ЮВАО', 'ВАО', 'ЗАО', 'ЦАО')):
                            moscow_match = re.search(r'Москва', candidate_clean)
                            if moscow_match:
                                # Extract from Москва onwards
                                candidate_clean = candidate_clean[moscow_match.start():].strip()
                        
                        # Must be long enough and contain commas (addresses usually have multiple parts)
                        if len(candidate_clean) > 25 and (',' in candidate_clean or len(candidate_clean.split()) > 3):
                            result["address_full"] = candidate_clean
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
                                    container_text = page.evaluate("""
                                        (el) => {
                                            if (!el) return '';
                                            const links = el.querySelectorAll('a');
                                            const parts = [];
                                            links.forEach(link => {
                                                const text = link.innerText.trim();
                                                if (text && (text.includes('Москва') || text.match(/[ул\\.]|улица|дом|д\\./i) || /\\d+/.test(text))) {
                                                    parts.push(text);
                                                }
                                            });
                                            return parts.join(', ');
                                        }
                                    """, parent)
                                    
                                    if container_text and len(container_text) > 15 and "Москва" in container_text:
                                        if re.search(r'(ул\.|улица)', container_text, re.I) and re.search(r'\d+', container_text):
                                            # Clean up the combined address
                                            address_clean = container_text.strip()
                                            # Remove prefixes
                                            moscow_index = address_clean.find("Москва")
                                            if moscow_index > 0:
                                                address_clean = address_clean[moscow_index:].strip()
                                            # Remove common prefixes
                                            address_clean = re.sub(r'^Продается\s+[\d\-комн\.\s]+квартира[^,]*,\s*', '', address_clean, flags=re.I).strip()
                                            address_clean = re.sub(r'\s+', ' ', address_clean).strip()
                                            result["address_full"] = address_clean
                                            LOGGER.info(f"✅ Full address from combined elements: {address_clean[:100]}")
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
                        matches = re.findall(pattern, page_text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                        if matches:
                            LOGGER.debug(f"Pattern {pattern} found {len(matches)} matches")
                            for match in matches:
                                match_clean = " ".join(match.split())
                                if len(match_clean) > 20 and "Москва" in match_clean:
                                    # Validate: should have street indicator and house number
                                    if re.search(r'(ул\.|улица)', match_clean, re.I) and re.search(r'\d+', match_clean):
                                        result["address_full"] = match_clean.strip()
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
                        matches = re.findall(pattern, page_html, re.IGNORECASE)
                        if matches:
                            for match in matches:
                                match_clean = " ".join(match.split())
                                if len(match_clean) > 15 and "Москва" in match_clean:
                                    if re.search(r'(ул\.|улица)', match_clean, re.I) and re.search(r'\d+', match_clean):
                                        result["address_full"] = match_clean.strip()
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
            LOGGER.info(f"✅ Full address saved: {result['address_full'][:100]}")
        else:
            LOGGER.warning(f"⚠️ Full address NOT extracted for {listing_url} - all methods failed")
            # Log page structure for debugging
            try:
                h1_exists = bool(page.query_selector("h1"))
                links_count = len(page.query_selector_all("a"))
                LOGGER.debug(f"Page structure: H1={h1_exists}, Links={links_count}")
            except Exception:
                pass

        # Extract description (full text, not truncated)
        try:
            # Try multiple selectors for description
            desc_selectors = [
                "[data-name='Description']",
                ".object-description",
                "[data-name='ObjectDescription']",
                ".offer-description",
                ".description",
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
                            LOGGER.debug(f"Description extracted via {selector}: {len(desc_text)} chars")
                            break
                except Exception:
                    continue
            
            # If still no description, try to get from textarea or content divs
            if not result["description"]:
                try:
                    # Some pages have description in textarea or content divs
                    content_elem = page.query_selector("textarea[name='description'], .content-text, .offer-text")
                    if content_elem:
                        desc_text = content_elem.inner_text().strip()
                        desc_text = "\n".join([p.strip() for p in desc_text.split("\n") if p.strip()])
                        if desc_text and len(desc_text) > 20:
                            result["description"] = desc_text
                            LOGGER.debug(f"Description from content: {len(desc_text)} chars")
                except Exception:
                    pass
                    
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

        # Extract property type - check for apartments, newbuildings, shares
        try:
            page_content = page.content()
            page_content_lower = page_content.lower()
            
            # Check for "Тип жилья" section which shows: Вторичка / Апартаменты or Новостройка
            # Look for property type indicators
            if 'апартамент' in page_content_lower or 'apartment' in page_content_lower:
                result["property_type"] = 'apartment'
            elif 'новостройка' in page_content_lower or 'newbuilding' in page_content_lower or '/newbuilding/' in listing_url.lower():
                result["property_type"] = 'newbuilding'
            elif 'доля' in page_content_lower or 'share' in page_content_lower or '/share/' in listing_url.lower():
                result["property_type"] = 'share'
            elif 'студия' in page_content_lower or 'studio' in page_content_lower:
                result["property_type"] = 'studio'
            elif 'квартира' in page_content_lower:
                result["property_type"] = 'flat'
            
            # Also check title
            title = page.title()
            if title and not result["property_type"]:
                title_lower = title.lower()
                if 'апартамент' in title_lower:
                    result["property_type"] = 'apartment'
                elif 'новостройка' in title_lower:
                    result["property_type"] = 'newbuilding'
                elif 'студия' in title_lower:
                    result["property_type"] = 'studio'
                elif 'квартира' in title_lower:
                    result["property_type"] = 'flat'
            
                LOGGER.debug(f"Property type: {result.get('property_type', 'unknown')}")

        except Exception as e:
            LOGGER.warning(f"Failed to extract property type: {e}")

        # Extract apartment details (living area, kitchen area, balcony, loggia, renovation, layout)
        try:
            page_content = page.content()
            
            # Extract living area (жилая площадь)
            living_area_match = re.search(r'жилая[:\s]+(\d+(?:[.,]\d+)?)\s*м²', page_content, re.IGNORECASE)
            if living_area_match:
                result["area_living"] = float(living_area_match.group(1).replace(",", "."))
            
            # Extract kitchen area (площадь кухни)
            kitchen_area_match = re.search(r'кухн[аи][:\s]+(\d+(?:[.,]\d+)?)\s*м²', page_content, re.IGNORECASE)
            if kitchen_area_match:
                result["area_kitchen"] = float(kitchen_area_match.group(1).replace(",", "."))
            
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
        try:
            page_content = page.content()
            
            # Extract year of construction
            year_match = re.search(r'год[:\s]+(\d{4})', page_content, re.IGNORECASE)
            if year_match:
                year = int(year_match.group(1))
                if 1900 <= year <= 2030:  # Validate year
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
            
        except Exception as e:
            LOGGER.warning(f"Failed to extract house details: {e}")

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
