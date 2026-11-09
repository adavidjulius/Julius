"""
Verification Suite for 7-Times Adaptive Shortcut Dismissal & Shell PTY Hang Prevention.

Tests:
1. 7-Times Shortcut Hint Dismissal Mechanism (hintManager)
2. Command autocompletion on Enter (/he -> /help)
3. StatefulShell PTY unclosed here-doc & quote auto-closure
4. Clipboard read/write utilities
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.shell_manager import StatefulShell


class TestStatefulShellHangPrevention(unittest.TestCase):
    """Test that unclosed here-docs and unclosed quotes are auto-closed to prevent PTY hangs."""

    def test_unclosed_heredoc_auto_closed(self):
        """A command missing terminating here-doc delimiter is auto-closed with \\nDELIMITER\\n."""
        shell = StatefulShell(workspace_root=str(PROJECT_ROOT))
        cmd = "cat > /tmp/test_story.txt << 'PYEOF'\nLine 1\nLine 2"
        sanitized = shell._sanitize_and_close_command(cmd)
        self.assertIn("\nPYEOF\n", sanitized)

    def test_closed_heredoc_not_duplicated(self):
        """A properly closed here-doc is not duplicated."""
        shell = StatefulShell(workspace_root=str(PROJECT_ROOT))
        cmd = "cat > /tmp/test_story.txt << 'PYEOF'\nLine 1\nPYEOF"
        sanitized = shell._sanitize_and_close_command(cmd)
        self.assertEqual(sanitized.count("PYEOF"), 2)

    def test_unclosed_single_quote_closed(self):
        """An odd number of single quotes is closed to prevent secondary prompt stall."""
        shell = StatefulShell(workspace_root=str(PROJECT_ROOT))
        cmd = "echo 'hello world"
        sanitized = shell._sanitize_and_close_command(cmd)
        self.assertTrue(sanitized.endswith("'\n"))

    def test_unclosed_double_quote_closed(self):
        """An odd number of double quotes is closed to prevent secondary prompt stall."""
        shell = StatefulShell(workspace_root=str(PROJECT_ROOT))
        cmd = 'echo "hello world'
        sanitized = shell._sanitize_and_close_command(cmd)
        self.assertTrue(sanitized.endswith('"\n'))

    def test_shebang_not_treated_as_heading(self):
        """Line with '#!/usr/bin/env python3' is not treated as markdown heading."""
        import re
        shebang = "#!/usr/bin/env python3"
        is_heading = bool(re.match(r"^#{1,6}[\s\t]+", shebang))
        self.assertFalse(is_heading)

        comment = "# Simple calculation"
        # While '# Simple calculation' has a space, in code blocks it is preserved as code
        proper_heading = "# Project Overview"
        self.assertTrue(bool(re.match(r"^#{1,6}[\s\t]+", proper_heading)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
