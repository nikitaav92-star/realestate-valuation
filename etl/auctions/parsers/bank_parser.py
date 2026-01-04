"""
Parser for bank pledge (collateral) sales.
Sources: Sberbank, VTB, Alfabank pledge showcases.
"""

import logging
import re
from datetime import datetime
from typing import AsyncGenerator, Optional

from ..base_parser import BaseAuctionParser
from ..models import AuctionLot, AuctionSource, AuctionStatus, PropertyType

logger = logging.getLogger(__name__)


class BankPledgeParser(BaseAuctionParser):
    """
    Parser for bank collateral sales.

    Aggregates from multiple bank sources:
    - Sberbank Vitrina Zalogov
    - VTB Zalog
    - Alfabank Collateral
    """

    source_type = AuctionSource.BANK_PLEDGE
    platform_name = "Залоговое имущество банков"
    base_url = "https://www.sberbank.ru"  # Primary source

    # Bank sources configuration
    BANK_SOURCES = [
        {
            "name": "Sberbank",
            "url": "https://www.sberbank.ru/ru/person/credits/money/zalog",
            "api_url": "https://www.sberbank.ru/proxy/services/zalog-services/api/lots",
        },
        {
            "name": "VTB",
            "url": "https://www.vtb.ru/personal/zalog/",
            "api_url": None,  # No public API, needs browser
        },
        {
            "name": "Alfabank",
            "url": "https://alfabank.ru/personal/loans/collateral/",
            "api_url": None,
        },
    ]

    def __init__(self, **kwargs):
        super().__init__(use_browser=False, **kwargs)

    async def fetch_lots(
        self,
        city: Optional[str] = None,
        property_type: Optional[str] = None,
        max_pages: int = 10,
    ) -> AsyncGenerator[AuctionLot, None]:
        """
        Fetch lots from bank pledge showcases.
        """
        # Try Sberbank API first (they have public API)
        async for lot in self._fetch_sberbank(city, max_pages):
            yield lot

        # Other banks require browser, skip for now
        # TODO: Add VTB and Alfabank parsers with Playwright

    async def _fetch_sberbank(
        self,
        city: Optional[str] = None,
        max_pages: int = 10,
    ) -> AsyncGenerator[AuctionLot, None]:
        """
        Fetch from Sberbank Zalog API.
        """
        base_api = "https://www.sberbank.ru/proxy/services/zalog-services/api/lots"

        for page in range(max_pages):
            try:
                params = {
                    "page": page,
                    "size": 50,
                    "category": "REAL_ESTATE",
                    "status": "ACTIVE",
                }

                if city and city.lower() == "москва":
                    params["region"] = "77"
                elif city and city.lower() == "санкт-петербург":
                    params["region"] = "78"

                url = f"{base_api}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
                logger.debug(f"Fetching Sberbank: {url}")

                response = await self.http_get(url)

                # Sberbank might block, handle gracefully
                if response.status_code != 200:
                    logger.warning(f"Sberbank API returned {response.status_code}")
                    break

                data = response.json()
                content = data.get("content", data.get("items", []))

                if not content:
                    break

                logger.info(f"Sberbank page {page}: Found {len(content)} lots")

                for item in content:
                    try:
                        lot = self._parse_sberbank_lot(item)
                        if lot and not lot.is_share():
                            yield lot
                    except Exception as e:
                        logger.error(f"Error parsing Sberbank lot: {e}")
                        continue

                # Check pagination
                total_pages = data.get("totalPages", 1)
                if page >= total_pages - 1:
                    break

            except Exception as e:
                logger.error(f"Error fetching Sberbank page {page}: {e}")
                break

    def _parse_sberbank_lot(self, item: dict) -> Optional[AuctionLot]:
        """Parse Sberbank lot from API response."""
        try:
            lot_id = item.get("id") or item.get("lotId")
            if not lot_id:
                return None

            title = item.get("name", item.get("title", ""))

            # Skip shares
            if "доля" in title.lower():
                return None

            description = item.get("description", "")

            # Address
            address_obj = item.get("address", {})
            if isinstance(address_obj, str):
                address = address_obj
            else:
                address = address_obj.get("fullAddress", "")

            region = item.get("region", {}).get("name", "")
            city = item.get("city", {}).get("name", "Москва")

            # Property type
            prop_type = PropertyType.APARTMENT
            category = item.get("category", "").lower()
            if "комнат" in title.lower() or category == "room":
                prop_type = PropertyType.ROOM
            elif "дом" in title.lower() or category == "house":
                prop_type = PropertyType.HOUSE
            elif "участ" in title.lower() or category == "land":
                prop_type = PropertyType.LAND
            elif "коммерч" in title.lower() or category == "commercial":
                prop_type = PropertyType.COMMERCIAL

            # Only collect apartments, rooms, houses
            if prop_type not in [PropertyType.APARTMENT, PropertyType.ROOM, PropertyType.HOUSE]:
                return None

            # Characteristics
            chars = item.get("characteristics", {})
            area_total = chars.get("totalArea") or chars.get("area")
            rooms = chars.get("rooms")
            floor = chars.get("floor")
            total_floors = chars.get("floors") or chars.get("totalFloors")

            # Price
            price = item.get("price") or item.get("startPrice")
            discount_price = item.get("discountPrice")

            # Use discount price if available
            current_price = discount_price or price

            # Calculate discount
            discount_percent = None
            if price and discount_price and price > discount_price:
                discount_percent = ((price - discount_price) / price) * 100

            # Photos
            photos = []
            for img in item.get("images", item.get("photos", [])):
                if isinstance(img, str):
                    photos.append(img)
                elif isinstance(img, dict):
                    photos.append(img.get("url", img.get("src", "")))

            # Source URL
            source_url = f"https://www.sberbank.ru/ru/person/credits/money/zalog/{lot_id}"

            return AuctionLot(
                external_id=str(lot_id),
                source_type=self.source_type,
                source_url=source_url,
                property_type=prop_type,
                title=title,
                description=description,
                region=region,
                city=city,
                address=address,
                area_total=area_total,
                rooms=rooms,
                floor=floor,
                total_floors=total_floors,
                initial_price=price,
                current_price=current_price,
                status=AuctionStatus.ACTIVE,
                bank_name="Sberbank",
                photos=photos,
                raw_data=item,
            )

        except Exception as e:
            logger.error(f"Error parsing Sberbank lot: {e}")
            return None


# Alias for import
Parser = BankPledgeParser
