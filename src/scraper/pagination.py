"""Pagination discovery — find next/previous page links on a rendered page."""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

NEXT_HINTS = ("next", "next page", "next →", "next>", "older", "»", "›")
PREV_HINTS = ("prev", "previous", "prev page", "newer", "«", "‹")

NEXT_SELECTORS = [
    'a[rel="next"]',
    'link[rel="next"]',
    'a[aria-label*="next" i]',
    'a[aria-label*="older" i]',
    '.next a',
    '.pagination-next a',
    'li.next a',
    'a.next',
]

PREV_SELECTORS = [
    'a[rel="prev"]',
    'link[rel="prev"]',
    'a[aria-label*="previous" i]',
    'a[aria-label*="newer" i]',
    '.prev a',
    '.pagination-prev a',
    'li.prev a',
    'a.prev',
]


async def _find_by_selectors(page, selectors: list[str]) -> Optional[str]:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                href = await loc.get_attribute("href")
                if href:
                    return urljoin(page.url, href)
        except Exception as exc:
            logger.debug("selector %s failed: %s", sel, exc)
    return None


async def _scan_anchors(page, hints: tuple[str, ...]) -> Optional[str]:
    try:
        anchors = await page.eval_on_selector_all(
            "a[href]",
            """els => els.map(e => ({href: e.href, text: ((e.innerText || e.getAttribute('aria-label') || e.title || '') + '').trim().toLowerCase()}))""",
        )
    except Exception as exc:
        logger.debug("anchor scan failed: %s", exc)
        return None
    for a in anchors or []:
        text = a.get("text") or ""
        if any(h in text for h in hints) and a.get("href"):
            return a["href"]
    return None


async def find_next_url(page) -> Optional[str]:
    """Return the absolute URL of the next page, or None."""
    found = await _find_by_selectors(page, NEXT_SELECTORS)
    if found:
        return found
    return await _scan_anchors(page, NEXT_HINTS)


async def find_prev_url(page) -> Optional[str]:
    """Return the absolute URL of the previous page, or None."""
    found = await _find_by_selectors(page, PREV_SELECTORS)
    if found:
        return found
    return await _scan_anchors(page, PREV_HINTS)
