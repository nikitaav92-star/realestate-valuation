#!/usr/bin/env python3
"""Create demo CIAN data to show what real collection would look like."""

import json
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

def generate_realistic_cian_data(count=50):
    """Generate realistic CIAN offer data for demonstration."""
    
    # Real Moscow addresses
    addresses = [
        "Москва, ул. Арбат, 15",
        "Москва, Ленинский проспект, 45",
        "Москва, ул. Тверская, 8",
        "Москва, Садовое кольцо, 12",
        "Москва, ул. Красная Пресня, 25",
        "Москва, Кутузовский проспект, 30",
        "Москва, ул. Новый Арбат, 20",
        "Москва, Ленинский проспект, 85",
        "Москва, ул. Пятницкая, 35",
        "Москва, Садовническая набережная, 10",
        "Москва, ул. Остоженка, 22",
        "Москва, Тверской бульвар, 18",
        "Москва, ул. Большая Дмитровка, 14",
        "Москва, Страстной бульвар, 16",
        "Москва, ул. Петровка, 28"
    ]
    
    # Real estate types
    room_types = ["Студия", "1-комн", "2-комн", "3-комн", "4-комн"]
    seller_types = ["Собственник", "Агент", "Застройщик"]
    
    offers = []
    
    for i in range(count):
        rooms = random.choice([0, 1, 2, 3, 4])
        room_type = room_types[rooms] if rooms < 4 else "4+ комн"
        
        # Realistic pricing based on rooms and location
        base_price = 8000000 if rooms == 0 else 10000000 + (rooms * 3000000)
        price = base_price + random.randint(-2000000, 5000000)
        
        # Realistic area
        area = 25 + (rooms * 15) + random.randint(-5, 10)
        
        # Realistic floor
        floor = random.randint(2, 25)
        total_floors = floor + random.randint(1, 10)
        
        offer = {
            "id": 1000000 + i,
            "title": f"{room_type} квартира, {area} м²",
            "price": f"{price:,} ₽".replace(",", " "),
            "price_numeric": price,
            "address": random.choice(addresses),
            "rooms": rooms,
            "area_total": area,
            "floor": f"{floor}/{total_floors}",
            "seller_type": random.choice(seller_types),
            "url": f"https://www.cian.ru/sale/flat/{1000000 + i}/",
            "region": 1,
            "deal_type": "sale",
            "lat": 55.7558 + random.uniform(-0.1, 0.1),
            "lon": 37.6176 + random.uniform(-0.1, 0.1),
            "first_seen": (datetime.now() - timedelta(days=random.randint(0, 30))).isoformat(),
            "last_seen": datetime.now().isoformat(),
            "is_active": True,
            "price_per_sqm": round(price / area),
            "main_photo_url": f"https://cdn.cian.ru/images/photo_{i % 10}.jpg",
            "condition_score": random.randint(2, 5),
            "condition_label": random.choice(["Требует ремонта", "Хорошее", "Отличное", "Евроремонт"]),
            "ai_analysis": random.choice([
                "Квартира в хорошем состоянии, требует косметического ремонта",
                "Отличное состояние, современный ремонт",
                "Требует капитального ремонта, но хорошая планировка",
                "Евроремонт, готова к проживанию"
            ])
        }
        
        offers.append(offer)
    
    return offers

def create_demo_data():
    """Create demo CIAN data files."""
    
    LOGGER.info("🎭 Creating DEMO CIAN data...")
    
    # Generate offers
    offers = generate_realistic_cian_data(100)
    
    # Create logs directory
    Path("logs").mkdir(exist_ok=True)
    
    # Save comprehensive data
    demo_data = {
        "collection_info": {
            "type": "DEMO DATA",
            "created_at": datetime.now().isoformat(),
            "total_offers": len(offers),
            "note": "This is realistic demo data showing what real CIAN collection would look like"
        },
        "offers": offers
    }
    
    # Save to file
    output_file = "logs/demo_cian_data.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(demo_data, f, ensure_ascii=False, indent=2)
    
    LOGGER.info(f"💾 Saved {len(offers)} demo offers to: {output_file}")
    
    # Create metrics file
    metrics = {
        "start_time": datetime.now().timestamp(),
        "pages_scraped": 5,
        "offers_collected": len(offers),
        "captchas_solved": 0,
        "captcha_cost_usd": 0.0,
        "proxy_used_pages": 1,
        "no_proxy_pages": 4,
        "cookie_refreshes": 5,
        "blocks_encountered": 0,
        "errors": [],
        "elapsed_time": 45.5,
        "offers_per_minute": 132.0,
        "avg_cost_per_page": 0.0,
        "data_type": "DEMO"
    }
    
    metrics_file = "logs/demo_metrics.json"
    with open(metrics_file, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2)
    
    # Show sample data
    LOGGER.info(f"\n📋 SAMPLE DEMO OFFERS:")
    for i, offer in enumerate(offers[:5]):
        LOGGER.info(f"\n{i+1}. {offer['title']}")
        LOGGER.info(f"   💰 {offer['price']}")
        LOGGER.info(f"   📍 {offer['address']}")
        LOGGER.info(f"   🏠 {offer['area_total']} м² | {offer['floor']} | {offer['seller_type']}")
        LOGGER.info(f"   🤖 AI: {offer['condition_label']} ({offer['condition_score']}/5)")
    
    # Summary
    LOGGER.info(f"\n📊 DEMO DATA SUMMARY:")
    LOGGER.info(f"   ✅ Total offers: {len(offers)}")
    LOGGER.info(f"   ✅ Price range: {min(o['price_numeric'] for o in offers):,} - {max(o['price_numeric'] for o in offers):,} ₽")
    LOGGER.info(f"   ✅ Area range: {min(o['area_total'] for o in offers)} - {max(o['area_total'] for o in offers)} м²")
    LOGGER.info(f"   ✅ Rooms: {min(o['rooms'] for o in offers)} - {max(o['rooms'] for o in offers)}")
    LOGGER.info(f"   ✅ AI scores: {min(o['condition_score'] for o in offers)} - {max(o['condition_score'] for o in offers)}")
    
    return len(offers)

if __name__ == "__main__":
    count = create_demo_data()
    LOGGER.info(f"\n🎉 Created {count} realistic demo CIAN offers!")
    LOGGER.info("📁 Check logs/demo_cian_data.json to see what real collection would look like")

