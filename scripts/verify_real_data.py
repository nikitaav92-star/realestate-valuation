#!/usr/bin/env python3
"""Verify real CIAN data collection and show actual offers."""

import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

def extract_offers_from_page(page):
    """Extract actual offers from CIAN page."""
    try:
        # Wait for page to load
        page.wait_for_selector('[data-name="OfferCard"]', timeout=10000)
        
        # Extract offers using JavaScript
        offers = page.evaluate("""
            () => {
                const cards = document.querySelectorAll('[data-name="OfferCard"]');
                const offers = [];
                
                cards.forEach((card, index) => {
                    try {
                        // Extract basic info
                        const titleEl = card.querySelector('[data-mark="OfferTitle"]');
                        const priceEl = card.querySelector('[data-mark="MainPrice"]');
                        const addressEl = card.querySelector('[data-mark="GeoLabel"]');
                        const roomsEl = card.querySelector('[data-mark="RoomsCount"]');
                        const areaEl = card.querySelector('[data-mark="AreaValue"]');
                        const floorEl = card.querySelector('[data-mark="FloorValue"]');
                        
                        const offer = {
                            index: index + 1,
                            title: titleEl ? titleEl.textContent.trim() : 'N/A',
                            price: priceEl ? priceEl.textContent.trim() : 'N/A',
                            address: addressEl ? addressEl.textContent.trim() : 'N/A',
                            rooms: roomsEl ? roomsEl.textContent.trim() : 'N/A',
                            area: areaEl ? areaEl.textContent.trim() : 'N/A',
                            floor: floorEl ? floorEl.textContent.trim() : 'N/A',
                            url: window.location.href
                        };
                        
                        offers.push(offer);
                    } catch (e) {
                        console.error('Error extracting offer:', e);
                    }
                });
                
                return offers;
            }
        """)
        
        return offers
    except Exception as e:
        LOGGER.error(f"Error extracting offers: {e}")
        return []

def test_real_cian_data():
    """Test real CIAN data collection."""
    LOGGER.info("🚀 Testing REAL CIAN data collection...")
    
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            # Navigate to CIAN
            url = "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1"
            LOGGER.info(f"Navigating to: {url}")
            
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            
            # Extract offers from first page
            LOGGER.info("Extracting offers from page...")
            offers = extract_offers_from_page(page)
            
            if offers:
                LOGGER.info(f"✅ Found {len(offers)} real offers!")
                
                # Show first 5 offers in detail
                LOGGER.info("\n📋 FIRST 5 REAL OFFERS:")
                for i, offer in enumerate(offers[:5]):
                    LOGGER.info(f"\n{i+1}. {offer['title']}")
                    LOGGER.info(f"   💰 Price: {offer['price']}")
                    LOGGER.info(f"   📍 Address: {offer['address']}")
                    LOGGER.info(f"   🏠 Rooms: {offer['rooms']}")
                    LOGGER.info(f"   📐 Area: {offer['area']}")
                    LOGGER.info(f"   🏢 Floor: {offer['floor']}")
                
                # Save to file for verification
                output_file = "logs/real_cian_offers.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(offers, f, ensure_ascii=False, indent=2)
                
                LOGGER.info(f"\n💾 Saved {len(offers)} offers to: {output_file}")
                
                # Summary
                LOGGER.info(f"\n📊 SUMMARY:")
                LOGGER.info(f"   Total offers found: {len(offers)}")
                LOGGER.info(f"   Data quality: {'✅ GOOD' if len(offers) > 0 else '❌ EMPTY'}")
                LOGGER.info(f"   Real data: {'✅ YES' if any(offer['price'] != 'N/A' for offer in offers) else '❌ NO'}")
                
                return len(offers)
            else:
                LOGGER.error("❌ No offers found!")
                return 0
                
        except Exception as e:
            LOGGER.error(f"❌ Error: {e}")
            return 0
        finally:
            browser.close()

if __name__ == "__main__":
    offers_count = test_real_cian_data()
    
    if offers_count > 0:
        LOGGER.info(f"\n🎉 SUCCESS: Found {offers_count} real CIAN offers!")
        LOGGER.info("📁 Check logs/real_cian_offers.json for full data")
    else:
        LOGGER.error("\n❌ FAILED: No real data found")
        sys.exit(1)

