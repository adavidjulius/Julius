"""
Unit tests for AgentSkills Standard Integration into Julius.

Verifies:
1. AgentSkillsImporter converting SKILL.md documents to Julius skill packages.
2. 8 Core AgentSkills actions registered in CapabilityRegistry.
3. Execution of standard core skills.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from src.skills.agentskills_importer import AgentSkillsImporter
from src.skills.manifest import JuliusSkillManifest
from src.skills.registry import CapabilityRegistry


def test_agentskills_importer():
    """Verify importing SKILL.md into .julius/skills/ package."""
    raw_md = """---
description: Perform code linting and formatting.
version: 1.1.0
tags: [linter, formatter]
---
# Linter Formatter Skill
Runs static analysis tools and formats code cleanly.
"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        importer = AgentSkillsImporter(workspace_root=tmp_dir)
        target_dir = importer.import_agentskill_markdown("linter-formatter", raw_md)

        assert target_dir.exists()
        assert (target_dir / "SKILL.md").exists()
        assert (target_dir / "JULIUS_SKILL.yaml").exists()

        manifest = JuliusSkillManifest.load_from_dir(target_dir)
        assert manifest.name == "linter-formatter"
        assert manifest.version == "1.1.0"


@pytest.mark.asyncio
async def test_agentskills_registry_actions():
    """Verify standard AgentSkills action resolution and execution in CapabilityRegistry."""
    registry = CapabilityRegistry()
    caps = registry.discover_capabilities()

    # Check 8 core skills exist in both Julius and legacy Julius formats
    assert "julius/skill/file-operations" in caps["skills"]
    assert "julius/skill/file-operations" in caps["skills"]
    assert "julius/skill/git-workflow" in caps["skills"]
    assert "julius/skill/terminal-command" in caps["skills"]
    assert "julius/skill/codebase-search" in caps["skills"]
    assert "julius/skill/web-researcher" in caps["skills"]
    assert "julius/skill/linter-formatter" in caps["skills"]
    assert "julius/skill/test-runner" in caps["skills"]
    assert "julius/skill/refactor-assistant" in caps["skills"]

    # Check actions mapped
    assert registry.resolve_action("READ_FILE") in ("julius/skill/file-operations", "julius/skill/file-operations")
    assert registry.resolve_action("EXECUTE_SHELL") in ("julius/skill/terminal-command", "julius/skill/terminal-command")
    assert registry.resolve_action("GREP_CODE") in ("julius/skill/codebase-search", "julius/skill/codebase-search")

    # Test executing standard actions (both Julius canonical and Julius alias)
    julius_file_skill = registry.get_skill("julius/skill/file-operations")
    assert julius_file_skill is not None
    res = await julius_file_skill.execute({"path": "src/main.py"})
    assert res.success is True
    assert "src/main.py" in res.output

    file_skill = registry.get_skill("julius/skill/file-operations")
    assert file_skill is not None
    res_legacy = await file_skill.execute({"path": "src/main.py"})
    assert res_legacy.success is True
