"""
Runtime World Model Module

Maintains a persistent state model of the browser workspace over time, tracking elements, values, and focus states.
"""

import logging
import time
from typing import Any, Dict, List, Optional
from ..perception.scene_graph import SceneGraph

logger = logging.getLogger(__name__)

class WorldModel:
    def __init__(self) -> None:
        self.current_graph: Optional[SceneGraph] = None
        self.last_update_time: float = 0.0
        self.focus_node_id: Optional[str] = None
        self.history: List[Dict[str, Any]] = []

    def update(self, scene_graph: SceneGraph, diffs: List[Dict[str, Any]]) -> None:
        """
        Updates the persistent world state with a new frame's Scene Graph and diff payload.
        """
        self.current_graph = scene_graph
        self.last_update_time = time.time()
        
        # Apply diffs/state changes to track element history or focus
        for d in diffs:
            el_id = d.get("id")
            change_type = d.get("type")
            changes = d.get("changes", {})
            
            if change_type == "modified":
                logger.debug("WorldModel updated: Element %s modified: %s", el_id, changes)
                # Keep tracking history
                self.history.append({
                    "timestamp": self.last_update_time,
                    "id": el_id,
                    "changes": changes
                })
                
                # Update focus if input is selected/modified
                if "text" in changes:
                    self.focus_node_id = el_id

        # Cap history length to avoid memory growth
        if len(self.history) > 200:
            self.history = self.history[-200:]
            
        logger.info("WorldModel updated. Total tracked elements: %d", len(scene_graph.nodes_map) if scene_graph else 0)

    def get_element(self, element_id: str) -> Optional[Any]:
        """Gets an element from the active Scene Graph."""
        if self.current_graph:
            return self.current_graph.find_node(element_id)
        return None
