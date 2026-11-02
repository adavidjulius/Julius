"""
Perception Diff Engine Module

Detects changes between consecutive Scene Graph states to optimize planner payload size.
"""

import logging
from typing import Any, Dict, List, Optional
from .scene_graph import SceneGraph

logger = logging.getLogger(__name__)

class DiffEngine:
    def __init__(self) -> None:
        self.prev_state: Dict[str, Dict[str, Any]] = {}

    def diff(self, current_graph: SceneGraph) -> List[Dict[str, Any]]:
        """
        Compares the current Scene Graph with the previous stored state.
        
        Returns:
            List of change dicts:
            {
                "id": str,
                "type": "added" | "removed" | "modified",
                "changes": Dict[str, Tuple[Any, Any]]
            }
        """
        curr_state = {
            node_id: {
                "id": node.id,
                "role": node.role,
                "text": node.text,
                "bbox": node.bbox,
                "enabled": node.enabled,
                "selector": node.selector
            }
            for node_id, node in current_graph.nodes_map.items()
        }

        diffs = []

        # 1. Check for modified and removed elements
        for node_id, prev_node in self.prev_state.items():
            if node_id not in curr_state:
                diffs.append({
                    "id": node_id,
                    "type": "removed",
                    "changes": {}
                })
            else:
                curr_node = curr_state[node_id]
                node_changes = {}
                
                # Check fields for changes
                for field in ["text", "enabled", "bbox"]:
                    if prev_node[field] != curr_node[field]:
                        node_changes[field] = (prev_node[field], curr_node[field])
                        
                if node_changes:
                    diffs.append({
                        "id": node_id,
                        "type": "modified",
                        "changes": node_changes
                    })

        # 2. Check for newly added elements
        for node_id, curr_node in curr_state.items():
            if node_id not in self.prev_state:
                diffs.append({
                    "id": node_id,
                    "type": "added",
                    "changes": {
                        "role": (None, curr_node["role"]),
                        "text": (None, curr_node["text"]),
                        "bbox": (None, curr_node["bbox"])
                    }
                })

        # Persist the current state for the next frame comparison
        self.prev_state = curr_state
        return diffs
