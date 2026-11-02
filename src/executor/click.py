"""
Executor Click Action Module

Executes deterministic click actions on the browser page.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

async def click_element(page: Any, element_id: str, scene_graph: Any) -> bool:
    """
    Clicks an element on the page using its SceneNode bounding box or selector.
    """
    if not page:
        return False

    node = scene_graph.find_node(element_id) if scene_graph else None
    
    # 1. Coordinate-based click (OmniParser/Visual coordinate mapping)
    if node and node.bbox:
        x1, y1, x2, y2 = node.bbox
        x = (x1 + x2) / 2
        y = (y1 + y2) / 2
        
        try:
            logger.info("Executing coordinate click at (%d, %d) for element: %s", x, y, element_id)
            if hasattr(page, "mouse") and page.mouse:
                await page.mouse.click(x, y)
                return True
        except Exception as exc:
            logger.warning("Coordinate click failed, falling back to selector: %s", exc)

    # 2. Selector-based click fallback
    selector = node.selector if node else element_id
    if selector:
        try:
            logger.info("Executing selector click on: %s", selector)
            if hasattr(page, "click"):
                await page.click(selector)
                return True
        except Exception as exc:
            logger.error("Selector click failed: %s", exc)

    return False
