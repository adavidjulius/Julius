"""
Layer 4 — AST Database, Layer 9 — File Database, Layer 14 — Semantic Embeddings.

SQLite persistence engine for workspace files, extracted AST symbols,
float32 vector embeddings, and secret redaction.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
import re
import sqlite3
import struct
import logging
import threading
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

from .parser import SymbolNode, ParsedASTNode

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 128

# Patterns to detect & redact secret credentials
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|passwd|auth[_-]?token|bearer)\s*[:=]\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*"),  # JWT
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


def redact_secrets(text: str, file_name: str = "") -> str:
    """Redact sensitive API keys, JWTs, and private keys from string content via SecretsManager."""
    try:
        from src.security.secrets import get_secrets_manager
        return get_secrets_manager().choke_point_pkb(text, file_name)
    except Exception:
        # Fallback to local regex redaction
        clean_text = text
        for pattern in SECRET_PATTERNS:
            clean_text = pattern.sub("[REDACTED_SECRET]", clean_text)
        return clean_text


def compute_feature_embedding(text: str, dim: int = EMBEDDING_DIM) -> np.ndarray:
    """
    Generate a 128-dimensional Feature Hashing embedding vector for code/text.
    Deterministic, fast, zero-dependency.
    """
    vec = np.zeros(dim, dtype=np.float32)
    tokens = re.findall(r"\w+", text.lower())
    if not tokens:
        return vec
    for token in tokens:
        idx = hash(token) % dim
        val = 1.0 if (hash(token) // dim) % 2 == 0 else -1.0
        vec[idx] += val
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


class _AutoClosingConnection:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._conn.close()
        except Exception:
            pass

    def __del__(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


class PKBStorageEngine:
    """
    Thread-safe SQLite storage repository for files, AST nodes, symbols,
    and vector embeddings.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_tables()

    def _get_connection(self) -> _AutoClosingConnection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return _AutoClosingConnection(conn)

    def _init_tables(self) -> None:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Layer 9 — File Database
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    file_path TEXT PRIMARY KEY,
                    checksum TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    last_modified REAL NOT NULL,
                    language TEXT NOT NULL,
                    indexed_at REAL NOT NULL
                )
            """)

            # Layer 3 — Symbol Database
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS symbols (
                    symbol_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    signature TEXT,
                    docstring TEXT,
                    parent_symbol TEXT,
                    visibility TEXT NOT NULL,
                    source_code TEXT NOT NULL,
                    FOREIGN KEY(file_path) REFERENCES files(file_path) ON DELETE CASCADE
                )
            """)

            # Layer 4 — AST Nodes Database
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ast_nodes (
                    node_id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    file_path TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    text TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    FOREIGN KEY(file_path) REFERENCES files(file_path) ON DELETE CASCADE
                )
            """)

            # Layer 14 — Semantic Embeddings Database
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    entity_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,  -- 'symbol' | 'file' | 'doc'
                    file_path TEXT NOT NULL,
                    vector BLOB NOT NULL
                )
            """)

            conn.commit()

    def save_file_and_symbols(
        self,
        rel_path: str,
        checksum: str,
        size_bytes: int,
        mtime: float,
        language: str,
        symbols: List[SymbolNode],
        ast_nodes: List[ParsedASTNode],
    ) -> None:
        """Atomic replacement of file metadata, AST nodes, symbols, and embeddings."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()

            # Clean previous indices for this file
            cursor.execute("DELETE FROM files WHERE file_path = ?", (rel_path,))
            cursor.execute("DELETE FROM symbols WHERE file_path = ?", (rel_path,))
            cursor.execute("DELETE FROM ast_nodes WHERE file_path = ?", (rel_path,))
            cursor.execute("DELETE FROM embeddings WHERE file_path = ?", (rel_path,))

            now = os.path.getmtime(self.db_path) if self.db_path.exists() else 0.0

            cursor.execute(
                "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?)",
                (rel_path, checksum, size_bytes, mtime, language, now)
            )

            for sym in symbols:
                clean_source = redact_secrets(sym.source_code, rel_path)
                clean_doc = redact_secrets(sym.docstring, rel_path) if sym.docstring else None
                clean_sig = redact_secrets(sym.signature, rel_path) if sym.signature else None
                cursor.execute(
                    """
                    INSERT INTO symbols (symbol_id, name, kind, file_path, start_line, end_line, signature, docstring, parent_symbol, visibility, source_code)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sym.symbol_id, sym.name, sym.kind, sym.file_path,
                        sym.start_line, sym.end_line, clean_sig,
                        clean_doc, sym.parent_symbol, sym.visibility,
                        clean_source
                    )
                )

                # Embed symbol
                vec = compute_feature_embedding(f"{sym.name} {sym.kind} {clean_doc or ''} {clean_source}")
                vec_blob = vec.tobytes()
                cursor.execute(
                    "INSERT INTO embeddings VALUES (?, ?, ?, ?)",
                    (sym.symbol_id, "symbol", rel_path, vec_blob)
                )

            for ast in ast_nodes:
                clean_ast_text = redact_secrets(ast.text, rel_path) if ast.text else ""
                cursor.execute(
                    "INSERT INTO ast_nodes VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (ast.node_id, ast.parent_id, rel_path, ast.kind, clean_ast_text, ast.start_line, ast.end_line)
                )

            conn.commit()

    def remove_file(self, rel_path: str) -> None:
        """Delete all indexed data associated with a removed file."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM files WHERE file_path = ?", (rel_path,))
            cursor.execute("DELETE FROM symbols WHERE file_path = ?", (rel_path,))
            cursor.execute("DELETE FROM ast_nodes WHERE file_path = ?", (rel_path,))
            cursor.execute("DELETE FROM embeddings WHERE file_path = ?", (rel_path,))
            conn.commit()

    def get_symbol_by_id(self, symbol_id: str) -> Optional[SymbolNode]:
        """Fetch a specific symbol by its unique Symbol ID."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM symbols WHERE symbol_id = ?", (symbol_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return SymbolNode(
                symbol_id=row["symbol_id"],
                name=row["name"],
                kind=row["kind"],
                file_path=row["file_path"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                signature=row["signature"],
                docstring=row["docstring"],
                parent_symbol=row["parent_symbol"],
                visibility=row["visibility"],
                source_code=row["source_code"],
            )

    def search_symbols_by_name(self, query: str, limit: int = 20) -> List[SymbolNode]:
        """Search symbols by exact or partial name."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM symbols WHERE name LIKE ? OR symbol_id LIKE ? LIMIT ?",
                (f"%{query}%", f"%{query}%", limit)
            )
            rows = cursor.fetchall()
            return [
                SymbolNode(
                    symbol_id=r["symbol_id"],
                    name=r["name"],
                    kind=r["kind"],
                    file_path=r["file_path"],
                    start_line=r["start_line"],
                    end_line=r["end_line"],
                    signature=r["signature"],
                    docstring=r["docstring"],
                    parent_symbol=r["parent_symbol"],
                    visibility=r["visibility"],
                    source_code=r["source_code"],
                )
                for r in rows
            ]

    def vector_semantic_search(self, query_text: str, top_k: int = 10) -> List[Tuple[SymbolNode, float]]:
        """Perform cosine similarity vector search over embedded symbols."""
        query_vec = compute_feature_embedding(query_text)
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT entity_id, vector FROM embeddings WHERE entity_type = 'symbol'")
            rows = cursor.fetchall()

            scored: List[Tuple[str, float]] = []
            for r in rows:
                vec_blob = r["vector"]
                vec = np.frombuffer(vec_blob, dtype=np.float32)
                sim = float(np.dot(query_vec, vec))
                scored.append((r["entity_id"], sim))

            scored.sort(key=lambda x: x[1], reverse=True)
            top_scored = scored[:top_k]

            results: List[Tuple[SymbolNode, float]] = []
            if top_scored:
                placeholders = ",".join("?" for _ in top_scored)
                sym_ids = [s[0] for s in top_scored]
                cursor.execute(f"SELECT * FROM symbols WHERE symbol_id IN ({placeholders})", sym_ids)
                sym_rows = {r["symbol_id"]: r for r in cursor.fetchall()}
                for sym_id, score in top_scored:
                    if sym_id in sym_rows:
                        r = sym_rows[sym_id]
                        sym = SymbolNode(
                            symbol_id=r["symbol_id"],
                            name=r["name"],
                            kind=r["kind"],
                            file_path=r["file_path"],
                            start_line=r["start_line"],
                            end_line=r["end_line"],
                            signature=r["signature"],
                            docstring=r["docstring"],
                            parent_symbol=r["parent_symbol"],
                            visibility=r["visibility"],
                            source_code=r["source_code"],
                        )
                        results.append((sym, score))

            return results
