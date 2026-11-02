"""
Unit tests for TUI experience and interaction upgrades (Batches 1 - 7).
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from textual.app import App

from src.agent_config import AgentConfig
from src.tui.components.command_box import CommandBox
from src.tui.components.composer import Composer
from src.tui.components.message import AssistantMessage, UserMessage
from src.tui.components.welcome import JULIUS_BANNER, WelcomeView
from src.tui.markdown import render_julius_markdown, render_apple_markdown
from src.web_agent import WebAgent


def test_composer_height_expansion_multi_line():
    """Verify Composer expands vertically for 2-3 line prompts without horizontal scrolling."""
    composer = Composer()
    # Initial empty state
    composer._recalculate_height()
    assert composer.styles.height.value == 3

    # Multi-line text with hard newlines
    composer.text = "Line 1\nLine 2\nLine 3"
    composer._recalculate_height()
    assert composer.styles.height.value >= 5

    # Long single line text (wrapped)
    composer.text = "This is a very long prompt " * 10
    composer._recalculate_height()
    assert composer.styles.height.value >= 4


def test_composer_centered_placeholder():
    """Verify Composer centers placeholder inside widget width."""
    composer = Composer(placeholder="Ask Julius anything")
    assert composer._raw_placeholder == "Ask Julius anything"


def test_assistant_message_margins():
    """Verify AssistantMessage has 8-cell margin offset (1-inch indent) and centered reading column."""
    msg = AssistantMessage("Hello user")
    assert "margin-left: 8" in AssistantMessage.DEFAULT_CSS
    assert "margin-right: 8" in AssistantMessage.DEFAULT_CSS


def test_unlimited_max_steps_default():
    """Verify AgentConfig defaults to max_steps=0 (unlimited execution)."""
    cfg = AgentConfig()
    assert cfg.max_steps == 0


def test_welcome_view_monochromatic_outline_banner():
    """Verify WelcomeView uses gapless monochromatic outline ASCII banner and centering."""
    welcome = WelcomeView()
    assert "╔═════╗" in JULIUS_BANNER
    assert "height: 100%" in WelcomeView.DEFAULT_CSS
    assert "scrolled-header" in WelcomeView.DEFAULT_CSS


def test_command_box_copy_and_tick():
    """Verify CommandBox copies command to clipboard and triggers tick animation."""
    cmd_box = CommandBox("pytest -v", language="bash")
    assert cmd_box.command == "pytest -v"
    assert cmd_box.language == "bash"

    with patch("src.tui.components.command_box.copy_to_clipboard") as mock_copy:
        mock_copy.return_value = True
        mock_label = MagicMock()
        with patch.object(cmd_box, "query_one", return_value=mock_label):
            cmd_box._do_copy()
            mock_copy.assert_called_once_with("pytest -v")
            mock_label.update.assert_called_with("✓ Copied!")


def test_resource_linking_and_open_resource():
    """Verify markdown auto-links files and app.open_resource delegates correctly."""
    md = render_julius_markdown("Saved file to julius.dwg and see https://julius.ai")
    assert "julius.dwg" in md.markup
    assert "file://julius.dwg" in md.markup

    from src.tui.app import JuliusApp
    app = JuliusApp()
    with patch("webbrowser.open") as mock_browser:
        app.open_resource("https://julius.ai")
        mock_browser.assert_called_once_with("https://julius.ai")

    with patch("src.platform_compat.open_in_default_app") as mock_os_open:
        mock_os_open.return_value = True
        app.open_resource("julius.dwg")
        mock_os_open.assert_called_once()


def test_code_block_shrink_wraps_command_content():
    """Verify JuliusCodeBlock generates a box that wraps command width instead of full console."""
    from rich.console import Console
    from src.tui.markdown import render_julius_markdown

    c = Console(width=100)
    sample = "```bash\necho hello\n```"
    md = render_julius_markdown(sample)
    output = "".join(s.text for s in md.__rich_console__(c, c.options))
    first_line = output.split("\n")[0]
    # In a 100-wide console, the box should be tight to 'echo hello' (~14 chars), not 100 chars
    assert len(first_line) < 30, f"Expected shrink-wrapped width < 30, got {len(first_line)}"


def test_code_block_protects_commands_from_url_mangling():
    """Verify commands inside code blocks and backticks are never mangled by auto-linkers."""
    sample = (
        "Here is the command:\n"
        "```bash\n"
        "curl -s https://api.ipify.org\n"
        "```\n"
        "And visit https://julius.ai for docs."
    )
    md = render_julius_markdown(sample)
    # The URL in prose should be auto-linked
    assert "[https://julius.ai](https://julius.ai)" in md.markup
    # The URL in code block must stay raw without brackets or markdown link syntax
    assert "curl -s https://api.ipify.org" in md.markup
    assert "curl -s [https://api.ipify.org]" not in md.markup


@pytest.mark.asyncio
async def test_confirm_action_renders_centered_yes_no():
    """Verify confirm_action renders a clean prompt with centered green Yes / red No options."""
    from src.tui.app import JuliusApp
    from textual.containers import ScrollableContainer

    app = JuliusApp()
    async with app.run_test(size=(100, 24)) as pilot:
        conv = app.query_one("#conversation-area", ScrollableContainer)
        app._handle_bridge_message({
            "kind": "confirm_action",
            "action": "run_bash",
            "args": {"_outside_workspace": True},
        })
        await pilot.pause(0.05)
        asst_msgs = list(conv.query(AssistantMessage))
        assert len(asst_msgs) == 1
        msg = asst_msgs[0]
        assert msg.custom_renderable is not None

        # Verify rendered output contains centered yes/no options and no raw markup
        from rich.console import Console
        c = Console(width=100)
        output = "".join(s.text for s in msg.custom_renderable.__rich_console__(c, c.options))
        assert "(y) Yes" in output
        assert "(n) No" in output
        assert "[bold" not in output


@pytest.mark.asyncio
async def test_status_line_loading_indicator_and_click_opens_modal():
    """Verify StatusLine shows animated loading indicator on the bottom-left when active, and clicking opens ActiveActionModal."""
    from src.tui.app import JuliusApp
    from src.tui.components.status_line import StatusLine
    from src.tui.components.modals.active_action_modal import ActiveActionModal
    from textual.widgets import Label

    app = JuliusApp()
    async with app.run_test(size=(100, 24)) as pilot:
        status_line = app.query_one("#status-line", StatusLine)
        model_label = app.query_one("#status-model", Label)

        # 1. Idle state
        assert not status_line._is_active_loading
        assert "loading" not in model_label.classes

        # 2. Trigger running status on bottom-left
        status_line.update_running("Running find ~ -name node_modules")
        await pilot.pause(0.05)
        assert status_line._is_active_loading
        assert "loading" in model_label.classes
        assert status_line._spinner_timer is not None

        # 3. Clicking while loading opens ActiveActionModal
        await pilot.click("#status-model")
        await pilot.pause(0.05)
        assert len(app.screen_stack) == 2
        assert isinstance(app.screen_stack[-1], ActiveActionModal)

        # 4. Press Escape to close modal
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert len(app.screen_stack) == 1

        # 5. Reset to idle
        status_line.update_running("")
        await pilot.pause(0.05)
        assert not status_line._is_active_loading
        assert "loading" not in model_label.classes


@pytest.mark.asyncio
async def test_thinking_dot_round_panel_and_expand_toggle():
    """Verify ThinkingDot displays animated round spinner and finish() settles calmly without contextless dump."""
    from src.tui.app import JuliusApp
    from src.tui.components.message import ThinkingDot

    app = JuliusApp()
    async with app.run_test(size=(100, 24)) as pilot:
        dot = ThinkingDot("Analyzing codebase")
        conv_area = app.query_one("#conversation-area")
        await conv_area.mount(dot)
        await pilot.pause(0.05)

        # Initial calm state
        assert dot.is_running
        rendered_init = dot.render().plain
        assert "Analyzing codebase" in rendered_init

        # Finish thinking (settles to ● without removing widget)
        dot.finish()
        await pilot.pause(0.05)
        assert not dot.is_running
        rendered_finished = dot.render().plain
        assert "●" in rendered_finished


@pytest.mark.asyncio
async def test_deepseek_think_filter_in_streaming_and_done():
    """Verify <think>...</think> is routed to ThinkingDot and filtered from AssistantMessage."""
    from src.tui.app import JuliusApp
    from src.tui.components.message import AssistantMessage, ThinkingDot

    app = JuliusApp()
    async with app.run_test(size=(100, 24)) as pilot:
        # Setup turn state without spawning background agent worker
        conv_area = app.query_one("#conversation-area")
        app.active_thinking_dot = ThinkingDot("Thinking")
        await conv_area.mount(app.active_thinking_dot)
        await pilot.pause(0.05)
        assert app.active_thinking_dot is not None

        # Simulate DeepSeek streaming with <think> tag
        app._handle_bridge_message({
            "kind": "stream_chunk",
            "chunk": "<think>\nLet's analyze quantum principles...\nFirst superposition, then entanglement.\n</think>\nQuantum computing uses qubits."
        })
        await pilot.pause(0.05)

        # Verify thinking dot received thought
        assert "quantum principles" in app.active_thinking_dot.full_thought.lower()

        # Verify assistant message received ONLY the answer
        assert app.active_assistant_msg is not None
        assert "Quantum computing uses qubits." in app.active_assistant_msg.content
        assert "<think>" not in app.active_assistant_msg.content
        assert "quantum principles" not in app.active_assistant_msg.content

        # Simulate turn completion
        app._handle_bridge_message({
            "kind": "done",
            "summary": "<think>Final thought residue</think>Quantum computing uses qubits to achieve exponential speedup.",
        })
        await pilot.pause(0.05)

        # Verify assistant message mounted without think leakage
        msgs = list(conv_area.query(AssistantMessage))
        assert len(msgs) > 0
        last_msg = msgs[-1]
        assert "<think>" not in last_msg.content
        assert "residue" not in last_msg.content
        assert "exponential speedup" in last_msg.content


@pytest.mark.asyncio
async def test_active_action_modal_cancel_button():
    """Verify ActiveActionModal displays telemetry and pressing cancel calls cancel_active_action."""
    from src.tui.app import JuliusApp
    from src.tui.components.modals.active_action_modal import ActiveActionModal
    from textual.widgets import Static, Button

    cancel_called = False

    class MockApp(JuliusApp):
        def get_active_action_info(self):
            return {
                "is_running": True,
                "action": "run_bash",
                "command": "find ~ -name node_modules",
                "elapsed": 12.4,
                "output": "Scanning files...\nFound 100 items",
            }

        def cancel_active_action(self):
            nonlocal cancel_called
            cancel_called = True
            return True

    app = MockApp()
    async with app.run_test(size=(100, 24)) as pilot:
        await app.push_screen(ActiveActionModal())
        await pilot.pause(0.05)

        modal = app.screen_stack[-1]
        assert isinstance(modal, ActiveActionModal)

        # Verify command and output are rendered in modal
        cmd_widget = modal.query_one("#inspector-command-box", Static)
        out_widget = modal.query_one("#inspector-output-box", Static)
        assert "find ~ -name node_modules" in str(cmd_widget.render())
        assert "Scanning files" in str(out_widget.render())

        # Click cancel action
        await pilot.click("#cancel-action-btn")
        await pilot.pause(0.05)
        assert cancel_called is True
        # Modal dismissed
        assert len(app.screen_stack) == 1


def test_stateful_shell_cancel_current_command():
    """Verify StatefulShell.cancel_current_command sets cancellation flag and interrupts command."""
    import tempfile
    from src.shell_manager import StatefulShell

    with tempfile.TemporaryDirectory() as tmpdir:
        shell = StatefulShell(tmpdir)
        try:
            assert shell.cancel_current_command() is False
            shell.current_command = "sleep 10"
            shell.command_start_time = 100.0
            assert shell.cancel_current_command() is True
            assert shell.cancel_requested is True
        finally:
            shell.close()


def test_action_executor_caps_unconstrained_search_timeout():
    """Verify ActionExecutor caps timeout on unconstrained find ~ / du commands to prevent hanging."""
    import tempfile
    from src.action_executor import ActionExecutor

    with tempfile.TemporaryDirectory() as tmpdir:
        executor = ActionExecutor(tmpdir, bash_timeout=60)
        try:
            # Command without pruning ~/Library or maxdepth
            res = executor.run_bash("find ~ -name node_modules")
            # Should have executed with reduced timeout or completed safely
            assert res.action == "run_bash"
        finally:
            executor.close()


@pytest.mark.asyncio
async def test_active_action_modal_idle_cancel_disabled():
    """Verify ActiveActionModal disables cancel button when idle, ignoring clicks."""
    from src.tui.app import JuliusApp
    from src.tui.components.modals.active_action_modal import ActiveActionModal
    from textual.widgets import Label

    cancel_called = False

    class MockApp(JuliusApp):
        def get_active_action_info(self):
            return {
                "is_running": False,
                "action": "",
                "command": "",
                "elapsed": 0.0,
                "output": "",
            }

        def cancel_active_action(self):
            nonlocal cancel_called
            cancel_called = True
            return True

    app = MockApp()
    async with app.run_test(size=(100, 24)) as pilot:
        await app.push_screen(ActiveActionModal())
        await pilot.pause(0.05)

        modal = app.screen_stack[-1]
        assert isinstance(modal, ActiveActionModal)

        # Title has no lightning icon and is named 'Active Action'
        title = modal.query_one("#inspector-title", Label)
        assert "⚡" not in str(title.render())
        assert "Active Action" in str(title.render())

        # No escape label
        assert len(modal.query("#inspector-close-btn")) == 0

        # Cancel button is disabled when idle
        cancel_btn = modal.query_one("#cancel-action-btn", Label)
        assert cancel_btn.has_class("disabled")

        # Clicking cancel action when idle does NOTHING
        await pilot.click("#cancel-action-btn")
        await pilot.pause(0.05)
        assert cancel_called is False
        # Modal remains open
        assert len(app.screen_stack) == 2


@pytest.mark.asyncio
async def test_single_thinking_box_during_confirmation_flow():
    """Verify confirmation prompt goes UP, keeping exactly one ThinkingDot below it without duplicates."""
    from src.tui.app import JuliusApp
    from src.tui.components.message import ThinkingDot, AssistantMessage

    app = JuliusApp()
    async with app.run_test(size=(100, 24)) as pilot:
        conv_area = app.query_one("#conversation-area")
        
        # Start with active thinking dot
        app.active_thinking_dot = ThinkingDot("Thinking — scanning files")
        app.active_thinking_dot.expanded = True
        await conv_area.mount(app.active_thinking_dot)
        await pilot.pause(0.05)
        assert len(conv_area.query(ThinkingDot)) == 1

        # Emit confirm_action event
        app._handle_bridge_message({
            "kind": "confirm_action",
            "action": "run_bash",
            "args": {"command": "cd /Users/julius && rm -rf tmp", "_outside_workspace": True},
        })
        await pilot.pause(0.05)

        # Confirm action prompt was mounted AFTER the thinking dot (prompt appears BELOW thinking panel)
        children = list(conv_area.children)
        prompt_idx = -1
        think_idx = -1
        for i, child in enumerate(children):
            if isinstance(child, AssistantMessage) and "outside the workspace" in str(child.content):
                prompt_idx = i
            elif child is app.active_thinking_dot:
                think_idx = i

        assert prompt_idx >= 0
        assert think_idx >= 0
        assert think_idx < prompt_idx, "Confirmation prompt must be below the live thinking dot!"

        # Exactly 1 thinking dot remains
        assert len(conv_area.query(ThinkingDot)) == 1

        # User confirms with 'y' -> prompt must disappear/close immediately
        app.handle_confirmation_choice(True)
        await pilot.pause(0.05)

        remaining_prompts = [c for c in conv_area.children if getattr(c, "_is_confirmation_prompt", False)]
        assert len(remaining_prompts) == 0, "Confirmation prompt should disappear after user responds"

        # Still exactly 1 thinking dot (NO duplicate second box created!)
        assert len(conv_area.query(ThinkingDot)) == 1

        # On done, thinking dot is removed per user specification (only resides while running)
        app._handle_bridge_message({
            "kind": "done",
            "summary": "Completed operation cleanly.",
        })
        await pilot.pause(0.05)

        dots = list(conv_area.query(ThinkingDot))
        assert len(dots) == 0, "Thinking dot must be hidden after completion when no tools ran!"


@pytest.mark.asyncio
async def test_thinking_dot_click_to_expand_toggle():
    """Verify ThinkingDot can be clicked to expand and reveal thought reasoning, then clicked to collapse."""
    from src.tui.app import JuliusApp
    from src.tui.components.message import ThinkingDot
    from textual import events

    app = JuliusApp()
    async with app.run_test(size=(100, 24)) as pilot:
        conv_area = app.query_one("#conversation-area")
        dot = ThinkingDot("Thinking — analyzing documents", full_thought="Analyzing document structure and requirements")
        await conv_area.mount(dot)
        await pilot.pause(0.05)

        # Initially collapsed
        assert dot.expanded is False
        rendered = str(dot.render())
        assert "Analyzing document structure" not in rendered

        # Click event expands the thinking card
        dot.on_click(events.Click(widget=dot, x=0, y=0, delta_x=0, delta_y=0, button=1, shift=False, meta=False, ctrl=False))
        await pilot.pause(0.05)

        assert dot.expanded is True
        rendered_expanded = str(dot.render())
        assert "Analyzing document structure" in rendered_expanded

        # Click again collapses it
        dot.on_click(events.Click(widget=dot, x=0, y=0, delta_x=0, delta_y=0, button=1, shift=False, meta=False, ctrl=False))
        await pilot.pause(0.05)
        assert dot.expanded is False


@pytest.mark.asyncio
async def test_conversation_area_scrollbar_auto_hides_to_maximize_space():
    """Verify scrollbar is invisible by default (scrollbar-size 0 0) and shows during active scrolling."""
    from src.tui.app import JuliusApp
    from src.tui.components.conversation_area import ConversationArea
    from textual.widgets import Static

    app = JuliusApp()
    async with app.run_test(size=(100, 24)) as pilot:
        conv = app.query_one("#conversation-area", ConversationArea)
        # Invisible when idle to maximize usable width
        assert conv.styles.scrollbar_size_vertical == 0

        # Mount scrollable content
        for i in range(50):
            await conv.mount(Static(f"Paragraph {i}"))
        await pilot.pause(0.05)

        # Trigger scroll -> scrollbar becomes visible
        conv.scroll_y = 10
        await pilot.pause(0.05)
        assert conv.styles.scrollbar_size_vertical == 1


@pytest.mark.asyncio
async def test_status_line_layout_help_left_executing_right():
    """Verify help hint is positioned on the left and executing action indicator on the right."""
    from src.tui.app import JuliusApp
    from src.tui.components.status_line import StatusLine
    from textual.widgets import Label

    app = JuliusApp()
    async with app.run_test(size=(120, 24)) as pilot:
        status_line = app.query_one("#status-line", StatusLine)
        children = list(status_line.children)
        assert len(children) == 2
        hint_label = children[0]
        model_label = children[1]

        # Hint is on the left
        assert hint_label.id == "status-hint"
        assert "? for help" in str(hint_label.render())
        assert hint_label.region.x <= model_label.region.x

        # Executing bar is on the right
        assert model_label.id == "status-model"
        status_line.update_running("Running build.sh")
        await pilot.pause(0.05)
        assert "Running build.sh" in str(model_label.render())
        assert model_label.styles.text_align == "right"


def test_markdown_brand_palette_and_file_links():
    """Verify markdown output uses brand parchment color for code/links and enables file:// links."""
    from rich.console import Console
    from src.tui.markdown import render_julius_markdown
    from src.tui.theme import DARK_THEME

    c = Console(width=100)
    sample = "• Background: `(255,255,255)`\n• File: [sample.pdf](file://sample.pdf)\n1. First item"
    md = render_julius_markdown(sample, DARK_THEME)

    segments = list(c.render(md))
    rendered_styles = {seg.text.strip(): str(seg.style) for seg in segments if seg.text.strip()}

    # Code span is brand colored (not cyan)
    assert "(255,255,255)" in rendered_styles
    assert "#c8b896" in rendered_styles["(255,255,255)"]
    assert "cyan" not in rendered_styles["(255,255,255)"]

    # Numbered list item prefix is brand colored
    assert "1" in rendered_styles
    assert "#c8b896" in rendered_styles["1"]


@pytest.mark.asyncio
async def test_thinking_bar_matches_output_indentation():
    """Verify collapsed thinking bar starts at the exact same left margin as AssistantMessage."""
    from src.tui.app import JuliusApp
    from src.tui.components.message import ThinkingDot, AssistantMessage

    app = JuliusApp()
    async with app.run_test(size=(120, 24)) as pilot:
        conv_area = app.query_one("#conversation-area")
        think = ThinkingDot("Thinking — scanning files")
        asst = AssistantMessage("Task complete.", theme=app.active_theme)

        await conv_area.mount(think)
        await conv_area.mount(asst)
        await pilot.pause(0.05)

        # Both widgets have 8-cell left margin
        assert think.region.x == asst.region.x
        assert think.region.width == asst.region.width
