"""Tests for Julius 2.0 Operating Manual, batch execution, and extended tools."""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.action_executor import ActionExecutor, ActionResult
from src.agent_prompts import (
    SYSTEM_PROMPT,
    CORE_ACTIONS,
    EXTENDED_ACTIONS,
    VALID_ACTIONS,
    TERMINAL_ACTIONS,
    MAX_PARALLEL_ACTIONS,
    extract_json_block,
    normalize_actions,
    format_batch_results,
    build_initial_prompt,
    build_step_prompt,
)
from src.response_validator import validate_action


class TestJulius2PromptsAndParsing(unittest.TestCase):
    """Test Julius 2.0 prompt definitions, JSON extraction, and normalization."""

    def test_system_prompt_identity_and_version(self):
        self.assertIn("JULIUS — OPERATING MANUAL", SYSTEM_PROMPT)
        self.assertIn("Version 2.0", SYSTEM_PROMPT)
        self.assertIn("Your name is Julius", SYSTEM_PROMPT)
        self.assertIn("PART 5 — PARALLEL EXECUTION AND SPEED", SYSTEM_PROMPT)
        self.assertIn("PART 4 — TOOL REFERENCE", SYSTEM_PROMPT)

    def test_action_registries(self):
        self.assertIn("run_bash", CORE_ACTIONS)
        self.assertIn("read_file", CORE_ACTIONS)
        self.assertIn("multi_edit", EXTENDED_ACTIONS)
        self.assertIn("glob", EXTENDED_ACTIONS)
        self.assertIn("run_tests", EXTENDED_ACTIONS)
        self.assertIn("todo", EXTENDED_ACTIONS)
        self.assertIn("checkpoint", EXTENDED_ACTIONS)
        self.assertIn("fetch_url", EXTENDED_ACTIONS)
        self.assertIn("run_python", EXTENDED_ACTIONS)
        self.assertTrue(EXTENDED_ACTIONS.issubset(VALID_ACTIONS))
        self.assertEqual(MAX_PARALLEL_ACTIONS, 8)

    def test_extract_json_block_fenced(self):
        text = 'Here is the plan:\n```json\n{"thought": "test", "action": "run_bash", "args": {"command": "ls"}}\n```'
        data = extract_json_block(text)
        self.assertEqual(data["action"], "run_bash")
        self.assertEqual(data["args"]["command"], "ls")

    def test_extract_json_block_bare(self):
        text = '{"thought": "bare", "action": "done", "args": {"summary": "Finished."}}'
        data = extract_json_block(text)
        self.assertEqual(data["action"], "done")
        self.assertEqual(data["thought"], "bare")

    def test_extract_json_block_with_surrounding_text(self):
        text = 'Prefix text {"thought": "surrounded", "action": "converse", "args": {"message": "hi"}} trailing notes'
        data = extract_json_block(text)
        self.assertEqual(data["action"], "converse")

    def test_normalize_actions_shape_a(self):
        payload = {"thought": "reasoning", "action": "read_file", "args": {"path": "main.py"}}
        actions, mode = normalize_actions(payload)
        self.assertEqual(mode, "sequential")
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action"], "read_file")
        self.assertEqual(actions[0]["args"]["path"], "main.py")
        self.assertEqual(actions[0]["id"], "a1")

    def test_normalize_actions_shape_b_parallel(self):
        payload = {
            "thought": "parallel reads",
            "actions": [
                {"id": "r1", "action": "read_file", "args": {"path": "a.py"}},
                {"id": "r2", "action": "read_file", "args": {"path": "b.py"}},
            ],
            "mode": "parallel",
        }
        actions, mode = normalize_actions(payload)
        self.assertEqual(mode, "parallel")
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]["id"], "r1")
        self.assertEqual(actions[1]["id"], "r2")

    def test_normalize_actions_shape_b_sequential(self):
        payload = {
            "thought": "sequential steps",
            "actions": [
                {"id": "s1", "action": "run_bash", "args": {"command": "mkdir test"}},
                {"id": "s2", "action": "write_file", "args": {"path": "test/f.txt", "content": "hi"}},
            ],
            "mode": "sequential",
        }
        actions, mode = normalize_actions(payload)
        self.assertEqual(mode, "sequential")
        self.assertEqual(len(actions), 2)

    def test_normalize_actions_duplicate_writes_in_parallel_fails(self):
        payload = {
            "thought": "conflict",
            "actions": [
                {"action": "edit_file", "args": {"path": "main.py", "old_text": "a", "new_text": "b"}},
                {"action": "edit_file", "args": {"path": "main.py", "old_text": "c", "new_text": "d"}},
            ],
            "mode": "parallel",
        }
        with self.assertRaises(ValueError) as ctx:
            normalize_actions(payload)
        self.assertIn("Two writes to main.py", str(ctx.exception))

    def test_normalize_actions_terminal_in_batch_fails(self):
        payload = {
            "thought": "invalid batch",
            "actions": [
                {"action": "read_file", "args": {"path": "a.py"}},
                {"action": "done", "args": {"summary": "Done."}},
            ],
            "mode": "parallel",
        }
        with self.assertRaises(ValueError) as ctx:
            normalize_actions(payload)
        self.assertIn("Terminal actions", str(ctx.exception))

    def test_format_batch_results(self):
        results = [
            {"id": "a1", "action": "read_file", "ok": True, "output": "def foo(): pass"},
            {"id": "a2", "action": "run_bash", "ok": False, "output": "command not found"},
        ]
        formatted = format_batch_results(results)
        self.assertIn("[a1] read_file -> ok", formatted)
        self.assertIn("def foo(): pass", formatted)
        self.assertIn("[a2] run_bash -> FAILED", formatted)
        self.assertIn("command not found", formatted)


class TestResponseValidatorBatch(unittest.TestCase):
    """Test validate_action with Shape B batches and extended tools."""

    def test_valid_batch_parallel(self):
        data = {
            "thought": "read two files",
            "actions": [
                {"id": "a1", "action": "read_file", "args": {"path": "x.py"}},
                {"id": "a2", "action": "glob", "args": {"pattern": "*.py"}},
            ],
            "mode": "parallel",
        }
        is_valid, err = validate_action(data)
        self.assertTrue(is_valid)
        self.assertEqual(err, "")

    def test_valid_extended_actions_single(self):
        for act, args in [
            ("multi_edit", {"path": "a.py", "edits": []}),
            ("glob", {"pattern": "*.py"}),
            ("run_tests", {}),
            ("todo", {"items": []}),
            ("checkpoint", {"action": "create"}),
            ("fetch_url", {"url": "https://example.com"}),
            ("run_python", {"code": "print(1)"}),
        ]:
            data = {"thought": "t", "action": act, "args": args}
            is_valid, err = validate_action(data)
            self.assertTrue(is_valid, f"Action {act} failed validation: {err}")

    def test_batch_exceeds_max_limit(self):
        items = [{"action": "read_file", "args": {"path": f"file_{i}.py"}} for i in range(10)]
        data = {"thought": "too many", "actions": items, "mode": "parallel"}
        is_valid, err = validate_action(data)
        self.assertFalse(is_valid)
        self.assertIn("At most 8 actions", err)


class TestExtendedToolsExecution(unittest.TestCase):
    """Test execution of the extended tools in ActionExecutor."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = self.temp_dir.name
        self.executor = ActionExecutor(self.workspace, use_docker_sandbox=False)

    def tearDown(self):
        self.executor.close()
        self.temp_dir.cleanup()

    def test_multi_edit_atomic_success(self):
        test_file = Path(self.workspace) / "test_doc.txt"
        test_file.write_text("Hello World\nLine 2: foo\nLine 3: bar\n")

        edits = [
            {"old_text": "Hello World", "new_text": "Hello Julius"},
            {"old_text": "foo", "new_text": "FOO_UPDATED"},
            {"old_text": "bar", "new_text": "BAR_UPDATED"},
        ]
        res = self.executor.execute("multi_edit", {"path": "test_doc.txt", "edits": edits})
        self.assertTrue(res.success)
        self.assertIn("Applied 3 edit(s) atomically", res.output)

        content = test_file.read_text()
        self.assertIn("Hello Julius", content)
        self.assertIn("FOO_UPDATED", content)
        self.assertIn("BAR_UPDATED", content)

    def test_multi_edit_atomic_rollback_on_failure(self):
        test_file = Path(self.workspace) / "rollback_test.txt"
        original = "Unique line 1\nTarget line 2\nTarget line 2\n"
        test_file.write_text(original)

        # Edit 1 succeeds, Edit 2 matches multiple times (ambiguous) -> should abort completely
        edits = [
            {"old_text": "Unique line 1", "new_text": "Modified line 1"},
            {"old_text": "Target line 2", "new_text": "Modified line 2"},
        ]
        res = self.executor.execute("multi_edit", {"path": "rollback_test.txt", "edits": edits})
        self.assertFalse(res.success)
        self.assertIn("matched 2 times", res.output)
        # Content must remain completely unchanged
        self.assertEqual(test_file.read_text(), original)

    def test_glob_tool(self):
        (Path(self.workspace) / "src").mkdir()
        (Path(self.workspace) / "src" / "a.py").write_text("a = 1")
        (Path(self.workspace) / "src" / "b.py").write_text("b = 2")
        (Path(self.workspace) / "src" / "test.txt").write_text("text")

        res = self.executor.execute("glob", {"pattern": "**/*.py"})
        self.assertTrue(res.success)
        self.assertIn("src/a.py", res.output)
        self.assertIn("src/b.py", res.output)
        self.assertNotIn("test.txt", res.output)

    def test_run_python_tool(self):
        code = "import sys\nprint('Python version:', sys.version_info[0])\nprint(2 + 2)"
        res = self.executor.execute("run_python", {"code": code})
        self.assertTrue(res.success)
        self.assertIn("4", res.output)
        self.assertIn("Python version:", res.output)

    def test_run_python_tool_error(self):
        code = "raise ValueError('Custom Julius Error')"
        res = self.executor.execute("run_python", {"code": code})
        self.assertFalse(res.success)
        self.assertIn("Custom Julius Error", res.output)

    def test_todo_tool(self):
        items = [
            {"id": "t1", "text": "Set up project", "status": "done"},
            {"id": "t2", "text": "Implement feature", "status": "in_progress"},
            {"id": "t3", "text": "Write tests", "status": "pending"},
        ]
        res = self.executor.execute("todo", {"items": items})
        self.assertTrue(res.success)
        self.assertIn("[x] t1: Set up project", res.output)
        self.assertIn("[>] t2: Implement feature", res.output)
        self.assertIn("[ ] t3: Write tests", res.output)

    def test_checkpoint_tool(self):
        res_create = self.executor.execute("checkpoint", {"action": "create", "name": "cp1"})
        self.assertTrue(res_create.success)
        self.assertIn("Created checkpoint 'cp1'", res_create.output)

        res_list = self.executor.execute("checkpoint", {"action": "list"})
        self.assertTrue(res_list.success)
        self.assertIn("cp1", res_list.output)

        res_restore = self.executor.execute("checkpoint", {"action": "restore", "name": "cp1"})
        self.assertTrue(res_restore.success)
        self.assertIn("Restored workspace state", res_restore.output)

    def test_fetch_url_invalid(self):
        res = self.executor.execute("fetch_url", {"url": "ftp://bad.scheme"})
        self.assertFalse(res.success)
        self.assertIn("Must start with http:// or https://", res.output)


class TestWebAgentBatchExecution(unittest.IsolatedAsyncioTestCase):
    """Test batch action handling inside WebAgent."""

    async def test_parallel_batch_execution(self):
        from src.web_agent import WebAgent
        from src.agent_config import AgentConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "f1.txt").write_text("Content 1")
            (Path(tmpdir) / "f2.txt").write_text("Content 2")

            config = AgentConfig(
                allowed_directory=tmpdir,
                abort_hotkey=None,
                max_steps=3,
            )
            agent = WebAgent(config=config)

            # Mock LLM client to return Shape B parallel batch on step 1, then done on step 2
            mock_client = AsyncMock()

            # Step 1 response
            response1 = MagicMock()
            response1.error = None
            response1.parsed_json = {
                "thought": "Read both files in parallel",
                "actions": [
                    {"id": "p1", "action": "read_file", "args": {"path": "f1.txt"}},
                    {"id": "p2", "action": "read_file", "args": {"path": "f2.txt"}},
                ],
                "mode": "parallel",
            }
            response1.raw_text = json.dumps(response1.parsed_json)

            # Step 2 response
            response2 = MagicMock()
            response2.error = None
            response2.parsed_json = {
                "thought": "Finished reading",
                "action": "done",
                "args": {"summary": "Read f1 and f2 in parallel."},
            }
            response2.raw_text = json.dumps(response2.parsed_json)

            mock_client.send_message.side_effect = [response1, response2, response2, response2]
            agent.client = mock_client
            agent._owns_client = False

            events = []
            agent.on_event = lambda evt: events.append(evt)

            result = await agent.run("Read f1 and f2")
            self.assertTrue(result.success)
            self.assertEqual(result.stop_reason, "done")
            self.assertEqual(result.summary, "Read f1 and f2 in parallel.")

            # Check that both p1 and p2 were recorded in steps
            actions_run = [s.action for s in result.steps]
            self.assertIn("read_file", actions_run)
            self.assertEqual(actions_run.count("read_file"), 2)

    async def test_sequential_batch_execution_stops_on_failure(self):
        from src.web_agent import WebAgent
        from src.agent_config import AgentConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            config = AgentConfig(
                allowed_directory=tmpdir,
                abort_hotkey=None,
                max_steps=3,
            )
            agent = WebAgent(config=config)

            mock_client = AsyncMock()

            # Step 1: Sequential batch where item 1 fails
            response1 = MagicMock()
            response1.error = None
            response1.parsed_json = {
                "thought": "Try sequential actions",
                "actions": [
                    {"id": "s1", "action": "read_file", "args": {"path": "non_existent.txt"}},
                    {"id": "s2", "action": "write_file", "args": {"path": "skipped.txt", "content": "no"}},
                ],
                "mode": "sequential",
            }
            response1.raw_text = json.dumps(response1.parsed_json)

            # Step 2: Done
            response2 = MagicMock()
            response2.error = None
            response2.parsed_json = {
                "thought": "Report result",
                "action": "done",
                "args": {"summary": "Encountered failure and stopped."},
            }
            response2.raw_text = json.dumps(response2.parsed_json)

            mock_client.send_message.side_effect = [response1, response2, response2, response2]
            agent.client = mock_client
            agent._owns_client = False

            result = await agent.run("Run sequential actions")
            self.assertTrue(result.success)

            # Check that skipped.txt was NEVER created because item 1 failed
            self.assertFalse((Path(tmpdir) / "skipped.txt").exists())


if __name__ == "__main__":
    unittest.main()
