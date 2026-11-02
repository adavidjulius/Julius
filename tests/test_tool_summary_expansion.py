"""
Tests for ThinkingDot click-to-expand, completion disappearance,
and ToolSummary per-step opening arrows with command inspection.
"""

import pytest
from textual import events
from src.tui.app import JuliusApp
from src.tui.components.message import ThinkingDot
from src.tui.components.tool_summary import ToolSummary
from src.tui.state import ToolExecutionRecord


@pytest.mark.asyncio
async def test_thinking_dot_click_expands_and_collapses():
    """Verify thinking bar is present while thinking and can be clicked to expand/collapse."""
    dot = ThinkingDot("Thinking — analyzing repository", full_thought="Inspecting files and planning brand guide")
    assert not dot.expanded

    # Click to expand
    dot.on_click(events.Click(widget=dot, x=0, y=0, delta_x=0, delta_y=0, button=1, shift=False, meta=False, ctrl=False))
    assert dot.expanded is True
    rendered_expanded = str(dot.render())
    assert "Inspecting files and planning brand guide" in rendered_expanded
    assert "⌄" in rendered_expanded

    # Click again to collapse
    dot.on_click(events.Click(widget=dot, x=0, y=0, delta_x=0, delta_y=0, button=1, shift=False, meta=False, ctrl=False))
    assert dot.expanded is False
    rendered_collapsed = str(dot.render())
    assert "Inspecting files and planning brand guide" not in rendered_collapsed


@pytest.mark.asyncio
async def test_thinking_dot_disappears_on_completion_with_tools():
    """Verify thinking dot disappears after task completion when tools were executed, leaving only ToolSummary."""
    app = JuliusApp()
    async with app.run_test(size=(100, 24)) as pilot:
        conv_area = app.query_one("#conversation-area")
        dot = ThinkingDot("Thinking — preparing execution")
        app.active_thinking_dot = dot
        await conv_area.mount(dot)
        await pilot.pause(0.05)

        # Active thinking dot exists
        assert len(conv_area.query(ThinkingDot)) == 1

        tools = [
            ToolExecutionRecord(
                tool_name="search_files",
                summary="Executed search_files (brand)",
                duration_s=0.1,
                command="search_files(pattern='brand', path='Brand Book')",
                output="Found 3 matches",
            )
        ]

        # Dispatch task completion with tools
        app._handle_bridge_message({
            "kind": "done",
            "summary": "Here is the plan for the brand guide.",
            "tools": tools,
        })
        await pilot.pause(0.05)

        # Thinking dot MUST disappear completely from the conversation area
        assert len(conv_area.query(ThinkingDot)) == 0, "Thinking dot should disappear after completion when tools ran"

        # ToolSummary MUST be mounted
        summaries = list(conv_area.query(ToolSummary))
        assert len(summaries) == 1
        assert "Ran 1 step" in str(summaries[0]._content_widget.render())


@pytest.mark.asyncio
async def test_thinking_dot_disappears_on_completion_without_tools():
    """Verify thinking dot disappears completely when response completes without running any tools (conversational turn)."""
    from src.tui.components.message import AssistantMessage

    app = JuliusApp()
    async with app.run_test(size=(100, 24)) as pilot:
        conv_area = app.query_one("#conversation-area")
        dot = ThinkingDot("Thinking")
        app.active_thinking_dot = dot
        await conv_area.mount(dot)
        await pilot.pause(0.05)

        assert len(conv_area.query(ThinkingDot)) == 1

        # Turn finishes with conversational answer and NO tools executed
        app._handle_bridge_message({
            "kind": "done",
            "summary": "I am an AI assistant and I answered directly without tools.",
            "tools": [],
        })
        await pilot.pause(0.05)

        # Thinking dot MUST disappear completely from DOM
        assert len(conv_area.query(ThinkingDot)) == 0, "Thinking dot should disappear after completion without tools"
        assert app.active_thinking_dot is None

        # No ToolSummary should be mounted
        assert len(conv_area.query(ToolSummary)) == 0, "No Ran X steps should be mounted for direct answers"

        # Assistant response must be mounted directly
        msgs = list(conv_area.query(AssistantMessage))
        assert len(msgs) == 1
        assert "answered directly without tools" in msgs[0].content


def test_thinking_dot_no_duplicate_thinking_label():
    """Verify ThinkingDot never produces duplicate 'Thinking — Thinking' and transitions cleanly to context."""
    # 1. Start label should be cleanly 'Thinking', not 'Thinking — Thinking'
    dot = ThinkingDot("Thinking")
    assert dot.label == "Thinking"
    rendered = str(dot.render())
    assert "Thinking — Thinking" not in rendered
    assert "Thinking" in rendered

    # 2. Updating with new context converts into 'Thinking — Context'
    dot.update_label("Scanning files")
    assert dot.label == "Thinking — Scanning files"
    rendered2 = str(dot.render())
    assert "Thinking — Thinking" not in rendered2
    assert "Thinking — Scanning files" in rendered2

    # 3. If incoming thought has redundant prefix, strip it cleanly
    dot.update_label("Thinking — Checking git status")
    assert dot.label == "Thinking — Checking git status"

    dot.update_label("Thinking this is conversational, but the message implies I helped")
    assert dot.label == "Thinking — This is conversational, but the message implies I helped"


def test_thinking_dot_format_summary_prefix_stripping():
    """Verify format_summary handles all edge cases and strips redundant prefixes."""
    assert ThinkingDot.format_summary("") == "Thinking"
    assert ThinkingDot.format_summary("   ") == "Thinking"
    assert ThinkingDot.format_summary("Thinking") == "Thinking"
    assert ThinkingDot.format_summary("thinking") == "Thinking"
    assert ThinkingDot.format_summary("Thinking...") == "Thinking"
    assert ThinkingDot.format_summary("Thinking…") == "Thinking"
    assert ThinkingDot.format_summary("Thinking — Thinking") == "Thinking"
    assert ThinkingDot.format_summary("Thinking - Thinking") == "Thinking"
    assert ThinkingDot.format_summary("Thinking: Thinking") == "Thinking"
    assert ThinkingDot.format_summary("Thinking — Thinking — Searching files") == "Thinking — Searching files"
    assert ThinkingDot.format_summary("Thinking Process: inspecting code") == "Thinking — Inspecting code"
    assert ThinkingDot.format_summary("Thought: analyzing repository") == "Thinking — Analyzing repository"
    assert ThinkingDot.format_summary("Reasoning: checking disk space") == "Thinking — Checking disk space"
    assert ThinkingDot.format_summary("Thinking this is conversational") == "Thinking — This is conversational"
    assert ThinkingDot.format_summary("Thinking analyzing repository") == "Thinking — Analyzing repository"


@pytest.mark.asyncio
async def test_tool_summary_nested_arrow_command_expansion():
    """Verify ToolSummary expands to show steps with arrows, and clicking a step opens its command and output."""
    tools = [
        ToolExecutionRecord(
            tool_name="search_files",
            summary="Executed search_files",
            duration_s=0.1,
            command="search_files(pattern='brand', path='.')",
            output="3 files matched",
        ),
        ToolExecutionRecord(
            tool_name="read_file",
            summary="Read file Brand Book/INSTALLATION_GUIDE.md",
            duration_s=0.2,
            command="read_file(path='Brand Book/INSTALLATION_GUIDE.md')",
            output="# Julius Agent Installation Guide",
        ),
        ToolExecutionRecord(
            tool_name="run_bash",
            summary="Ran bash: git status",
            duration_s=0.3,
            command="git status --short",
            output="M install.sh",
        ),
    ]

    app = JuliusApp()
    async with app.run_test(size=(100, 24)) as pilot:
        conv_area = app.query_one("#conversation-area")
        summary_widget = ToolSummary(tools, total_duration_s=0.6)
        await conv_area.mount(summary_widget)
        await pilot.pause(0.05)

        assert not summary_widget.expanded

        # Collapsed view
        collapsed_text = str(summary_widget._content_widget.render())
        assert "Ran 3 steps" in collapsed_text
        assert "Executed search_files" not in collapsed_text

        # 1. Expand whole summary
        summary_widget.on_click(events.Click(widget=summary_widget, x=0, y=0, delta_x=0, delta_y=0, button=1, shift=False, meta=False, ctrl=False))
        await pilot.pause(0.02)
        assert summary_widget.expanded is True

        expanded_text = str(summary_widget._content_widget.render())
        assert "⌄ Ran 3 steps" in expanded_text
        assert "› Executed search_files (0.1s)" in expanded_text
        assert "› Read file Brand Book/INSTALLATION_GUIDE.md (0.2s)" in expanded_text
        assert "› Ran bash: git status (0.3s)" in expanded_text
        # Commands should not be visible yet
        assert "search_files(pattern=" not in expanded_text

        # 2. Click step 0 (Executed search_files) at line 1
        summary_widget.on_click(events.Click(widget=summary_widget, x=0, y=1, delta_x=0, delta_y=0, button=1, shift=False, meta=False, ctrl=False))
        await pilot.pause(0.02)
        assert 0 in summary_widget.expanded_steps

        step0_open_text = str(summary_widget._content_widget.render())
        # Step 0 now has open arrow ⌄ and displays its command & output inside a dynamic grey box!
        assert "⌄ Executed search_files (0.1s)" in step0_open_text
        assert "$ search_files(pattern='brand', path='.')" in step0_open_text
        assert "3 files matched" in step0_open_text
        assert "╭" in step0_open_text and "╰" in step0_open_text, "Step command should be enclosed in dynamic grey box"
        # Step 1 is still collapsed with ›
        assert "› Read file Brand Book/INSTALLATION_GUIDE.md (0.2s)" in step0_open_text

        # 3. Click line 0 to collapse the entire ToolSummary
        summary_widget.on_click(events.Click(widget=summary_widget, x=0, y=0, delta_x=0, delta_y=0, button=1, shift=False, meta=False, ctrl=False))
        await pilot.pause(0.02)
        assert summary_widget.expanded is False
        assert "Executed search_files" not in str(summary_widget._content_widget.render())


@pytest.mark.asyncio
async def test_thinking_panel_grey_box_and_multi_thought_accumulation():
    """Verify thinking panel accumulates streaming thoughts and renders a clean grey container."""
    dot = ThinkingDot("Thinking — analyzing repository")
    dot.append_thought("Top-level junk removed. A top-level pycache still shows.")
    dot.append_thought("Inspecting git status to verify clean tree.")
    assert len(dot.thoughts) == 2

    # Toggle expansion
    dot.toggle()
    assert dot.expanded is True

    rendered = str(dot.render())
    assert ("╭" in rendered or "┌" in rendered) and ("╰" in rendered or "└" in rendered), "Expanded thinking panel must render container borders"
    assert "Top-level junk removed" in rendered
    assert "Inspecting git status" in rendered
    assert "⌄" in rendered
