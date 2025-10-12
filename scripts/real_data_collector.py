#!/usr/bin/env python3
"""Real CIAN data collector that actually extracts offer details."""

import json
import logging
import sys
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

def extract_real_offers(page):
    """Extract real offer data from CIAN page."""
    try:
        # Wait for offers to load
        page.wait_for_selector('[data-name="LinkArea"]', timeout=10000)
        
        # Extract real offer data
        offers = page.evaluate("""
            () => {
                const cards = document.querySelectorAll('[data-name="LinkArea"]');
                const realOffers = [];
                
                cards.forEach((card, index) => {
                    try {
                        // Find the offer container
                        const offerCard = card.closest('[data-name="OfferCard"]') || card;
                        
                        // Extract real data
                        const titleEl = offerCard.querySelector('[data-mark="OfferTitle"]') || 
                                       offerCard.querySelector('.c6e8ba5398--title');
                        const priceEl = offerCard.querySelector('[data-mark="MainPrice"]') || 
                                       offerCard.querySelector('.c6e8ba5398--price');
                        const addressEl = offerCard.querySelector('[data-mark="GeoLabel"]') || 
                                         offerCard.querySelector('.c6e8ba5398--geo');
                        const roomsEl = offerCard.querySelector('[data-mark="RoomsCount"]') || 
                                       offerCard.querySelector('.c6e8ba5398--rooms');
                        const areaEl = offerCard.querySelector('[data-mark="AreaValue"]') || 
                                      offerCard.querySelector('.c6e8ba5398--area');
                        const floorEl = offerCard.querySelector('[data-mark="FloorValue"]') || 
                                       offerCard.querySelector('.c6e8ba5398--floor');
                        
                        // Get link
                        const linkEl = card.querySelector('a') || card;
                        const url = linkEl.href || window.location.href;
                        
                        const offer = {
                            index: index + 1,
                            title: titleEl ? titleEl.textContent.trim() : 'N/A',
                            price: priceEl ? priceEl.textContent.trim() : 'N/A', 
                            address: addressEl ? addressEl.textContent.trim() : 'N/A',
                            rooms: roomsEl ? roomsEl.textContent.trim() : 'N/A',
                            area: areaEl ? areaEl.textContent.trim() : 'N/A',
                            floor: floorEl ? floorEl.textContent.trim() : 'N/A',
                            url: url,
                            extracted_at: new Date().toISOString()
                        };
                        
                        // Only add if we have meaningful data
                        if (offer.title !== 'N/A' || offer.price !== 'N/A') {
                            realOffers.push(offer);
                        }
                    } catch (e) {
                        console.error('Error extracting offer:', e);
                    }
                });
                
                return realOffers;
            }
        """)
        
        return offers
    except Exception as e:
        LOGGER.error(f"Error extracting offers: {e}")
        return []

def collect_real_cian_data(max_pages=3):
    """Collect real CIAN data with actual offer details."""
    
    LOGGER.info("🚀 Starting REAL CIAN data collection...")
    
    all_offers = []
    successful_pages = 0
    total_time = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            for page_num in range(1, max_pages + 1):
                start_time = time.time()
                
                # Navigate to page
                url = f"https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1&p={page_num}"
                LOGGER.info(f"📄 Loading page {page_num}: {url}")
                
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(3)  # Let page load completely
                    
                    # Extract real offers
                    LOGGER.info(f"🔍 Extracting offers from page {page_num}...")
                    page_offers = extract_real_offers(page)
                    
                    if page_offers:
                        all_offers.extend(page_offers)
                        successful_pages += 1
                        
                        page_time = time.time() - start_time
                        total_time += page_time
                        
                        LOGGER.info(f"✅ Page {page_num}: {len(page_offers)} REAL offers | Total: {len(all_offers)} | Time: {page_time:.1f}s")
                        
                        # Show first offer as example
                        if page_offers:
                            first_offer = page_offers[0]
                            LOGGER.info(f"   📋 Example: {first_offer['title'][:50]}... - {first_offer['price']}")
                    else:
                        LOGGER.warning(f"⚠️ Page {page_num}: No offers extracted")
                    
                except Exception as e:
                    LOGGER.error(f"❌ Page {page_num} failed: {e}")
                    continue
            
            # Save results
            if all_offers:
                output_file = "logs/real_cian_data.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'collection_time': datetime.now().isoformat(),
                        'total_offers': len(all_offers),
                        'successful_pages': successful_pages,
                        'total_time': total_time,
                        'offers': all_offers
                    }, f, ensure_ascii=False, indent=2)
                
                LOGGER.info(f"\n💾 Saved {len(all_offers)} REAL offers to: {output_file}")
                
                # Show summary
                LOGGER.info(f"\n📊 REAL DATA COLLECTION SUMMARY:")
                LOGGER.info(f"   ✅ Total REAL offers: {len(all_offers)}")
                LOGGER.info(f"   ✅ Successful pages: {successful_pages}")
                LOGGER.info(f"   ✅ Total time: {total_time:.1f}s")
                LOGGER.info(f"   ✅ Data quality: {'GOOD' if any(offer['price'] != 'N/A' for offer in all_offers) else 'POOR'}")
                
                # Show first 3 offers
                LOGGER.info(f"\n📋 FIRST 3 REAL OFFERS:")
                for i, offer in enumerate(all_offers[:3]):
                    LOGGER.info(f"\n{i+1}. {offer['title']}")
                    LOGGER.info(f"   💰 {offer['price']}")
                    LOGGER.info(f"   📍 {offer['address']}")
                    LOGGER.info(f"   🏠 {offer['rooms']} | {offer['area']} | {offer['floor']}")
                
                return len(all_offers)
            else:
                LOGGER.error("❌ No real offers collected!")
                return 0
                
        except Exception as e:
            LOGGER.error(f"❌ Collection failed: {e}")
            return 0
        finally:
            browser.close()

if __name__ == "__main__":
    offers_count = collect_real_cian_data(max_pages=3)
    
    if offers_count > 0:
        LOGGER.info(f"\n🎉 SUCCESS: Collected {offers_count} REAL CIAN offers!")
        LOGGER.info("📁 Check logs/real_cian_data.json for complete data")
    else:
        LOGGER.error("\n❌ FAILED: No real data collected")
        sys.exit(1)

