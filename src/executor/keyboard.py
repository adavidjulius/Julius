"""
Executor Keyboard Action Module

Executes deterministic keyboard actions (typing, key pressing) on the browser page.
"""

import logging
from typing import Any
from .click import click_element

logger = logging.getLogger(__name__)

async def type_text(page: Any, element_id: str, text: str, scene_graph: Any) -> bool:
    """
    Types text into an element by focusing it (using coordinate click or selector)
    and inserting text.
    """
    if not page:
        return False

    logger.info("Executing text entry of '%s' into element: %s", text, element_id)

    # First, focus/click the element to set keyboard cursor focus
    focused = await click_element(page, element_id, scene_graph)
    if not focused:
        logger.warning("Could not focus element %s before typing", element_id)

    # Type the text
    try:
        if hasattr(page, "keyboard") and page.keyboard:
            await page.keyboard.insert_text(text)
            return True
        elif hasattr(page, "fill"):
            node = scene_graph.find_node(element_id) if scene_graph else None
            selector = node.selector if node else element_id
            await page.fill(selector, text)
            return True
    except Exception as exc:
        logger.error("Failed to type text: %s", exc)

    return False

async def press_key(page: Any, key: str) -> bool:
    """Presses a keyboard key (e.g. 'Enter', 'Backspace', 'Tab')."""
    if not page:
        return False

    try:
        logger.info("Pressing key: %s", key)
        if hasattr(page, "keyboard") and page.keyboard:
            await page.keyboard.press(key)
            return True
    except Exception as exc:
        logger.error("Failed to press key %s: %s", key, exc)

    return False
