"""Tests for src/context_injector.py — workspace context generation."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from src.context_injector import build_workspace_context


class TestBuildWorkspaceContext(unittest.TestCase):
    """Tests for dynamic workspace context injection."""

    def setUp(self):
        """Create a temporary workspace directory for each test."""
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up the temporary workspace."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_directory_returns_empty(self):
        result = build_workspace_context(self.tmpdir)
        self.assertEqual(result, '')

    def test_nonexistent_directory_returns_empty(self):
        result = build_workspace_context('/nonexistent/path/that/does/not/exist')
        self.assertEqual(result, '')

    def test_detects_prd_json(self):
        prd = {'name': 'TestProject', 'version': '1.0.0', 'description': 'A test project'}
        (Path(self.tmpdir) / 'prd.json').write_text(json.dumps(prd))
        result = build_workspace_context(self.tmpdir)
        self.assertIn('TestProject', result)
        self.assertIn('1.0.0', result)
        self.assertIn('A test project', result)

    def test_detects_progress_txt(self):
        (Path(self.tmpdir) / 'progress.txt').write_text('Step 1: Done\nStep 2: In progress\n')
        result = build_workspace_context(self.tmpdir)
        self.assertIn('progress.txt', result)
        self.assertIn('2 lines', result)

    def test_detects_python_ecosystem(self):
        (Path(self.tmpdir) / 'requirements.txt').write_text('flask==2.0\n')
        result = build_workspace_context(self.tmpdir)
        self.assertIn('Python (pip)', result)

    def test_detects_node_ecosystem(self):
        (Path(self.tmpdir) / 'package.json').write_text('{}')
        result = build_workspace_context(self.tmpdir)
        self.assertIn('Node.js', result)

    def test_detects_git(self):
        (Path(self.tmpdir) / '.git').mkdir()
        result = build_workspace_context(self.tmpdir)
        self.assertIn('Git', result)

    def test_detects_dockerfile(self):
        (Path(self.tmpdir) / 'Dockerfile').write_text('FROM python:3.11\n')
        result = build_workspace_context(self.tmpdir)
        self.assertIn('Dockerfile', result)

    def test_detects_entry_points(self):
        (Path(self.tmpdir) / 'main.py').write_text('print("hello")\n')
        result = build_workspace_context(self.tmpdir)
        self.assertIn('main.py', result)

    def test_framework_environment_block(self):
        # Need at least one marker to trigger the framework block
        (Path(self.tmpdir) / '.git').mkdir()
        result = build_workspace_context(self.tmpdir)
        self.assertIn('CURRENT FRAMEWORK ENVIRONMENT', result)

    def test_multiple_ecosystems(self):
        (Path(self.tmpdir) / 'requirements.txt').write_text('flask\n')
        (Path(self.tmpdir) / 'package.json').write_text('{}')
        result = build_workspace_context(self.tmpdir)
        self.assertIn('Python (pip)', result)
        self.assertIn('Node.js', result)

    def test_malformed_prd_json(self):
        """Should not crash on invalid JSON in prd.json."""
        (Path(self.tmpdir) / 'prd.json').write_text('not valid json {{{')
        # Should still work, just skip the prd data
        result = build_workspace_context(self.tmpdir)
        self.assertNotIn('Unknown Project', result)  # Fallback shouldn't appear for parse errors


if __name__ == '__main__':
    unittest.main()
