"""
Layer 18 — Incremental Indexing & Layer 19 — Query API.

Main orchestrator facade unifying file change watching, incremental symbol/graph
indexing, and rich structured Query APIs for coding agents.
"""

from __future__ import annotations

import os
import hashlib
import logging
import threading
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple, Any

from .watcher import RepositoryWatcher
from .parser import LanguageParser, SymbolNode, ParsedASTNode
from .storage import PKBStorageEngine
from .graphs import PKBGraphEngine, GraphEdge, extract_graph_edges
from .metadata import PKBMetadataEngine, GitCommitInfo
from .retrieval import RetrievalEngine, RetrievalContext, ContextOptimizer, PKBMemorySystem
from src.security.secrets import get_secrets_manager

logger = logging.getLogger(__name__)


def compute_file_checksum(content: str) -> str:
    """Compute sha256 checksum for file content."""
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()


class PKBQueryAPI:
    """Layer 19 — High-level Query API exposing structured repository intelligence."""

    def __init__(self, pkb: ProjectKnowledgeBase) -> None:
        self.pkb = pkb

    def findSymbol(self, query: str) -> List[SymbolNode]:
        """Look up symbols matching a query string."""
        return self.pkb.storage.search_symbols_by_name(query)

    def findCallers(self, symbol_id: str, depth: int = 1) -> List[GraphEdge]:
        """Find callers of a target symbol."""
        return self.pkb.graphs.find_callers(symbol_id, depth=depth)

    def findCallees(self, symbol_id: str, depth: int = 1) -> List[GraphEdge]:
        """Find callees invoked by a symbol."""
        return self.pkb.graphs.find_callees(symbol_id, depth=depth)

    def findTests(self, symbol_name: str) -> List[str]:
        """Find unit tests covering a function or class."""
        return self.pkb.metadata.find_tests_for_symbol(symbol_name)

    def findDependencies(self, file_path: str) -> List[str]:
        """Find imports and module dependencies of a file."""
        return self.pkb.graphs.find_imports(file_path)

    def getGitProvenance(self, file_path: str, line_number: int = 1) -> Optional[GitCommitInfo]:
        """Get git author and blame info for code line."""
        return self.pkb.metadata.get_git_blame_for_line(file_path, line_number)

    def buildContext(self, query: str, max_tokens: int = 2500) -> RetrievalContext:
        """Build minimal optimized LLM prompt context for a prompt query."""
        self.pkb.retrieval.optimizer.max_token_budget = max_tokens
        return self.pkb.retrieval.retrieve(query)


class ProjectKnowledgeBase:
    """
    Compiler-grade Project Knowledge Base (PKB) Engine.
    Coordinates Repository Watcher, AST Parser, Storage, Graphs, Metadata, and Retrieval.
    """

    def __init__(self, workspace_root: str, db_name: str = "pkb.db") -> None:
        self.workspace_root = str(Path(workspace_root).resolve())
        julius_dir = Path(self.workspace_root) / ".julius"
        legacy_dir = Path(self.workspace_root) / ".julius"
        self.julius_dir = julius_dir if julius_dir.exists() or not legacy_dir.exists() else legacy_dir
        self.julius_dir.mkdir(parents=True, exist_ok=True)
        self.julius_dir = self.julius_dir  # Backward compatibility alias
        self.db_path = str(self.julius_dir / db_name)

        # Initialize core components
        self.parser = LanguageParser()
        self.storage = PKBStorageEngine(self.db_path)
        self.graphs = PKBGraphEngine(self.db_path)
        self.metadata = PKBMetadataEngine(self.workspace_root, self.db_path)
        self.retrieval = RetrievalEngine(self.storage, self.graphs, self.metadata)
        self.query_api = PKBQueryAPI(self)

        self.watcher = RepositoryWatcher(
            workspace_root=self.workspace_root,
            on_change_callback=self._handle_file_events,
        )
        self._lock = threading.Lock()

    def start(self, auto_index: bool = True) -> None:
        """Start PKB engine and file watcher."""
        if auto_index:
            self.index_workspace()
        self.watcher.start()
        logger.info(f"ProjectKnowledgeBase initialized & watching {self.workspace_root}")

    def stop(self) -> None:
        """Stop PKB file watcher."""
        self.watcher.stop()

    def index_workspace(self) -> Tuple[int, int]:
        """Perform initial workspace indexing of all files."""
        indexed_files = 0
        total_symbols = 0

        snapshot = self.watcher.scan_workspace()
        for rel_path in snapshot:
            symbols_count = self.index_file(rel_path)
            indexed_files += 1
            total_symbols += symbols_count

        logger.info(f"PKB full workspace index complete: {indexed_files} files, {total_symbols} symbols.")
        return indexed_files, total_symbols

    def index_file(self, rel_path: str) -> int:
        """Incrementally index a single file atomically."""
        full_path = Path(self.workspace_root) / rel_path
        if not full_path.exists():
            self.storage.remove_file(rel_path)
            self.graphs.remove_file_edges(rel_path)
            return 0

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                raw_content = f.read()
        except OSError:
            return 0

        # Layer 2: PKB Secrets Redaction Choke Point (T1.4)
        sec_mgr = get_secrets_manager()
        content = sec_mgr.choke_point_pkb(raw_content, full_path.name)

        checksum = compute_file_checksum(content)
        stat = full_path.stat()
        mtime = stat.st_mtime
        size_bytes = stat.st_size
        language = full_path.suffix.lstrip(".").lower() or "txt"

        # 1. Parse AST and extract symbols
        symbols, ast_nodes = self.parser.parse_file(rel_path, content)

        # 2. Persist File & Symbols to Storage
        self.storage.save_file_and_symbols(
            rel_path=rel_path,
            checksum=checksum,
            size_bytes=size_bytes,
            mtime=mtime,
            language=language,
            symbols=symbols,
            ast_nodes=ast_nodes,
        )

        # 3. Extract & update Graph Edges
        edges = extract_graph_edges(rel_path, content, symbols)
        self.graphs.update_file_edges(rel_path, edges)

        return len(symbols)

    def _handle_file_events(self, events: List[Tuple[str, str]]) -> None:
        """Handle debounced batch events from the repository watcher."""
        logger.debug(f"PKB processing incremental events: {events}")
        for rel_path, event_type in events:
            if event_type in {"created", "modified"}:
                self.index_file(rel_path)
            elif event_type == "deleted":
                self.storage.remove_file(rel_path)
                self.graphs.remove_file_edges(rel_path)
