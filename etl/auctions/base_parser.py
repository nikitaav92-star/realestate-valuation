"""
Base class for auction parsers.
All source-specific parsers inherit from this.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import AsyncGenerator, Optional

import httpx
from playwright.async_api import async_playwright, Browser, Page

from .models import AuctionLot, AuctionSource

logger = logging.getLogger(__name__)


class BaseAuctionParser(ABC):
    """
    Base class for auction lot parsers.

    Subclasses must implement:
    - source_type: AuctionSource
    - platform_name: str
    - base_url: str
    - fetch_lots(): AsyncGenerator of AuctionLot
    """

    source_type: AuctionSource
    platform_name: str
    base_url: str

    def __init__(
        self,
        use_browser: bool = False,
        proxy: Optional[str] = None,
        headless: bool = True,
    ):
        self.use_browser = use_browser
        self.proxy = proxy
        self.headless = headless
        self._browser: Optional[Browser] = None
        self._http_client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    async def setup(self):
        """Initialize resources."""
        if self.use_browser:
            playwright = await async_playwright().start()
            launch_options = {"headless": self.headless}
            if self.proxy:
                launch_options["proxy"] = {"server": self.proxy}
            self._browser = await playwright.chromium.launch(**launch_options)
            logger.info(f"Browser started for {self.platform_name}")
        else:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
            logger.info(f"HTTP client started for {self.platform_name}")

    async def cleanup(self):
        """Cleanup resources."""
        if self._browser:
            await self._browser.close()
            logger.info(f"Browser closed for {self.platform_name}")
        if self._http_client:
            await self._http_client.aclose()
            logger.info(f"HTTP client closed for {self.platform_name}")

    async def get_page(self) -> Page:
        """Get a new browser page."""
        if not self._browser:
            raise RuntimeError("Browser not initialized. Call setup() first or use use_browser=True")
        context = await self._browser.new_context()
        return await context.new_page()

    async def http_get(self, url: str, **kwargs) -> httpx.Response:
        """Make HTTP GET request."""
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized. Call setup() first")
        return await self._http_client.get(url, **kwargs)

    async def http_post(self, url: str, **kwargs) -> httpx.Response:
        """Make HTTP POST request."""
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized. Call setup() first")
        return await self._http_client.post(url, **kwargs)

    @abstractmethod
    async def fetch_lots(
        self,
        city: Optional[str] = None,
        property_type: Optional[str] = None,
        max_pages: int = 10,
    ) -> AsyncGenerator[AuctionLot, None]:
        """
        Fetch auction lots from source.

        Args:
            city: Filter by city (e.g., "Москва")
            property_type: Filter by property type
            max_pages: Maximum pages to fetch

        Yields:
            AuctionLot objects
        """
        pass

    def filter_lot(self, lot: AuctionLot) -> bool:
        """
        Filter lot based on requirements.
        Returns True if lot should be collected.
        """
        # Skip shares (доли)
        if lot.is_share():
            logger.debug(f"Skipping share lot: {lot.external_id}")
            return False

        # Only real estate
        if not lot.is_valid_for_collection():
            logger.debug(f"Skipping non-real-estate lot: {lot.external_id}")
            return False

        return True

    async def collect(
        self,
        city: Optional[str] = None,
        property_type: Optional[str] = None,
        max_pages: int = 10,
    ) -> list[AuctionLot]:
        """
        Collect and filter lots.

        Returns:
            List of valid AuctionLot objects
        """
        lots = []
        skipped = 0

        async for lot in self.fetch_lots(city, property_type, max_pages):
            if self.filter_lot(lot):
                lots.append(lot)
            else:
                skipped += 1

        logger.info(
            f"{self.platform_name}: Collected {len(lots)} lots, skipped {skipped}"
        )
        return lots


class MockAuctionParser(BaseAuctionParser):
    """Mock parser for testing."""

    source_type = AuctionSource.FSSP
    platform_name = "Mock Parser"
    base_url = "https://example.com"

    async def fetch_lots(
        self,
        city: Optional[str] = None,
        property_type: Optional[str] = None,
        max_pages: int = 10,
    ) -> AsyncGenerator[AuctionLot, None]:
        """Generate mock lots for testing."""
        for i in range(5):
            yield AuctionLot(
                external_id=f"mock-{i}",
                source_type=self.source_type,
                source_url=f"{self.base_url}/lot/{i}",
                lot_number=f"LOT-{i:04d}",
                title=f"Квартира {i+1}-комнатная",
                address=f"г. Москва, ул. Тестовая, д. {i+1}",
                city="Москва",
                area_total=50 + i * 10,
                rooms=i + 1,
                floor=i + 1,
                total_floors=10,
                initial_price=5_000_000 + i * 1_000_000,
                current_price=4_500_000 + i * 900_000,
                auction_date=datetime.now(),
            )
