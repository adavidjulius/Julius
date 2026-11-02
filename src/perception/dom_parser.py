"""
Perception DOM Parser Module

Extracts semantic DOM element structures and their visual coordinates from the browser page.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

class DOMParser:
    async def parse(self, page: Any) -> List[Dict[str, Any]]:
        """
        Parses the DOM of the active page to extract elements, bounding boxes, and metadata.
        """
        if not page:
            return []

        try:
            import asyncio
            # Execute with a 5-second timeout to prevent Python hangs
            raw_elements = await asyncio.wait_for(page.evaluate("""
                () => {
                    const results = [];
                    const elements = document.getElementsByTagName('*');
                    const skipTags = new Set(['script', 'style', 'noscript', 'path', 'svg', 'link', 'meta', 'br', 'hr']);
                    
                    for (let i = 0; i < elements.length; i++) {
                        if (results.length >= 300) break; // Cap to prevent token/memory blowup
                        
                        const el = elements[i];
                        const tag = el.tagName.toLowerCase();
                        if (skipTags.has(tag)) continue;
                        
                        // Only capture elements with contents or that are interactive/visible
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;
                        
                        // Check visibility
                        const style = window.getComputedStyle(el);
                        if (style.visibility === 'hidden' || style.display === 'none' || parseFloat(style.opacity) === 0) {
                            continue;
                        }

                        // Determine role
                        let role = el.getAttribute('role') || tag;
                        
                        // Extract text content or value
                        let text = '';
                        if (tag === 'input' || tag === 'textarea') {
                            text = el.value || el.getAttribute('placeholder') || '';
                        } else if (tag === 'select') {
                            text = el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : '';
                        } else {
                            text = el.innerText || el.textContent || '';
                        }
                        text = text.trim().slice(0, 100);

                        // Capture selector and identifiers
                        let selector = '';
                        if (el.id) {
                            selector = '#' + el.id;
                        } else if (el.name) {
                            selector = `${tag}[name="${el.name}"]`;
                        } else {
                            selector = tag;
                        }

                        results.push({
                            "id": el.id || `dom-${i}`,
                            "tag": tag,
                            "role": role,
                            "text": text,
                            "selector": selector,
                            "bbox": [
                                Math.round(rect.left),
                                Math.round(rect.top),
                                Math.round(rect.right),
                                Math.round(rect.bottom)
                            ],
                            "enabled": !el.disabled,
                            "parent_id": el.parentElement ? (el.parentElement.id || '') : ''
                        });
                    }
                    return results;
                }
            """), timeout=5.0)
            return raw_elements or []
        except Exception as exc:
            logger.error("Failed to parse DOM via page evaluation or timed out: %s", exc)
            return []
