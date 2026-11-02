"""Tests for src/response_validator.py — action schema validation."""

import unittest
from src.response_validator import validate_action


class TestValidateAction(unittest.TestCase):
    """Tests for the structural JSON action validator."""

    # ── Valid cases ───────────────────────────────────────────────

    def test_valid_run_bash(self):
        data = {'thought': 'test', 'action': 'run_bash', 'args': {'command': 'ls'}}
        is_valid, error = validate_action(data)
        self.assertTrue(is_valid)
        self.assertEqual(error, '')

    def test_valid_done(self):
        data = {'thought': 'done', 'action': 'done', 'args': {'summary': 'All done.'}}
        is_valid, error = validate_action(data)
        self.assertTrue(is_valid)

    def test_valid_converse(self):
        data = {'thought': 'conversational', 'action': 'converse', 'args': {'message': 'Hello!'}}
        is_valid, error = validate_action(data)
        self.assertTrue(is_valid)

    def test_valid_edit_file(self):
        data = {
            'thought': 'fix bug',
            'action': 'edit_file',
            'args': {'path': 'main.py', 'old_text': 'foo', 'new_text': 'bar'},
        }
        is_valid, error = validate_action(data)
        self.assertTrue(is_valid)

    def test_valid_read_symbol(self):
        data = {
            'thought': 'read',
            'action': 'read_symbol',
            'args': {'path': 'main.py', 'symbol': 'my_func'},
        }
        is_valid, error = validate_action(data)
        self.assertTrue(is_valid)

    def test_valid_with_extra_keys(self):
        """Extra keys in args should not cause rejection — we only check minimums."""
        data = {
            'thought': 'read with range',
            'action': 'read_file',
            'args': {'path': 'main.py', 'start_line': 1, 'end_line': 50},
        }
        is_valid, error = validate_action(data)
        self.assertTrue(is_valid)

    # ── Invalid cases ────────────────────────────────────────────

    def test_not_a_dict(self):
        is_valid, error = validate_action("not a dict")
        self.assertFalse(is_valid)
        self.assertIn('not a JSON object', error)

    def test_missing_thought(self):
        data = {'action': 'done', 'args': {'summary': 'test'}}
        is_valid, error = validate_action(data)
        self.assertFalse(is_valid)
        self.assertIn('thought', error)

    def test_missing_action(self):
        data = {'thought': 'test', 'args': {'summary': 'test'}}
        is_valid, error = validate_action(data)
        self.assertFalse(is_valid)
        self.assertIn('action', error)

    def test_missing_args(self):
        data = {'thought': 'test', 'action': 'done'}
        is_valid, error = validate_action(data)
        self.assertFalse(is_valid)
        self.assertIn('args', error)

    def test_unknown_action(self):
        data = {'thought': 'test', 'action': 'fly_to_moon', 'args': {}}
        is_valid, error = validate_action(data)
        self.assertFalse(is_valid)
        self.assertIn('Unknown action', error)

    def test_missing_required_arg(self):
        data = {'thought': 'test', 'action': 'run_bash', 'args': {}}
        is_valid, error = validate_action(data)
        self.assertFalse(is_valid)
        self.assertIn('command', error)

    def test_missing_edit_file_args(self):
        data = {'thought': 'test', 'action': 'edit_file', 'args': {'path': 'x.py'}}
        is_valid, error = validate_action(data)
        self.assertFalse(is_valid)
        # Should mention the missing old_text or new_text
        self.assertTrue('old_text' in error or 'new_text' in error)

    def test_null_required_arg(self):
        data = {'thought': 'test', 'action': 'done', 'args': {'summary': None}}
        is_valid, error = validate_action(data)
        self.assertFalse(is_valid)
        self.assertIn('null', error)

    def test_args_not_dict(self):
        data = {'thought': 'test', 'action': 'done', 'args': 'not a dict'}
        is_valid, error = validate_action(data)
        self.assertFalse(is_valid)
        self.assertIn('JSON object', error)

    def test_empty_action_string(self):
        data = {'thought': 'test', 'action': '', 'args': {}}
        is_valid, error = validate_action(data)
    def test_extract_json_block_with_control_characters(self):
        """Ensure multiline strings with raw newlines/tabs parse without JSONDecodeError."""
        from src.agent_prompts import extract_json_block
        raw_text = '```json\n{\n  "thought": "Testing control characters",\n  "action": "run_bash",\n  "args": {\n    "command": "python3 -c \'\nimport os\nprint(1)\n\'"\n  }\n}\n```'
        result = extract_json_block(raw_text)
        self.assertEqual(result.get("action"), "run_bash")
        self.assertIn("Testing control characters", result.get("thought"))

    def test_parse_action_does_not_convert_action_json_to_done(self):
        """If LLM returns json-like text that fails, it should return None rather than marking the task as done."""
        from unittest.mock import MagicMock
        from src.web_agent import WebAgent
        resp = MagicMock()
        resp.parsed_json = None
        resp.raw_text = '{"thought": "broken json", "action": "run_bash", "args": {"command": broken}}'
        action_data = WebAgent._parse_action(resp)
        self.assertIsNone(action_data)


if __name__ == '__main__':
    unittest.main()
