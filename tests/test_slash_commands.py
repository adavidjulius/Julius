"""
Comprehensive smoke and behavior test suite for Julius slash commands.

Verifies:
1. Smoke testing on empty sessions (/doctor, /context, /cost, /compact, /undo, /help, /review, /heal, /init).
2. Honest /undo rollback of file mutations (restoring pre-edit content and removing newly created files).
3. Turn-aligned /compact slicing (always retaining a window starting on a user turn).
4. Canonical commands registry consistency across autocomplete, palette, and router.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest
from unittest.mock import AsyncMock
from textual.containers import ScrollableContainer

from src.agent_config import AgentConfig
from src.tui.app import JuliusApp
from src.tui.commands import (
    CANONICAL_COMMANDS,
    COMMAND_SUGGESTIONS,
    COMMAND_LOOKUP,
)
from src.tui.components.message import AssistantMessage


@pytest.mark.asyncio
async def test_slash_commands_smoke_on_empty_session(tmp_path):
    """Verify executing all built-in slash commands on an empty session raises no exceptions."""
    app = JuliusApp(workspace_dir=str(tmp_path), config=AgentConfig())
    async with app.run_test(size=(100, 24)) as pilot:
        app._run_agent_task_worker = AsyncMock()
        conv_area = app.query_one("#conversation-area", ScrollableContainer)

        # 1. /doctor
        app._handle_slash_command("/doctor")
        await pilot.pause(0.05)
        assert any("Doctor Diagnostic Report" in getattr(msg, "content", "") for msg in conv_area.children)

        # 2. /context
        app._handle_slash_command("/context")
        await pilot.pause(0.05)
        assert any("Workspace Context Telemetry" in getattr(msg, "content", "") for msg in conv_area.children)

        # 3. /cost
        app._handle_slash_command("/cost")
        await pilot.pause(0.05)
        assert any("Session Telemetry & Cost" in getattr(msg, "content", "") for msg in conv_area.children)

        # 4. /compact on empty history
        app._handle_slash_command("/compact")
        await pilot.pause(0.05)
        assert any("Context Compacted" in getattr(msg, "content", "") for msg in conv_area.children)

        # 5. /undo on empty session
        app._handle_slash_command("/undo")
        await pilot.pause(0.05)
        # Empty session toast displayed without raising

        # 6. /review (grounded with git check on empty dir)
        app._handle_slash_command("/review")
        await pilot.pause(0.05)

        # 7. /heal (grounded)
        app._handle_slash_command("/heal")
        await pilot.pause(0.05)

        # 8. /init
        app._handle_slash_command("/init")
        await pilot.pause(0.05)


@pytest.mark.asyncio
async def test_undo_restores_file_content_and_removes_created_files(tmp_path):
    """Verify /undo performs honest rollback: restores modified file and removes created file."""
    app = JuliusApp(workspace_dir=str(tmp_path), config=AgentConfig())
    async with app.run_test(size=(100, 24)) as pilot:
        conv_area = app.query_one("#conversation-area", ScrollableContainer)

        # Case 1: Existing file edited
        existing_file = tmp_path / "existing.py"
        existing_file.write_text("ORIGINAL_CONTENT", encoding="utf-8")

        # Record modification and mutate
        app.session_state.record_file_modification(str(existing_file))
        existing_file.write_text("MUTATED_CONTENT", encoding="utf-8")
        assert existing_file.read_text(encoding="utf-8") == "MUTATED_CONTENT"

        # Case 2: New file created
        new_file = tmp_path / "new_created.py"
        app.session_state.record_file_modification(str(new_file))
        new_file.write_text("NEW_CONTENT", encoding="utf-8")
        assert new_file.exists()

        assert len(app.session_state.modified_files) == 2

        # 1st /undo: should remove new_created.py
        app._handle_slash_command("/undo")
        await pilot.pause(0.05)
        assert not new_file.exists()
        assert len(app.session_state.modified_files) == 1

        # 2nd /undo: should restore existing.py to ORIGINAL_CONTENT
        app._handle_slash_command("/undo")
        await pilot.pause(0.05)
        assert existing_file.read_text(encoding="utf-8") == "ORIGINAL_CONTENT"
        assert len(app.session_state.modified_files) == 0

        # 3rd /undo: stack empty, should handle gracefully
        app._handle_slash_command("/undo")
        await pilot.pause(0.05)
        assert len(app.session_state.modified_files) == 0


@pytest.mark.asyncio
async def test_compact_slices_by_turn_and_starts_on_user_turn():
    """Verify /compact keeps recent turns and always starts the retained window on a user turn."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(100, 24)) as pilot:
        # Populate history with multiple turns
        app.session_state.history = [
            ("user", "prompt 1"),
            ("assistant", "answer 1"),
            ("user", "prompt 2"),
            ("assistant", "answer 2"),
            ("user", "prompt 3"),
            ("assistant", "answer 3"),
        ]

        app._handle_slash_command("/compact")
        await pilot.pause(0.05)

        retained = app.session_state.history
        assert len(retained) >= 2
        # Retained window MUST begin with a user turn
        assert retained[0][0] == "user"
        assert retained[-1][0] == "assistant"

        # Test edge case: history ending with multiple assistant turns or cut mid-turn
        app.session_state.history = [
            ("user", "turn 1"),
            ("assistant", "turn 1 answer"),
            ("assistant", "orphan intermediate 1"),
            ("assistant", "orphan intermediate 2"),
            ("user", "turn 2"),
            ("assistant", "turn 2 answer"),
        ]
        app._handle_slash_command("/compact")
        await pilot.pause(0.05)

        assert app.session_state.history[0][0] == "user"


def test_canonical_commands_registry_unification():
    """Verify canonical commands table unifies autocomplete and router, with palette removed."""
    cmd_names = [cmd.name for cmd in CANONICAL_COMMANDS]

    # No duplicates
    assert len(cmd_names) == len(set(cmd_names))

    # All autocomplete items match canonical
    assert len(COMMAND_SUGGESTIONS) == len(CANONICAL_COMMANDS)
    for name, desc in COMMAND_SUGGESTIONS:
        assert name.startswith("/")
        assert len(desc) > 5

    # Palette command is completely removed
    assert "/palette" not in cmd_names
    assert "/cmd" not in cmd_names
    assert "/palette" not in COMMAND_LOOKUP
    assert "/cmd" not in COMMAND_LOOKUP

    # Lookup routes both names and aliases
    assert COMMAND_LOOKUP["/help"].handler_id == "help"
    assert COMMAND_LOOKUP["/?"].handler_id == "help"
    assert COMMAND_LOOKUP["/diff"].handler_id == "diff"
    assert COMMAND_LOOKUP["/changes"].handler_id == "diff"
    assert COMMAND_LOOKUP["/action"].handler_id == "action"
    assert COMMAND_LOOKUP["/ps"].handler_id == "action"
    assert COMMAND_LOOKUP["/clear"].handler_id == "clear"
    assert COMMAND_LOOKUP["/new"].handler_id == "clear"
    assert COMMAND_LOOKUP["/quit"].handler_id == "quit"
    assert COMMAND_LOOKUP["/exit"].handler_id == "quit"


@pytest.mark.asyncio
async def test_ran_steps_duration_formatting_in_minutes_after_60s():
    """Verify ran steps duration is formatted in seconds under 60s and in minutes after 60s."""
    from src.tui.components.tool_summary import format_step_duration, ToolSummary
    from src.tui.state import ToolExecutionRecord

    # < 60 seconds -> seconds format
    assert format_step_duration(0.2) == "0.2s"
    assert format_step_duration(15.4) == "15.4s"
    assert format_step_duration(59.9) == "59.9s"

    # >= 60 seconds -> minutes format
    assert format_step_duration(60.0) == "1m"
    assert format_step_duration(60.4) == "1m"
    assert format_step_duration(65.0) == "1m 5s"
    assert format_step_duration(75.0) == "1m 15s"
    assert format_step_duration(120.0) == "2m"
    assert format_step_duration(135.0) == "2m 15s"
    assert format_step_duration(3600.0) == "60m"

    # ToolSummary widget integration test inside Textual App
    records = [
        ToolExecutionRecord("run_bash", "Ran test suite", duration_s=45.0),
        ToolExecutionRecord("write_file", "Wrote patch", duration_s=35.0),
    ]
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(100, 24)) as pilot:
        conv = app.query_one("#conversation-area", ScrollableContainer)
        summary = ToolSummary(tools=records, total_duration_s=80.0)
        await conv.mount(summary)
        await pilot.pause(0.05)
        rendered = str(summary._content_widget.render())
        # Should say Ran 2 steps · 1m 20s
        assert "Ran 2 steps · 1m 20s" in rendered


def test_zero_interruption_policy_in_llm_prompts():
    """Verify LLM operating manual and planner prompts enforce zero-interruption shadow clone policy."""
    from src.agent_prompts import SYSTEM_PROMPT
    from src.planner.prompts import PLANNER_SYSTEM_PROMPT

    # System prompt principle 10 & section 12.4
    assert "Zero-Interruption & Shadow Clone Policy" in SYSTEM_PROMPT
    assert "Never kill or terminate an active running job" in SYSTEM_PROMPT
    assert "May I go ahead and make a small clone, fix that, and merge it back?" in SYSTEM_PROMPT

    # Planner system prompt
    assert "ZERO-INTERRUPTION POLICY" in PLANNER_SYSTEM_PROMPT
    assert "Never terminate or kill an active running job" in PLANNER_SYSTEM_PROMPT

