"""
Layer 5 — Call Graph, Layer 6 — Import Graph, Layer 7 — Dependency Graph, Layer 8 — Symbol Relationship Graph.

In-memory and SQLite-backed directed graph graph engines enabling instant
traversal of callers, callees, import relationships, and symbol dependencies.
"""

from __future__ import annotations

from contextlib import contextmanager
import re
import sqlite3
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphEdge:
    """Directed edge in the Symbol Relationship & Call Graph."""
    source_id: str
    target_id: str
    rel_type: str       # 'calls' | 'imports' | 'inherits' | 'implements' | 'uses' | 'overrides'
    file_path: str
    line_number: int = 0


class PKBGraphEngine:
    """
    Directed Graph engine handling Call Graph, Import Graph,
    Dependency Graph, and Symbol Relationship Graph.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._init_tables()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _init_tables(self) -> None:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()

            # Graph edges table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS graph_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    rel_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_number INTEGER NOT NULL
                )
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_edge_source ON graph_edges(source_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_edge_target ON graph_edges(target_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_edge_file ON graph_edges(file_path)")

            conn.commit()

    def update_file_edges(self, rel_path: str, edges: List[GraphEdge]) -> None:
        """Atomic replacement of graph edges for a given file."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM graph_edges WHERE file_path = ?", (rel_path,))
            for edge in edges:
                cursor.execute(
                    "INSERT INTO graph_edges (source_id, target_id, rel_type, file_path, line_number) VALUES (?, ?, ?, ?, ?)",
                    (edge.source_id, edge.target_id, edge.rel_type, edge.file_path, edge.line_number)
                )
            conn.commit()

    def remove_file_edges(self, rel_path: str) -> None:
        """Remove all graph edges for a deleted file."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM graph_edges WHERE file_path = ?", (rel_path,))
            conn.commit()

    def find_callers(self, target_symbol: str, depth: int = 1) -> List[GraphEdge]:
        """Find all symbols/files that invoke the given target symbol."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            results: List[GraphEdge] = []
            visited: Set[str] = set()
            frontier = {target_symbol}

            for _ in range(depth):
                if not frontier:
                    break
                next_frontier = set()
                for t in frontier:
                    if t in visited:
                        continue
                    visited.add(t)

                    cursor.execute(
                        "SELECT * FROM graph_edges WHERE target_id = ? AND rel_type = 'calls'",
                        (t,)
                    )
                    for row in cursor.fetchall():
                        edge = GraphEdge(
                            source_id=row["source_id"],
                            target_id=row["target_id"],
                            rel_type=row["rel_type"],
                            file_path=row["file_path"],
                            line_number=row["line_number"],
                        )
                        results.append(edge)
                        next_frontier.add(row["source_id"])

                frontier = next_frontier

            return results

    def find_callees(self, source_symbol: str, depth: int = 1) -> List[GraphEdge]:
        """Find all symbols/methods invoked by the given source symbol."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            results: List[GraphEdge] = []
            visited: Set[str] = set()
            frontier = {source_symbol}

            for _ in range(depth):
                if not frontier:
                    break
                next_frontier = set()
                for s in frontier:
                    if s in visited:
                        continue
                    visited.add(s)

                    cursor.execute(
                        "SELECT * FROM graph_edges WHERE source_id = ? AND rel_type = 'calls'",
                        (s,)
                    )
                    for row in cursor.fetchall():
                        edge = GraphEdge(
                            source_id=row["source_id"],
                            target_id=row["target_id"],
                            rel_type=row["rel_type"],
                            file_path=row["file_path"],
                            line_number=row["line_number"],
                        )
                        results.append(edge)
                        next_frontier.add(row["target_id"])

                frontier = next_frontier

            return results

    def find_imports(self, file_path: str) -> List[str]:
        """Find modules/files imported by the given file."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT target_id FROM graph_edges WHERE file_path = ? AND rel_type = 'imports'",
                (file_path,)
            )
            return [row["target_id"] for row in cursor.fetchall()]

    def find_dependents(self, module_name: str) -> List[str]:
        """Reverse import lookup: find all files that import this module."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT file_path FROM graph_edges WHERE target_id LIKE ? AND rel_type = 'imports'",
                (f"%{module_name}%",)
            )
            return list({row["file_path"] for row in cursor.fetchall()})

    def compute_pagerank(self, damping: float = 0.85, max_iter: int = 20) -> Dict[str, float]:
        """Compute PageRank scores over the symbol call/dependency graph."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT source_id FROM graph_edges UNION SELECT DISTINCT target_id FROM graph_edges")
            nodes = [row[0] for row in cursor.fetchall()]
            
            if not nodes:
                return {}
            
            n = len(nodes)
            ranks = {node: 1.0 / n for node in nodes}
            
            cursor.execute("SELECT source_id, target_id FROM graph_edges")
            out_edges: Dict[str, List[str]] = {node: [] for node in nodes}
            in_edges: Dict[str, List[str]] = {node: [] for node in nodes}
            
            for row in cursor.fetchall():
                src, tgt = row[0], row[1]
                if src in out_edges and tgt in in_edges:
                    out_edges[src].append(tgt)
                    in_edges[tgt].append(src)
            
            for _ in range(max_iter):
                new_ranks: Dict[str, float] = {}
                for node in nodes:
                    rank_sum = sum(
                        ranks[in_node] / len(out_edges[in_node])
                        for in_node in in_edges[node]
                        if out_edges[in_node]
                    )
                    new_ranks[node] = (1.0 - damping) / n + damping * rank_sum
                ranks = new_ranks

            return ranks



def extract_graph_edges(rel_path: str, content: str, symbols: List[Any]) -> List[GraphEdge]:
    """
    Extract call graph edges, import graph edges, and inheritance relationships
    from source code content.
    """
    edges: List[GraphEdge] = []
    lines = content.splitlines()
    ext = Path(rel_path).suffix.lower()

    import_pattern = re.compile(r"^\s*(?:from\s+([A-Za-z0-9_.]+)\s+import|import\s+([A-Za-z0-9_.]+))")
    ts_import_pattern = re.compile(r"^\s*import\s+.*?\s+from\s+['\"](.*?)['\"]")

    for line_idx, line in enumerate(lines, start=1):
        if ext == ".py":
            m = import_pattern.match(line)
            if m:
                target = m.group(1) or m.group(2)
                edges.append(GraphEdge(
                    source_id=rel_path,
                    target_id=target,
                    rel_type="imports",
                    file_path=rel_path,
                    line_number=line_idx,
                ))
        elif ext in {".js", ".ts", ".jsx", ".tsx"}:
            m = ts_import_pattern.match(line)
            if m:
                target = m.group(1)
                edges.append(GraphEdge(
                    source_id=rel_path,
                    target_id=target,
                    rel_type="imports",
                    file_path=rel_path,
                    line_number=line_idx,
                ))

    # Call Graph & Inheritance Extraction across symbols
    known_symbol_names = {sym.name: sym.symbol_id for sym in symbols if hasattr(sym, "name")}

    for sym in symbols:
        if not hasattr(sym, "source_code") or not sym.source_code:
            continue

        # Check for function calls within symbol source code
        for target_name, target_id in known_symbol_names.items():
            if target_name == sym.name:
                continue
            # Regex check for function call pattern: target_name(...)
            call_pattern = re.compile(rf"\b{re.escape(target_name)}\s*\(")
            if call_pattern.search(sym.source_code):
                edges.append(GraphEdge(
                    source_id=sym.symbol_id,
                    target_id=target_id,
                    rel_type="calls",
                    file_path=rel_path,
                    line_number=sym.start_line,
                ))

    return edges
