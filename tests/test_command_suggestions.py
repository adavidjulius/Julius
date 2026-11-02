"""
Tests for slash command auto-complete suggestions above Composer.
"""

from __future__ import annotations

import pytest
from src.tui.app import JuliusApp
from src.agent_config import AgentConfig
from src.tui.components.composer import Composer
from src.tui.components.command_suggestions import CommandSuggestions, COMMANDS


@pytest.mark.asyncio
async def test_command_suggestions_matching_prefix():
    """Verify typing /h shows suggestions starting with h (/help), and /p shows /plan, /ps, etc."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(100, 24)) as pilot:
        sugg = app.query_one("#command-suggestions", CommandSuggestions)
        comp = app.query_one("#composer-input", Composer)

        # Initially invisible
        assert not sugg.is_visible

        # 1. Type /h -> only commands starting with /h
        comp.insert("/h")
        await pilot.pause(0.05)
        assert sugg.is_visible
        match_cmds = [m[0] for m in sugg.matches]
        assert "/help" in match_cmds
        for cmd in match_cmds:
            assert cmd.startswith("/h")

        # 2. Clear and type /p -> commands starting with /p
        comp.text = ""
        comp.insert("/p")
        await pilot.pause(0.05)
        assert sugg.is_visible
        p_cmds = [m[0] for m in sugg.matches]
        assert "/plan" in p_cmds
        assert "/palette" not in p_cmds
        for cmd in p_cmds:
            assert cmd.startswith("/p")

        # 3. Case-insensitivity: /H
        comp.text = ""
        comp.insert("/H")
        await pilot.pause(0.05)
        assert sugg.is_visible
        assert "/help" in [m[0] for m in sugg.matches]


@pytest.mark.asyncio
async def test_command_suggestions_tab_completion():
    """Verify pressing Tab autocompletes the selected command into Composer with a trailing space."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(100, 24)) as pilot:
        sugg = app.query_one("#command-suggestions", CommandSuggestions)
        comp = app.query_one("#composer-input", Composer)

        comp.insert("/h")
        await pilot.pause(0.05)
        assert sugg.is_visible

        # Press Tab
        await pilot.press("tab")
        await pilot.pause(0.05)

        # Autocompleted into Composer and suggestions hidden
        assert comp.text == "/help "
        assert not sugg.is_visible


@pytest.mark.asyncio
async def test_command_suggestions_navigation_and_enter():
    """Verify Up/Down arrows cycle selection and Enter submits the chosen command."""
    submitted = []

    class TestApp(JuliusApp):
        def on_composer_submitted(self, event):
            submitted.append(event.text)

    app = TestApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(100, 24)) as pilot:
        sugg = app.query_one("#command-suggestions", CommandSuggestions)
        comp = app.query_one("#composer-input", Composer)

        comp.insert("/c")
        await pilot.pause(0.05)
        assert sugg.is_visible
        assert len(sugg.matches) > 1

        first_cmd = sugg.get_selected_command()
        await pilot.press("down")
        await pilot.pause(0.05)
        second_cmd = sugg.get_selected_command()
        assert first_cmd != second_cmd

        await pilot.press("up")
        await pilot.pause(0.05)
        back_to_first = sugg.get_selected_command()
        assert back_to_first == first_cmd

        # Submit via Enter
        await pilot.press("enter")
        await pilot.pause(0.05)
        assert first_cmd in submitted
        assert not sugg.is_visible


@pytest.mark.asyncio
async def test_command_suggestions_hidden_on_normal_prompt_and_space():
    """Verify suggestions stay hidden on normal prompts, hide after space, and hide on Escape."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(100, 24)) as pilot:
        sugg = app.query_one("#command-suggestions", CommandSuggestions)
        comp = app.query_one("#composer-input", Composer)

        # Normal text -> hidden
        comp.insert("explain how auth works")
        await pilot.pause(0.05)
        assert not sugg.is_visible

        # Slash command followed by space -> hidden
        comp.text = ""
        comp.insert("/model deepseek")
        await pilot.pause(0.05)
        assert not sugg.is_visible

        # Escape key hides suggestions
        comp.text = ""
        comp.insert("/h")
        await pilot.pause(0.05)
        assert sugg.is_visible
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert not sugg.is_visible


@pytest.mark.asyncio
async def test_command_suggestions_click_autocomplete():
    """Verify clicking on a suggestion row inserts it into the Composer."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(100, 24)) as pilot:
        sugg = app.query_one("#command-suggestions", CommandSuggestions)
        comp = app.query_one("#composer-input", Composer)

        comp.insert("/doc")
        await pilot.pause(0.05)
        assert sugg.is_visible
        assert sugg.matches[0][0] == "/doctor"

        # Click the suggestion line (offset y=1 for first command row below header)
        await pilot.click("#command-suggestions", offset=(2, 1))
        await pilot.pause(0.05)

        assert comp.text == "/doctor "
        assert not sugg.is_visible


def test_no_duplicate_commands_and_only_quit_not_exit():
    """Verify all suggestions have unique jobs with no redundant aliases, and only /quit is present."""
    cmd_names = [cmd for cmd, _ in COMMANDS]
    # No duplicate command names
    assert len(cmd_names) == len(set(cmd_names))
    # Only quit needed, no exit
    assert "/quit" in cmd_names
    assert "/exit" not in cmd_names
    # Aliases removed: only /action (no /inspect, /ps), only /clear (no /new), only /palette (no /cmd), only /diff (no /changes)
    assert "/action" in cmd_names
    assert "/inspect" not in cmd_names
    assert "/ps" not in cmd_names
    assert "/clear" in cmd_names
    assert "/new" not in cmd_names
    assert "/palette" not in cmd_names
    assert "/cmd" not in cmd_names
    assert "/diff" in cmd_names
    assert "/changes" not in cmd_names
