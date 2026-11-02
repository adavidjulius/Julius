"""Tests for Phase 4.3: Hot-Reloadable Skill Marketplace & Plugin Registry."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from src.plugins.loader import SkillLoader, SkillManifest
from src.plugins.registry import PluginRegistry


class TestPluginMarketplace(unittest.IsolatedAsyncioTestCase):
    """Test suite for skill loader, plugin registry, dynamic toggling, and hot reload."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name)
        self.skills_dir = self.workspace / ".agents" / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _create_skill(self, folder_name: str, name: str, desc: str, perms: list[str]) -> Path:
        skill_path = self.skills_dir / folder_name
        skill_path.mkdir(parents=True, exist_ok=True)
        skill_md = skill_path / "SKILL.md"

        perms_str = "\n".join(f"  - {p}" for p in perms)
        content = f"""---
name: "{name}"
description: "{desc}"
author: "Julius Test"
version: "1.2.0"
permissions:
{perms_str}
---

# {name}
Instructions here.
"""
        skill_md.write_text(content, encoding="utf-8")
        return skill_path

    def test_parse_yaml_frontmatter(self):
        """Frontmatter parser extracts scalar and list fields without PyYAML dependency."""
        raw = """---
name: "audio-synth"
description: "Direct DSP audio engine"
version: "2.1.0"
sandboxed: true
permissions:
  - audio.playback
  - filesystem.cache
---

# Body
Content here.
"""
        meta, body = SkillLoader.parse_yaml_frontmatter(raw)
        self.assertEqual(meta.get("name"), "audio-synth")
        self.assertEqual(meta.get("description"), "Direct DSP audio engine")
        self.assertEqual(meta.get("version"), "2.1.0")
        self.assertEqual(meta.get("sandboxed"), True)
        self.assertEqual(meta.get("permissions"), ["audio.playback", "filesystem.cache"])
        self.assertIn("# Body", body)

    def test_load_skill(self):
        """SkillLoader loads a valid skill directory into a SkillManifest."""
        skill_dir = self._create_skill("my_tool", "My Tool", "A great test tool", ["bash.exec"])
        manifest = SkillLoader.load_skill(skill_dir)

        self.assertIsNotNone(manifest)
        self.assertEqual(manifest.skill_id, "my_tool")
        self.assertEqual(manifest.name, "My Tool")
        self.assertEqual(manifest.description, "A great test tool")
        self.assertEqual(manifest.permissions, ["bash.exec"])
        self.assertTrue(manifest.enabled)

    def test_registry_discovery_and_toggling(self):
        """PluginRegistry discovers skills and toggles enabled status with persistence."""
        self._create_skill("skill_a", "Skill Alpha", "Alpha Tool", ["read"])
        self._create_skill("skill_b", "Skill Beta", "Beta Tool", ["write"])

        events = []
        registry = PluginRegistry(
            workspace_root=str(self.workspace),
            on_change_callback=lambda ev: events.append(ev),
        )

        self.assertIn("skill_a", registry._plugins)
        self.assertIn("skill_b", registry._plugins)

        # Toggle skill_a to disabled
        success = registry.set_plugin_enabled("skill_a", False)
        self.assertTrue(success)
        self.assertFalse(registry.get_plugin("skill_a").enabled)

        # Verify state file persistence
        state_file = self.workspace / ".julius" / "plugins_state.json"
        self.assertTrue(state_file.is_file())
        data = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertFalse(data["enabled_states"]["skill_a"])

        # Reload registry and verify disabled state is retained
        new_registry = PluginRegistry(workspace_root=str(self.workspace))
        self.assertFalse(new_registry.get_plugin("skill_a").enabled)
        self.assertTrue(new_registry.get_plugin("skill_b").enabled)

    def test_prompt_injection_context(self):
        """get_active_prompt_skills formats only enabled skills for system instructions."""
        self._create_skill("active_s", "Active Skill", "Ready to assist", ["terminal.run"])
        self._create_skill("disabled_s", "Disabled Skill", "Offline", ["net.fetch"])

        registry = PluginRegistry(workspace_root=str(self.workspace))
        registry.set_plugin_enabled("disabled_s", False)

        prompt_block = registry.get_active_prompt_skills()
        self.assertIn("Active Skill", prompt_block)
        self.assertIn("terminal.run", prompt_block)
        self.assertNotIn("Disabled Skill", prompt_block)

    async def test_hot_reload_watcher(self):
        """Watcher detects changes in filesystem and reloads registry dynamically."""
        registry = PluginRegistry(workspace_root=str(self.workspace))
        self.assertEqual(len(registry._plugins), 0)

        await registry.start_watcher(poll_interval=0.1)
        try:
            # Create a new skill while watcher is running
            self._create_skill("hot_skill", "Hot Skill", "Dynamically added", ["hot.reload"])
            await asyncio.sleep(0.35)

            # Check if auto-reloaded
            self.assertIn("hot_skill", registry._plugins)
            self.assertEqual(registry.get_plugin("hot_skill").name, "Hot Skill")
        finally:
            await registry.stop_watcher()


if __name__ == "__main__":
    unittest.main()
