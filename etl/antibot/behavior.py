"""Human behavior simulation for browser automation.

Provides realistic mouse movements, scrolling, and timing patterns
to avoid bot detection.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import List, Tuple

from playwright.sync_api import Page

LOGGER = logging.getLogger(__name__)


@dataclass
class BehaviorConfig:
    """Configuration for behavior simulation."""
    
    # Timing
    min_action_delay: float = 0.5  # Minimum delay between actions (seconds)
    max_action_delay: float = 2.0  # Maximum delay between actions
    page_load_delay: float = 2.0   # Delay after page load
    
    # Mouse
    mouse_speed: int = 100  # Pixels per second
    enable_mouse_movements: bool = True
    mouse_movements_per_action: int = 3
    
    # Scrolling
    enable_scrolling: bool = True
    scroll_steps: int = 5  # Number of scroll increments
    scroll_pause: float = 0.3  # Pause between scroll steps
    
    # Reading simulation
    reading_speed_wpm: int = 250  # Words per minute
    enable_reading_pauses: bool = True


class HumanBehavior:
    """Simulates human-like behavior in browser automation."""
    
    def __init__(self, config: BehaviorConfig | None = None):
        """Initialize behavior simulator.
        
        Parameters
        ----------
        config : BehaviorConfig, optional
            Configuration (uses defaults if not provided)
        """
        self.config = config or BehaviorConfig()
    
    def random_delay(self, min_delay: float | None = None, max_delay: float | None = None) -> None:
        """Sleep for a random duration.
        
        Parameters
        ----------
        min_delay : float, optional
            Minimum delay in seconds
        max_delay : float, optional
            Maximum delay in seconds
        """
        min_d = min_delay or self.config.min_action_delay
        max_d = max_delay or self.config.max_action_delay
        delay = random.uniform(min_d, max_d)
        LOGGER.debug(f"Random delay: {delay:.2f}s")
        time.sleep(delay)
    
    def move_mouse_smoothly(
        self,
        page: Page,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        steps: int = 10,
    ) -> None:
        """Move mouse smoothly from one point to another.
        
        Uses Bezier curve for natural movement.
        
        Parameters
        ----------
        page : Page
            Playwright page
        from_x, from_y : int
            Starting coordinates
        to_x, to_y : int
            Target coordinates
        steps : int
            Number of intermediate points
        """
        if not self.config.enable_mouse_movements:
            return
        
        # Generate Bezier curve points
        points = self._bezier_curve(
            (from_x, from_y),
            (to_x, to_y),
            steps,
        )
        
        # Move through points
        for x, y in points:
            page.mouse.move(x, y)
            time.sleep(0.01)  # Small delay between movements
    
    def _bezier_curve(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
        steps: int,
    ) -> List[Tuple[int, int]]:
        """Generate Bezier curve points for mouse movement.
        
        Parameters
        ----------
        start : tuple
            Starting point (x, y)
        end : tuple
            Ending point (x, y)
        steps : int
            Number of points
            
        Returns
        -------
        list
            List of (x, y) coordinates
        """
        # Generate control points for natural curve
        control1_x = start[0] + (end[0] - start[0]) * 0.3 + random.randint(-50, 50)
        control1_y = start[1] + (end[1] - start[1]) * 0.3 + random.randint(-50, 50)
        
        control2_x = start[0] + (end[0] - start[0]) * 0.7 + random.randint(-50, 50)
        control2_y = start[1] + (end[1] - start[1]) * 0.7 + random.randint(-50, 50)
        
        points = []
        for i in range(steps + 1):
            t = i / steps
            
            # Cubic Bezier curve formula
            x = (
                (1 - t) ** 3 * start[0]
                + 3 * (1 - t) ** 2 * t * control1_x
                + 3 * (1 - t) * t ** 2 * control2_x
                + t ** 3 * end[0]
            )
            
            y = (
                (1 - t) ** 3 * start[1]
                + 3 * (1 - t) ** 2 * t * control1_y
                + 3 * (1 - t) * t ** 2 * control2_y
                + t ** 3 * end[1]
            )
            
            points.append((int(x), int(y)))
        
        return points
    
    def random_mouse_movement(self, page: Page) -> None:
        """Move mouse to random position on page.
        
        Parameters
        ----------
        page : Page
            Playwright page
        """
        if not self.config.enable_mouse_movements:
            return
        
        viewport = page.viewport_size
        if not viewport:
            return
        
        # Get current mouse position (estimate)
        from_x = random.randint(100, viewport['width'] - 100)
        from_y = random.randint(100, viewport['height'] - 100)
        
        # Target position
        to_x = random.randint(100, viewport['width'] - 100)
        to_y = random.randint(100, viewport['height'] - 100)
        
        LOGGER.debug(f"Moving mouse from ({from_x}, {from_y}) to ({to_x}, {to_y})")
        self.move_mouse_smoothly(page, from_x, from_y, to_x, to_y)
    
    def scroll_page(
        self,
        page: Page,
        direction: str = "down",
        distance: int | None = None,
    ) -> None:
        """Scroll page naturally.
        
        Parameters
        ----------
        page : Page
            Playwright page
        direction : str
            Scroll direction ("down", "up")
        distance : int, optional
            Total scroll distance in pixels (random if not specified)
        """
        if not self.config.enable_scrolling:
            return
        
        if distance is None:
            # Random scroll distance (300-800px)
            distance = random.randint(300, 800)
        
        step_distance = distance // self.config.scroll_steps
        scroll_multiplier = 1 if direction == "down" else -1
        
        LOGGER.debug(f"Scrolling {direction} by {distance}px in {self.config.scroll_steps} steps")
        
        for i in range(self.config.scroll_steps):
            # Add small variation to each step
            step_with_variation = step_distance + random.randint(-20, 20)
            page.evaluate(f"window.scrollBy(0, {step_with_variation * scroll_multiplier})")
            
            # Pause between steps
            time.sleep(self.config.scroll_pause + random.uniform(-0.1, 0.1))
    
    def simulate_reading(self, page: Page, text_length: int = 500) -> None:
        """Simulate reading content by waiting appropriate time.
        
        Parameters
        ----------
        page : Page
            Playwright page
        text_length : int
            Approximate text length in characters
        """
        if not self.config.enable_reading_pauses:
            return
        
        # Estimate words (avg 5 chars per word)
        words = text_length / 5
        
        # Calculate reading time
        reading_time = (words / self.config.reading_speed_wpm) * 60
        
        # Add variation
        actual_time = reading_time * random.uniform(0.8, 1.2)
        
        LOGGER.debug(f"Simulating reading for {actual_time:.2f}s")
        time.sleep(actual_time)
    
    def page_interaction_sequence(
        self,
        page: Page,
        *,
        scroll: bool = True,
        mouse_movements: int | None = None,
        reading_pause: bool = True,
    ) -> None:
        """Perform a sequence of human-like interactions.
        
        Parameters
        ----------
        page : Page
            Playwright page
        scroll : bool
            Whether to scroll
        mouse_movements : int, optional
            Number of mouse movements (uses config default if None)
        reading_pause : bool
            Whether to simulate reading
        """
        LOGGER.info("Starting human-like interaction sequence")
        
        # Initial delay after page load
        self.random_delay(
            self.config.page_load_delay,
            self.config.page_load_delay + 1.0,
        )
        
        # Random mouse movements
        if mouse_movements is None:
            mouse_movements = self.config.mouse_movements_per_action
        
        for i in range(mouse_movements):
            self.random_mouse_movement(page)
            self.random_delay(0.3, 0.8)
        
        # Scroll down
        if scroll:
            self.scroll_page(page, "down")
            self.random_delay()
            
            # Maybe scroll back up a bit
            if random.random() < 0.3:
                self.scroll_page(page, "up", distance=200)
                self.random_delay()
        
        # Simulate reading
        if reading_pause:
            self.simulate_reading(page, text_length=1000)
        
        # Final mouse movement
        if self.config.enable_mouse_movements:
            self.random_mouse_movement(page)
        
        LOGGER.info("Interaction sequence completed")
    
    def hover_element(self, page: Page, selector: str) -> None:
        """Hover over an element naturally.
        
        Parameters
        ----------
        page : Page
            Playwright page
        selector : str
            Element selector
        """
        try:
            element = page.query_selector(selector)
            if not element:
                LOGGER.warning(f"Element not found: {selector}")
                return
            
            # Get element position
            box = element.bounding_box()
            if not box:
                return
            
            # Calculate center of element
            center_x = int(box['x'] + box['width'] / 2)
            center_y = int(box['y'] + box['height'] / 2)
            
            # Get current viewport position (estimate random starting point)
            viewport = page.viewport_size
            if viewport:
                from_x = random.randint(0, viewport['width'])
                from_y = random.randint(0, viewport['height'])
            else:
                from_x, from_y = 100, 100
            
            # Move mouse to element
            self.move_mouse_smoothly(page, from_x, from_y, center_x, center_y)
            
            # Hover for a bit
            time.sleep(random.uniform(0.5, 1.5))
            
        except Exception as e:
            LOGGER.warning(f"Failed to hover element {selector}: {e}")


class BehaviorPresets:
    """Pre-configured behavior patterns for different scenarios."""
    
    @staticmethod
    def fast() -> BehaviorConfig:
        """Fast but still human-like behavior."""
        return BehaviorConfig(
            min_action_delay=0.2,
            max_action_delay=0.8,
            page_load_delay=1.0,
            mouse_movements_per_action=2,
            scroll_steps=3,
            enable_reading_pauses=False,
        )
    
    @staticmethod
    def normal() -> BehaviorConfig:
        """Normal human behavior (default)."""
        return BehaviorConfig()
    
    @staticmethod
    def cautious() -> BehaviorConfig:
        """Very careful, slow behavior for high-security sites."""
        return BehaviorConfig(
            min_action_delay=1.0,
            max_action_delay=3.0,
            page_load_delay=3.0,
            mouse_movements_per_action=5,
            scroll_steps=8,
            scroll_pause=0.5,
            enable_reading_pauses=True,
            reading_speed_wpm=200,
        )
    
    @staticmethod
    def paranoid() -> BehaviorConfig:
        """Extremely cautious behavior."""
        return BehaviorConfig(
            min_action_delay=2.0,
            max_action_delay=5.0,
            page_load_delay=5.0,
            mouse_movements_per_action=8,
            scroll_steps=10,
            scroll_pause=0.8,
            enable_reading_pauses=True,
            reading_speed_wpm=150,
        )

