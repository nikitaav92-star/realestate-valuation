"""
Parser for FSSP (Federal Bailiff Service) auctions.
Source: torgi.gov.ru and fssprus.ru
"""

import logging
import re
from datetime import datetime
from typing import AsyncGenerator, Optional
from urllib.parse import urljoin, urlencode

from ..base_parser import BaseAuctionParser
from ..models import AuctionLot, AuctionSource, AuctionStatus, PropertyType

logger = logging.getLogger(__name__)


class FSSPParser(BaseAuctionParser):
    """
    Parser for FSSP auctions from torgi.gov.ru.

    API endpoint: https://torgi.gov.ru/new/api/public/lotcards/search
    """

    source_type = AuctionSource.FSSP
    platform_name = "Торги России (ФССП)"
    base_url = "https://torgi.gov.ru"
    api_url = "https://torgi.gov.ru/new/api/public/lotcards/search"

    def __init__(self, **kwargs):
        super().__init__(use_browser=False, **kwargs)

    async def fetch_lots(
        self,
        city: Optional[str] = None,
        property_type: Optional[str] = None,
        max_pages: int = 10,
    ) -> AsyncGenerator[AuctionLot, None]:
        """
        Fetch lots from torgi.gov.ru API.
        """
        page = 0
        per_page = 50

        while page < max_pages:
            try:
                # Build query params
                params = {
                    "dynSubjRF": "77",  # Moscow region code
                    "catCode": "9",     # Real estate category
                    "lotStatus": "PUBLISHED,APPLICATIONS_COLLECTING",
                    "sort": "firstVersionPublicationDate,desc",
                    "size": per_page,
                    "page": page,
                }

                if city and city.lower() == "москва":
                    params["dynSubjRF"] = "77"
                elif city and city.lower() == "санкт-петербург":
                    params["dynSubjRF"] = "78"

                # Property type filter
                # 9.1 - Квартиры, 9.2 - Комнаты, 9.3 - Дома
                if property_type == "apartment":
                    params["catCode"] = "9.1"
                elif property_type == "room":
                    params["catCode"] = "9.2"
                elif property_type == "house":
                    params["catCode"] = "9.3"

                url = f"{self.api_url}?{urlencode(params)}"
                logger.debug(f"Fetching: {url}")

                response = await self.http_get(url)
                response.raise_for_status()

                data = response.json()
                content = data.get("content", [])

                if not content:
                    logger.info(f"No more lots on page {page}")
                    break

                logger.info(f"Page {page}: Found {len(content)} lots")

                for item in content:
                    try:
                        lot = self._parse_lot(item)
                        if lot:
                            yield lot
                    except Exception as e:
                        logger.error(f"Error parsing lot: {e}")
                        continue

                # Check if more pages
                total_pages = data.get("totalPages", 0)
                if page >= total_pages - 1:
                    break

                page += 1

            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                break

    def _parse_lot(self, item: dict) -> Optional[AuctionLot]:
        """Parse single lot from API response."""
        try:
            lot_id = item.get("id")
            if not lot_id:
                return None

            # Extract basic info
            lot_number = item.get("lotNumber")
            description = item.get("lotDescription", "")
            lot_name = item.get("lotName", "")

            # Determine property type
            cat_code = item.get("catCode", "")
            prop_type = PropertyType.APARTMENT
            if "комнат" in lot_name.lower() or cat_code == "9.2":
                prop_type = PropertyType.ROOM
            elif "дом" in lot_name.lower() or cat_code == "9.3":
                prop_type = PropertyType.HOUSE

            # Skip shares
            if "доля" in lot_name.lower() or "доля" in description.lower():
                logger.debug(f"Skipping share lot: {lot_id}")
                return None

            # Extract address
            address_info = item.get("estateAddress", {})
            address = address_info.get("fullAddress", "")
            region = address_info.get("regionName", "")
            city = address_info.get("cityName", "")

            # Extract characteristics
            chars = item.get("characteristics", {})
            area_total = self._extract_area(chars.get("totalArea"))
            rooms = self._extract_rooms(lot_name, description)
            floor = self._extract_floor(chars.get("floor"))
            total_floors = self._extract_floor(chars.get("floors"))

            # Prices
            initial_price = item.get("startPrice")
            current_price = item.get("priceMin") or initial_price
            step_price = item.get("priceStep")
            deposit = item.get("deposit")

            # Dates
            auction_date = self._parse_date(item.get("biddingStartTime"))
            application_deadline = self._parse_date(item.get("biddingEndTime"))

            # Status
            status_str = item.get("lotStatus", "")
            status = AuctionStatus.ANNOUNCED
            if status_str == "APPLICATIONS_COLLECTING":
                status = AuctionStatus.ACTIVE
            elif status_str == "COMPLETED":
                status = AuctionStatus.COMPLETED
            elif status_str == "CANCELLED":
                status = AuctionStatus.CANCELLED

            # Source URL
            source_url = f"{self.base_url}/new/public/lots/lot/{lot_id}"

            # Organizer
            org_info = item.get("organizerInfo", {})
            organizer_name = org_info.get("organizerFullName")
            organizer_inn = org_info.get("organizerInn")

            # Photos
            photos = []
            for doc in item.get("lotImages", []):
                if doc.get("url"):
                    photos.append(doc["url"])

            return AuctionLot(
                external_id=str(lot_id),
                source_type=self.source_type,
                source_url=source_url,
                lot_number=lot_number,
                property_type=prop_type,
                title=lot_name,
                description=description,
                region=region,
                city=city or "Москва",
                address=address,
                area_total=area_total,
                rooms=rooms,
                floor=floor,
                total_floors=total_floors,
                initial_price=initial_price,
                current_price=current_price,
                step_price=step_price,
                deposit_amount=deposit,
                auction_date=auction_date,
                application_deadline=application_deadline,
                status=status,
                organizer_name=organizer_name,
                organizer_inn=organizer_inn,
                photos=photos,
                raw_data=item,
            )

        except Exception as e:
            logger.error(f"Error parsing lot: {e}")
            return None

    def _extract_area(self, value) -> Optional[float]:
        """Extract area from various formats."""
        if not value:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            match = re.search(r'[\d,.]+', value.replace(',', '.'))
            if match:
                return float(match.group())
        return None

    def _extract_rooms(self, title: str, description: str) -> Optional[int]:
        """Extract rooms count from text."""
        text = f"{title} {description}".lower()

        patterns = [
            r'(\d+)\s*-?\s*комн',
            r'(\d+)\s*к[.,\s]',
            r'однокомн',
            r'двухкомн',
            r'трехкомн',
            r'четырехкомн',
        ]

        for pattern in patterns[:2]:
            match = re.search(pattern, text)
            if match:
                return int(match.group(1))

        if 'однокомн' in text or 'студи' in text:
            return 1
        if 'двухкомн' in text:
            return 2
        if 'трехкомн' in text or 'трёхкомн' in text:
            return 3
        if 'четырехкомн' in text or 'четырёхкомн' in text:
            return 4

        return None

    def _extract_floor(self, value) -> Optional[int]:
        """Extract floor number."""
        if not value:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            match = re.search(r'\d+', value)
            if match:
                return int(match.group())
        return None

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date from API format."""
        if not date_str:
            return None
        try:
            # Try ISO format
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except Exception:
            try:
                # Try common formats
                for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%d.%m.%Y']:
                    try:
                        return datetime.strptime(date_str[:19], fmt)
                    except ValueError:
                        continue
            except Exception:
                pass
        return None


# Alias for import
Parser = FSSPParser
