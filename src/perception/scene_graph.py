"""
Perception Scene Graph Module

Constructs a hierarchical graph of UI elements from flat element lists.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class SceneNode:
    def __init__(self, element_data: Dict[str, Any]) -> None:
        self.id = element_data.get("id", "root")
        self.role = element_data.get("role", "window")
        self.tag = element_data.get("tag", "div")
        self.text = element_data.get("text", "")
        self.bbox = element_data.get("bbox", [0, 0, 1024, 768])
        self.enabled = element_data.get("enabled", True)
        self.parent_id = element_data.get("parent_id", "")
        self.selector = element_data.get("selector", "")
        self.children: List[SceneNode] = []

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the node and its children recursively."""
        return {
            "id": self.id,
            "role": self.role,
            "tag": self.tag,
            "text": self.text,
            "bbox": self.bbox,
            "enabled": self.enabled,
            "children": [child.to_dict() for child in self.children]
        }

class SceneGraph:
    def __init__(self) -> None:
        self.root: Optional[SceneNode] = None
        self.nodes_map: Dict[str, SceneNode] = {}

    def build(self, elements: List[Dict[str, Any]]) -> None:
        """
        Builds the tree by mapping parent-child IDs and checking geometry.
        """
        self.nodes_map = {}
        
        # Create all nodes
        for el in elements:
            node = SceneNode(el)
            self.nodes_map[node.id] = node

        # Ensure a root window element exists
        if "root" not in self.nodes_map:
            root_el = {
                "id": "root",
                "role": "window",
                "tag": "body",
                "text": "Julius Workspace",
                "bbox": [0, 0, 1280, 900],
                "enabled": True,
                "parent_id": ""
            }
            self.root = SceneNode(root_el)
            self.nodes_map["root"] = self.root
        else:
            self.root = self.nodes_map["root"]

        # Link parent and child nodes
        for node_id, node in list(self.nodes_map.items()):
            if node_id == "root":
                continue
                
            p_id = node.parent_id
            if p_id and p_id in self.nodes_map:
                self.nodes_map[p_id].children.append(node)
            else:
                # If parent not found, attach directly to root window
                self.root.children.append(node)

    def find_node(self, node_id: str) -> Optional[SceneNode]:
        """Finds a node by ID."""
        return self.nodes_map.get(node_id)
