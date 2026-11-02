"""
Executor Mouse Action Module

Executes deterministic mouse actions (hovering, scrolling, dragging) on the browser page.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

async def hover_element(page: Any, element_id: str, scene_graph: Any) -> bool:
    """Hovers the mouse cursor over an element."""
    if not page:
        return False

    node = scene_graph.find_node(element_id) if scene_graph else None
    if node and node.bbox:
        x1, y1, x2, y2 = node.bbox
        x = (x1 + x2) / 2
        y = (y1 + y2) / 2
        try:
            logger.info("Hovering mouse at coordinates (%d, %d)", x, y)
            if hasattr(page, "mouse") and page.mouse:
                await page.mouse.move(x, y)
                return True
        except Exception as exc:
            logger.warning("Coordinate hover failed: %s", exc)

    selector = node.selector if node else element_id
    if selector:
        try:
            logger.info("Hovering selector: %s", selector)
            if hasattr(page, "hover"):
                await page.hover(selector)
                return True
        except Exception as exc:
            logger.error("Selector hover failed: %s", exc)

    return False

async def scroll_page(page: Any, direction: str) -> bool:
    """Scrolls the page up or down."""
    if not page:
        return False

    try:
        logger.info("Scrolling page: %s", direction)
        delta_y = 400 if direction == "down" else -400
        
        # Use Page JS evaluation scroll to support custom engines without raw mouse wheel events
        await page.evaluate(f"window.scrollBy(0, {delta_y})")
        return True
    except Exception as exc:
        logger.error("Scroll action failed: %s", exc)

    return False

async def drag_element(page: Any, source_id: str, target_id: str, scene_graph: Any) -> bool:
    """Drags an element from source coordinates to target coordinates."""
    if not page:
        return False

    src_node = scene_graph.find_node(source_id) if scene_graph else None
    tgt_node = scene_graph.find_node(target_id) if scene_graph else None

    if src_node and tgt_node and src_node.bbox and tgt_node.bbox:
        sx1, sy1, sx2, sy2 = src_node.bbox
        tx1, ty1, tx2, ty2 = tgt_node.bbox
        
        sx, sy = (sx1 + sx2) / 2, (sy1 + sy2) / 2
        tx, ty = (tx1 + tx2) / 2, (ty1 + ty2) / 2

        try:
            logger.info("Dragging element from (%d, %d) to (%d, %d)", sx, sy, tx, ty)
            if hasattr(page, "mouse") and page.mouse:
                await page.mouse.move(sx, sy)
                await page.mouse.down()
                await page.mouse.move(tx, ty, steps=10)
                await page.mouse.up()
                return True
        except Exception as exc:
            logger.error("Drag and drop failed: %s", exc)

    return False
