import unittest
import os
import shutil
import tempfile
from src.action_executor import ActionExecutor

class TestActionExecutorStateful(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.executor = ActionExecutor(self.tmp_dir)

    def tearDown(self):
        self.executor.close()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @unittest.skipIf(os.name == "nt" and not shutil.which("bash"), "POSIX bash statefulness requires bash binary")
    def test_run_bash_stateful(self):
        # Run first command to set variable
        result = self.executor.run_bash("export FOO=bar")
        self.assertTrue(result.success)
        
        # Verify variable is preserved in second command
        result2 = self.executor.run_bash("echo $FOO")
        self.assertTrue(result2.success)
        self.assertEqual(result2.output.strip(), "bar")

        # Verify cd statefulness
        os.makedirs(os.path.join(self.tmp_dir, "nested_dir"), exist_ok=True)
        result3 = self.executor.run_bash("cd nested_dir")
        self.assertTrue(result3.success)
        
        result4 = self.executor.run_bash("pwd")
        self.assertTrue(result4.success)
        self.assertTrue(result4.output.strip().endswith("nested_dir"))

if __name__ == "__main__":
    unittest.main()
