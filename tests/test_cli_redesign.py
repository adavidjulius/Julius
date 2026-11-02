import unittest
from src.cli.mode_registry import ModeRegistry, global_mode_registry
from src.cli.presenter import render_confirmation_prompt, Spinner


class TestCLIRedesign(unittest.TestCase):
    def test_mode_registry_plan_prefix(self):
        reg = ModeRegistry()
        res = reg.resolve("/plan create a web app")
        self.assertEqual(res.mode, "plan")
        self.assertEqual(res.task, "create a web app")
        self.assertTrue(res.requires_plan)

    def test_mode_registry_act_prefix(self):
        reg = ModeRegistry()
        res = reg.resolve("/act list files")
        self.assertEqual(res.mode, "act")
        self.assertEqual(res.task, "list files")
        self.assertFalse(res.requires_plan)

    def test_mode_registry_new_prefix(self):
        reg = ModeRegistry()
        res = reg.resolve("/new")
        self.assertEqual(res.mode, "new")
        self.assertFalse(res.requires_plan)

    def test_mode_registry_exit_prefix(self):
        reg = ModeRegistry()
        res = reg.resolve("/exit")
        self.assertEqual(res.mode, "exit")
        self.assertFalse(res.requires_plan)

    def test_mode_registry_destructive_bare_task(self):
        reg = ModeRegistry()
        res = reg.resolve("delete temporary file log.txt")
        self.assertEqual(res.mode, "plan")
        self.assertTrue(res.requires_plan)
        self.assertTrue(res.is_destructive)

    def test_mode_registry_safe_bare_task(self):
        reg = ModeRegistry()
        res = reg.resolve("hello, who are you?")
        self.assertEqual(res.mode, "act")
        self.assertFalse(res.requires_plan)
        self.assertFalse(res.is_destructive)

    def test_presenter_confirmation_prompt(self):
        prompt = render_confirmation_prompt("edit_file", {"path": "hello.py", "old_text": "foo", "new_text": "bar"})
        self.assertIn("[a]ccept", prompt)


if __name__ == "__main__":
    unittest.main()
