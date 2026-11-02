"""
Unit tests for Phase 2 of Julius AI OS Architecture Blueprint Implementation.

Verifies:
1. ContextCompiler token budgeting, scoring, and minification.
2. IncrementalASTIndexer dirty-file queue processing.
3. Multi-tier memory integration into workspace context.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from src.context_compiler import ContextCompiler, SymbolScore
from src.pkb.graphs import PKBGraphEngine
from src.pkb.incremental import IncrementalASTIndexer
from src.context_injector import build_workspace_context
from src.memdir.multi_tier_memory import MultiTierMemoryManager


def test_context_compiler_scoring_and_minification():
    """Verify ContextCompiler score calculation, minification, and token packing."""
    compiler = ContextCompiler(default_token_budget=100)

    # Test code minification
    raw_code = '''
    def example_function():
        """This is a docstring that should be removed."""
        # Unimportant comment
        x = 42  # Keep this
        return x
    '''
    minified = compiler.minify_code_snippet(raw_code)
    assert 'docstring that should be removed' not in minified
    assert 'return x' in minified

    # Test score calculation
    score = compiler.calculate_score("SymA", pagerank=0.8, last_modified_delta_sec=100, similarity=0.9)
    assert score > 0.5

    # Test packing symbols into budget
    symbols_pool = [
        {
            "symbol_id": "func_alpha",
            "file_path": "src/alpha.py",
            "pagerank": 0.9,
            "last_modified_delta_sec": 10.0,
            "content": "def func_alpha():\n    return 1",
        },
        {
            "symbol_id": "func_beta",
            "file_path": "src/beta.py",
            "pagerank": 0.2,
            "last_modified_delta_sec": 7200.0,
            "content": "def func_beta():\n    return 2",
        },
    ]

    snapshot = compiler.compile_context("alpha function query", symbols_pool, token_budget=50)
    assert snapshot.total_tokens > 0
    assert "func_alpha" in snapshot.included_symbols
    assert snapshot.compiled_prompt.startswith("### Symbol:")


def test_incremental_ast_indexer():
    """Verify IncrementalASTIndexer queue processing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "pkb_inc.db"
        graph_engine = PKBGraphEngine(str(db_path))
        indexer = IncrementalASTIndexer(tmp_dir, graph_engine)

        # Create temporary file
        file_path = Path(tmp_dir) / "test_module.py"
        file_path.write_text("import os\n\ndef run():\n    pass\n", encoding="utf-8")

        indexer.mark_dirty("test_module.py")
        processed = indexer.process_dirty_files()
        assert processed == 1

        # Check that import edge was stored in graph engine
        imports = graph_engine.find_imports("test_module.py")
        assert "os" in imports


def test_workspace_context_memory_injection():
    """Verify MultiTierMemory injection into workspace context string."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create JULIUS.md rules file
        julius_md = Path(tmp_dir) / "JULIUS.md"
        julius_md.write_text("# Project Rules\nEnforce PEP 8 style guide.", encoding="utf-8")

        context = build_workspace_context(tmp_dir)
        assert "Project Memory Rules" in context or "Workspace Context" in context
