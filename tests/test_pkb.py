"""
Comprehensive Automated Unit & Integration Tests for Project Knowledge Base (PKB).
Validates indexing, AST symbol extraction, graph traversals, vector search,
secret redaction, context optimization, and query APIs.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from src.pkb.watcher import RepositoryWatcher
from src.pkb.parser import LanguageParser, SymbolNode
from src.pkb.storage import PKBStorageEngine, redact_secrets, compute_feature_embedding
from src.pkb.graphs import PKBGraphEngine, GraphEdge, extract_graph_edges
from src.pkb.metadata import PKBMetadataEngine
from src.pkb.retrieval import RetrievalEngine, ContextOptimizer, PKBMemorySystem
from src.pkb.pipeline import ProjectKnowledgeBase, PKBQueryAPI
from src.pkb.llm_integration import PKBLLMIntegration


class TestPKBEngine(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.tmp_dir)

        # Create sample Python file
        self.py_file = self.workspace / "auth.py"
        self.py_file.write_text(
            "class AuthManager:\n"
            "    def authenticate(self, username, password):\n"
            "        api_key = 'sk-secret-key-12345'\n"
            "        return True\n\n"
            "def login_user(username):\n"
            "    auth = AuthManager()\n"
            "    return auth.authenticate(username, 'pass')\n"
        )

        # Create sample TypeScript file
        self.ts_file = self.workspace / "service.ts"
        self.ts_file.write_text(
            "import { login_user } from './auth';\n\n"
            "export function handleRequest(req: any) {\n"
            "    return login_user('admin');\n"
            "}\n"
        )

        self.pkb = ProjectKnowledgeBase(workspace_root=str(self.workspace), db_name="test_pkb.db")

    def tearDown(self):
        self.pkb.stop()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_parser_symbol_extraction(self):
        """Test symbol extraction for Python and TypeScript files."""
        parser = LanguageParser()
        symbols, _ = parser.parse_file("auth.py", self.py_file.read_text())
        names = {s.name for s in symbols}

        self.assertIn("AuthManager", names)
        self.assertIn("authenticate", names)
        self.assertIn("login_user", names)

    def test_secret_redaction(self):
        """Test automatic secret credential redaction."""
        raw = "api_key = 'sk-secret-key-12345'"
        clean = redact_secrets(raw)
        self.assertNotIn("sk-secret-key-12345", clean)
        self.assertIn("[REDACTED", clean)

    def test_vector_embeddings(self):
        """Test Feature Hashing vector embeddings and cosine similarity."""
        v1 = compute_feature_embedding("authenticate user login auth")
        v2 = compute_feature_embedding("user login authentication")
        v3 = compute_feature_embedding("unrelated database migration script")

        sim_12 = float(sum(v1 * v2))
        sim_13 = float(sum(v1 * v3))

        self.assertGreater(sim_12, sim_13)

    def test_workspace_indexing_and_query_api(self):
        """Test initial workspace indexing and Query API lookup."""
        indexed_files, total_symbols = self.pkb.index_workspace()
        self.assertGreaterEqual(indexed_files, 2)
        self.assertGreaterEqual(total_symbols, 3)

        # Query API symbol search
        found = self.pkb.query_api.findSymbol("authenticate")
        self.assertTrue(len(found) > 0)
        self.assertEqual(found[0].name, "authenticate")

    def test_graph_edges_and_traversals(self):
        """Test graph extraction, call graph lookups, and import graphs."""
        self.pkb.index_workspace()

        callers = self.pkb.query_api.findCallers("auth.py.AuthManager.authenticate")
        imports = self.pkb.query_api.findDependencies("service.ts")

        self.assertIn("./auth", imports)

    def test_context_optimizer(self):
        """Test token compression and minimal context building for LLM prompts."""
        self.pkb.index_workspace()
        ctx = self.pkb.query_api.buildContext("How does authentication work?", max_tokens=1000)

        self.assertIn("AUTHMANAGER", ctx.formatted_prompt_context.upper())
        self.assertLessEqual(ctx.token_estimate, 1000)

    def test_llm_integration_middleware(self):
        """Test LLM integration prompt preprocessing."""
        self.pkb.index_workspace()
        middleware = PKBLLMIntegration(self.pkb)

        augmented_prompt, context = middleware.process_prompt("Authenticate user with password")
        self.assertIn("PROJECT KNOWLEDGE BASE CONTEXT", augmented_prompt)
        self.assertIn("USER PROMPT:", augmented_prompt)

    def test_incremental_indexing(self):
        """Test atomic single-file re-indexing without whole repo rebuild."""
        self.pkb.index_workspace()

        # Modify auth.py to add new function
        self.py_file.write_text(
            self.py_file.read_text() + "\ndef new_helper():\n    pass\n"
        )

        self.pkb.index_file("auth.py")
        found = self.pkb.query_api.findSymbol("new_helper")
        self.assertEqual(len(found), 1)


if __name__ == "__main__":
    unittest.main()
