"""
Anti-bot strategies for the Julius browser engine.

Provides:
  - Stealth header sets (realistic User-Agent, Accept-Language, etc.)
  - Human-like delay injection between actions
  - Bot/CAPTCHA detection from page content
  - Configurable anti-bot execution modes
"""

from __future__ import annotations

import asyncio
import random
import re
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

    from .structured_obs import BotDetection


class AntiBotMode(str, Enum):
    OFF = "off"         # No stealth — fastest, default
    HUMAN = "human"     # Human-like delays + realistic UA only
    STEALTH = "stealth" # Full stealth: delays + UA + extra headers + viewport randomisation


# ── User-Agent rotation pool ──────────────────────────────────────────────────

_USER_AGENTS = [
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]

_ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.9,es;q=0.8",
]

_VIEWPORTS = [
    {"width": 1280, "height": 800},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
]


# ── Bot-detection patterns ────────────────────────────────────────────────────

_BOT_DETECTION_PATTERNS: list[tuple[str, str, str]] = [
    # (page_title_pattern, url_pattern, detection_type)
    (r"just a moment", r"", "cloudflare_challenge"),
    (r"attention required", r"cloudflare", "cloudflare_waf"),
    (r"access denied", r"", "access_denied"),
    (r"403 forbidden", r"", "http_403"),
    (r"verify you are human", r"", "recaptcha_v3"),
    (r"robot", r"", "bot_detection_generic"),
    (r"captcha", r"", "captcha_generic"),
    (r"unusual traffic", r"google\.com", "google_unusual_traffic"),
    (r"your connection is not private", r"", "ssl_error"),
    (r"too many requests", r"", "rate_limited"),
    (r"blocked", r"", "generic_block"),
]


def pick_stealth_context_options(mode: AntiBotMode) -> dict:
    """
    Return ``browser.new_context(**options)`` kwargs appropriate for the mode.
    """
    if mode == AntiBotMode.OFF:
        return {"viewport": {"width": 1280, "height": 900}}

    ua = random.choice(_USER_AGENTS)
    lang = random.choice(_ACCEPT_LANGUAGES)
    viewport = random.choice(_VIEWPORTS) if mode == AntiBotMode.STEALTH else {"width": 1280, "height": 900}

    opts: dict = {
        "user_agent": ua,
        "locale": "en-US",
        "viewport": viewport,
        "extra_http_headers": {
            "Accept-Language": lang,
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
        },
    }

    if mode == AntiBotMode.STEALTH:
        opts["extra_http_headers"].update({
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1",
        })

    return opts


async def human_delay(action_type: str = "default") -> None:
    """
    Inject a realistic human-like pause before an action.

    Delays are tuned per action type:
      - navigation  : 800–1500 ms (page loads feel slower)
      - click       : 120–350 ms  (fast but not instant)
      - type        : 40–120 ms   (per character, called separately)
      - default     : 200–600 ms
    """
    ranges = {
        "navigation": (0.8, 1.5),
        "click": (0.12, 0.35),
        "type": (0.04, 0.12),
        "scroll": (0.3, 0.8),
        "default": (0.2, 0.6),
    }
    lo, hi = ranges.get(action_type, ranges["default"])
    await asyncio.sleep(random.uniform(lo, hi))


async def human_type(page: "Page", selector: str, text: str) -> None:
    """Type text character-by-character with randomised inter-key delays."""
    await page.click(selector)
    for char in text:
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.04, 0.14))


def detect_bot_block(title: str, url: str) -> "BotDetection":
    """
    Inspect page title and URL to determine if a bot-blocking page is shown.

    Returns a populated BotDetection if a block is found, otherwise returns
    a BotDetection with detected=False.
    """
    from .structured_obs import BotDetection

    title_lower = title.lower()
    url_lower = url.lower()

    for title_pat, url_pat, dtype in _BOT_DETECTION_PATTERNS:
        title_match = bool(title_pat) and bool(re.search(title_pat, title_lower))
        url_match = bool(url_pat) and bool(re.search(url_pat, url_lower))
        if title_match or url_match:
            suggestion = _suggest_for(dtype)
            return BotDetection(
                detected=True,
                detection_type=dtype,
                page_title=title,
                suggested_action=suggestion,
            )

    return BotDetection(detected=False)


def _suggest_for(dtype: str) -> str:
    suggestions = {
        "cloudflare_challenge": (
            "Cloudflare JS challenge detected. Use browser_load_session with a pre-authenticated "
            "session, or switch anti_bot_mode to 'stealth'."
        ),
        "cloudflare_waf": (
            "Cloudflare WAF block. The IP or UA may be flagged. Try anti_bot_mode='stealth' "
            "or use a residential proxy."
        ),
        "recaptcha_v3": (
            "reCAPTCHA v3 detected. Consider browser_load_session with a real user session, "
            "or ask the user to solve the CAPTCHA manually."
        ),
        "captcha_generic": (
            "CAPTCHA wall detected. Automated solving is not supported. "
            "Use browser_load_session with a human-authenticated session cookie."
        ),
        "google_unusual_traffic": (
            "Google is rate-limiting this IP. Wait a few minutes before retrying, "
            "or use the fetch MCP server instead."
        ),
        "rate_limited": (
            "Rate-limited (429 / Too Many Requests). Add a delay and retry, "
            "or use a different endpoint."
        ),
        "access_denied": (
            "Access denied. Check if the resource requires authentication. "
            "Use browser_load_session to restore a logged-in session."
        ),
    }
    return suggestions.get(dtype, "Automated access appears to be blocked. Manual intervention or session injection may be required.")


# ── Tracker Blocklist (Obscura pgl_domains.txt port) ─────────────────────────

class TrackerBlocklist:
    """
    Production-grade tracker/ad/fingerprinting domain blocklist.

    Ported directly from Obscura's ``obscura-net/src/blocklist.rs``.
    Uses the same ``pgl_domains.txt`` (3,520 domains) and the same
    subdomain-walk algorithm: exact match OR any parent-domain match.

    Example::

        bl = TrackerBlocklist.instance()
        bl.is_blocked("sub.google-analytics.com")  # True
        bl.is_blocked("example.com")               # False
    """

    _singleton: "TrackerBlocklist | None" = None

    def __init__(self) -> None:
        self._domains: frozenset[str] = frozenset()
        self._load()

    def _load(self) -> None:
        import os
        candidates = [
            # Same directory as this file
            os.path.join(os.path.dirname(__file__), "tracker_blocklist.txt"),
            # Julius_Browser copy
            os.path.join(
                os.path.dirname(__file__), "..", "..", "..",
                "Julius_Browser", "src", "assets", "pgl_domains.txt"
            ),
        ]
        for path in candidates:
            path = os.path.normpath(path)
            if os.path.isfile(path):
                domains: set[str] = set()
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        domain = line.strip()
                        if domain and not domain.startswith("#"):
                            domains.add(domain)
                self._domains = frozenset(domains)
                import logging
                logging.getLogger(__name__).debug(
                    "TrackerBlocklist: loaded %d domains from %s", len(self._domains), path
                )
                return
        import logging
        logging.getLogger(__name__).warning(
            "TrackerBlocklist: tracker_blocklist.txt not found — tracker blocking disabled"
        )

    @classmethod
    def instance(cls) -> "TrackerBlocklist":
        """Return the process-wide singleton (loaded once)."""
        if cls._singleton is None:
            cls._singleton = cls()
        return cls._singleton

    def is_blocked(self, host: str) -> bool:
        """
        Return True if ``host`` (or any of its parent domains) is a known tracker.

        Mirrors Obscura's ``blocklist::is_blocked()`` exactly:
        1. Exact domain match.
        2. Walk up parent domains (strip one label at a time, left to right).
        """
        if not host:
            return False
        if host in self._domains:
            return True
        domain = host
        while "." in domain:
            domain = domain[domain.index(".") + 1:]
            if domain in self._domains:
                return True
        return False

    def is_tracker_url(self, url: str) -> bool:
        """Convenience: parse URL and check the hostname."""
        try:
            from urllib.parse import urlparse
            host = urlparse(url).hostname or ""
            return self.is_blocked(host)
        except Exception:
            return False

    @property
    def domain_count(self) -> int:
        return len(self._domains)


async def route_block_trackers(page: "Page") -> None:
    """
    Install a Playwright ``page.route()`` handler that aborts any request
    whose hostname appears in the Obscura tracker blocklist.

    Designed to be called right after ``new_page()`` in STEALTH mode.
    Non-blocking: aborted requests are silently dropped (no exception).

    Usage::

        page = await context.new_page()
        await route_block_trackers(page)
    """
    bl = TrackerBlocklist.instance()
    if bl.domain_count == 0:
        return  # Blocklist not loaded; skip silently

    async def _abort_tracker(route: "Route") -> None:  # type: ignore[name-defined]
        try:
            if bl.is_tracker_url(route.request.url):
                await route.abort()
            else:
                await route.continue_()
        except Exception:
            try:
                await route.continue_()
            except Exception:
                pass

    # Match everything — our handler decides per-URL
    await page.route("**/*", _abort_tracker)

