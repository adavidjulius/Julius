import os
import shutil
import tempfile
import unittest
from src.rag_engine import RagEngine, reciprocal_rank_fusion


class TestRagEngine(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.engine = RagEngine(self.tmp_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_rag_indexing_and_search(self):
        # 1. Create a few test files
        python_file = os.path.join(self.tmp_dir, "calculator.py")
        with open(python_file, "w") as f:
            f.write("""
def add_numbers(a, b):
    \"\"\"Add two numbers together.\"\"\"
    return a + b

def subtract_numbers(a, b):
    \"\"\"Subtract two numbers.\"\"\"
    return a - b
""")

        readme_file = os.path.join(self.tmp_dir, "README.md")
        with open(readme_file, "w") as f:
            f.write("""
# Calculator Project
This project provides helper functions to add and subtract numbers.
Use standard Python modules.
""")

        # 2. Run indexer
        self.engine.index_workspace()

        # 3. Perform semantic searches
        results = self.engine.search_semantic("how do I add numbers?")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["filepath"], "calculator.py")
        self.assertIn("add_numbers", results[0]["text_content"])

        # Search for project overview
        results2 = self.engine.search_semantic("calculator project documentation")
        self.assertTrue(len(results2) > 0)
        self.assertEqual(results2[0]["filepath"], "README.md")
        self.assertIn("Calculator Project", results2[0]["text_content"])

    def test_reciprocal_rank_fusion(self):
        """Test RRF ranking algorithm properly fuses dense and BM25 result lists."""
        dense_results = [
            {"chunk_id": "c1", "filepath": "auth.py", "score": 0.95},
            {"chunk_id": "c2", "filepath": "user.py", "score": 0.85},
            {"chunk_id": "c3", "filepath": "token.py", "score": 0.75},
        ]
        bm25_results = [
            {"chunk_id": "c2", "filepath": "user.py", "score": 5.2},
            {"chunk_id": "c1", "filepath": "auth.py", "score": 4.1},
            {"chunk_id": "c4", "filepath": "db.py", "score": 2.0},
        ]

        fused = reciprocal_rank_fusion(dense_results, bm25_results, k=60)
        self.assertTrue(len(fused) > 0)
        # c1 and c2 should have the highest RRF scores since they appear in both result sets
        sorted_fused = sorted(fused.items(), key=lambda x: x[1], reverse=True)
        top_ids = [doc_id for doc_id, score in sorted_fused[:2]]
        self.assertIn("c1", top_ids)
        self.assertIn("c2", top_ids)

    def test_symbol_extraction_and_stats(self):
        """Test that symbols are parsed and stats are tracked."""
        py_file = os.path.join(self.tmp_dir, "service.py")
        with open(py_file, "w") as f:
            f.write("""
class AuthService:
    def verify_token(self, token: str) -> bool:
        return token == "secret"
""")

        self.engine.index_workspace()
        stats = self.engine.get_stats()
        self.assertGreater(stats["files_indexed"], 0)
        self.assertGreater(stats["total_chunks"], 0)

        # Symbol query
        sym_results = self.engine.search_symbols("AuthService")
        self.assertTrue(len(sym_results) > 0)
        self.assertIn("AuthService", [s["symbol_name"] for s in sym_results])


if __name__ == "__main__":
    unittest.main()
