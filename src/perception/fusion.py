"""
Perception DOM-Visual Fusion Module

Merges DOM layout analysis with OmniParser visual detections using bounding box overlaps.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

class DOMVisualFusion:
    def fuse(self, dom_elements: List[Dict[str, Any]], visual_detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Fuses DOM elements with visual detections from OmniParser.
        
        Args:
            dom_elements: Elements extracted from the DOM.
            visual_detections: Elements detected visually on the screenshot.
            
        Returns:
            List of fused elements with combined coordinates and semantic information.
        """
        fused_elements = []
        matched_visual_indices = set()

        for dom_el in dom_elements:
            dom_bbox = dom_el.get("bbox")
            best_match_idx = -1
            best_overlap = 0.0

            # Find matching visual element by overlap
            for i, vis_el in enumerate(visual_detections):
                vis_bbox = vis_el.get("bbox")
                overlap = self._calculate_containment_or_overlap(dom_bbox, vis_bbox)
                
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match_idx = i

            # If a visual match is found with substantial overlap, merge them
            if best_match_idx != -1 and best_overlap > 0.4:
                matched_visual_indices.add(best_match_idx)
                vis_el = visual_detections[best_match_idx]
                
                # Merge: DOM semantics win, visual coordinates update or refine
                merged = {
                    **dom_el,
                    "confidence": vis_el.get("confidence", 0.9),
                    "visual_type": vis_el.get("type", "unknown"),
                    # Refine bbox to match visual borders
                    "bbox": vis_el.get("bbox")
                }
                fused_elements.append(merged)
            else:
                # Keep unmatched DOM elements
                fused_elements.append({
                    **dom_el,
                    "confidence": 1.0,
                    "visual_type": "unknown"
                })

        # Add unmatched visual elements (e.g. canvas elements, image-only buttons)
        for i, vis_el in enumerate(visual_detections):
            if i not in matched_visual_indices:
                fused_elements.append({
                    "id": f"vis-{i}",
                    "tag": "visual-node",
                    "role": vis_el.get("type", "unknown"),
                    "text": vis_el.get("text", ""),
                    "selector": "",
                    "bbox": vis_el.get("bbox"),
                    "enabled": True,
                    "parent_id": "",
                    "confidence": vis_el.get("confidence", 0.8),
                    "visual_type": vis_el.get("type")
                })

        return fused_elements

    def _calculate_containment_or_overlap(self, bbox_a: List[int], bbox_b: List[int]) -> float:
        """Calculates area of intersection normalized by the area of the smaller bounding box."""
        ax1, ay1, ax2, ay2 = bbox_a
        bx1, by1, bx2, by2 = bbox_b

        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)

        if ix1 >= ix2 or iy1 >= iy2:
            return 0.0

        inter_area = (ix2 - ix1) * (iy2 - iy1)
        area_a = (ax2 - ax1) * (ay2 - ay1)
        area_b = (bx2 - bx1) * (by2 - by1)
        
        smaller_area = min(area_a, area_b)
        if smaller_area <= 0:
            return 0.0
            
        return inter_area / smaller_area
