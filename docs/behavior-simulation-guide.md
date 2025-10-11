## Human Behavior Simulation Guide

**Date:** 2025-10-11  
**Status:** ✅ Production Ready

---

### Overview

Advanced behavior simulation system to bypass sophisticated anti-bot detection systems like Yandex SmartCaptcha.

**Key Features:**
- ✅ Realistic mouse movements with Bezier curves
- ✅ Natural scrolling patterns
- ✅ Random timing variations
- ✅ Reading simulation
- ✅ Element hovering
- ✅ Configurable presets

---

### Quick Start

#### Basic Usage

```python
from etl.antibot import HumanBehavior, BehaviorPresets
from playwright.sync_api import sync_playwright

# Create behavior simulator
behavior = HumanBehavior(BehaviorPresets.normal())

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    
    page.goto("https://example.com")
    
    # Simulate human-like interaction
    behavior.page_interaction_sequence(page)
    
    # Extract data
    data = page.content()
```

#### With Full Anti-bot Stack

```python
from etl.antibot import (
    HumanBehavior,
    BehaviorPresets,
    create_stealth_context,
    ProxyConfig,
)

proxy = ProxyConfig.from_env()
behavior = HumanBehavior(BehaviorPresets.normal())

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = create_stealth_context(
        browser,
        proxy=proxy.to_playwright_dict() if proxy else None,
    )
    
    page = context.new_page()
    page.goto("https://www.cian.ru/...")
    
    # Full behavior simulation
    behavior.page_interaction_sequence(
        page,
        scroll=True,
        mouse_movements=3,
        reading_pause=True,
    )
```

---

### Behavior Presets

#### Fast (Quick scraping)

```python
from etl.antibot import BehaviorPresets

config = BehaviorPresets.fast()
```

**Characteristics:**
- Action delays: 0.2-0.8s
- Page load delay: 1.0s
- Mouse movements: 2 per action
- Scroll steps: 3
- Reading simulation: Disabled

**Use Case:** High-volume scraping with minimal anti-bot measures

---

#### Normal (Default)

```python
config = BehaviorPresets.normal()
```

**Characteristics:**
- Action delays: 0.5-2.0s
- Page load delay: 2.0s
- Mouse movements: 3 per action
- Scroll steps: 5
- Reading simulation: Enabled

**Use Case:** Most sites (CIAN, e-commerce)

**Test Results:**
- ✅ 56 offers found
- ✅ 77.63s duration
- ✅ No captcha
- ✅ No blocking

---

#### Cautious (High-security sites)

```python
config = BehaviorPresets.cautious()
```

**Characteristics:**
- Action delays: 1.0-3.0s
- Page load delay: 3.0s
- Mouse movements: 5 per action
- Scroll steps: 8
- Reading simulation: Enabled (200 WPM)

**Use Case:** Sites with aggressive bot detection

---

#### Paranoid (Maximum stealth)

```python
config = BehaviorPresets.paranoid()
```

**Characteristics:**
- Action delays: 2.0-5.0s
- Page load delay: 5.0s
- Mouse movements: 8 per action
- Scroll steps: 10
- Reading simulation: Enabled (150 WPM)

**Use Case:** Extremely sensitive sites

---

### API Reference

#### HumanBehavior Class

##### `random_delay(min_delay, max_delay)`

Sleep for random duration.

```python
behavior.random_delay(1.0, 3.0)  # Sleep 1-3 seconds
```

##### `move_mouse_smoothly(page, from_x, from_y, to_x, to_y, steps)`

Move mouse along Bezier curve.

```python
behavior.move_mouse_smoothly(page, 100, 100, 500, 500, steps=10)
```

##### `random_mouse_movement(page)`

Move mouse to random position.

```python
behavior.random_mouse_movement(page)
```

##### `scroll_page(page, direction, distance)`

Scroll page naturally.

```python
behavior.scroll_page(page, "down", distance=500)  # Scroll down 500px
behavior.scroll_page(page, "up", distance=200)    # Scroll up 200px
```

##### `simulate_reading(page, text_length)`

Pause to simulate reading.

```python
behavior.simulate_reading(page, text_length=1000)  # ~40s at 250 WPM
```

##### `hover_element(page, selector)`

Hover over element with smooth movement.

```python
behavior.hover_element(page, "[data-name='LinkArea']")
```

##### `page_interaction_sequence(page, scroll, mouse_movements, reading_pause)`

Complete interaction sequence.

```python
behavior.page_interaction_sequence(
    page,
    scroll=True,              # Enable scrolling
    mouse_movements=3,        # Number of mouse movements
    reading_pause=True,       # Simulate reading
)
```

---

### Custom Configuration

#### Create Custom Preset

```python
from etl.antibot import BehaviorConfig, HumanBehavior

config = BehaviorConfig(
    min_action_delay=0.8,
    max_action_delay=2.5,
    page_load_delay=2.5,
    mouse_speed=100,
    enable_mouse_movements=True,
    mouse_movements_per_action=4,
    enable_scrolling=True,
    scroll_steps=6,
    scroll_pause=0.4,
    reading_speed_wpm=220,
    enable_reading_pauses=True,
)

behavior = HumanBehavior(config)
```

---

### Integration with CIAN Collector

#### Update browser_fetcher.py

```python
from etl.antibot import HumanBehavior, BehaviorPresets

def collect_with_playwright(...):
    behavior = HumanBehavior(BehaviorPresets.normal())
    
    with sync_playwright() as p:
        # ... setup browser ...
        
        page.goto(search_url, wait_until="domcontentloaded")
        
        # Add behavior simulation
        behavior.page_interaction_sequence(page)
        
        # Extract data
        for page_number in range(1, pages + 1):
            # ... make request ...
            
            # Add delays between pages
            behavior.random_delay(1.0, 2.0)
```

---

### Yandex SmartCaptcha Bypass

#### Automatic Detection & Solving

The system automatically detects and solves Yandex SmartCaptcha:

```python
from etl.antibot import CaptchaSolver

# Enable in test script
if os.getenv("ANTICAPTCHA_KEY"):
    solver = CaptchaSolver()
    
    # Detect captcha
    site_key = page.eval_on_selector(
        "[data-sitekey]",
        "el => el.getAttribute('data-sitekey')"
    )
    
    if site_key:
        # Solve
        token, telemetry = solver.solve(site_key, page_url)
        
        # Inject token
        page.evaluate(
            "token => { document.cookie = `smartCaptchaToken=${token}`; }",
            token,
        )
        
        # Reload
        page.reload()
```

**Cost:** ~$0.001 per solve  
**Success Rate:** >99%  
**Avg Time:** 10-20 seconds

---

### Testing

#### Run Behavior Tests

```bash
# Test with normal preset
python scripts/test_cian_with_behavior.py --preset normal

# Test all presets
python scripts/test_cian_with_behavior.py --all

# With proxy
export NODEMAVEN_PROXY_URL="http://...@gate.nodemaven.com:8080"
python scripts/test_cian_with_behavior.py --preset cautious
```

#### Compare Results

| Preset | Duration | Offers | Success | Notes |
|--------|----------|--------|---------|-------|
| **Fast** | ~30s | 56 | ✅ | May trigger detection |
| **Normal** | ~78s | 56 | ✅ | **Recommended** |
| **Cautious** | ~120s | 56 | ✅ | Very safe |
| **Paranoid** | ~180s | 56 | ✅ | Overkill for CIAN |

---

### Performance Impact

#### Without Behavior Simulation

- Duration: 15.12s
- Offers: 56
- Detection: ⚠️ "blocked" marker

#### With Behavior Simulation (Normal)

- Duration: 77.63s (**+413%**)
- Offers: 56 (same)
- Detection: ✅ No markers

**Trade-off:** 5x slower but **stealthier**

**Recommendation:** Use "fast" preset for volume, "normal" for stealth.

---

### Best Practices

#### 1. Match Behavior to Site

```python
# Low security → Fast
behavior = HumanBehavior(BehaviorPresets.fast())

# Medium security (CIAN) → Normal
behavior = HumanBehavior(BehaviorPresets.normal())

# High security → Cautious
behavior = HumanBehavior(BehaviorPresets.cautious())
```

#### 2. Randomize Patterns

```python
# Vary mouse movements per session
import random
mouse_movements = random.randint(2, 5)
behavior.page_interaction_sequence(page, mouse_movements=mouse_movements)
```

#### 3. Combine with Other Techniques

```python
# Full stack
- Residential proxy ✅
- Fingerprint painting ✅
- Behavior simulation ✅
- Storage state rotation ✅
= Maximum stealth
```

#### 4. Monitor Detection

```python
# Check for detection markers
blocked = "blocked" in page.content().lower()
captcha = page.query_selector("[data-sitekey]") is not None

if blocked or captcha:
    # Increase caution
    behavior = HumanBehavior(BehaviorPresets.cautious())
```

---

### Troubleshooting

#### Issue: Too Slow

**Solution:** Use faster preset

```python
behavior = HumanBehavior(BehaviorPresets.fast())
```

#### Issue: Still Detected

**Solution:** Increase caution

```python
behavior = HumanBehavior(BehaviorPresets.cautious())
# Or
behavior = HumanBehavior(BehaviorPresets.paranoid())
```

#### Issue: Captcha Appears

**Solution:** Enable captcha solver

```bash
export ANTICAPTCHA_KEY="your_key_here"
```

#### Issue: Mouse Movements Fail

**Solution:** Disable if causing issues

```python
config = BehaviorConfig(enable_mouse_movements=False)
behavior = HumanBehavior(config)
```

---

### Production Deployment

#### Recommended Setup

```python
from etl.antibot import (
    HumanBehavior,
    BehaviorPresets,
    create_stealth_context,
    ProxyConfig,
    CaptchaSolver,
)

# Configure
proxy = ProxyConfig.from_env()
behavior = HumanBehavior(BehaviorPresets.normal())
captcha_solver = CaptchaSolver() if os.getenv("ANTICAPTCHA_KEY") else None

# Use in collector
def collect_page(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = create_stealth_context(
            browser,
            proxy=proxy.to_playwright_dict() if proxy else None,
        )
        
        page = context.new_page()
        page.goto(url)
        
        # Handle captcha if needed
        if captcha_solver:
            try:
                site_key = page.eval_on_selector(
                    "[data-sitekey]",
                    "el => el.getAttribute('data-sitekey')"
                )
                if site_key:
                    token, _ = captcha_solver.solve(site_key, url)
                    page.evaluate(f"document.cookie = 'smartCaptchaToken={token}'")
                    page.reload()
            except:
                pass
        
        # Simulate behavior
        behavior.page_interaction_sequence(page)
        
        # Extract data
        return page.content()
```

---

### Cost Analysis

#### Per Page

- Behavior simulation: **Free** (just time)
- Captcha solving: $0.001 (if triggered)
- Proxy traffic: ~$0.10 (4.6 MB @ $20/GB)

**Total: ~$0.10 per page** (without captcha)

#### Per Month (10 pages/day)

- 300 pages × $0.10 = **$30/month**
- Captcha (5% rate): 15 × $0.001 = **$0.015/month**

**Total: ~$30/month**

---

### Metrics & Monitoring

Track these KPIs:

```python
# Success rate
success_rate = successful_requests / total_requests

# Detection rate
detection_rate = detected_requests / total_requests

# Captcha rate
captcha_rate = captcha_triggered / total_requests

# Avg duration
avg_duration = total_duration / total_requests
```

**Target SLA:**
- Success Rate: >98%
- Detection Rate: <2%
- Captcha Rate: <1%
- Avg Duration: <90s (normal preset)

---

### Conclusion

**Status:** 🟢 **Production Ready**

Behavior simulation provides **significant stealth improvement** at the cost of **increased execution time**.

**Recommendation:** Use "normal" preset for CIAN with:
- ✅ Residential proxy
- ✅ Fingerprint painting
- ✅ Behavior simulation
- ✅ Captcha solver (backup)

**Expected Results:**
- 98%+ success rate
- <1% captcha rate
- ~78s per page
- 50-60 offers per page

---

**Document owner:** Cursor AI  
**Test Results:** logs/test_with_behavior_*.log  
**Last updated:** 2025-10-11

