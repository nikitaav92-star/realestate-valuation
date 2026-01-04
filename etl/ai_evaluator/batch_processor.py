"""Batch processing for cost-effective AI analysis."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from .photo_analyzer import PhotoAnalyzer, ConditionRating, AIProvider

LOGGER = logging.getLogger(__name__)


@dataclass
class BatchStats:
    """Statistics for batch processing."""
    
    total_analyzed: int = 0
    total_cost_usd: float = 0.0
    total_time_sec: float = 0.0
    errors: List[str] = field(default_factory=list)
    
    def avg_cost(self) -> float:
        return self.total_cost_usd / self.total_analyzed if self.total_analyzed > 0 else 0
    
    def avg_time(self) -> float:
        return self.total_time_sec / self.total_analyzed if self.total_analyzed > 0 else 0


class BatchProcessor:
    """Process photos in batches for cost efficiency."""
    
    def __init__(
        self,
        provider: AIProvider = AIProvider.OPENAI,
        *,
        batch_size: int = 50,
        concurrency: int = 10,
        detail: str = "low",
    ):
        """Initialize batch processor.
        
        Parameters
        ----------
        provider : AIProvider
            AI provider to use
        batch_size : int
            Number of listings to process per batch
        concurrency : int
            Number of parallel API calls
        detail : str
            Detail level for images ("low" or "high")
        """
        self.analyzer = PhotoAnalyzer(provider)
        self.batch_size = batch_size
        self.concurrency = concurrency
        self.detail = detail
        self.stats = BatchStats()
    
    async def process_listings(
        self,
        listings_with_photos: List[tuple[int, str]],
        *,
        progress_callback: Optional[callable] = None,
    ) -> BatchStats:
        """Process multiple listings with photos.
        
        Parameters
        ----------
        listings_with_photos : list
            List of (listing_id, photo_url) tuples
        progress_callback : callable, optional
            Callback function(current, total, stats)
            
        Returns
        -------
        BatchStats
            Processing statistics
        """
        total = len(listings_with_photos)
        LOGGER.info(f"Starting batch processing: {total} listings")
        
        # Process in batches
        for batch_start in range(0, total, self.batch_size):
            batch_end = min(batch_start + self.batch_size, total)
            batch = listings_with_photos[batch_start:batch_end]
            
            LOGGER.info(
                f"Processing batch {batch_start // self.batch_size + 1}: "
                f"listings {batch_start + 1}-{batch_end}"
            )
            
            # Process batch with concurrency limit
            await self._process_batch(batch)
            
            # Progress callback
            if progress_callback:
                progress_callback(batch_end, total, self.stats)
            
            # Log progress
            LOGGER.info(
                f"Progress: {self.stats.total_analyzed}/{total} "
                f"(${self.stats.total_cost_usd:.2f}, "
                f"{self.stats.total_time_sec:.0f}s)"
            )
            
            # Rate limit between batches
            if batch_end < total:
                await asyncio.sleep(1)
        
        LOGGER.info(
            f"Batch processing complete: {self.stats.total_analyzed} analyzed, "
            f"${self.stats.total_cost_usd:.2f} total cost"
        )
        
        return self.stats
    
    async def _process_batch(self, batch: List[tuple[int, str]]) -> None:
        """Process a single batch with concurrency limit."""
        semaphore = asyncio.Semaphore(self.concurrency)
        
        async def analyze_one(listing_id: int, photo_url: str):
            async with semaphore:
                try:
                    # Run in thread pool (sync API calls)
                    rating = await asyncio.to_thread(
                        self.analyzer.analyze_condition,
                        listing_id,
                        photo_url,
                        detail=self.detail,
                    )
                    
                    # Update stats
                    self.stats.total_analyzed += 1
                    self.stats.total_cost_usd += rating.cost_usd
                    self.stats.total_time_sec += rating.processing_time_sec
                    
                    return rating
                    
                except Exception as e:
                    error_msg = f"Listing {listing_id}: {e}"
                    self.stats.errors.append(error_msg)
                    LOGGER.error(error_msg)
                    return None
        
        # Process batch in parallel
        tasks = [analyze_one(lid, url) for lid, url in batch]
        await asyncio.gather(*tasks)

