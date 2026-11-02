"""
Semantic memory: persisted project facts.
Key-value store of project invariants that rarely change.
"parser → always generates AST", "indexer → uses Tree-sitter", "cache → .julius/cache"
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .storage import MemoryStorage

logger = logging.getLogger(__name__)


class SemanticMemory:
    """
    Stores and retrieves semantic facts about the project.
    Facts are key-value pairs with categories and confidence scores.
    """

    def __init__(self, storage: MemoryStorage) -> None:
        self._storage = storage

    def record_fact(self, key: str, value: str, category: str = "general",
                    confidence: float = 1.0) -> None:
        """Store a semantic fact."""
        self._storage.save_fact(key, value, category, confidence)
        logger.info(f"SemanticMemory: Recorded fact '{key}' = '{value[:60]}'")

    def get_fact(self, key: str) -> Optional[Dict[str, Any]]:
        """Get a specific fact by key."""
        return self._storage.get_fact(key)

    def get_all_facts(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all facts, optionally filtered by category."""
        return self._storage.get_all_facts(category)

    def search_facts(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search facts by key, value, or category."""
        return self._storage.search_facts(query, limit=limit)

    def delete_fact(self, key: str) -> None:
        """Delete a fact by key."""
        self._storage.delete_fact(key)
        logger.info(f"SemanticMemory: Deleted fact '{key}'")

    def record_project_fact(self, key: str, value: str) -> None:
        """Convenience method for project-level facts."""
        self.record_fact(key, value, category="project")

    def record_architecture_fact(self, key: str, value: str) -> None:
        """Convenience method for architecture facts."""
        self.record_fact(key, value, category="architecture")

    def to_prompt_block(self, categories: Optional[List[str]] = None, limit: int = 20) -> str:
        """Render semantic facts as a compact prompt block."""
        if categories:
            facts = []
            for cat in categories:
                facts.extend(self.get_all_facts(category=cat))
        else:
            facts = self.get_all_facts()

        if not facts:
            return "<no_semantic_memory/>"

        lines = ["<semantic_memory>"]
        for f in facts[:limit]:
            lines.append(f"  [{f['category']}] {f['fact_key']}: {f['fact_value'][:100]}")
        lines.append("</semantic_memory>")
        return "\n".join(lines)
