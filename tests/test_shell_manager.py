import unittest
import os
import shutil
import tempfile
from src.shell_manager import StatefulShell

@unittest.skipIf(os.name == "nt" and not shutil.which("bash"), "StatefulShell PTY requires POSIX bash environment")
class TestShellManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_stateful_execution(self):
        shell = StatefulShell(self.tmp_dir)
        
        # Test basic command
        success, output = shell.execute_command("echo 'hello world'")
        self.assertTrue(success)
        self.assertEqual(output.strip(), "hello world")
        
        # Test statefulness (variables)
        success, _ = shell.execute_command("export MY_VAR=february")
        self.assertTrue(success)
        
        success, output = shell.execute_command("echo $MY_VAR")
        self.assertTrue(success)
        self.assertEqual(output.strip(), "february")
        
        # Test statefulness (cd)
        sub_dir = os.path.join(self.tmp_dir, "nested")
        os.makedirs(sub_dir, exist_ok=True)
        
        success, _ = shell.execute_command("cd nested")
        self.assertTrue(success)
        
        success, output = shell.execute_command("pwd")
        self.assertTrue(success)
        # Resolved paths might differ, but they should end with nested
        self.assertTrue(output.strip().endswith("nested"))
        
        shell.close()

    def test_large_heredoc_does_not_deadlock(self):
        """Verify multiline payloads exceeding typical PTY buffer size (>2KB) execute smoothly without deadlocks."""
        shell = StatefulShell(self.tmp_dir)
        lines = [f"# Code line {i}: " + ("x" * 60) for i in range(50)]
        payload = "\n".join(lines)
        target_file = os.path.join(self.tmp_dir, "large_code.py")
        cmd = f"cat > '{target_file}' <<'EOF'\n{payload}\nEOF\nwc -l '{target_file}'"

        success, output = shell.execute_command(cmd, timeout=5)
        self.assertTrue(success)
        self.assertIn("50", output)
        self.assertTrue(os.path.exists(target_file))
        with open(target_file) as f:
            content = f.read()
        self.assertEqual(len(content.splitlines()), 50)
        shell.close()

    def test_multiline_heredoc_with_chained_commands(self):
        """Verify commands like 'cd ... && cat >> file <<EOF ... EOF\nwc -l' execute correctly."""
        shell = StatefulShell(self.tmp_dir)
        script_path = os.path.join(self.tmp_dir, "crawler.py")
        cmd = f"""cd '{self.tmp_dir}' && cat >> '{script_path}' <<'EOF'
async def crawl(self, start_url):
    return "done"
EOF
wc -l '{script_path}'"""
        success, output = shell.execute_command(cmd, timeout=5)
        self.assertTrue(success)
        self.assertIn("2", output)
        shell.close()

    def test_history_expansion_suppressed(self):
        """Verify exclamation marks do not trigger bash history expansion errors."""
        shell = StatefulShell(self.tmp_dir)
        success, output = shell.execute_command('echo "Hello World!"', timeout=5)
        self.assertTrue(success)
        self.assertIn("Hello World!", output)
        shell.close()

if __name__ == "__main__":
    unittest.main()
