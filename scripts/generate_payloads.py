#!/usr/bin/env python3
"""Generate payload files for CIAN parser with extended filters."""

import os
from pathlib import Path

PAYLOADS_DIR = Path("/home/ubuntu/realestate/etl/collector_cian/payloads/deep")

# Room types configuration
# object_type: 1=1к, 2=2к, 3=3к, 4=4к, 5=5к+, 7=студия, 9=свободная планировка
ROOM_TYPES = {
    "1kk": {"room": [1], "object_type": [1]},
    "2kk": {"room": [2], "object_type": [2]},
    "3kk": {"room": [3], "object_type": [3]},
    "4kk": {"room": [4], "object_type": [4]},
    "5kk": {"room": [5, 6], "object_type": [5]},  # 5+ rooms
    "studio": {"room": [9], "object_type": [7]},  # Studio
    "free": {"room": [7], "object_type": [9]},    # Free layout
}

# Price range: 5M to 100M with 1M step
PRICE_MIN = 5_000_000
PRICE_MAX = 100_000_000
PRICE_STEP = 1_000_000

# Area range: 10-200 m²
AREA_MIN = 10
AREA_MAX = 200

PAYLOAD_TEMPLATE = """jsonQuery:
  region:
    type: terms
    value: [1]
  engine_version:
    type: term
    value: 2
  deal_type:
    type: term
    value: sale
  offer_type:
    type: term
    value: flat
  building_status:
    type: term
    value: secondary
  object_type:
    type: terms
    value: {object_type}
  is_apartments:
    type: term
    value: 0
  is_share:
    type: term
    value: false
  is_first_floor:
    type: term
    value: false
  price:
    type: range
    value:
      gte: {price_min}
      lte: {price_max}
  total_area:
    type: range
    value:
      gte: {area_min}
      lte: {area_max}
  room:
    type: terms
    value: {room}
limit: 28
sort:
  type: term
  value: price_object_order_asc
"""

def main():
    PAYLOADS_DIR.mkdir(parents=True, exist_ok=True)

    count = 0
    for room_type, config in ROOM_TYPES.items():
        price = PRICE_MIN
        while price < PRICE_MAX:
            price_max = price + PRICE_STEP

            payload = PAYLOAD_TEMPLATE.format(
                object_type=config["object_type"],
                room=config["room"],
                price_min=price,
                price_max=price_max,
                area_min=AREA_MIN,
                area_max=AREA_MAX,
            )

            filename = f"{room_type}_{price}_{price_max}.yaml"
            filepath = PAYLOADS_DIR / filename
            filepath.write_text(payload)
            count += 1

            price = price_max

    print(f"Created {count} payload files")
    print(f"Room types: {list(ROOM_TYPES.keys())}")
    print(f"Price range: {PRICE_MIN/1e6:.0f}M - {PRICE_MAX/1e6:.0f}M (step {PRICE_STEP/1e6:.0f}M)")
    print(f"Area range: {AREA_MIN} - {AREA_MAX} m²")

if __name__ == "__main__":
    main()
