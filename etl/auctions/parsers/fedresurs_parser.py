"""
Parser for bankruptcy auctions from Fedresurs (EFRSB).
Source: bankrot.fedresurs.ru
"""

import logging
import re
from datetime import datetime
from typing import AsyncGenerator, Optional

from ..base_parser import BaseAuctionParser
from ..models import AuctionLot, AuctionSource, AuctionStatus, PropertyType

logger = logging.getLogger(__name__)


class FedresursParser(BaseAuctionParser):
    """
    Parser for bankruptcy auctions from bankrot.fedresurs.ru.

    Uses Playwright for scraping as site has anti-bot protection.
    """

    source_type = AuctionSource.BANKRUPT
    platform_name = "Федресурс (Банкротство)"
    base_url = "https://bankrot.fedresurs.ru"

    def __init__(self, **kwargs):
        # Fedresurs needs browser due to heavy JS
        super().__init__(use_browser=True, **kwargs)

    async def fetch_lots(
        self,
        city: Optional[str] = None,
        property_type: Optional[str] = None,
        max_pages: int = 10,
    ) -> AsyncGenerator[AuctionLot, None]:
        """
        Fetch bankruptcy lots from Fedresurs.
        """
        page = await self.get_page()

        try:
            # Navigate to real estate lots
            search_url = f"{self.base_url}/TradesSearch.aspx"
            logger.info(f"Navigating to {search_url}")

            await page.goto(search_url, wait_until="networkidle", timeout=60000)

            # Wait for page load
            await page.wait_for_timeout(2000)

            # Set filters
            # Select "Недвижимое имущество" category
            category_selector = 'select[name*="PropertyType"], #PropertyType'
            try:
                await page.select_option(category_selector, label="Недвижимое имущество")
            except Exception as e:
                logger.warning(f"Could not set category filter: {e}")

            # Set region (Moscow = 77)
            if city and city.lower() == "москва":
                region_selector = 'select[name*="Region"], #Region'
                try:
                    await page.select_option(region_selector, value="77")
                except Exception as e:
                    logger.warning(f"Could not set region filter: {e}")

            # Click search
            search_button = 'input[type="submit"][value*="Поиск"], button:has-text("Поиск")'
            try:
                await page.click(search_button)
                await page.wait_for_load_state("networkidle")
            except Exception as e:
                logger.warning(f"Could not click search: {e}")

            # Parse results
            for page_num in range(max_pages):
                logger.info(f"Parsing page {page_num + 1}")

                # Find lot cards
                lot_cards = await page.query_selector_all('.lot-card, .trade-item, tr.lot-row')

                if not lot_cards:
                    logger.info("No more lots found")
                    break

                for card in lot_cards:
                    try:
                        lot = await self._parse_lot_card(page, card)
                        if lot:
                            yield lot
                    except Exception as e:
                        logger.error(f"Error parsing lot card: {e}")
                        continue

                # Try to go to next page
                next_button = await page.query_selector('a.next-page, .pagination a:has-text("»")')
                if next_button:
                    await next_button.click()
                    await page.wait_for_load_state("networkidle")
                    await page.wait_for_timeout(1000)
                else:
                    break

        except Exception as e:
            logger.error(f"Error fetching lots: {e}")

        finally:
            await page.close()

    async def _parse_lot_card(self, page, card) -> Optional[AuctionLot]:
        """Parse single lot card element."""
        try:
            # Try to get lot ID from link
            link = await card.query_selector('a[href*="LotInfo"], a[href*="Trade"]')
            if not link:
                return None

            href = await link.get_attribute('href')
            lot_id = self._extract_id_from_url(href)
            if not lot_id:
                return None

            # Get title
            title_el = await card.query_selector('.lot-title, .title, h3')
            title = await title_el.inner_text() if title_el else ""

            # Skip shares
            if "доля" in title.lower():
                return None

            # Get description
            desc_el = await card.query_selector('.description, .lot-desc')
            description = await desc_el.inner_text() if desc_el else ""

            # Get price
            price_el = await card.query_selector('.price, .lot-price, .start-price')
            price_text = await price_el.inner_text() if price_el else ""
            price = self._parse_price(price_text)

            # Get address
            addr_el = await card.query_selector('.address, .location')
            address = await addr_el.inner_text() if addr_el else ""

            # Get debtor info
            debtor_el = await card.query_selector('.debtor, .debtor-name')
            debtor = await debtor_el.inner_text() if debtor_el else None

            # Get auction date
            date_el = await card.query_selector('.date, .auction-date')
            date_text = await date_el.inner_text() if date_el else ""
            auction_date = self._parse_date(date_text)

            # Determine property type
            prop_type = PropertyType.APARTMENT
            if "комнат" in title.lower():
                prop_type = PropertyType.ROOM
            elif "дом" in title.lower():
                prop_type = PropertyType.HOUSE

            # Extract characteristics from title/description
            text = f"{title} {description}"
            area = self._extract_area(text)
            rooms = self._extract_rooms(text)

            source_url = f"{self.base_url}{href}" if href.startswith('/') else href

            return AuctionLot(
                external_id=lot_id,
                source_type=self.source_type,
                source_url=source_url,
                property_type=prop_type,
                title=title.strip(),
                description=description.strip(),
                address=address.strip(),
                city="Москва",  # Default for now
                area_total=area,
                rooms=rooms,
                initial_price=price,
                current_price=price,
                auction_date=auction_date,
                status=AuctionStatus.ANNOUNCED,
                debtor_name=debtor,
            )

        except Exception as e:
            logger.error(f"Error parsing lot card: {e}")
            return None

    def _extract_id_from_url(self, url: str) -> Optional[str]:
        """Extract lot ID from URL."""
        if not url:
            return None
        # Try various patterns
        patterns = [
            r'id=(\d+)',
            r'LotId=(\d+)',
            r'/(\d+)$',
            r'Trade/(\d+)',
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
        # Remove currency and spaces
        clean = re.sub(r'[^\d,.]', '', text.replace(',', '.'))
        try:
            return float(clean)
        except ValueError:
            return None

    def _parse_date(self, text: str) -> Optional[datetime]:
        """Parse date from text."""
        if not text:
            return None
        # Common patterns
        patterns = [
            r'(\d{2})\.(\d{2})\.(\d{4})',
            r'(\d{4})-(\d{2})-(\d{2})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    groups = match.groups()
                    if len(groups[0]) == 4:  # YYYY-MM-DD
                        return datetime(int(groups[0]), int(groups[1]), int(groups[2]))
                    else:  # DD.MM.YYYY
                        return datetime(int(groups[2]), int(groups[1]), int(groups[0]))
                except ValueError:
                    continue
        return None

    def _extract_area(self, text: str) -> Optional[float]:
        """Extract area from text."""
        patterns = [
            r'(\d+[.,]?\d*)\s*(?:кв\.?\s*м|м2|м²)',
            r'площад\w*\s*(\d+[.,]?\d*)',
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
            r'(\d+)\s*-?\s*комн',
            r'(\d+)\s*к[.,\s]',
        ]
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                return int(match.group(1))

        if 'однокомн' in text_lower or 'студи' in text_lower:
            return 1
        if 'двухкомн' in text_lower:
            return 2
        if 'трехкомн' in text_lower or 'трёхкомн' in text_lower:
            return 3

        return None


# Alias for import
Parser = FedresursParser
