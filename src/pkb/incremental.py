"""
Incremental AST Indexer for Julius PKB.

Monitors dirty files, extracts AST symbols and graph edges, and updates
PKB graph engine state atomically.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Set, Optional

from .graphs import PKBGraphEngine, extract_graph_edges

logger = logging.getLogger(__name__)


class IncrementalASTIndexer:
    """Manages incremental parsing and indexing of workspace file changes."""

    def __init__(self, workspace_root: str, graph_engine: PKBGraphEngine) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.graph_engine = graph_engine
        self._dirty_files: Set[str] = set()

    def mark_dirty(self, rel_path: str) -> None:
        """Mark file path as dirty requiring index update."""
        self._dirty_files.add(rel_path)
        logger.debug(f"Marked dirty file: {rel_path}")

    def process_dirty_files(self, symbol_parser_func: Optional[Any] = None) -> int:
        """
        Process queued dirty files, re-parsing ASTs and updating graph edges.
        Returns count of processed files.
        """
        if not self._dirty_files:
            return 0

        processed_count = 0
        queue = list(self._dirty_files)
        self._dirty_files.clear()

        for rel_path in queue:
            abs_path = self.workspace_root / rel_path
            if not abs_path.exists():
                self.graph_engine.remove_file_edges(rel_path)
                processed_count += 1
                continue

            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
                symbols = []
                if symbol_parser_func:
                    symbols = symbol_parser_func(rel_path, content)

                edges = extract_graph_edges(rel_path, content, symbols)
                self.graph_engine.update_file_edges(rel_path, edges)
                processed_count += 1
            except Exception as exc:
                logger.error(f"Error processing dirty file {rel_path}: {exc}")

        return processed_count
