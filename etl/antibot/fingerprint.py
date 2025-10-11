"""Device fingerprinting and Playwright context painting."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List

from playwright.sync_api import BrowserContext


@dataclass
class DeviceFingerprint:
    """Device fingerprint configuration."""
    
    user_agent: str
    viewport_width: int
    viewport_height: int
    device_scale_factor: float
    is_mobile: bool
    has_touch: bool
    locale: str
    timezone_id: str
    platform: str
    webgl_vendor: str
    webgl_renderer: str
    
    def to_playwright_context(self) -> Dict[str, Any]:
        """Convert to Playwright context kwargs."""
        return {
            "user_agent": self.user_agent,
            "viewport": {
                "width": self.viewport_width,
                "height": self.viewport_height,
            },
            "device_scale_factor": self.device_scale_factor,
            "is_mobile": self.is_mobile,
            "has_touch": self.has_touch,
            "locale": self.locale,
            "timezone_id": self.timezone_id,
        }


class FingerprintPainter:
    """Painter for applying device fingerprints to browser contexts."""
    
    # Common desktop configurations
    DESKTOP_FINGERPRINTS: List[DeviceFingerprint] = [
        DeviceFingerprint(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport_width=1920,
            viewport_height=1080,
            device_scale_factor=1.0,
            is_mobile=False,
            has_touch=False,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            platform="Win32",
            webgl_vendor="Google Inc. (NVIDIA)",
            webgl_renderer="ANGLE (NVIDIA GeForce GTX 1060 6GB Direct3D11 vs_5_0 ps_5_0)",
        ),
        DeviceFingerprint(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport_width=1440,
            viewport_height=900,
            device_scale_factor=2.0,
            is_mobile=False,
            has_touch=False,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            platform="MacIntel",
            webgl_vendor="Google Inc. (Apple)",
            webgl_renderer="ANGLE (Apple, Apple M1 Pro, OpenGL 4.1)",
        ),
        DeviceFingerprint(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport_width=1920,
            viewport_height=1080,
            device_scale_factor=1.0,
            is_mobile=False,
            has_touch=False,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            platform="Linux x86_64",
            webgl_vendor="Google Inc. (NVIDIA)",
            webgl_renderer="ANGLE (NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0)",
        ),
    ]
    
    # Common mobile configurations
    MOBILE_FINGERPRINTS: List[DeviceFingerprint] = [
        DeviceFingerprint(
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            ),
            viewport_width=390,
            viewport_height=844,
            device_scale_factor=3.0,
            is_mobile=True,
            has_touch=True,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            platform="iPhone",
            webgl_vendor="Apple Inc.",
            webgl_renderer="Apple GPU",
        ),
        DeviceFingerprint(
            user_agent=(
                "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
            ),
            viewport_width=360,
            viewport_height=800,
            device_scale_factor=3.0,
            is_mobile=True,
            has_touch=True,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            platform="Linux armv8l",
            webgl_vendor="Qualcomm",
            webgl_renderer="Adreno (TM) 730",
        ),
    ]
    
    def __init__(self, *, prefer_mobile: bool = False) -> None:
        """Initialize fingerprint painter.
        
        Parameters
        ----------
        prefer_mobile : bool
            If True, randomly select mobile fingerprints more often
        """
        self.prefer_mobile = prefer_mobile
    
    def get_random_fingerprint(self) -> DeviceFingerprint:
        """Get a random device fingerprint."""
        if self.prefer_mobile or (not self.prefer_mobile and random.random() < 0.2):
            return random.choice(self.MOBILE_FINGERPRINTS)
        return random.choice(self.DESKTOP_FINGERPRINTS)
    
    def paint_context(
        self,
        context: BrowserContext,
        fingerprint: DeviceFingerprint | None = None,
    ) -> None:
        """Paint browser context with device fingerprint.
        
        Parameters
        ----------
        context : BrowserContext
            Playwright browser context
        fingerprint : DeviceFingerprint, optional
            Fingerprint to apply (random if not provided)
        """
        if fingerprint is None:
            fingerprint = self.get_random_fingerprint()
        
        # Apply navigator overrides
        init_script = f"""
        () => {{
            // Override navigator properties
            Object.defineProperty(navigator, 'webdriver', {{
                get: () => undefined,
            }});
            
            Object.defineProperty(navigator, 'platform', {{
                get: () => '{fingerprint.platform}',
            }});
            
            Object.defineProperty(navigator, 'hardwareConcurrency', {{
                get: () => {random.randint(4, 16)},
            }});
            
            Object.defineProperty(navigator, 'deviceMemory', {{
                get: () => {random.choice([4, 8, 16])},
            }});
            
            // Override WebGL fingerprint
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {{
                if (parameter === 37445) {{
                    return '{fingerprint.webgl_vendor}';
                }}
                if (parameter === 37446) {{
                    return '{fingerprint.webgl_renderer}';
                }}
                return getParameter.call(this, parameter);
            }};
            
            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({{ state: Notification.permission }}) :
                    originalQuery(parameters)
            );
            
            // Add realistic plugins
            Object.defineProperty(navigator, 'plugins', {{
                get: () => [
                    {{
                        name: 'Chrome PDF Plugin',
                        description: 'Portable Document Format',
                        filename: 'internal-pdf-viewer',
                    }},
                    {{
                        name: 'Chrome PDF Viewer',
                        description: 'Portable Document Format',
                        filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                    }},
                    {{
                        name: 'Native Client',
                        description: 'Native Client Executable',
                        filename: 'internal-nacl-plugin',
                    }},
                ],
            }});
        }}
        """
        context.add_init_script(init_script)


def create_stealth_context(
    browser: Any,
    *,
    fingerprint: DeviceFingerprint | None = None,
    prefer_mobile: bool = False,
    **kwargs: Any,
) -> BrowserContext:
    """Create a stealth browser context with fingerprint painting.
    
    Parameters
    ----------
    browser : Browser
        Playwright browser instance
    fingerprint : DeviceFingerprint, optional
        Specific fingerprint to use (random if not provided)
    prefer_mobile : bool
        Prefer mobile fingerprints
    **kwargs
        Additional context kwargs
        
    Returns
    -------
    BrowserContext
        Configured browser context
    """
    painter = FingerprintPainter(prefer_mobile=prefer_mobile)
    
    if fingerprint is None:
        fingerprint = painter.get_random_fingerprint()
    
    # Merge fingerprint config with user kwargs
    context_kwargs = fingerprint.to_playwright_context()
    context_kwargs.update(kwargs)
    
    # Create context and paint
    context = browser.new_context(**context_kwargs)
    painter.paint_context(context, fingerprint)
    
    return context

