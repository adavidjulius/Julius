"""
Perception Accessibility Tree Module

Parses and normalizes the accessibility tree from the browser snapshot.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class AccessibilityTreeParser:
    def parse(self, ax_snapshot: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Parses and flattens the nested accessibility tree snapshot into a list of normalized node dicts.
        """
        if not ax_snapshot:
            return []

        nodes = []
        self._traverse(ax_snapshot, None, nodes)
        return nodes

    def _traverse(self, node: Dict[str, Any], parent_id: Optional[str], nodes_list: List[Dict[str, Any]]) -> None:
        """Recursive traversal helper to flatten and index the accessibility tree."""
        node_id = f"ax-{len(nodes_list)}"
        
        normalized_node = {
            "id": node_id,
            "role": node.get("role", "unknown"),
            "text": node.get("name", "").strip(),
            "value": node.get("value", ""),
            "description": node.get("description", ""),
            "checked": node.get("checked", None),
            "disabled": node.get("disabled", False),
            "parent_id": parent_id,
            "children_count": len(node.get("children", []))
        }
        
        nodes_list.append(normalized_node)
        
        for child in node.get("children", []):
            self._traverse(child, node_id, nodes_list)
