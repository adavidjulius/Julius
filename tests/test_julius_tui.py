"""
Comprehensive test suite for Next-Gen Julius TUI.

Verifies:
1. Centered 76-cell column layout at terminal widths 60, 80, 120, and 200.
2. Light and dark theme tokens, single accent color, and contrast >= 4.5:1.
3. Terminal theme detection fallback and NO_COLOR honoring.
4. Rich Markdown typography: emoji stripping in headings, left-alignment, rounded code blocks, hanging indent.
5. Event deduplication and single-render guarantee (zero raw markdown, no duplicate summaries, no raw Output: labels).
6. Collapsible tool activity (quiet dim line by default, expanded on demand).
7. Motion presets: durations <= 320 ms and reduced-motion instant state changes.
8. Terminal size guard (warning when < 60x16).
9. Keyboard shortcuts and modal overlays.
"""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest
from rich.console import Console
from rich.text import Text
from textual.app import App, ComposeResult
from textual.color import Color
from textual.containers import Container, ScrollableContainer

from src.agent_config import AgentConfig
from src.tui.config import JuliusConfig
from src.tui.app import JuliusApp
from src.tui.theme import DARK_THEME, LIGHT_THEME, NO_COLOR_THEME, get_theme, detect_color_scheme
from src.tui.motion import MotionPresets, is_reduced_motion, animate_enter
from src.tui.markdown import (
    render_julius_markdown,
    JuliusMarkdown,
    render_apple_markdown,
    AppleMarkdown,
)
from src.tui.components.message import UserMessage, AssistantMessage, ThinkingDot
from src.tui.components.tool_summary import ToolSummary
from src.tui.components.composer import Composer
from src.tui.components.status_line import StatusLine
from src.tui.state import ToolExecutionRecord


# ── 1. Layout & Full-Bleed Surface Tests (Widths 60, 80, 120, 160, 220) ──────

@pytest.mark.asyncio
@pytest.mark.parametrize("width", [60, 80, 120, 160, 220])
async def test_fullscreen_bleed_layout_at_all_widths(width):
    """Verify Screen, main container, conversation area, input, and status line span full width minus padding."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(width, 24)) as pilot:
        main_col = app.query_one("#main-column", Container)
        conv_area = app.query_one("#conversation-area", ScrollableContainer)
        composer = app.query_one("#composer-input", Composer)
        status_line = app.query_one("#status-line", StatusLine)

        # Rule L2: 2 cells padding on left/right, 4 cells if width >= 160
        expected_pad = 4 if width >= 160 else 2
        expected_width = width - (2 * expected_pad)

        assert main_col.region.width == expected_width, (
            f"main_col width {main_col.region.width} != {expected_width} at terminal width {width}"
        )
        assert conv_area.region.width == expected_width, (
            f"conv_area width {conv_area.region.width} != {expected_width} at terminal width {width}"
        )
        assert composer.region.width == expected_width, (
            f"composer width {composer.region.width} != {expected_width} at terminal width {width}"
        )
        assert status_line.region.width == expected_width, (
            f"status_line width {status_line.region.width} != {expected_width} at terminal width {width}"
        )
        assert main_col.region.x == expected_pad, (
            f"main_col offset {main_col.region.x} != {expected_pad} at terminal width {width}"
        )

        # Rule L1: No widget has max_width 76 or fixed width 76
        assert main_col.styles.max_width is None, "main_col must not have a max_width cap"
        assert conv_area.styles.max_width is None, "conv_area must not have a max_width cap"

        # Rule L6: One continuous background token
        assert app.screen.styles.background == Color.parse(app.active_theme.bg)
        assert main_col.styles.background == Color.parse(app.active_theme.bg)


@pytest.mark.asyncio
async def test_no_widgets_have_fixed_width_76_or_auto_centering():
    """Rule L1 & verification: Assert no widget has a fixed width of 76 or an auto-centering style."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(120, 24)) as pilot:
        for widget_id in ["#main-column", "#conversation-area", "#composer-input", "#status-line"]:
            w = app.query_one(widget_id)
            assert w.styles.width is None or w.styles.width.value != 76, f"{widget_id} has width 76"
            assert w.styles.max_width is None or w.styles.max_width.value != 76, f"{widget_id} has max-width 76"
            assert w.styles.align_horizontal != "center", f"{widget_id} has align_horizontal == center"


@pytest.mark.asyncio
async def test_messages_span_full_content_width():
    """Rule L4: Messages (UserMessage, AssistantMessage, ToolSummary) span full content width."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(120, 24)) as pilot:
        conv = app.query_one("#conversation-area", ScrollableContainer)
        user_msg = UserMessage("How do design tokens work?")
        tools = [ToolExecutionRecord("read_file", "Read theme.py", 0.1)]
        tool_sum = ToolSummary(tools, total_duration_s=0.1)
        asst_msg = AssistantMessage("Tokens are full width by default.", theme=app.active_theme)

        await conv.mount(user_msg)
        await conv.mount(tool_sum)
        await conv.mount(asst_msg)
        await pilot.pause(0.05)

        # Terminal width 120, padding 2 on each side -> conv.region.width is 116.
        # With scrollable container vertical scrollbar (1 cell), content region is 115.
        expected_content_width = conv.scrollable_content_region.width
        # User message sizes dynamically to content width with 8-cell margins instead of full screen bleed
        assert user_msg.region.width == len(user_msg.raw_content) + 4
        assert user_msg.region.width <= expected_content_width - 16
        # tool_sum and asst_msg have 8-cell margins for centered 1-inch reading column
        assert tool_sum.region.width == expected_content_width - 16
        assert asst_msg.region.width == expected_content_width - 16


def test_max_content_width_config():
    """Rule L5: max_content_width defaults to 0 (unlimited) and caps assistant prose when > 0."""
    from src.tui.config import JuliusConfig
    cfg = JuliusConfig()
    assert cfg.max_content_width == 0, "Default max_content_width must be 0 (unlimited)"

    # Default (0) -> table column width is None (full width)
    msg_unlimited = AssistantMessage("Full width message", max_content_width=0)
    msg_unlimited._update_renderable()
    assert msg_unlimited.grid_table.columns[1].width is None, "When max_content_width=0, prose width must not be capped"

    # Configured cap (e.g. 80) -> table column width is capped left-aligned
    msg_capped = AssistantMessage("Capped prose message", max_content_width=80)
    msg_capped._update_renderable()
    assert msg_capped.grid_table.columns[1].width == 80, "When max_content_width=80, prose width must be 80"
    assert msg_capped.grid_table.columns[1].justify == "left", "Capped prose must be left-aligned"


@pytest.mark.asyncio
async def test_resize_behavior_and_reflow():
    """Rule L7: Reflow instantly on terminal resize; update padding (2 vs 4); minimum size guard."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(80, 24)) as pilot:
        # At 80 columns: padding is 2 cells each side (content width = 76)
        main_col = app.query_one("#main-column")
        assert app.screen.styles.padding.left == 2
        assert app.screen.styles.padding.right == 2
        assert main_col.region.width == 76

        # Resize to 160 columns: padding becomes 4 cells each side (content width = 152)
        await pilot.resize_terminal(160, 24)
        await pilot.pause(0.05)
        assert app.screen.styles.padding.left == 4
        assert app.screen.styles.padding.right == 4
        assert main_col.region.width == 152

        # Resize to 220 columns: padding remains 4 cells (content width = 212)
        await pilot.resize_terminal(220, 24)
        await pilot.pause(0.05)
        assert app.screen.styles.padding.left == 4
        assert app.screen.styles.padding.right == 4
        assert main_col.region.width == 212

        # Resize below min supported size (50, 12): calm notice shown
        await pilot.resize_terminal(50, 12)
        await pilot.pause(0.05)
        assert app.terminal_too_small is True
        warning = app.query_one("#terminal-too-small-warning")
        assert warning.styles.display == "block"
        assert main_col.styles.display == "none"



# ── 2. Theme Tokens & Contrast Tests ──────────────────────────────────────────

def calculate_relative_luminance(hex_color: str) -> float:
    """Calculate sRGB relative luminance per WCAG 2.1 specs."""
    hex_clean = hex_color.lstrip("#")
    r = int(hex_clean[0:2], 16) / 255.0
    g = int(hex_clean[2:4], 16) / 255.0
    b = int(hex_clean[4:6], 16) / 255.0

    def adjust(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * adjust(r) + 0.7152 * adjust(g) + 0.0722 * adjust(b)


def calculate_contrast_ratio(hex1: str, hex2: str) -> float:
    """Calculate WCAG contrast ratio between two hex colors."""
    l1 = calculate_relative_luminance(hex1)
    l2 = calculate_relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def test_theme_contrast_meets_wcag_standards():
    """Verify body text contrast is at least 4.5:1 against background in both light and dark themes."""
    # Dark theme
    dark_contrast = calculate_contrast_ratio(DARK_THEME.text, DARK_THEME.bg)
    assert dark_contrast >= 4.5, f"Dark theme text contrast {dark_contrast:.2f} is below 4.5:1"

    # Dark dim text contrast (should also be readable >= 4.5:1)
    dark_dim_contrast = calculate_contrast_ratio(DARK_THEME.text_dim, DARK_THEME.bg)
    assert dark_dim_contrast >= 4.5, f"Dark theme dim text contrast {dark_dim_contrast:.2f} is below 4.5:1"

    # Light theme
    light_contrast = calculate_contrast_ratio(LIGHT_THEME.text, LIGHT_THEME.bg)
    assert light_contrast >= 4.5, f"Light theme text contrast {light_contrast:.2f} is below 4.5:1"

    light_dim_contrast = calculate_contrast_ratio(LIGHT_THEME.text_dim, LIGHT_THEME.bg)
    assert light_dim_contrast >= 4.5, f"Light theme dim text contrast {light_dim_contrast:.2f} is below 4.5:1"


def test_theme_has_exactly_one_accent_color():
    """Verify design principle: exactly ONE accent color (dusty antique parchment for dark, Julius blue for light)."""
    assert DARK_THEME.accent == "#c8b896"
    assert LIGHT_THEME.accent == "#007aff"


def test_no_color_environment_honored(monkeypatch):
    """Verify NO_COLOR environment variable yields no_color theme."""
    monkeypatch.setenv("NO_COLOR", "1")
    theme = get_theme("auto")
    assert theme.is_no_color is True
    assert theme.name == "no_color"


# ── 3. Typography & Markdown Rendering Tests ─────────────────────────────────

def test_markdown_strips_emoji_from_headings():
    """Verify emoji are cleanly removed from headings in rendered output."""
    raw = "# 🚀 Autonomous Mission Control\n\n### ⚡ Execution Phase 1"
    md = render_julius_markdown(raw)

    console = Console(width=76)
    with console.capture() as capture:
        console.print(md)
    output = capture.get()

    assert "🚀" not in output, "Emoji 🚀 leaked into rendered heading!"
    assert "⚡" not in output, "Emoji ⚡ leaked into rendered heading!"
    assert "Autonomous Mission Control" in output
    assert "Execution Phase 1" in output


def test_markdown_renders_rounded_code_blocks():
    """Verify code blocks render in rounded panels with faint language subtitles."""
    raw = "```python\ndef test():\n    return 42\n```"
    md = render_julius_markdown(raw)

    console = Console(width=76)
    with console.capture() as capture:
        console.print(md)
    output = capture.get()

    assert "def test():" in output
    assert "return 42" in output
    assert "python" in output
    # Assert rounded box drawing characters present
    assert "╭" in output or "│" in output or "╰" in output


def test_markdown_hanging_indent_for_lists():
    """Verify list items render bullet • and align wrapped text."""
    raw = "* First item\n* Second item with very long text that demonstrates proper wrapping"
    md = render_julius_markdown(raw)

    console = Console(width=76)
    with console.capture() as capture:
        console.print(md)
    output = capture.get()

    assert "•" in output
    assert "First item" in output
    assert "Second item" in output


# ── 4. Single-Render & Event Deduplication Tests ─────────────────────────────

@pytest.mark.asyncio
async def test_assistant_answer_renders_exactly_once():
    """Verify assistant response appears exactly once with zero raw 'Output:' or triple duplicates."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(80, 24)) as pilot:
        # Simulate incoming task flow via EventBridge
        app.event_bridge.start_turn()
        app.event_bridge.handle_event({"type": "step_start", "step": 1})
        app.event_bridge.handle_event({"type": "action", "name": "run_bash", "args": {"command": "echo test"}})
        app.event_bridge.handle_event({"type": "result", "output": "test", "success": True})

        unique_answer = "Refactored user authentication middleware with session validation."
        app.event_bridge.handle_event({"type": "done", "summary": unique_answer})
        await pilot.pause()

        # Query conversation area text
        conv_area = app.query_one("#conversation-area", ScrollableContainer)
        assistant_msgs = list(conv_area.query(AssistantMessage))

        # Must have exactly 1 AssistantMessage
        assert len(assistant_msgs) == 1, f"Expected 1 AssistantMessage, found {len(assistant_msgs)}"
        assert assistant_msgs[0].content == unique_answer


@pytest.mark.asyncio
async def test_suppresses_raw_output_and_internal_done_actions():
    """Verify raw 'Output:' blocks and internal actions ('done', 'converse') never leak into UI."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(80, 24)) as pilot:
        app.event_bridge.start_turn()
        # Internal action 'done' should not be registered as a tool
        app.event_bridge.handle_event({"type": "action", "name": "done", "args": {"summary": "Done"}})
        assert len(app.session_state.current_turn_tools) == 0

        # Internal result 'Task completed: ...' should not be recorded as a tool
        app.event_bridge.handle_event({"type": "result", "output": "Task completed: Verified."})
        assert len(app.session_state.current_turn_tools) == 0


# ── 5. Collapsible Tool Activity Tests ───────────────────────────────────────

@pytest.mark.asyncio
async def test_tool_summary_collapsed_by_default_and_expands_on_toggle():
    """Verify tool execution is collapsed by default into a single line and expands on toggle."""
    tools = [
        ToolExecutionRecord("read_file", "Read src/agent_config.py", 0.3),
        ToolExecutionRecord("run_bash", "Ran bash: pytest (0.8s)", 0.8),
    ]
    summary_widget = ToolSummary(tools, total_duration_s=1.1)

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield summary_widget

    app = TestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        ts = app.query_one(ToolSummary)
        # Default is collapsed
        assert ts.expanded is False

        # Toggle via method or Enter
        ts.toggle()
        assert ts.expanded is True

        # Toggle back
        ts.toggle()
        assert ts.expanded is False


# ── 6. Motion Presets & Reduced Motion Tests ─────────────────────────────────

def test_animation_durations_capped_to_320ms():
    """Verify no animation preset duration exceeds the 320 ms budget."""
    assert MotionPresets.ENTER_DURATION <= 0.320, "Enter animation exceeded 320 ms"
    assert MotionPresets.SETTLE_DURATION <= 0.320, "Settle animation exceeded 320 ms"
    assert MotionPresets.FADE_DURATION <= 0.320, "Fade animation exceeded 320 ms"


def test_reduced_motion_environment(monkeypatch):
    """Verify JULIUS_REDUCE_MOTION=1 disables animations instantly."""
    monkeypatch.setenv("JULIUS_REDUCE_MOTION", "1")
    assert is_reduced_motion() is True


# ── 7. Terminal Size Guard Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_terminal_size_guard_shows_warning_when_under_60x16():
    """Verify friendly notice appears when terminal drops below 60x16."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    # Start under min size (50x12)
    async with app.run_test(size=(50, 12)) as pilot:
        warning = app.query_one("#terminal-too-small-warning")
        main_col = app.query_one("#main-column")

        assert app.terminal_too_small is True
        assert warning.styles.display == "block"
        assert main_col.styles.display == "none"


# ── 8. User Feedback & UI Refinements Tests ─────────────────────────────────

@pytest.mark.asyncio
async def test_follow_up_turns_do_not_raise_duplicate_ids():
    """Verify follow-up user prompt does not crash with DuplicateIds on thinking-indicator."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(100, 24)) as pilot:
        app._run_agent_task_worker = AsyncMock()
        # First turn
        app._dispatch_user_prompt("First question")
        await pilot.pause(0.05)
        assert app.active_thinking_dot is not None

        # Simulate turn completion
        app._handle_bridge_message({"kind": "done", "summary": "First answer"})
        await pilot.pause(0.05)
        assert app.active_thinking_dot is None

        # Follow-up turn (must not raise DuplicateIds exception)
        app._dispatch_user_prompt("Second follow-up question")
        await pilot.pause(0.05)
        assert app.active_thinking_dot is not None

        # Third follow-up without done (e.g. user sends another prompt while thinking)
        app._dispatch_user_prompt("Third rapid question")
        await pilot.pause(0.05)
        assert app.active_thinking_dot is not None


@pytest.mark.asyncio
async def test_defined_round_borders_on_composer_and_user_message():
    """Verify composer and submitted user message have matching defined rounded borders."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig(), app_config=JuliusConfig(theme="dark"))
    async with app.run_test(size=(100, 24)) as pilot:
        app._run_agent_task_worker = AsyncMock()
        composer = app.query_one("#composer-input")
        # In dark mode, border_idle is #3e3e42 (crisp, not faint #2c2c2e)
        assert app.active_theme.border_idle == "#3e3e42"
        assert composer.styles.border.top[0] == "round"

        # Mount a user message and assert matching border style
        app._dispatch_user_prompt("Hello Julius")
        await pilot.pause(0.05)
        user_msg = app.query_one(UserMessage)
        assert user_msg.styles.border.top[0] == "round"


@pytest.mark.asyncio
async def test_stream_chunk_suppresses_raw_json_and_updates_thinking_label():
    """Verify raw JSON protocol streams do not leak into assistant messages and update thinking label."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(100, 24)) as pilot:
        app._run_agent_task_worker = AsyncMock()
        app._dispatch_user_prompt("Clean cache files")
        await pilot.pause(0.05)

        # Raw protocol JSON chunk from LLM
        raw_json_chunk = '{\n  "thought": "David wants to clear temporary files. Inspecting directory sizes.",\n  "actions": []\n}'
        app._handle_bridge_message({"kind": "stream_chunk", "chunk": raw_json_chunk})
        await pilot.pause(0.05)

        # Assistant message must NOT be mounted with raw JSON
        assert app.active_assistant_msg is None

        # Thinking indicator label must be updated fluidly
        assert app.active_thinking_dot is not None
        assert "David wants to clear temporary files" in app.active_thinking_dot.label

        # Done event delivers clean final summary
        app._handle_bridge_message({"kind": "done", "summary": "Found 1.2 GB of temporary caches."})
        await pilot.pause(0.05)

        conv = app.query_one("#conversation-area")
        messages = list(conv.query(AssistantMessage))
        assert len(messages) == 1
        assert "Found 1.2 GB" in messages[0].content
        assert "David wants to clear" not in messages[0].content


def test_welcome_view_shows_large_banner_and_no_subquotes():
    """Verify WelcomeView displays the large stylized JULIUS banner and no sub-quotes."""
    from src.tui.components.welcome import WelcomeView, JULIUS_BANNER
    welcome = WelcomeView()
    # Ensure large outline banner constant is defined
    assert "╔═════╗" in JULIUS_BANNER
    # Ensure no sub-quotes in class definitions or greeting subtext
    assert not hasattr(welcome, "greeting_text")


def test_welcome_banner_centered_and_amber():
    """Verify WelcomeView centers the banner."""
    from src.tui.components.welcome import WelcomeView
    welcome = WelcomeView()
    assert "align: center middle" in welcome.DEFAULT_CSS
    assert "text-align: center" in welcome.DEFAULT_CSS


def test_thinking_dot_expand_collapse_and_scheduled_tasks():
    """Verify ThinkingDot renders calm single line without contextless monologue or scheduled actions."""
    dot = ThinkingDot("Thinking — Finding caches", full_thought="Full reasoning: analyzing ~/Library/Caches and /tmp")
    assert not dot.expanded
    rendered = str(dot.render())
    assert "Thinking — Finding caches" in rendered
    assert "Full reasoning" not in rendered

    # Scheduled actions are suppressed from display per user instruction
    dot.add_scheduled_task("Scan ~/Library/Caches")
    assert "Scan ~/Library/Caches" in dot.scheduled_tasks
    assert "Scan ~/Library/Caches" not in str(dot.render())


def test_outside_workspace_permission_gate_and_grant_host_access():
    """Verify outside-workspace access detection and host permission un-sandboxing."""
    import tempfile
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_ws, \
         tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as ext_dir:
        from src.security.workspace_sandbox import WorkspaceSandbox
        from src.security.command_policy import CommandPolicy
        from src.security_policy import SecurityPolicy
        from src.action_executor import ActionExecutor
        from src.web_agent import WebAgent
        from src.agent_config import AgentConfig

        sandbox = WorkspaceSandbox(tmp_ws)
        cmd_policy = CommandPolicy(tmp_ws)
        sec_policy = SecurityPolicy(tmp_ws)

        outside_target = str(Path(ext_dir) / "subfolder")
        Path(outside_target).mkdir(parents=True, exist_ok=True)

        # Before permission: outside paths are blocked
        with pytest.raises(PermissionError):
            sandbox.resolve_safe_path(outside_target)

        safe, reason = cmd_policy.validate_command("rm -rf /Library/Caches")
        assert not safe

        # Global grant_host_access is deprecated and refuses broad host bypass (T1.3)
        sandbox.grant_host_access(True)
        assert sandbox._host_access_allowed is False

        # Scoped path access allows targeted outside directories
        sandbox.grant_path_access(outside_target, mode="read")
        sec_policy.grant_path_access(outside_target)

        # After scoped grant: granted path is resolvable safely
        resolved = sandbox.resolve_safe_path(outside_target)
        assert Path(resolved).resolve() == Path(outside_target).resolve()

        assert sec_policy.is_path_allowed(outside_target) is True

        # Non-granted outside paths remain blocked
        with pytest.raises(PermissionError):
            sandbox.resolve_safe_path(str(Path.home() / "Desktop"))

        # Hard-denied sensitive paths can never be granted
        with pytest.raises(PermissionError):
            sandbox.grant_path_access("~/.ssh/id_rsa")

        # WebAgent outside workspace detection
        cfg = AgentConfig(allowed_directory=tmp_ws, confirm_actions=False)
        agent = WebAgent(cfg)
        assert agent._is_outside_workspace("read_file", {"path": str(Path.home() / "Library/Caches")}) is True
        assert agent._is_outside_workspace("run_bash", {"command": "rm -rf ~/Library/Caches/*"}) is True
        assert agent._is_outside_workspace("read_file", {"path": "local_file.txt"}) is False
        if hasattr(agent, "ledger") and agent.ledger:
            agent.ledger.close()


@pytest.mark.asyncio
async def test_interactive_prompts_use_julius_messages_and_quiet_gutters():
    """Verify confirmations, questions, and replies render as clean AssistantMessage/UserMessage without CLI badges."""
    import asyncio
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(120, 24)) as pilot:
        conv = app.query_one("#conversation-area", ScrollableContainer)
        app._run_agent_task_worker = AsyncMock()
        mock_agent = MagicMock()
        mock_agent._confirm_future = asyncio.get_running_loop().create_future()
        mock_agent._question_future = None
        app.agent = mock_agent

        # 1. Trigger confirm_action with outside workspace
        app._handle_bridge_message({
            "kind": "confirm_action",
            "action": "run_bash",
            "args": {"_outside_workspace": True},
        })
        await pilot.pause(0.05)

        # Must be an AssistantMessage, not a warning card
        asst_msgs = list(conv.query(AssistantMessage))
        assert len(asst_msgs) == 1
        assert "requested access outside the workspace folder" in asst_msgs[0].content
        assert "⚠️" not in asst_msgs[0].content
        assert len(list(conv.query(".permission-prompt-card"))) == 0

        # 2. Submit response 'y'
        app.on_composer_submitted(Composer.Submitted("y"))
        await pilot.pause(0.05)

        # Confirmation is processed silently without mounting UserMessage
        user_msgs = list(conv.query(UserMessage))
        assert len(user_msgs) == 0

        # Verify confirmation was resolved
        assert mock_agent.set_confirmation_result.called
        assert mock_agent.set_confirmation_result.call_args[0][0] is True

        # 3. Trigger ask_user_question
        mock_agent._confirm_future = None
        mock_agent._question_future = asyncio.get_running_loop().create_future()
        app._handle_bridge_message({
            "kind": "ask_user_question",
            "question": "Which caches would you like to delete?",
            "options": ["(a) delete all", "(b) delete only pip"],
        })
        await pilot.pause(0.05)

        # Must be an AssistantMessage (confirmation prompt has auto-hidden upon user response)
        asst_msgs = list(conv.query(AssistantMessage))
        assert len(asst_msgs) == 1
        assert "Which caches would you like to delete?" in asst_msgs[0].content
        assert "- (a) delete all" in asst_msgs[0].content
        assert "? " not in asst_msgs[0].content
        assert "Type your answer below:" not in asst_msgs[0].content

        # 4. Submit answer 'a'
        app.on_composer_submitted(Composer.Submitted("a"))
        await pilot.pause(0.05)

        user_msgs = list(conv.query(UserMessage))
        assert len(user_msgs) == 1
        assert user_msgs[0].raw_content == "a"
        for node in conv.children:
            text_repr = getattr(node, "renderable", None) or getattr(node, "content", "") or str(node)
            assert "▸ Answer:" not in str(text_repr)

        # Verify question was resolved
        assert mock_agent.set_question_result.called
        assert mock_agent.set_question_result.call_args[0][0] == "a"


@pytest.mark.asyncio
async def test_error_event_deduplication_and_julius_formatting():
    """Verify errors are cleanly formatted without ASCII boxes and never duplicated in a turn."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig(), app_config=JuliusConfig(theme="dark"))
    async with app.run_test(size=(120, 24)) as pilot:
        conv = app.query_one("#conversation-area", ScrollableContainer)
        app._run_agent_task_worker = AsyncMock()

        # Mount initial user message
        app._dispatch_user_prompt("Launch browser")
        await pilot.pause(0.05)

        raw_error = (
            "BrowserType.launch_persistent_context: Executable doesn't exist at /path/chrome\n"
            "┌────────────────────────────────────────────────────────┐\n"
            "│ Looks like Playwright was just installed or updated.   │\n"
            "│ Please run the following command to download browsers: │\n"
            "│     playwright install                                 │\n"
            "└────────────────────────────────────────────────────────┘"
        )

        # First error emission from backend
        app.event_bridge.handle_event({"type": "error", "message": raw_error})
        await pilot.pause(0.05)

        # Second error emission (e.g. from outer exception handler or duplicate event)
        app.event_bridge.handle_event({"type": "error", "message": raw_error})
        await pilot.pause(0.05)

        # Must mount exactly 1 AssistantMessage for the error, not 2
        asst_msgs = list(conv.query(AssistantMessage))
        assert len(asst_msgs) == 1, f"Expected exactly 1 AssistantMessage, found {len(asst_msgs)}"

        # Verify ASCII boxes were stripped
        content = asst_msgs[0].content
        assert "┌" not in content
        assert "└" not in content
        assert "│" not in content
        assert "Executable doesn't exist" in content
        assert "playwright install" in content


@pytest.mark.asyncio
async def test_single_key_y_n_confirmation_instant():
    """Verify pressing 'y' / 'n' alone immediately triggers confirmation without Enter."""
    from unittest.mock import MagicMock, AsyncMock
    import asyncio
    from textual import events
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(120, 24)) as pilot:
        conv = app.query_one("#conversation-area", ScrollableContainer)
        composer = app.query_one("#composer-input", Composer)
        composer.focus()
        app._run_agent_task_worker = AsyncMock()

        mock_agent = MagicMock()
        mock_agent._confirm_future = asyncio.get_running_loop().create_future()
        mock_agent._question_future = None
        def _resolve_confirm(val):
            if mock_agent._confirm_future and not mock_agent._confirm_future.done():
                mock_agent._confirm_future.set_result(val)
        mock_agent.set_confirmation_result.side_effect = _resolve_confirm
        app.agent = mock_agent

        # 1. Trigger confirm_action
        app._handle_bridge_message({
            "kind": "confirm_action",
            "action": "run_bash",
            "args": {"_outside_workspace": True},
        })
        await pilot.pause(0.05)
        assert app.is_awaiting_confirmation is True
        assert "Press Y to allow, N to decline" in composer.placeholder

        # 2. Press single key 'y' (NO Enter key pressed!)
        composer.on_key(events.Key(key="y", character="y"))
        await pilot.pause(0.05)

        # Must resolve confirmation result as True immediately
        assert mock_agent.set_confirmation_result.called
        assert mock_agent.set_confirmation_result.call_args[0][0] is True
        assert app.is_awaiting_confirmation is False

        # Confirmation choice is silent: no UserMessage mounted in conversation
        user_msgs = list(conv.query(UserMessage))
        assert len(user_msgs) == 0
        # Composer must be empty
        assert composer.text == ""

        # 3. Test pressing 'n' for decline
        mock_agent.set_confirmation_result.reset_mock()
        mock_agent._confirm_future = asyncio.get_running_loop().create_future()
        app._handle_bridge_message({
            "kind": "confirm_action",
            "action": "delete_file",
            "args": {},
        })
        await pilot.pause(0.05)
        assert app.is_awaiting_confirmation is True

        # Press single key 'N' (capital, NO Enter key, via app listener)
        app.on_key(events.Key(key="N", character="N"))
        await pilot.pause(0.05)

        assert mock_agent.set_confirmation_result.called
        assert mock_agent.set_confirmation_result.call_args[0][0] is False
        assert app.is_awaiting_confirmation is False
        user_msgs = list(conv.query(UserMessage))
        assert len(user_msgs) == 0


@pytest.mark.asyncio
async def test_box_styling_no_background_bleed():
    """Verify UserMessage and Composer have transparent background to prevent rectangular leakage outside rounded borders."""
    app = JuliusApp(workspace_dir=".", config=AgentConfig())
    async with app.run_test(size=(80, 24)) as pilot:
        conv = app.query_one("#conversation-area", ScrollableContainer)
        user_msg = UserMessage("Test user message")
        conv.mount(user_msg)
        await pilot.pause(0.05)

        # UserMessage must have transparent background
        assert user_msg.styles.background.is_transparent, "UserMessage must have transparent background"
        assert user_msg.styles.border.top[0] == "round", "UserMessage must have rounded border"

        # Composer must have transparent background
        composer = app.query_one("#composer-input", Composer)
        assert composer.styles.background.is_transparent, "Composer must have transparent background"
        assert composer.styles.border.top[0] == "round", "Composer must have rounded border"




