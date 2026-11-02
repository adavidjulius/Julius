"""
Execution Graph: DAG-based task relationship tracking.
Tasks are linked to nodes/subjects. Instead of linear Task A → Task B → Task C,
store relationships like: Parser → [AST, Tree-sitter, Cache, PKB]
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from .storage import MemoryStorage

logger = logging.getLogger(__name__)


class ExecutionGraph:
    """
    DAG-based execution graph tracking relationships between tasks and subjects.
    Each node represents a subject (feature, module, concept).
    Each edge represents a relationship (depends_on, implements, fixes, etc.)
    """

    def __init__(self, storage: MemoryStorage) -> None:
        self._storage = storage

    def ensure_node(self, name: str, category: str = "general",
                    metadata: Optional[Dict[str, Any]] = None) -> str:
        """Create a node if it doesn't exist, or return existing. Returns node_id."""
        # Check if node already exists
        existing = self._find_node_by_name(name)
        if existing:
            return existing["node_id"]
        node_id = str(uuid.uuid4())
        self._storage.save_graph_node(node_id, name, category, metadata or {})
        logger.info(f"ExecutionGraph: Created node '{name}' ({category})")
        return node_id

    def _find_node_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        nodes = self._storage.get_all_graph_nodes()
        for n in nodes:
            if n["name"] == name:
                return n
        return None

    def add_edge(self, source_name: str, target_name: str,
                 relationship: str = "depends_on",
                 task_id: Optional[str] = None) -> None:
        """Add a directed edge between two named nodes. Creates nodes if needed."""
        source_id = self.ensure_node(source_name)
        target_id = self.ensure_node(target_name)
        self._storage.save_graph_edge(source_id, target_id, task_id, relationship)
        logger.info(f"ExecutionGraph: Edge '{source_name}' --[{relationship}]--> '{target_name}'")

    def get_children(self, node_name: str) -> List[Dict[str, Any]]:
        """Get all child nodes of a given node."""
        node = self._find_node_by_name(node_name)
        if not node:
            return []
        return self._storage.get_graph_children(node["node_id"])

    def get_parents(self, node_name: str) -> List[Dict[str, Any]]:
        """Get all parent nodes of a given node."""
        node = self._find_node_by_name(node_name)
        if not node:
            return []
        return self._storage.get_graph_parents(node["node_id"])

    def get_all_nodes(self) -> List[Dict[str, Any]]:
        """Get all nodes in the graph."""
        return self._storage.get_all_graph_nodes()

    def get_graph_by_category(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get nodes grouped by category."""
        nodes = self.get_all_nodes()
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for n in nodes:
            cat = n.get("category", "general")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(n)
        return by_category

    def to_prompt_block(self) -> str:
        """Render execution graph as a compact prompt block."""
        by_category = self.get_graph_by_category()
        if not by_category:
            return "<no_execution_graph/>"

        lines = ["<execution_graph>"]
        for category, nodes in sorted(by_category.items()):
            lines.append(f"  [{category}]")
            for n in nodes:
                children = self.get_children(n["name"])
                if children:
                    child_names = [c["name"] for c in children]
                    lines.append(f"    {n['name']} -> {', '.join(child_names)}")
                else:
                    lines.append(f"    {n['name']}")
        lines.append("</execution_graph>")
        return "\n".join(lines)
