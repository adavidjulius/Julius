import unittest
import os
import shutil
import tempfile
from src.action_executor import ActionExecutor

class TestActionExecutorLedger(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.executor = ActionExecutor(self.tmp_dir)

    def tearDown(self):
        self.executor.close()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_write_and_edit_undo(self):
        # 1. Start action boundary
        self.executor.start_new_action("Test Action Flow")
        
        # 2. Write file
        test_file = "info.txt"
        res = self.executor.write_file(test_file, "Line 1\n")
        self.assertTrue(res.success)
        
        # 3. Edit file
        res = self.executor.edit_file(test_file, "Line 1\n", "Line 1 Edited\n")
        self.assertTrue(res.success)
        
        # Verify content modified
        abs_path = os.path.join(self.tmp_dir, test_file)
        with open(abs_path, 'r') as f:
            self.assertEqual(f.read(), "Line 1 Edited\n")
            
        # 4. Revert
        reverted = self.executor.undo_last_action()
        self.assertEqual(len(reverted), 1)  # modified file (original was created inside action, wait, actually we snapshotted the non-existence first!)
        # Let's verify that the file is completely gone because it was created during the action
        self.assertFalse(os.path.exists(abs_path))

if __name__ == "__main__":
    unittest.main()
