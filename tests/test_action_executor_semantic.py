import unittest
import os
import shutil
import tempfile
from src.action_executor import ActionExecutor

class TestActionExecutorSemantic(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.executor = ActionExecutor(self.tmp_dir)

    def tearDown(self):
        self.executor.close()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_search_semantic_dispatch(self):
        # Create a document
        test_file = "guide.txt"
        self.executor.write_file(test_file, "This is a user manual for operating the Julius Agent.\nMake sure to run in non-interactive mode.\n")
        
        # Dispatch action
        res = self.executor.execute("search_semantic", {"query": "how to operate agent"})
        self.assertTrue(res.success)
        self.assertIn("guide.txt", res.output)
        self.assertIn("user manual", res.output)

if __name__ == "__main__":
    unittest.main()
