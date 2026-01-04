"""
Parser for DGI Moscow (Department of City Property) auctions.
Sources: investmoscow.ru, mos.ru/tender
"""

import logging
import re
from datetime import datetime
from typing import AsyncGenerator, Optional

from ..base_parser import BaseAuctionParser
from ..models import AuctionLot, AuctionSource, AuctionStatus, PropertyType

logger = logging.getLogger(__name__)


class DGIMoscowParser(BaseAuctionParser):
    """
    Parser for Moscow city property auctions.

    Sources:
    - investmoscow.ru - Investment portal
    - mos.ru/tender - City tenders
    """

    source_type = AuctionSource.DGI_MOSCOW
    platform_name = "ДГИ Москвы"
    base_url = "https://investmoscow.ru"

    def __init__(self, **kwargs):
        super().__init__(use_browser=True, **kwargs)

    async def fetch_lots(
        self,
        city: Optional[str] = None,
        property_type: Optional[str] = None,
        max_pages: int = 10,
    ) -> AsyncGenerator[AuctionLot, None]:
        """
        Fetch lots from investmoscow.ru and mos.ru
        """
        # investmoscow.ru
        async for lot in self._fetch_investmoscow(max_pages):
            yield lot

    async def _fetch_investmoscow(
        self,
        max_pages: int = 10,
    ) -> AsyncGenerator[AuctionLot, None]:
        """
        Fetch from investmoscow.ru
        """
        page = await self.get_page()

        try:
            # Navigate to real estate auctions
            url = f"{self.base_url}/tenders/land-and-real-estate/"
            logger.info(f"Navigating to {url}")

            await page.goto(url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)

            for page_num in range(max_pages):
                logger.info(f"Parsing page {page_num + 1}")

                # Find tender cards
                cards = await page.query_selector_all('.tender-card, .lot-item, .auction-item')

                if not cards:
                    # Try alternative selectors
                    cards = await page.query_selector_all('[class*="tender"], [class*="lot"]')

                if not cards:
                    logger.info("No tender cards found")
                    break

                logger.info(f"Found {len(cards)} tender cards")

                for card in cards:
                    try:
                        lot = await self._parse_tender_card(page, card)
                        if lot:
                            yield lot
                    except Exception as e:
                        logger.error(f"Error parsing tender card: {e}")
                        continue

                # Pagination
                next_btn = await page.query_selector('a.next, .pagination__next, button:has-text("Далее")')
                if next_btn:
                    is_disabled = await next_btn.get_attribute('disabled')
                    if not is_disabled:
                        await next_btn.click()
                        await page.wait_for_load_state("networkidle")
                        await page.wait_for_timeout(2000)
                    else:
                        break
                else:
                    break

        except Exception as e:
            logger.error(f"Error fetching investmoscow: {e}")

        finally:
            await page.close()

    async def _parse_tender_card(self, page, card) -> Optional[AuctionLot]:
        """Parse single tender card."""
        try:
            # Get link and ID
            link = await card.query_selector('a[href*="tender"], a[href*="lot"]')
            if not link:
                return None

            href = await link.get_attribute('href')
            lot_id = self._extract_id(href)
            if not lot_id:
                return None

            # Title
            title_el = await card.query_selector('.title, h3, h4, .tender-title')
            title = await title_el.inner_text() if title_el else ""
            title = title.strip()

            # Skip non-residential and shares
            title_lower = title.lower()
            if "доля" in title_lower:
                return None
            if "земел" in title_lower and "квартир" not in title_lower:
                return None  # Skip pure land lots

            # Determine if it's residential
            is_residential = any(kw in title_lower for kw in [
                'квартир', 'комнат', 'жил', 'дом', 'апартамент'
            ])

            if not is_residential:
                # Check description
                desc_el = await card.query_selector('.description, .text')
                if desc_el:
                    desc = await desc_el.inner_text()
                    is_residential = any(kw in desc.lower() for kw in [
                        'квартир', 'комнат', 'жил'
                    ])

            if not is_residential:
                return None

            # Property type
            prop_type = PropertyType.APARTMENT
            if "комнат" in title_lower and "квартир" not in title_lower:
                prop_type = PropertyType.ROOM
            elif "дом" in title_lower:
                prop_type = PropertyType.HOUSE

            # Address
            addr_el = await card.query_selector('.address, .location')
            address = await addr_el.inner_text() if addr_el else ""

            # Price
            price_el = await card.query_selector('.price, .sum, .cost')
            price_text = await price_el.inner_text() if price_el else ""
            price = self._parse_price(price_text)

            # Date
            date_el = await card.query_selector('.date, .deadline')
            date_text = await date_el.inner_text() if date_el else ""
            auction_date = self._parse_date(date_text)

            # Area
            area = self._extract_area(title)

            # Rooms
            rooms = self._extract_rooms(title)

            # Source URL
            source_url = href if href.startswith('http') else f"{self.base_url}{href}"

            return AuctionLot(
                external_id=lot_id,
                source_type=self.source_type,
                source_url=source_url,
                property_type=prop_type,
                title=title,
                address=address.strip(),
                city="Москва",
                area_total=area,
                rooms=rooms,
                initial_price=price,
                current_price=price,
                auction_date=auction_date,
                status=AuctionStatus.ANNOUNCED,
                organizer_name="ДГИ города Москвы",
            )

        except Exception as e:
            logger.error(f"Error parsing tender card: {e}")
            return None

    def _extract_id(self, url: str) -> Optional[str]:
        """Extract lot ID from URL."""
        if not url:
            return None
        patterns = [
            r'/(\d+)/?$',
            r'id[=:](\d+)',
            r'tender/(\d+)',
            r'lot/(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _parse_price(self, text: str) -> Optional[float]:
        """Parse price from text."""
        if not text:
            return None
        clean = re.sub(r'[^\d,.]', '', text.replace(',', '.').replace(' ', ''))
        try:
            return float(clean)
        except ValueError:
            return None

    def _parse_date(self, text: str) -> Optional[datetime]:
        """Parse date from text."""
        if not text:
            return None
        patterns = [
            (r'(\d{2})\.(\d{2})\.(\d{4})', lambda m: datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))),
            (r'(\d{4})-(\d{2})-(\d{2})', lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))),
        ]
        for pattern, parser in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return parser(match)
                except ValueError:
                    continue
        return None

    def _extract_area(self, text: str) -> Optional[float]:
        """Extract area from text."""
        patterns = [
            r'(\d+[.,]?\d*)\s*(?:кв\.?\s*м|м2|м²)',
            r'площад\w*[:\s]+(\d+[.,]?\d*)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                try:
                    return float(match.group(1).replace(',', '.'))
                except ValueError:
                    continue
        return None

    def _extract_rooms(self, text: str) -> Optional[int]:
        """Extract rooms count from text."""
        text_lower = text.lower()

        patterns = [
            (r'(\d+)\s*-?\s*комн', lambda m: int(m.group(1))),
        ]

        for pattern, parser in patterns:
            match = re.search(pattern, text_lower)
            if match:
                return parser(match)

        if 'однокомн' in text_lower:
            return 1
        if 'двухкомн' in text_lower:
            return 2
        if 'трехкомн' in text_lower or 'трёхкомн' in text_lower:
            return 3

        return None


# Alias for import
Parser = DGIMoscowParser
