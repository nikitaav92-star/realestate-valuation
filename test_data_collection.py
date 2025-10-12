#!/usr/bin/env python3
"""
Комплексный тест сбора данных и работы алгоритма
Comprehensive test for data collection and algorithm operation
"""
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import httpx
from etl.collector_cian.fetcher import CIAN_URL, load_payload, collect
from etl.collector_cian.mapper import extract_offers, to_listing, to_price
from etl.upsert import get_db_connection, upsert_listing, upsert_price_if_changed

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("test_data_collection.log"),
    ],
)

LOGGER = logging.getLogger(__name__)


class TestResults:
    """Container for test results"""
    def __init__(self):
        self.tests = []
        self.start_time = time.time()
    
    def add(self, name: str, success: bool, details: str = "", data: Any = None):
        """Add test result"""
        self.tests.append({
            "name": name,
            "success": success,
            "details": details,
            "data": data,
            "timestamp": time.time()
        })
    
    def print_summary(self):
        """Print test summary"""
        LOGGER.info("\n" + "=" * 80)
        LOGGER.info("📊 SUMMARY OF TESTS / ИТОГИ ТЕСТИРОВАНИЯ")
        LOGGER.info("=" * 80)
        
        success_count = sum(1 for t in self.tests if t["success"])
        total_tests = len(self.tests)
        
        for i, test in enumerate(self.tests, 1):
            status = "✅ PASS" if test["success"] else "❌ FAIL"
            LOGGER.info(f"{i}. {status}: {test['name']}")
            if test["details"]:
                LOGGER.info(f"   Details: {test['details']}")
        
        LOGGER.info("=" * 80)
        LOGGER.info(f"Success Rate: {success_count}/{total_tests} ({success_count/total_tests*100:.1f}%)")
        LOGGER.info(f"Total Duration: {time.time() - self.start_time:.2f}s")
        LOGGER.info("=" * 80)
        
        return success_count == total_tests


def test_database_connection(results: TestResults) -> bool:
    """Тест 1: Проверка подключения к базе данных"""
    LOGGER.info("\n🔍 Test 1: Database Connection / Подключение к БД")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('listings', 'listing_prices')
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        if 'listings' in tables and 'listing_prices' in tables:
            results.add("Database Connection", True, f"Tables found: {tables}")
            LOGGER.info("✅ Database connected, tables exist")
            
            # Get counts
            cursor.execute("SELECT COUNT(*) FROM listings")
            listings_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM listing_prices")
            prices_count = cursor.fetchone()[0]
            
            LOGGER.info(f"   Current data: {listings_count} listings, {prices_count} prices")
            conn.close()
            return True
        else:
            results.add("Database Connection", False, f"Missing tables. Found: {tables}")
            LOGGER.error("❌ Required tables not found")
            conn.close()
            return False
            
    except Exception as e:
        results.add("Database Connection", False, str(e))
        LOGGER.error(f"❌ Database connection failed: {e}")
        return False


def test_payload_loading(results: TestResults) -> dict:
    """Тест 2: Загрузка конфигурации запроса"""
    LOGGER.info("\n🔍 Test 2: Payload Loading / Загрузка конфигурации")
    
    try:
        payload_path = Path(__file__).parent / "etl/collector_cian/payloads/base.yaml"
        payload = load_payload(payload_path)
        
        # Validate required structure
        if "jsonQuery" not in payload:
            results.add("Payload Loading", False, "Missing jsonQuery section")
            LOGGER.error("❌ Missing required jsonQuery section")
            return None
        
        json_query = payload.get("jsonQuery", {})
        results.add("Payload Loading", True, f"Loaded payload with {len(json_query)} filters")
        LOGGER.info(f"✅ Payload loaded successfully: {len(json_query)} filters in jsonQuery")
        LOGGER.info(f"   Limit: {payload.get('limit', 'N/A')}, Sort: {payload.get('sort', {}).get('value', 'N/A')}")
        return payload
        
    except Exception as e:
        results.add("Payload Loading", False, str(e))
        LOGGER.error(f"❌ Payload loading failed: {e}")
        return None


async def test_data_collection(results: TestResults, payload: dict) -> List[dict]:
    """Тест 3: Сбор данных с CIAN"""
    LOGGER.info("\n🔍 Test 3: Data Collection / Сбор данных")
    
    try:
        # Collect data for 1 page
        LOGGER.info("Collecting data from CIAN (1 page)...")
        responses = await collect(payload, pages=1)
        
        if not responses:
            results.add("Data Collection", False, "No responses received")
            LOGGER.error("❌ No responses received")
            return []
        
        # Extract offers
        all_offers = []
        for response in responses:
            offers = extract_offers(response)
            all_offers.extend(offers)
        
        if not all_offers:
            results.add("Data Collection", False, "No offers extracted from response")
            LOGGER.error("❌ No offers extracted")
            return []
        
        results.add("Data Collection", True, f"Collected {len(all_offers)} offers")
        LOGGER.info(f"✅ Data collected successfully: {len(all_offers)} offers")
        
        # Show sample offer
        if all_offers:
            sample = all_offers[0]
            LOGGER.info(f"   Sample offer ID: {sample.get('id', 'N/A')}")
            LOGGER.info(f"   Price: {sample.get('bargainTerms', {}).get('priceRur', 'N/A')} RUB")
        
        return all_offers
        
    except Exception as e:
        results.add("Data Collection", False, str(e))
        LOGGER.error(f"❌ Data collection failed: {e}")
        return []


def test_data_mapping(results: TestResults, offers: List[dict]) -> List[tuple]:
    """Тест 4: Преобразование данных (маппинг)"""
    LOGGER.info("\n🔍 Test 4: Data Mapping / Преобразование данных")
    
    try:
        if not offers:
            results.add("Data Mapping", False, "No offers to map")
            LOGGER.warning("⚠️  No offers to map")
            return []
        
        mapped_data = []
        success_count = 0
        error_count = 0
        
        for offer in offers[:5]:  # Test first 5 offers
            try:
                listing = to_listing(offer)
                price = to_price(offer)
                mapped_data.append((listing, price))
                success_count += 1
            except Exception as e:
                error_count += 1
                LOGGER.warning(f"   Mapping error for offer {offer.get('id')}: {e}")
        
        if success_count > 0:
            results.add("Data Mapping", True, 
                       f"Mapped {success_count}/{len(offers[:5])} offers successfully")
            LOGGER.info(f"✅ Data mapping successful: {success_count} offers")
            
            # Show sample mapped data
            if mapped_data:
                listing, price = mapped_data[0]
                LOGGER.info(f"   Sample mapped listing: ID={listing.id}, Price={price.price}")
            
            return mapped_data
        else:
            results.add("Data Mapping", False, f"All {error_count} mappings failed")
            LOGGER.error("❌ All mappings failed")
            return []
            
    except Exception as e:
        results.add("Data Mapping", False, str(e))
        LOGGER.error(f"❌ Data mapping failed: {e}")
        return []


def test_database_upsert(results: TestResults, mapped_data: List[tuple]) -> bool:
    """Тест 5: Сохранение в базу данных"""
    LOGGER.info("\n🔍 Test 5: Database Upsert / Сохранение в БД")
    
    try:
        if not mapped_data:
            results.add("Database Upsert", False, "No data to save")
            LOGGER.warning("⚠️  No data to save")
            return False
        
        conn = get_db_connection()
        
        try:
            listings_saved = 0
            prices_saved = 0
            
            for listing, price in mapped_data:
                upsert_listing(conn, listing)
                if upsert_price_if_changed(conn, listing.id, price.price):
                    prices_saved += 1
                listings_saved += 1
            
            conn.commit()
            
            results.add("Database Upsert", True, 
                       f"Saved {listings_saved} listings, {prices_saved} new prices")
            LOGGER.info(f"✅ Data saved: {listings_saved} listings, {prices_saved} new prices")
            
            return True
            
        finally:
            conn.close()
            
    except Exception as e:
        results.add("Database Upsert", False, str(e))
        LOGGER.error(f"❌ Database upsert failed: {e}")
        return False


def test_data_retrieval(results: TestResults) -> bool:
    """Тест 6: Проверка сохраненных данных"""
    LOGGER.info("\n🔍 Test 6: Data Retrieval / Проверка сохраненных данных")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get latest listings
        cursor.execute("""
            SELECT l.id, l.address, l.area_total, l.floor, l.rooms,
                   p.price, p.seen_at
            FROM listings l
            LEFT JOIN listing_prices p ON l.id = p.id
            ORDER BY p.seen_at DESC
            LIMIT 5
        """)
        
        rows = cursor.fetchall()
        
        if rows:
            results.add("Data Retrieval", True, f"Retrieved {len(rows)} listings")
            LOGGER.info(f"✅ Data retrieved successfully: {len(rows)} listings")
            
            LOGGER.info("\n   Latest listings:")
            for i, row in enumerate(rows, 1):
                listing_id, address, area, floor, rooms, price, recorded = row
                LOGGER.info(f"   {i}. ID: {listing_id}")
                if address:
                    LOGGER.info(f"      Address: {address[:60]}...")
                LOGGER.info(f"      Area: {area} m², Floor: {floor}, Rooms: {rooms}")
                if price:
                    LOGGER.info(f"      Price: {price:,} RUB")
            
            conn.close()
            return True
        else:
            results.add("Data Retrieval", False, "No data in database")
            LOGGER.warning("⚠️  No data found in database")
            conn.close()
            return False
            
    except Exception as e:
        results.add("Data Retrieval", False, str(e))
        LOGGER.error(f"❌ Data retrieval failed: {e}")
        return False


def test_algorithm_logic(results: TestResults) -> bool:
    """Тест 7: Проверка логики алгоритма (SCD Type 2)"""
    LOGGER.info("\n🔍 Test 7: Algorithm Logic / Проверка алгоритма (SCD Type 2)")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check for price history (SCD Type 2)
        cursor.execute("""
            SELECT id, COUNT(*) as price_changes
            FROM listing_prices
            GROUP BY id
            HAVING COUNT(*) > 1
            ORDER BY price_changes DESC
            LIMIT 5
        """)
        
        rows = cursor.fetchall()
        
        if rows:
            results.add("Algorithm Logic (SCD2)", True, 
                       f"Found {len(rows)} listings with price history")
            LOGGER.info(f"✅ SCD Type 2 working: {len(rows)} listings with price changes")
            
            # Show price history for one listing
            listing_id = rows[0][0]
            cursor.execute("""
                SELECT price, seen_at
                FROM listing_prices
                WHERE id = %s
                ORDER BY seen_at DESC
            """, (listing_id,))
            
            price_history = cursor.fetchall()
            LOGGER.info(f"\n   Price history for listing {listing_id}:")
            for price, seen_at in price_history:
                LOGGER.info(f"      {price:,} RUB (seen at {seen_at})")
        else:
            results.add("Algorithm Logic (SCD2)", True, 
                       "No price changes yet (expected for first run)")
            LOGGER.info("✅ SCD Type 2 ready (no price changes detected yet)")
        
        conn.close()
        return True
        
    except Exception as e:
        results.add("Algorithm Logic (SCD2)", False, str(e))
        LOGGER.error(f"❌ Algorithm check failed: {e}")
        return False


async def main():
    """Main test orchestrator"""
    LOGGER.info("=" * 80)
    LOGGER.info("🚀 STARTING COMPREHENSIVE DATA COLLECTION TEST")
    LOGGER.info("🚀 ЗАПУСК КОМПЛЕКСНОГО ТЕСТА СБОРА ДАННЫХ")
    LOGGER.info("=" * 80)
    
    results = TestResults()
    
    # Test 1: Database Connection
    if not test_database_connection(results):
        LOGGER.error("\n❌ Database not available, stopping tests")
        results.print_summary()
        return
    
    # Test 2: Payload Loading
    payload = test_payload_loading(results)
    if not payload:
        LOGGER.error("\n❌ Cannot proceed without valid payload")
        results.print_summary()
        return
    
    # Test 3: Data Collection
    offers = await test_data_collection(results, payload)
    
    # Test 4: Data Mapping
    mapped_data = test_data_mapping(results, offers)
    
    # Test 5: Database Upsert
    test_database_upsert(results, mapped_data)
    
    # Test 6: Data Retrieval
    test_data_retrieval(results)
    
    # Test 7: Algorithm Logic
    test_algorithm_logic(results)
    
    # Print summary
    all_passed = results.print_summary()
    
    # Save results to file
    results_file = Path(__file__).parent / "logs" / "test_results.json"
    results_file.parent.mkdir(exist_ok=True)
    
    with open(results_file, "w") as f:
        json.dump({
            "timestamp": time.time(),
            "all_tests_passed": all_passed,
            "tests": results.tests
        }, f, indent=2)
    
    LOGGER.info(f"\n📄 Results saved to: {results_file}")
    
    if all_passed:
        LOGGER.info("\n🎉 ALL TESTS PASSED! / ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    else:
        LOGGER.warning("\n⚠️  SOME TESTS FAILED / НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")


if __name__ == "__main__":
    asyncio.run(main())

