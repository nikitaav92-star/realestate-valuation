#!/usr/bin/env python3
"""Test production filters and strict validation.

Tests:
1. New payload with production filters
2. Strict validation (all 15 fields required)
3. Data quality checks
"""
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from etl.collector_cian.fetcher import load_payload
from etl.collector_cian.mapper_v2 import (
    extract_offers,
    validate_and_map_offers,
    ListingValidationError,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

LOGGER = logging.getLogger(__name__)


def test_payload_filters():
    """Test that production payload has correct filters."""
    LOGGER.info("=" * 80)
    LOGGER.info("Testing production payload filters")
    LOGGER.info("=" * 80)
    
    payload_path = Path(__file__).parent.parent / "etl/collector_cian/payloads/production.yaml"
    
    if not payload_path.exists():
        LOGGER.error(f"Production payload not found: {payload_path}")
        return False
    
    payload = load_payload(payload_path)
    query = payload.get("jsonQuery", {})
    
    # Check required filters
    checks = {
        "Регион (Москва)": query.get("region", {}).get("value") == [1],
        "Тип сделки (продажа)": query.get("deal_type", {}).get("value") == "sale",
        "Тип жилья (вторичка)": query.get("building_status", {}).get("value") == "secondary",
        "Категория (квартиры)": query.get("offer_type", {}).get("value") == "flat",
        "Цена (до 30 млн)": query.get("price", {}).get("value", {}).get("lte") == 30000000,
        "Этаж (от 2)": query.get("floor", {}).get("value", {}).get("gte") == 2,
        "Комнаты (0,1,2,3)": query.get("room", {}).get("value") == [0, 1, 2, 3],
    }
    
    all_passed = True
    for check_name, result in checks.items():
        status = "✅" if result else "❌"
        LOGGER.info(f"{status} {check_name}: {result}")
        if not result:
            all_passed = False
    
    return all_passed


def test_strict_validation():
    """Test strict validation with sample data."""
    LOGGER.info("\n" + "=" * 80)
    LOGGER.info("Testing strict validation")
    LOGGER.info("=" * 80)
    
    # Valid offer (all fields present)
    valid_offer = {
        "offerId": 123456789,
        "seoUrl": "https://www.cian.ru/sale/flat/123456789/",
        "region": 1,
        "address": "Москва, Тверская улица, 10",
        "geo": {
            "coordinates": {
                "lat": 55.751244,
                "lng": 37.618423
            }
        },
        "operationName": "sale",
        "rooms": 2,
        "totalSquare": 65.5,
        "floor": 5,
        "userType": "owner",
        "price": {
            "value": 15000000
        }
    }
    
    # Invalid offers (missing required fields)
    invalid_offers = [
        {
            "offerId": 111,
            "seoUrl": "https://www.cian.ru/sale/flat/111/",
            # Missing address
        },
        {
            "offerId": 222,
            "seoUrl": "https://www.cian.ru/sale/flat/222/",
            "address": "Москва",
            # Missing coordinates
        },
        {
            "offerId": 333,
            "seoUrl": "https://www.cian.ru/sale/flat/333/",
            "address": "Москва",
            "geo": {"coordinates": {"lat": 55.75, "lng": 37.62}},
            # Missing price
        },
    ]
    
    # Test valid offer
    try:
        listings, prices, errors = validate_and_map_offers([valid_offer])
        if len(listings) == 1 and len(errors) == 0:
            LOGGER.info("✅ Valid offer mapped successfully")
            LOGGER.info(f"   ID: {listings[0].id}")
            LOGGER.info(f"   URL: {listings[0].url}")
            LOGGER.info(f"   Address: {listings[0].address}")
            LOGGER.info(f"   Rooms: {listings[0].rooms}")
            LOGGER.info(f"   Area: {listings[0].area_total} m²")
            LOGGER.info(f"   Price: {prices[0].price:,.0f} ₽")
        else:
            LOGGER.error("❌ Valid offer failed validation")
            return False
    except Exception as e:
        LOGGER.error(f"❌ Valid offer raised exception: {e}")
        return False
    
    # Test invalid offers
    LOGGER.info("\nTesting invalid offers (should be rejected):")
    listings, prices, errors = validate_and_map_offers(invalid_offers)
    
    if len(errors) == len(invalid_offers):
        LOGGER.info(f"✅ All {len(errors)} invalid offers correctly rejected")
        for error in errors:
            LOGGER.info(f"   • {error}")
    else:
        LOGGER.error(f"❌ Expected {len(invalid_offers)} errors, got {len(errors)}")
        return False
    
    return True


def main():
    """Run all tests."""
    LOGGER.info("🚀 Testing production configuration\n")
    
    # Test 1: Payload filters
    filters_ok = test_payload_filters()
    
    # Test 2: Strict validation
    validation_ok = test_strict_validation()
    
    # Summary
    LOGGER.info("\n" + "=" * 80)
    LOGGER.info("📊 TEST SUMMARY")
    LOGGER.info("=" * 80)
    LOGGER.info(f"Payload filters: {'✅ PASS' if filters_ok else '❌ FAIL'}")
    LOGGER.info(f"Strict validation: {'✅ PASS' if validation_ok else '❌ FAIL'}")
    
    if filters_ok and validation_ok:
        LOGGER.info("\n🎉 All tests passed! Ready for production.")
        return 0
    else:
        LOGGER.error("\n❌ Some tests failed. Fix issues before production.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

