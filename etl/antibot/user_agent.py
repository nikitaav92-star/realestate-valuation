"""User-agent pool management."""
from __future__ import annotations

import random
from typing import List


class UserAgentPool:
    """Pool of realistic user-agent strings."""
    
    # Desktop user agents
    DESKTOP_USER_AGENTS: List[str] = [
        # Chrome on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        
        # Chrome on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        
        # Chrome on Linux
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        
        # Firefox on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        
        # Firefox on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0",
        
        # Safari on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        
        # Edge on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    ]
    
    # Mobile user agents
    MOBILE_USER_AGENTS: List[str] = [
        # iPhone Safari
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        
        # iPad Safari
        "Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        
        # Android Chrome
        "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 12; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    ]
    
    def __init__(self, *, prefer_mobile: bool = False) -> None:
        """Initialize user-agent pool.
        
        Parameters
        ----------
        prefer_mobile : bool
            If True, select mobile agents more frequently
        """
        self.prefer_mobile = prefer_mobile
    
    def get_random(self) -> str:
        """Get a random user-agent string.
        
        Returns
        -------
        str
            Random user-agent string
        """
        if self.prefer_mobile or (not self.prefer_mobile and random.random() < 0.2):
            return random.choice(self.MOBILE_USER_AGENTS)
        return random.choice(self.DESKTOP_USER_AGENTS)
    
    def get_desktop(self) -> str:
        """Get a random desktop user-agent.
        
        Returns
        -------
        str
            Random desktop user-agent string
        """
        return random.choice(self.DESKTOP_USER_AGENTS)
    
    def get_mobile(self) -> str:
        """Get a random mobile user-agent.
        
        Returns
        -------
        str
            Random mobile user-agent string
        """
        return random.choice(self.MOBILE_USER_AGENTS)
    
    def get_by_browser(self, browser: str) -> str:
        """Get a random user-agent for specific browser.
        
        Parameters
        ----------
        browser : str
            Browser name (chrome, firefox, safari, edge)
            
        Returns
        -------
        str
            Random user-agent for the browser
        """
        browser = browser.lower()
        
        if browser == "chrome":
            agents = [ua for ua in self.DESKTOP_USER_AGENTS if "Chrome" in ua and "Edg" not in ua]
        elif browser == "firefox":
            agents = [ua for ua in self.DESKTOP_USER_AGENTS if "Firefox" in ua]
        elif browser == "safari":
            agents = [ua for ua in self.DESKTOP_USER_AGENTS if "Safari" in ua and "Chrome" not in ua]
        elif browser == "edge":
            agents = [ua for ua in self.DESKTOP_USER_AGENTS if "Edg" in ua]
        else:
            agents = self.DESKTOP_USER_AGENTS
        
        return random.choice(agents) if agents else self.get_desktop()

