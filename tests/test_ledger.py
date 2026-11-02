import unittest
import os
import shutil
import tempfile
from src.ledger import Ledger

class TestLedger(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.ledger = Ledger(self.tmp_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_undo_restores_file(self):
        # Create an initial file
        test_file = os.path.join(self.tmp_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("Original Content")

        # Start action
        action_id = self.ledger.start_action("Edit file")
        
        # Take snapshot before modification
        self.ledger.snapshot_file(action_id, test_file)
        
        # Modify the file
        with open(test_file, "w") as f:
            f.write("Modified Content")

        # Run undo
        reverted = self.ledger.undo_last_action()
        self.assertEqual(len(reverted), 1)
        self.assertTrue(reverted[0].startswith("Restored:"))
        
        # Verify content is back to original
        with open(test_file, "r") as f:
            content = f.read()
        self.assertEqual(content, "Original Content")

    def test_undo_deletes_created_file(self):
        # Start action
        action_id = self.ledger.start_action("Create file")
        
        # File does not exist yet, snapshot will record it as is_deleted=1
        new_file = os.path.join(self.tmp_dir, "new.txt")
        self.ledger.snapshot_file(action_id, new_file)
        
        # Create the file
        with open(new_file, "w") as f:
            f.write("New File Content")

        self.assertTrue(os.path.exists(new_file))

        # Run undo
        reverted = self.ledger.undo_last_action()
        self.assertEqual(len(reverted), 1)
        self.assertTrue(reverted[0].startswith("Deleted:"))
        
        # Verify file is deleted
        self.assertFalse(os.path.exists(new_file))

if __name__ == "__main__":
    unittest.main()
