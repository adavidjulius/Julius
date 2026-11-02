"""
Hybrid Dense + AST Semantic RAG Engine v2.

Phase 2.1 — Milestone 2.1: Replaces the 128-dim Feature Hash with dual indexing:
  - **Dense Vector Table**: ONNX embeddings (fastembed / BGE-small-en-v1.5 or
    MiniLM, 384 dimensions) for symbol-level semantic search.
  - **FTS5 / BM25 Table**: Full-text search for exact keyword, identifier, and
    path matching.

Scores are combined using Reciprocal Rank Fusion (RRF):
    RRF(d) = Σ_{m ∈ {Dense, BM25}} 1/(60 + rank_m(d))

Tree-sitter AST symbol extraction supports Python, TypeScript, Rust, C/C++, and Go.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import sqlite3
import struct
import time
from pathlib import Path
from typing import Any

import numpy as np

try:
    from .ast_parser import list_symbols, SymbolInfo
    _AST_AVAILABLE = True
except ImportError:
    _AST_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Embedding configuration ──────────────────────────────────────────────────

DENSE_DIM = 384          # Dimension for dense embeddings (MiniLM / BGE-small)
FALLBACK_DIM = 128       # Fallback Feature Hash dimension
RRF_K = 60               # RRF smoothing constant

# Supported file extensions for indexing
SUPPORTED_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.mjs',
    '.rs', '.go', '.c', '.cpp', '.cc', '.h', '.hpp',
    '.html', '.css', '.md', '.txt', '.sh', '.yml', '.yaml', '.json',
    '.toml', '.cfg', '.ini', '.sql',
}

STOP_WORDS = {
    # English stop words
    'how', 'do', 'i', 'the', 'a', 'an', 'and', 'or', 'but', 'if', 'then', 'else', 'for', 'while', 'with', 'about',
    'this', 'that', 'to', 'of', 'in', 'on', 'at', 'by', 'from', 'is', 'was', 'were', 'be', 'been', 'being', 'have',
    'has', 'had', 'does', 'did', 'some', 'any', 'all', 'both', 'each', 'few', 'more', 'most', 'other', 'such',
    # Programming keywords/noise
    'def', 'class', 'return', 'import', 'from', 'as', 'async', 'await', 'try', 'except', 'finally', 'pass', 'raise',
    'assert', 'global', 'nonlocal', 'lambda', 'yield', 'function', 'const', 'let', 'var', 'export', 'default',
}


# ── Dense Embedding Provider ─────────────────────────────────────────────────

class EmbeddingProvider:
    """Provides dense vector embeddings using fastembed (ONNX) or fallback Feature Hash.

    Attempts to load ``fastembed`` with ``BGE-small-en-v1.5`` (384-d).
    Falls back to a deterministic 128-d Feature Hash if fastembed is unavailable.
    """

    def __init__(self) -> None:
        self._model = None
        self._dim = FALLBACK_DIM
        self._use_fastembed = False

        try:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            self._dim = DENSE_DIM
            self._use_fastembed = True
            logger.info("EmbeddingProvider: using fastembed BGE-small-en-v1.5 (%d-d)", self._dim)
        except ImportError:
            logger.info("fastembed not available — falling back to Feature Hash (%d-d)", FALLBACK_DIM)
        except Exception as exc:
            logger.warning("fastembed init failed (%s) — falling back to Feature Hash", exc)

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def is_dense(self) -> bool:
        return self._use_fastembed

    def embed(self, text: str) -> np.ndarray:
        """Generate an embedding vector for the given text."""
        if self._use_fastembed and self._model is not None:
            return self._embed_dense(text)
        return self._embed_feature_hash(text)

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Batch-embed multiple texts."""
        if self._use_fastembed and self._model is not None:
            try:
                embeddings = list(self._model.embed(texts))
                return [np.array(e, dtype=np.float32) for e in embeddings]
            except Exception as exc:
                logger.warning("Batch embed failed: %s — falling back to individual", exc)

        return [self.embed(t) for t in texts]

    def _embed_dense(self, text: str) -> np.ndarray:
        """Generate dense embedding using fastembed."""
        try:
            embeddings = list(self._model.embed([text]))
            return np.array(embeddings[0], dtype=np.float32)
        except Exception as exc:
            logger.warning("Dense embed failed: %s", exc)
            return self._embed_feature_hash(text)

    def _embed_feature_hash(self, text: str) -> np.ndarray:
        """Fallback: 128-d Feature Hashing embedding."""
        vector = np.zeros(FALLBACK_DIM, dtype=np.float32)
        raw_words = re.findall(r'\b\w+\b', text.lower())

        words = []
        for w in raw_words:
            if w.isdigit() or len(w) <= 2:
                continue
            if w in STOP_WORDS:
                continue
            words.append(w)
            if '_' in w:
                parts = [p for p in w.split('_') if len(p) > 2 and p not in STOP_WORDS]
                words.extend(parts)
            camel_parts = re.findall(r'[a-z]+|[A-Z][a-z]*', w)
            if len(camel_parts) > 1:
                for p in camel_parts:
                    p_low = p.lower()
                    if len(p_low) > 2 and p_low not in STOP_WORDS:
                        words.append(p_low)

        if not words:
            return vector

        for word in words:
            h_bytes = hashlib.md5(word.encode('utf-8')).digest()
            h_val = int.from_bytes(h_bytes[:8], byteorder='big', signed=True)
            idx = abs(h_val) % FALLBACK_DIM
            val = 1.0 if h_val > 0 else -1.0
            vector[idx] += val

        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector


# ── RRF Score Combiner ────────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    dense_ranking: list[str],
    bm25_ranking: list[str],
    k: int = RRF_K,
) -> dict[str, float]:
    """Combine rankings using Reciprocal Rank Fusion.

    RRF(d) = Σ_{m ∈ {Dense, BM25}} 1/(k + rank_m(d))

    Args:
        dense_ranking: Document IDs ordered by dense similarity (best first).
        bm25_ranking: Document IDs ordered by BM25 score (best first).
        k: Smoothing constant (default: 60).

    Returns:
        Dict mapping document ID to RRF score.
    """
    scores: dict[str, float] = {}

    def _extract_id(item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("chunk_id") or item.get("id") or item)
        return str(item)

    for rank, item in enumerate(dense_ranking):
        doc_id = _extract_id(item)
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)

    for rank, item in enumerate(bm25_ranking):
        doc_id = _extract_id(item)
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)

    return scores


# ── Hybrid RAG Engine ─────────────────────────────────────────────────────────

class RagEngine:
    """
    Local context indexer and hybrid semantic search engine.

    Maintains dual indexing in ``.julius/rag.db``:
      - Dense vector embeddings for symbol-level semantic search
      - FTS5 full-text search for exact keyword / identifier matching

    Results are combined using Reciprocal Rank Fusion (RRF).
    """

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = str(os.path.abspath(workspace_root))
        julius_dir = Path(self.workspace_root) / '.julius'
        legacy_dir = Path(self.workspace_root) / '.julius'
        self.julius_dir = julius_dir if julius_dir.exists() or not legacy_dir.exists() else legacy_dir
        self.julius_dir.mkdir(parents=True, exist_ok=True)
        self.julius_dir = self.julius_dir  # Backward compatibility alias
        self.db_path = self.julius_dir / 'rag.db'

        self._embedder = EmbeddingProvider()
        self._init_db()

    @contextlib.contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @property
    def embedding_dim(self) -> int:
        return self._embedder.dim

    def _init_db(self) -> None:
        """Initialise RAG index tables with FTS5 support."""
        with self._connect() as conn:
            cursor = conn.cursor()

            # Table for file index tracking (for incremental indexing)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS indexed_files (
                    filepath TEXT PRIMARY KEY,
                    mtime REAL NOT NULL,
                    size INTEGER NOT NULL
                )
            """)

            # Table for text chunks and their dense vector embeddings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filepath TEXT NOT NULL,
                    chunk_type TEXT NOT NULL, -- 'symbol' or 'text'
                    symbol_name TEXT,
                    symbol_kind TEXT,         -- 'function', 'class', 'method', etc.
                    start_line INTEGER,
                    end_line INTEGER,
                    text_content TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    embedding_dim INTEGER NOT NULL DEFAULT 128,
                    FOREIGN KEY(filepath) REFERENCES indexed_files(filepath) ON DELETE CASCADE
                )
            """)

            # FTS5 virtual table for BM25 keyword search
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    filepath,
                    symbol_name,
                    text_content,
                    content='chunks',
                    content_rowid='id',
                    tokenize='porter unicode61'
                )
            """)

            # Triggers to keep FTS5 in sync with chunks table
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunks_fts(rowid, filepath, symbol_name, text_content)
                    VALUES (new.id, new.filepath, new.symbol_name, new.text_content);
                END
            """)

            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, filepath, symbol_name, text_content)
                    VALUES ('delete', old.id, old.filepath, old.symbol_name, old.text_content);
                END
            """)

            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, filepath, symbol_name, text_content)
                    VALUES ('delete', old.id, old.filepath, old.symbol_name, old.text_content);
                    INSERT INTO chunks_fts(rowid, filepath, symbol_name, text_content)
                    VALUES (new.id, new.filepath, new.symbol_name, new.text_content);
                END
            """)

            conn.commit()

    # ── Embedding helpers ─────────────────────────────────────────────────────

    def compute_embedding(self, text: str) -> np.ndarray:
        """Generate an embedding vector for the given text."""
        return self._embedder.embed(text)

    def serialize_vector(self, vec: np.ndarray) -> bytes:
        """Pack a float32 numpy array into raw bytes."""
        return struct.pack(f'{len(vec)}f', *vec)

    def deserialize_vector(self, data: bytes) -> np.ndarray:
        """Unpack raw bytes back into a float32 numpy array."""
        count = len(data) // 4
        floats = struct.unpack(f'{count}f', data)
        return np.array(floats, dtype=np.float32)

    # ── Indexing ──────────────────────────────────────────────────────────────

    def index_workspace(self) -> None:
        """
        Scan workspace recursively, chunk modified files, and update RAG database.
        """
        logger.info("RAG v2: Indexing workspace (embedding_dim=%d)...", self._embedder.dim)
        start_time = time.time()
        files_indexed = 0

        for root, dirs, files in os.walk(self.workspace_root):
            # Skip hidden and ignored folders
            dirs[:] = [d for d in dirs if d not in (
                '.git', '.venv', '__pycache__', 'node_modules', '.julius', '.julius',
                '.pytest_cache', '.mypy_cache', 'dist', 'build', '.tox',
            )]

            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue

                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.workspace_root)

                try:
                    stat = os.stat(full_path)
                    mtime = stat.st_mtime
                    size = stat.st_size
                except OSError:
                    continue

                # Check if file has changed since last indexing
                with self._connect() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT mtime, size FROM indexed_files WHERE filepath = ?", (rel_path,))
                    row = cursor.fetchone()

                    if row and row[0] == mtime and row[1] == size:
                        continue  # File has not changed

                    # File modified or new: remove old chunks first
                    cursor.execute("DELETE FROM indexed_files WHERE filepath = ?", (rel_path,))
                    cursor.execute("DELETE FROM chunks WHERE filepath = ?", (rel_path,))
                    conn.commit()

                # Generate new chunks and save
                try:
                    self._index_file(full_path, rel_path, mtime, size)
                    files_indexed += 1
                except Exception as e:
                    logger.error(f"RAG v2: Error indexing {rel_path}: {e}")

        elapsed = time.time() - start_time
        logger.info("RAG v2: Indexed %d files in %.2fs", files_indexed, elapsed)

    def _index_file(self, full_path: str, rel_path: str, mtime: float, size: int) -> None:
        """Slice file into logical chunks and insert into database."""
        try:
            with open(full_path, 'r', errors='ignore') as f:
                content = f.read()
        except Exception:
            return

        chunks_to_insert = []
        dim = self._embedder.dim

        # 1. Try AST-based symbol chunking
        symbols = []
        ext = os.path.splitext(full_path)[1].lower()
        if _AST_AVAILABLE and ext in ('.py', '.js', '.ts', '.jsx', '.tsx', '.mjs'):
            try:
                symbols = list_symbols(full_path)
            except Exception:
                pass

        lines = content.splitlines()

        if symbols:
            # Build batch texts for efficient embedding
            sym_texts = []
            sym_meta = []
            for sym in symbols:
                start = max(0, sym.start_line - 1)
                end = min(len(lines), sym.end_line)
                sym_text = "\n".join(lines[start:end])
                if sym_text.strip():
                    sym_texts.append(sym_text)
                    sym_meta.append(sym)

            # Batch embed symbols
            if sym_texts:
                embeddings = self._embedder.embed_batch(sym_texts)
                for sym_text, sym, vec in zip(sym_texts, sym_meta, embeddings):
                    chunks_to_insert.append((
                        rel_path, 'symbol', sym.name, sym.kind,
                        sym.start_line, sym.end_line,
                        sym_text, self.serialize_vector(vec), dim,
                    ))

        # 2. Add sliding window line-based text chunks (fallback and for non-code files)
        chunk_size_lines = 50
        overlap_lines = 10

        window_texts = []
        window_meta = []

        for i in range(0, len(lines), chunk_size_lines - overlap_lines):
            chunk_lines = lines[i:i + chunk_size_lines]
            text = "\n".join(chunk_lines).strip()
            if text:
                window_texts.append(text)
                window_meta.append((i + 1, i + len(chunk_lines)))
            if i + chunk_size_lines >= len(lines):
                break

        # Batch embed windows
        if window_texts:
            embeddings = self._embedder.embed_batch(window_texts)
            for text, (start, end), vec in zip(window_texts, window_meta, embeddings):
                chunks_to_insert.append((
                    rel_path, 'text', None, None,
                    start, end,
                    text, self.serialize_vector(vec), dim,
                ))

        # Save to SQLite
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO indexed_files (filepath, mtime, size) VALUES (?, ?, ?)",
                (rel_path, mtime, size)
            )
            for chunk in chunks_to_insert:
                cursor.execute(
                    """INSERT INTO chunks
                       (filepath, chunk_type, symbol_name, symbol_kind,
                        start_line, end_line, text_content, embedding, embedding_dim)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    chunk
                )
            conn.commit()

    # ── Search: Dense Vector ──────────────────────────────────────────────────

    def _search_dense(self, query: str, limit: int = 20) -> list[dict]:
        """Search using dense vector cosine similarity."""
        query_vec = self._embedder.embed(query)
        matches = []

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, filepath, chunk_type, symbol_name, symbol_kind, "
                "start_line, end_line, text_content, embedding, embedding_dim FROM chunks"
            )
            rows = cursor.fetchall()

            for row_id, filepath, chunk_type, symbol_name, symbol_kind, \
                    start_line, end_line, text_content, embedding_bytes, emb_dim in rows:
                chunk_vec = self.deserialize_vector(embedding_bytes)

                # Handle dimension mismatch gracefully
                if len(chunk_vec) != len(query_vec):
                    continue

                # Compute cosine similarity
                dot_product = np.dot(query_vec, chunk_vec)
                norm_query = np.linalg.norm(query_vec)
                norm_chunk = np.linalg.norm(chunk_vec)

                similarity = 0.0
                if norm_query > 0 and norm_chunk > 0:
                    similarity = float(dot_product / (norm_query * norm_chunk))

                matches.append({
                    "id": row_id,
                    "filepath": filepath,
                    "chunk_type": chunk_type,
                    "symbol_name": symbol_name,
                    "symbol_kind": symbol_kind,
                    "start_line": start_line,
                    "end_line": end_line,
                    "text_content": text_content,
                    "score": similarity,
                })

        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches[:limit]

    # ── Search: BM25 Full-Text ────────────────────────────────────────────────

    def _search_bm25(self, query: str, limit: int = 20) -> list[dict]:
        """Search using FTS5 BM25 ranking."""
        matches = []

        # Escape FTS5 special characters
        fts_query = re.sub(r'[^\w\s]', ' ', query).strip()
        if not fts_query:
            return []

        # Convert to FTS5 query format (OR between terms)
        terms = fts_query.split()
        fts_expression = " OR ".join(f'"{t}"' for t in terms if t)

        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT c.id, c.filepath, c.chunk_type, c.symbol_name, c.symbol_kind,
                           c.start_line, c.end_line, c.text_content,
                           bm25(chunks_fts) as rank
                    FROM chunks_fts
                    JOIN chunks c ON chunks_fts.rowid = c.id
                    WHERE chunks_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_expression, limit),
                )
                for row in cursor.fetchall():
                    matches.append({
                        "id": row[0],
                        "filepath": row[1],
                        "chunk_type": row[2],
                        "symbol_name": row[3],
                        "symbol_kind": row[4],
                        "start_line": row[5],
                        "end_line": row[6],
                        "text_content": row[7],
                        "score": -row[8],  # bm25() returns negative scores
                    })
        except Exception as exc:
            logger.warning("BM25 search error: %s", exc)

        return matches

    # ── Hybrid Search with RRF ────────────────────────────────────────────────

    def search_semantic(self, query: str, limit: int = 5) -> list[dict]:
        """
        Query the RAG index using hybrid Dense + BM25 with RRF fusion.

        Returns the top matching text chunks ranked by combined relevance.
        """
        start_time = time.time()

        # Get rankings from both retrieval methods
        dense_results = self._search_dense(query, limit=limit * 4)
        bm25_results = self._search_bm25(query, limit=limit * 4)

        # Build lookup dicts
        all_results: dict[int, dict] = {}
        for r in dense_results:
            all_results[r["id"]] = r
        for r in bm25_results:
            if r["id"] not in all_results:
                all_results[r["id"]] = r

        # Build ranked ID lists
        dense_ranking = [str(r["id"]) for r in dense_results]
        bm25_ranking = [str(r["id"]) for r in bm25_results]

        # Compute RRF scores
        rrf_scores = reciprocal_rank_fusion(dense_ranking, bm25_ranking)

        # Build final results
        final_results = []
        for doc_id_str, rrf_score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True):
            doc_id = int(doc_id_str)
            if doc_id in all_results:
                result = all_results[doc_id].copy()
                result["score"] = rrf_score
                result["retrieval_method"] = "hybrid_rrf"
                final_results.append(result)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info("RAG v2 search: query=%r, results=%d, latency=%.1fms", query[:50], len(final_results), elapsed_ms)

        return final_results[:limit]

    # ── Convenience: search symbols only ──────────────────────────────────────

    def search_symbols(self, query: str, limit: int = 10) -> list[dict]:
        """Search only symbol-type chunks (functions, classes, methods)."""
        results = self.search_semantic(query, limit=limit * 2)
        symbols = [r for r in results if r.get("chunk_type") == "symbol"]
        return symbols[:limit]

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return index statistics."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM indexed_files")
            files_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM chunks")
            chunks_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM chunks WHERE chunk_type = 'symbol'")
            symbols_count = cursor.fetchone()[0]

        return {
            "indexed_files": files_count,
            "files_indexed": files_count,
            "total_chunks": chunks_count,
            "symbol_chunks": symbols_count,
            "text_chunks": chunks_count - symbols_count,
            "embedding_dim": self._embedder.dim,
            "embedding_provider": "fastembed" if self._embedder.is_dense else "feature_hash",
            "db_path": str(self.db_path),
        }
