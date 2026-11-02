"""
Perception Capture Module

Handles capturing browser state (Accessibility Tree, DOM snapshot, Screenshot) in parallel.
"""

import asyncio
import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

async def capture_state(page: Any) -> Tuple[Dict[str, Any] | None, str, bytes]:
    """
    Captures all browser state in parallel:
    - Accessibility Tree (if supported)
    - DOM Snapshot (HTML content)
    - Screenshot (binary bytes)
    
    Returns:
        Tuple of (ax_tree, dom_html, screenshot_bytes)
    """
    # 1. Accessibility Tree Capture Task
    async def get_accessibility():
        try:
            if hasattr(page, "accessibility") and page.accessibility:
                return await asyncio.wait_for(page.accessibility.snapshot(), timeout=3.0)
        except Exception as exc:
            logger.debug("Failed to capture accessibility snapshot or timed out: %s", exc)
        return None

    # 2. DOM Snapshot Task
    async def get_dom_html():
        try:
            if hasattr(page, "content"):
                return await asyncio.wait_for(page.content(), timeout=5.0)
            elif hasattr(page, "evaluate"):
                return await asyncio.wait_for(page.evaluate("document.documentElement.outerHTML"), timeout=5.0)
        except Exception as exc:
            logger.error("Failed to capture DOM HTML or timed out: %s", exc)
        return "<html></html>"

    # 3. Screenshot Task
    async def get_screenshot():
        try:
            if hasattr(page, "screenshot"):
                return await asyncio.wait_for(page.screenshot(), timeout=5.0)
        except Exception as exc:
            logger.error("Failed to capture screenshot or timed out: %s", exc)
        return b""

    # Execute in parallel to minimize latency
    ax_tree, dom_html, screenshot_bytes = await asyncio.gather(
        get_accessibility(),
        get_dom_html(),
        get_screenshot()
    )

    return ax_tree, dom_html, screenshot_bytes

