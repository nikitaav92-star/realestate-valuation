"""CLI entry point for Cursor-friendly data collection tasks.

╔══════════════════════════════════════════════════════════════════════════════╗
║  КРИТИЧЕСКОЕ ПРАВИЛО: ПРОКСИ ЗАПРЕЩЁН ДЛЯ ПАРСИНГА!                         ║
║  ═══════════════════════════════════════════════════                         ║
║                                                                              ║
║  Прокси ОЧЕНЬ ДОРОГОЙ! Трафик через прокси стоит огромных денег!            ║
║                                                                              ║
║  РАЗРЕШЕНО использовать прокси ТОЛЬКО для:                                  ║
║    - Обновления cookies (отдельный скрипт: config/get_cookies_with_proxy.py)║
║                                                                              ║
║  ЗАПРЕЩЕНО использовать прокси для:                                         ║
║    - Парсинга страниц листингов                                             ║
║    - Сбора списков объявлений                                               ║
║    - Любого другого трафика к cian.ru                                       ║
║                                                                              ║
║  При rate limit (HTTP 429):                                                 ║
║    1. Увеличить задержку (exponential backoff)                              ║
║    2. После 3 rate limits - ОСТАНОВИТЬСЯ                                    ║
║    3. Сообщить пользователю обновить cookies                                ║
║    4. НИКОГДА НЕ ПЕРЕКЛЮЧАТЬСЯ НА ПРОКСИ!                                   ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional

import orjson
import yaml
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from etl.collector_cian.fetcher import CianBlockedError, CianFetchError, collect, load_payload
from etl.collector_cian.browser_fetcher import collect_with_playwright, parse_listing_detail, RateLimitError, setup_route_blocking
# ПРОКСИ ИМПОРТ УДАЛЁН! Прокси только для cookies (отдельный скрипт)
from etl.collector_cian.mapper import extract_offers, to_listing, to_price
from etl.upsert import (
    get_db_connection,
    upsert_listing,
    upsert_price_if_changed,
    update_listing_details,
    insert_listing_photos,
)
from etl.encumbrance_analyzer import analyze_description, get_analyzer

LOGGER = logging.getLogger(__name__)
DEFAULT_LOCK_PATH = Path("/tmp/cian_parser.lock")
DEFAULT_AUTONOMOUS_LOG = Path("logs/autonomous_collector.log")
AUTONOMOUS_LOG_ATTR = "_autonomous_log_handler"

ROOT_DIR = Path(__file__).resolve().parents[2]

load_dotenv(ROOT_DIR / ".env")


def _env_flag(name: str) -> bool:
    value = os.getenv(name)
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


def _detail_timeout_seconds(default: int = 30) -> Optional[int]:
    raw_value = os.getenv("CIAN_DETAIL_TIMEOUT")
    if raw_value is None:
        return default if default > 0 else None
    try:
        seconds = int(raw_value)
    except ValueError:
        seconds = default
    return seconds if seconds > 0 else None


@contextmanager
def _parser_run_lock(force: bool = False):
    """Prevent multiple parser instances from running simultaneously."""
    lock_env = os.getenv("CIAN_PARSER_LOCK")
    lock_path = Path(lock_env).expanduser() if lock_env else DEFAULT_LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if force:
        LOGGER.warning("⚠️ Force run enabled: skipping parser lock at %s", lock_path)
        yield
        return

    lock_file = lock_path.open("a+")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.seek(0)
        owner = lock_file.read().strip()
        raise RuntimeError(
            f"Parser already running (lock: {lock_path}). Owner: {owner or 'unknown'}"
        )

    try:
        metadata = f"pid={os.getpid()} started={time.strftime('%Y-%m-%d %H:%M:%S')}"
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(metadata)
        lock_file.flush()
        LOGGER.info("🔒 Parser lock acquired: %s (%s)", lock_path, metadata)
        yield
    finally:
        try:
            lock_file.seek(0)
            lock_file.truncate()
        except OSError:
            pass
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        lock_file.close()
        try:
            lock_path.unlink()
        except OSError:
            pass
        LOGGER.info("🔓 Parser lock released")


def _setup_file_logger(log_path: Path) -> None:
    """Attach rotating file handler for autonomous collector logs."""
    root_logger = logging.getLogger()
    if any(getattr(handler, AUTONOMOUS_LOG_ATTR, False) for handler in root_logger.handlers):
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=5_000_000,
        backupCount=5,
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    setattr(handler, AUTONOMOUS_LOG_ATTR, True)
    root_logger.addHandler(handler)


def _collect_responses(payload: dict, pages: int, start_page: int = 1):
    """Fetch HTML/JSON responses using API or Playwright fallback."""
    try:
        return asyncio.run(collect(payload, pages))
    except Exception as exc:  # pragma: no cover - network dependent
        root_exc = getattr(exc, "__cause__", None) or exc
        # Check if it's a CIAN API error (blocked or server error) - fallback to Playwright
        if isinstance(root_exc, (CianBlockedError, CianFetchError)):
            LOGGER.warning(
                "HTTP access blocked or failed (%s), falling back to Playwright WITHOUT proxy (using saved cookies)", root_exc
            )
            return collect_with_playwright(payload, pages, use_smart_proxy=False, start_page=start_page)

        # Also check exception message for common error patterns
        exc_str = str(exc).lower()
        if any(pattern in exc_str for pattern in ["503", "504", "500", "502", "blocked", "forbidden", "timeout"]):
            LOGGER.warning(
                "HTTP error detected (%s), falling back to Playwright WITHOUT proxy (using saved cookies)", exc
            )
            return collect_with_playwright(payload, pages, use_smart_proxy=False, start_page=start_page)

        raise


def _collect_and_process(payload: dict, pages: int, parse_details: bool, start_page: int = 1) -> tuple[int, int, int, int]:
    """Collect data for N pages and persist to DB."""
    responses = _collect_responses(payload, pages, start_page=start_page)
    offers = (offer for resp in responses for offer in extract_offers(resp))
    return _process_offers(offers, parse_details=parse_details)


def _log_data_quality_metrics() -> None:
    """Print overall data completeness stats."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE rooms IS NOT NULL) * 100.0 / NULLIF(COUNT(*), 0) as pct_rooms,
                        COUNT(*) FILTER (WHERE area_total IS NOT NULL) * 100.0 / NULLIF(COUNT(*), 0) as pct_area,
                        COUNT(*) FILTER (WHERE address IS NOT NULL AND address != '') * 100.0 / NULLIF(COUNT(*), 0) as pct_address
                    FROM listings
                    WHERE is_active = TRUE
                    """
                )
                row = cur.fetchone()
                if row:
                    total, pct_rooms, pct_area, pct_address = row
                    LOGGER.info(
                        "📈 Data Quality: total=%s, rooms=%.1f%%, area=%.1f%%, address=%.1f%%",
                        total,
                        pct_rooms or 0,
                        pct_area or 0,
                        pct_address or 0,
                    )
    except Exception as e:  # pragma: no cover - diagnostics only
        LOGGER.warning("Failed to log data quality metrics: %s", e)


def _load_payload(path: str) -> dict:
    return load_payload(path)


def command_pull(payload_path: str, pages: int) -> None:
    """Fetch offers and emit raw JSON lines to stdout."""
    payload = _load_payload(payload_path)
    responses = _collect_responses(payload, pages)
    count = 0
    for response in responses:
        for offer in extract_offers(response):
            sys.stdout.write(orjson.dumps(offer).decode() + "\n")
            count += 1
    LOGGER.info("pulled_offers=%s", count)


def _process_offers(offers: Iterable[dict], parse_details: bool = False) -> tuple[int, int, int, int]:
    """Process offers: upsert listings and prices, optionally parse details.
    
    Returns:
        Tuple of (listings_count, prices_count, details_count, photos_count)
    """
    conn = get_db_connection()
    listings = prices = details_parsed = photos_inserted = 0
    
    # Collect listing URLs for detail parsing
    listing_urls = []
    
    newbuildings_skipped = 0
    shares_skipped = 0
    apartments_skipped = 0
    
    try:
        for offer in offers:
            try:
                listing = to_listing(offer)
            except ValueError as e:
                # Skip newbuildings, apartment shares, and apartments
                error_msg = str(e)
                if "Newbuilding" in error_msg:
                    newbuildings_skipped += 1
                    continue
                elif "Apartment share" in error_msg or "share" in error_msg.lower():
                    shares_skipped += 1
                    continue
                elif "Apartment detected" in error_msg or "apartment" in error_msg.lower():
                    apartments_skipped += 1
                    continue
                raise
            
            price = to_price(offer)
            upsert_listing(conn, listing)
            if upsert_price_if_changed(conn, listing.id, price.price):
                prices += 1
            listings += 1
            
            # Store URL for detail parsing
            if parse_details and listing.url:
                listing_urls.append((listing.id, listing.url))
        
        conn.commit()
        skip_info = []
        if newbuildings_skipped > 0:
            skip_info.append(f"{newbuildings_skipped} newbuildings")
        if shares_skipped > 0:
            skip_info.append(f"{shares_skipped} shares")
        if apartments_skipped > 0:
            skip_info.append(f"{apartments_skipped} apartments")
        
        if skip_info:
                LOGGER.info("✅ Upserted %d listings, %d new prices, skipped: %s", 
                    listings, prices, ", ".join(skip_info))
        else:
            LOGGER.info("✅ Upserted %d listings, %d new prices", listings, prices)
        
        # Parse details if requested
        if parse_details and listing_urls:
            LOGGER.info("🔍 Starting detailed parsing for %d listings...", len(listing_urls))
            try:
                details_parsed, photos_inserted = _parse_listing_details(conn, listing_urls)
                # Final commit after all details are parsed
                conn.commit()
                LOGGER.info("✅ All details parsed and committed to database")
            except Exception as e:
                # Commit any partial progress before re-raising
                try:
                    conn.commit()
                    LOGGER.info("✅ Committed partial progress before error")
                except:
                    conn.rollback()
                    LOGGER.warning("⚠️ Rolled back transaction due to commit error")
                # Log error but don't fail completely - partial data is better than no data
                LOGGER.error(f"❌ Error during detailed parsing: {e}")
                # Set defaults if parsing failed
                details_parsed = 0
                photos_inserted = 0
            
    except Exception as e:
        conn.rollback()
        LOGGER.error("❌ Error processing offers: %s", e)
        raise
    finally:
        conn.close()
    
    return listings, prices, details_parsed, photos_inserted


def _parse_listing_details(conn, listing_urls: list[tuple[int, str]]) -> tuple[int, int]:
    """Parse detailed information for each listing URL.

    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║  ПРОКСИ ЗАПРЕЩЁН! Используем только cookies + exponential backoff           ║
    ╚══════════════════════════════════════════════════════════════════════════════╝

    Strategy:
    1. Use saved cookies for authentication
    2. On HTTP 429 (rate limit) - exponential backoff (10s, 20s, 40s)
    3. After 3 rate limits - STOP and tell user to refresh cookies
    4. NEVER use proxy for parsing! Proxy only for cookie refresh (separate script)

    Args:
        conn: Database connection
        listing_urls: List of (listing_id, url) tuples

    Returns:
        Tuple of (details_parsed_count, photos_inserted_count)
    """
    details_count = 0
    photos_count = 0
    detail_timeout = _detail_timeout_seconds()

    # Load saved cookies path
    storage_path = Path(os.getenv("CIAN_STORAGE_STATE", "config/cian_browser_state.json"))

    LOGGER.info(f"🔓 Starting detail parsing (NO PROXY - cookies + backoff only)")

    if storage_path.exists():
        LOGGER.info(f"📂 Loading cookies from {storage_path}")
    else:
        LOGGER.warning(f"⚠️  No saved cookies at {storage_path}")
        LOGGER.info("💡 Run: python config/get_cookies_with_proxy.py to get cookies first")

    consecutive_failures = 0
    max_consecutive_failures = 5  # Stop after 5 consecutive failures

    # Rate limit tracking - NO PROXY, only backoff!
    rate_limit_count = 0
    max_rate_limits = 3  # Stop after 3 rate limits - cookies likely expired
    base_delay = 10  # Base delay for exponential backoff

    browser = None
    page = None

    try:
        with sync_playwright() as p:
            # Start WITHOUT proxy (using saved cookies)
            browser = p.chromium.launch(headless=True)

            # Create context with saved cookies
            context_kwargs = {
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            }
            if storage_path.exists():
                context_kwargs["storage_state"] = str(storage_path)

            context = browser.new_context(**context_kwargs)
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            page = context.new_page()
            
            for idx, (listing_id, url) in enumerate(listing_urls, 1):
                try:
                    LOGGER.info(f"[{idx}/{len(listing_urls)}] Parsing details: {url}")
                    
                    # Parse detail page with RateLimitError and EPIPE handling
                    details = None
                    try:
                        details = parse_listing_detail(page, url, max_duration=detail_timeout)
                    except RateLimitError as rate_limit_exc:
                        # HTTP 429 - Rate limited! NO PROXY - use exponential backoff
                        rate_limit_count += 1
                        LOGGER.warning(f"  🚫 Rate limited (HTTP 429)! Count: {rate_limit_count}/{max_rate_limits}")

                        # Check if we've hit too many rate limits - cookies likely expired
                        if rate_limit_count >= max_rate_limits:
                            LOGGER.error("❌ Too many rate limits - cookies likely expired!")
                            LOGGER.error("💡 Run: python config/get_cookies_with_proxy.py --force")
                            break

                        # Exponential backoff (NO PROXY!)
                        wait_time = base_delay * (2 ** rate_limit_count)
                        LOGGER.info(f"  ⏳ Waiting {wait_time} seconds before retry (exponential backoff)...")
                        time.sleep(wait_time)

                        # Retry once after backoff (still NO PROXY!)
                        try:
                            details = parse_listing_detail(page, url, max_duration=detail_timeout)
                        except RateLimitError:
                            LOGGER.warning(f"  🚫 Still rate limited after backoff, skipping this listing")
                            continue
                    except TimeoutError as timeout_exc:
                        consecutive_failures += 1
                        LOGGER.warning(f"  ⏱️ Detail parsing timeout for listing {listing_id}: {timeout_exc}")
                        continue
                    except Exception as parse_error:
                        error_str = str(parse_error)
                        # Handle EPIPE error (Playwright pipe closed) - this is non-fatal
                        is_epipe_error = any(keyword in error_str for keyword in [
                            "EPIPE",
                            "write EPIPE",
                            "Broken pipe",
                            "Connection reset by peer",
                            "errno: -32"
                        ])
                        
                        if is_epipe_error:
                            LOGGER.warning(f"  ⚠️ EPIPE error (browser connection lost): {error_str[:100]}")
                            LOGGER.info("  🔄 Recreating browser connection (without proxy)...")
                            try:
                                if browser:
                                    browser.close()
                            except Exception:
                                pass

                            # Recreate browser WITHOUT proxy (using saved cookies)
                            try:
                                browser = p.chromium.launch(headless=True)
                                new_context = browser.new_context(**context_kwargs)
                                new_context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
                                page = new_context.new_page()
                                consecutive_failures = 0
                                LOGGER.info("  ✅ Browser recreated (no proxy), retrying...")
                                # Retry parsing
                                details = parse_listing_detail(page, url, max_duration=detail_timeout)
                            except TimeoutError as timeout_exc:
                                consecutive_failures += 1
                                LOGGER.warning(f"  ⏱️ Detail parsing timeout after reconnect for listing {listing_id}: {timeout_exc}")
                                continue
                            except Exception as recreate_error:
                                LOGGER.error(f"  ❌ Failed to recreate browser: {recreate_error}")
                                try:
                                    conn.commit()
                                except Exception:
                                    pass
                                continue
                        else:
                            raise  # Re-raise non-EPIPE errors
                    
                    if details:
                        # Reset failure counter on success
                        consecutive_failures = 0
                        
                        try:
                            # Skip newbuildings and shares detected during detail parsing
                            property_type = details.get("property_type", "").lower() if details.get("property_type") else ""
                            if property_type == "newbuilding":
                                LOGGER.info(f"  ⏭️ Skipping newbuilding (property_type='{property_type}' from 'Тип жилья') for listing {listing_id}")
                                continue
                            
                            if property_type == "share":
                                LOGGER.info(f"  ⏭️ Skipping share (detected 'Размер доли' or share indicators) for listing {listing_id}")
                                continue

                            if property_type == "room":
                                LOGGER.info(f"  ⏭️ Skipping room (detected 'комната' in description or /room/ URL) for listing {listing_id}")
                                continue

                            # Also check address_full for new construction indicators
                            address_full = details.get("address_full")
                            if address_full:
                                address_lower = address_full.lower()
                                newbuilding_indicators = ["жилой комплекс", "жилой район", "жк ", "жк.", "новострой"]
                                if any(indicator in address_lower for indicator in newbuilding_indicators):
                                    LOGGER.info(f"  ⏭️ Skipping newbuilding (address contains new construction indicators) for listing {listing_id}")
                                    continue
                            
                            # Analyze description for encumbrances
                            description = details.get("description")
                            if description:
                                try:
                                    enc_analysis = analyze_description(description)
                                    details["has_encumbrances"] = enc_analysis["has_encumbrances"]
                                    details["encumbrance_types"] = enc_analysis.get("flags", [])
                                    details["encumbrance_details"] = enc_analysis
                                    details["encumbrance_confidence"] = enc_analysis.get("confidence", 0.0)
                                    
                                    if enc_analysis["has_encumbrances"]:
                                        analyzer = get_analyzer()
                                        summary = analyzer.get_summary(enc_analysis)
                                        LOGGER.info(f"  ⚠️ Encumbrances detected:\n{summary}")
                                except Exception as e:
                                    LOGGER.warning(f"  ⚠️ Failed to analyze encumbrances: {e}")
                            
                            # Update listing with details
                            update_listing_details(conn, listing_id, details)
                            details_count += 1
                            
                            # Commit after each successful update to ensure data is saved
                            conn.commit()
                            
                            # Normalize address using FIAS if address_full is available
                            # FIAS is disabled by default (very slow ~2min/address)
                            # Set ENABLE_FIAS=1 to enable
                            if address_full and _env_flag("ENABLE_FIAS"):
                                try:
                                    from etl.fias_normalizer import normalize_address
                                    from etl.upsert import upsert_fias_data

                                    fias_data = normalize_address(address_full)
                                    if fias_data:
                                        upsert_fias_data(
                                            conn, listing_id,
                                            fias_address=fias_data.get("fias_address"),
                                            fias_id=fias_data.get("fias_id"),
                                            postal_code=fias_data.get("postal_code"),
                                            quality_code=fias_data.get("quality_code"),
                                        )
                                        conn.commit()  # Commit FIAS data
                                        LOGGER.debug(f"  📍 Address normalized: {fias_data.get('quality_code')}")
                                except Exception as e:
                                    LOGGER.warning(f"  ⚠️ Failed to normalize address: {e}")
                                    # Don't fail the whole process if normalization fails
                            
                            # Insert photos
                            if details.get("photos"):
                                photos = insert_listing_photos(conn, listing_id, details["photos"])
                                conn.commit()  # Commit photos
                                photos_count += photos
                                desc_len = len(details.get("description", "")) if details.get("description") else 0
                                photo_count = len(details.get("photos", []))
                                building = details.get("building_type", "N/A")
                                LOGGER.info(f"  ✅ Saved: desc={desc_len} chars, photos={photo_count}, building_type={building}")
                            else:
                                LOGGER.warning(f"  ⚠️ No photos found for listing {listing_id}")
                        except Exception as save_error:
                            LOGGER.error(f"  ❌ Error saving details for listing {listing_id}: {save_error}")
                            # Try to commit partial progress
                            try:
                                conn.commit()
                            except:
                                conn.rollback()
                            continue
                    else:
                        consecutive_failures += 1
                        error_msg = "Failed to parse details"
                        
                        # Check if it's a network/block error
                        if "ERR_" in str(error_msg) or "timeout" in str(error_msg).lower():
                            LOGGER.warning(f"  ⚠️ Network error detected (failures: {consecutive_failures}/{max_consecutive_failures})")

                            # Too many failures - try auto-refresh cookies
                            if consecutive_failures >= max_consecutive_failures:
                                LOGGER.warning(f"⚠️  {consecutive_failures} consecutive failures - attempting to refresh cookies...")
                                try:
                                    from config.get_cookies_with_proxy import refresh_cookies_if_needed
                                    if refresh_cookies_if_needed(force=True):
                                        LOGGER.info("✅ Cookies refreshed! Recreating browser...")
                                        try:
                                            browser.close()
                                        except:
                                            pass
                                        browser = p.chromium.launch(headless=True)
                                        if storage_path.exists():
                                            context_kwargs["storage_state"] = str(storage_path)
                                        new_context = browser.new_context(**context_kwargs)
                                        new_context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
                                        page = new_context.new_page()
                                        consecutive_failures = 0
                                        LOGGER.info("✅ Continuing with fresh cookies...")
                                    else:
                                        LOGGER.error("❌ Failed to refresh cookies, stopping")
                                        break
                                except Exception as refresh_err:
                                    LOGGER.error(f"❌ Auto-refresh failed: {refresh_err}")
                                    break

                        LOGGER.warning(f"  ❌ Failed to parse details for listing {listing_id}")
                    
                    # Small delay to avoid detection
                    time.sleep(2)
                    
                except Exception as e:
                    consecutive_failures += 1
                    error_str = str(e)
                    
                    # Handle EPIPE error at exception level
                    is_epipe_error = any(keyword in error_str for keyword in [
                        "EPIPE",
                        "write EPIPE",
                        "Broken pipe",
                        "Connection reset by peer",
                        "errno: -32"
                    ])
                    
                    if is_epipe_error:
                        LOGGER.warning(f"  ⚠️ EPIPE error: {error_str[:100]} (failures: {consecutive_failures}/{max_consecutive_failures})")
                        LOGGER.info("  🔄 Recreating browser connection (without proxy)...")
                        try:
                            if browser:
                                browser.close()
                        except:
                            pass

                        # Recreate browser WITHOUT proxy
                        try:
                            browser = p.chromium.launch(headless=True)
                            new_context = browser.new_context(**context_kwargs)
                            new_context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
                            page = new_context.new_page()
                            consecutive_failures = 0
                            LOGGER.info("  ✅ Browser recreated (no proxy), continuing...")
                        except Exception as recreate_error:
                            LOGGER.error(f"  ❌ Failed to recreate browser: {recreate_error}")
                            try:
                                conn.commit()
                            except:
                                pass
                        continue

                    # Too many failures - try to auto-refresh cookies via proxy
                    if consecutive_failures >= max_consecutive_failures:
                        LOGGER.warning(f"⚠️  {consecutive_failures} consecutive failures - attempting to refresh cookies via proxy...")

                        try:
                            from config.get_cookies_with_proxy import refresh_cookies_if_needed
                            if refresh_cookies_if_needed(force=True):
                                LOGGER.info("✅ Cookies refreshed! Recreating browser...")
                                # Recreate browser with fresh cookies
                                try:
                                    browser.close()
                                except:
                                    pass
                                browser = p.chromium.launch(headless=True)
                                # Reload context with new cookies
                                if storage_path.exists():
                                    context_kwargs["storage_state"] = str(storage_path)
                                new_context = browser.new_context(**context_kwargs)
                                new_context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
                                page = new_context.new_page()
                                consecutive_failures = 0
                                LOGGER.info("✅ Browser recreated with fresh cookies, continuing...")
                                continue
                            else:
                                LOGGER.error("❌ Failed to refresh cookies")
                                LOGGER.info("💡 Try manually: python config/get_cookies_with_proxy.py")
                                break
                        except Exception as refresh_error:
                            LOGGER.error(f"❌ Auto-refresh failed: {refresh_error}")
                            LOGGER.info("💡 Try manually: python config/get_cookies_with_proxy.py")
                            break
                    else:
                        LOGGER.error(f"  ❌ Error parsing {url}: {e}")
                    
                    # Commit partial progress even on error
                    try:
                        conn.commit()
                    except:
                        pass
                    
                    continue
                    
    except Exception as e:
        error_str = str(e)
        # Handle EPIPE at top level
        is_epipe_error = any(keyword in error_str for keyword in [
            "EPIPE",
            "write EPIPE",
            "Broken pipe",
            "Connection reset by peer",
            "errno: -32"
        ])
        
        if is_epipe_error:
            LOGGER.warning(f"⚠️ EPIPE error at top level: {error_str[:100]}")
            LOGGER.info("Attempting to continue with remaining listings...")
        else:
            LOGGER.error(f"❌ Fatal error in _parse_listing_details: {e}")
    finally:
        # Ensure browser is closed
        try:
            if browser:
                browser.close()
        except Exception as e:
            # Ignore errors when closing browser (EPIPE is common here)
            if "EPIPE" not in str(e):
                LOGGER.debug(f"Error closing browser: {e}")
    
    LOGGER.info("✅ Detailed parsing complete: %d listings, %d photos", details_count, photos_count)
    return details_count, photos_count


def command_to_db(payload_path: str, pages: int, parse_details: bool = False, unlimited: bool = False, start_page: int = 1) -> None:
    """Fetch offers and load them directly into PostgreSQL.
    
    Args:
        payload_path: Path to YAML payload file
        pages: Number of pages to fetch
        parse_details: If True, parse detailed info (description, photos, dates) for each listing
    """
    payload = _load_payload(payload_path)
    listings, prices, details, photos = _collect_and_process(payload, pages, parse_details=parse_details, start_page=start_page)
    
    _log_data_quality_metrics()
    
    # Log execution history
    import datetime
    execution_time = datetime.datetime.now().isoformat()
    
    if parse_details:
        LOGGER.info("📊 Summary: listings=%s, new_prices=%s, details_parsed=%s, photos_inserted=%s", 
                   listings, prices, details, photos)
        LOGGER.info("📝 Execution history: time=%s, pages=%s, parse_details=True, completed=True", 
                   execution_time, pages)
    else:
        LOGGER.info("📊 Summary: listings=%s, new_prices=%s", listings, prices)
        LOGGER.info("📝 Execution history: time=%s, pages=%s, parse_details=False, completed=True", 
                   execution_time, pages)
    
    LOGGER.info("✅ Parser cycle completed successfully. Stopping. (No auto-restart)")


def command_autonomous(
    payload_path: str,
    pages_per_run: int,
    *,
    target_offers: int,
    sleep_seconds: int,
    parse_details: bool,
    max_runtime: int,
    max_runs: int,
    log_file: str,
    max_failures: int,
) -> None:
    """Long-running mode that keeps collecting data in chunks."""
    payload = _load_payload(payload_path)
    log_path = Path(log_file) if log_file else DEFAULT_AUTONOMOUS_LOG
    _setup_file_logger(log_path)

    totals = {
        "listings": 0,
        "prices": 0,
        "details": 0,
        "photos": 0,
    }
    iteration = 0
    start_ts = time.time()
    consecutive_failures = 0
    empty_iterations = 0

    LOGGER.info(
        "🚀 Autonomous collector started: payload=%s, pages_per_run=%s, target_offers=%s",
        payload_path,
        pages_per_run,
        target_offers or "∞",
    )

    while True:
        iteration += 1
        LOGGER.info("▶️  Chunk %s starting...", iteration)
        try:
            listings, prices, details, photos = _collect_and_process(
                payload,
                pages_per_run,
                parse_details=parse_details,
            )
        except Exception as exc:
            consecutive_failures += 1
            LOGGER.error(
                "❌ Autonomous chunk %s failed (%s/%s consecutive errors): %s",
                iteration,
                consecutive_failures,
                max_failures,
                exc,
            )
            if consecutive_failures >= max_failures:
                LOGGER.error("Stopping autonomous collector due to too many failures")
                raise
            if sleep_seconds > 0:
                LOGGER.info("Sleeping %s seconds before retry after failure", sleep_seconds)
                time.sleep(sleep_seconds)
            continue

        consecutive_failures = 0
        totals["listings"] += listings
        totals["prices"] += prices
        totals["details"] += details
        totals["photos"] += photos

        if listings == 0:
            empty_iterations += 1
            LOGGER.warning("Chunk %s yielded no listings (empty iteration %s)", iteration, empty_iterations)
        else:
            empty_iterations = 0

        LOGGER.info(
            "🧩 Chunk %s summary: +%s listings, +%s prices, +%s details, +%s photos. Totals=%s listings",
            iteration,
            listings,
            prices,
            details,
            photos,
            totals["listings"],
        )

        _log_data_quality_metrics()

        if target_offers and totals["listings"] >= target_offers:
            LOGGER.info(
                "🎯 Target reached: %s listings collected (>= %s)",
                totals["listings"],
                target_offers,
            )
            break

        if max_runs and iteration >= max_runs:
            LOGGER.info("⏹️  Reached maximum iterations (%s)", max_runs)
            break

        elapsed = time.time() - start_ts
        if max_runtime and elapsed >= max_runtime:
            LOGGER.info("⏹️  Reached max runtime (%.0f / %s seconds)", elapsed, max_runtime)
            break

        if empty_iterations >= max_failures:
            LOGGER.warning(
                "⏹️  No listings returned for %s consecutive chunks. Stopping to avoid busy loop.",
                empty_iterations,
            )
            break

        if sleep_seconds > 0:
            LOGGER.info("💤 Sleeping for %s seconds before next chunk", sleep_seconds)
            time.sleep(sleep_seconds)

    total_elapsed = time.time() - start_ts
    LOGGER.info(
        "✅ Autonomous collector finished after %s chunk(s) in %.1f seconds. Totals: listings=%s prices=%s details=%s photos=%s",
        iteration,
        total_elapsed,
        totals["listings"],
        totals["prices"],
        totals["details"],
        totals["photos"],
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CIAN collector CLI")
    sub = parser.add_subparsers(dest="cmd")

    def add_common_arguments(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--payload",
            default="etl/collector_cian/payloads/base.yaml",
            help="Path to YAML payload describing the search filters",
        )
        subparser.add_argument("--pages", type=int, default=1, help="Number of pages to fetch")
        subparser.add_argument(
            "--force-run",
            action="store_true",
            help="Skip parser lock (or set CIAN_FORCE_RUN=1) if you really need concurrent runs",
        )

    pull_parser = sub.add_parser("pull", help="Fetch data and print JSONL to stdout")
    add_common_arguments(pull_parser)

    to_db_parser = sub.add_parser("to-db", help="Fetch data and upsert into PostgreSQL")
    add_common_arguments(to_db_parser)
    to_db_parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="Start from this page number (default: 1)",
    )
    to_db_parser.add_argument(
        "--parse-details",
        action="store_true",
        default=True,
        help="Parse detailed information (description, photos, publication date) for each listing (default: True)",
    )
    to_db_parser.add_argument(
        "--no-parse-details",
        action="store_false",
        dest="parse_details",
        help="Skip detailed parsing (faster but less data)",
    )
    
    auto_parser = sub.add_parser("autonomous", help="Run continuous autonomous collector loop")
    add_common_arguments(auto_parser)
    auto_parser.set_defaults(pages=5)
    auto_parser.add_argument(
        "--target-offers",
        type=int,
        default=100000,
        help="Stop after collecting at least this many listings (0 = no limit)",
    )
    auto_parser.add_argument(
        "--sleep-seconds",
        type=int,
        default=60,
        help="Pause between chunks (seconds)",
    )
    auto_parser.add_argument(
        "--max-runtime",
        type=int,
        default=0,
        help="Maximum runtime in seconds (0 = unlimited)",
    )
    auto_parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Maximum number of chunks to execute (0 = unlimited)",
    )
    auto_parser.add_argument(
        "--log-file",
        default=str(DEFAULT_AUTONOMOUS_LOG),
        help="Path to rotating log file for autonomous runs",
    )
    auto_parser.add_argument(
        "--max-failures",
        type=int,
        default=5,
        help="Stop after N consecutive failures or empty chunks",
    )
    auto_parser.add_argument(
        "--parse-details",
        action="store_true",
        default=True,
        help="Parse detailed information for each listing (default: True)",
    )
    auto_parser.add_argument(
        "--no-parse-details",
        action="store_false",
        dest="parse_details",
        help="Skip detailed parsing for faster bulk collection",
    )
    
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd in {"pull", "to-db", "autonomous"}:
        force_run = getattr(args, "force_run", False) or _env_flag("CIAN_FORCE_RUN")
        try:
            with _parser_run_lock(force=force_run):
                if args.cmd == "pull":
                    command_pull(args.payload, args.pages)
                elif args.cmd == "to-db":
                    command_to_db(args.payload, args.pages, parse_details=getattr(args, "parse_details", False), start_page=getattr(args, "start_page", 1))
                else:
                    command_autonomous(
                        args.payload,
                        args.pages,
                        target_offers=args.target_offers,
                        sleep_seconds=args.sleep_seconds,
                        parse_details=getattr(args, "parse_details", True),
                        max_runtime=args.max_runtime,
                        max_runs=args.max_runs,
                        log_file=args.log_file,
                        max_failures=args.max_failures,
                    )
        except RuntimeError as lock_error:
            LOGGER.error(lock_error)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
