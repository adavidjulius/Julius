"""
Tests for Julius CLI v3.1 output formatting, event deduplication, and streaming tracking.
Guarantees:
1. Internal control-flow actions ('done', 'converse', 'finish') are NEVER printed as user tools.
2. Internal action result outputs ('Task completed:', 'Conversation recorded:') are suppressed.
3. Assistant completion summary is printed exactly once without box panels or repetitive blocks.
4. Token counts and streaming previews are tracked in real time during execution.
"""

import pytest
from unittest.mock import MagicMock
from src.agent_config import AgentConfig
from src.cli.v3_tui import JuliusCLIV3App


@pytest.mark.asyncio
async def test_v3_tui_suppresses_done_and_converse_action_leakage():
    """Verify 'done' and 'converse' actions are not rendered as tools."""
    config = AgentConfig()
    app = JuliusCLIV3App(workspace_dir=".", config=config)

    async with app.run_test() as pilot:
        log = app.query_one("#conversation-log")
        written_lines = []

        orig_write = log.write
        def spy_write(item, *args, **kwargs):
            written_lines.append(str(item))
            return orig_write(item, *args, **kwargs)

        log.write = spy_write

        # 1. Action 'done' should NOT be written to log
        app._handle_agent_event({"type": "action", "name": "done", "args": {"summary": "Completed test"}})
        assert not any("Tool (done)" in l for l in written_lines), "Internal 'done' action was leaked to output!"

        # 2. Action 'converse' should NOT be written to log
        app._handle_agent_event({"type": "action", "name": "converse", "args": {"message": "Hello"}})
        assert not any("Tool (converse)" in l for l in written_lines), "Internal 'converse' action was leaked to output!"

        # 3. Action 'ask_human' should NOT be written to log
        app._handle_agent_event({"type": "action", "name": "ask_human", "args": {"question": "Clarify please"}})
        assert not any("Tool (ask_human)" in l for l in written_lines), "Internal 'ask_human' action was leaked to output!"

        # 4. Action 'run_bash' SHOULD be written to log
        app._handle_agent_event({"type": "action", "name": "run_bash", "args": {"command": "echo test"}})
        assert any("Bash:" in l for l in written_lines), "Valid tool 'run_bash' should be logged"


@pytest.mark.asyncio
async def test_v3_tui_suppresses_task_completed_result():
    """Verify 'Task completed: ...' result outputs are not rendered to avoid duplication."""
    config = AgentConfig()
    app = JuliusCLIV3App(workspace_dir=".", config=config)

    async with app.run_test() as pilot:
        log = app.query_one("#conversation-log")
        written_lines = []

        orig_write = log.write
        def spy_write(item, *args, **kwargs):
            written_lines.append(str(item))
            return orig_write(item, *args, **kwargs)

        log.write = spy_write

        # Result 'Task completed: ...' should be suppressed
        app._handle_agent_event({"type": "result", "output": "Task completed: Files verified successfully."})
        assert not any("Task completed:" in l for l in written_lines)

        # Real tool result should be rendered
        app._handle_agent_event({"type": "result", "output": "file1.txt\nfile2.txt", "success": True})
        assert any("Output:" in l for l in written_lines)


@pytest.mark.asyncio
async def test_v3_tui_renders_done_summary_exactly_once():
    """Verify 'done' event outputs the assistant response once in clean markdown without box duplicates."""
    config = AgentConfig()
    app = JuliusCLIV3App(workspace_dir=".", config=config)

    async with app.run_test() as pilot:
        log = app.query_one("#conversation-log")
        written_lines = []

        orig_write = log.write
        def spy_write(item, *args, **kwargs):
            from rich.markdown import Markdown
            if isinstance(item, Markdown):
                written_lines.append(item.markup)
            else:
                written_lines.append(str(item))
            return orig_write(item, *args, **kwargs)

        log.write = spy_write

        unique_summary = "Unique assistant response text for testing deduplication."
        app._handle_agent_event({"type": "done", "summary": unique_summary})

        joined = " ".join(written_lines)
        count = joined.count(unique_summary)
        assert count == 1, f"Expected summary to appear exactly once, but appeared {count} times: {written_lines}"
        assert "Task Done" not in joined, "Giant duplicate Task Done box should not be rendered"


@pytest.mark.asyncio
async def test_v3_tui_streaming_and_token_count_tracking():
    """Verify live status token counter and thought stream extraction."""
    config = AgentConfig()
    app = JuliusCLIV3App(workspace_dir=".", config=config)

    async with app.run_test() as pilot:
        app._start_live_status()
        assert app.is_working is True
        assert app._token_count == 0

        # Simulate JSON stream chunk with thought
        app._handle_agent_event({"type": "stream", "text": '{"thought": "Inspecting directory tree structure'})
        assert app._token_count > 0
        assert "Inspecting directory tree structure" in app._latest_stream_preview

        # Stop live status
        app._stop_live_status()
        assert app.is_working is False


@pytest.mark.asyncio
async def test_v3_tui_custom_answer_wiring_and_resolution():
    """Verify custom answer submission sends responses and resolves pending state."""
    config = AgentConfig()
    app = JuliusCLIV3App(workspace_dir=".", config=config)

    async with app.run_test() as pilot:
        # Simulate incoming question
        app._handle_agent_event({
            "type": "ask_user_question",
            "question": "Which file do you want to inspect?",
            "options": ["1. chrome_profile", "2. logs", "3. Julius"]
        })
        assert app._pending_question is True

        # Mock websocket to record sent messages
        sent_messages = []
        mock_ws = MagicMock()
        mock_ws.closed = False
        async def mock_send_json(data):
            sent_messages.append(data)
        mock_ws.send_json = mock_send_json
        app._ws = mock_ws

        # User submits custom answer
        from src.cli.v3_tui import PromptTextArea
        await app.on_prompt_text_area_submitted(PromptTextArea.Submitted("chrome_profile logs Julius"))

        assert app._pending_question is False
        assert len(sent_messages) == 3
        types_sent = [m["type"] for m in sent_messages]
        assert "question_response" in types_sent
        assert "human_response" in types_sent
        assert "action_response" in types_sent
        assert all(m["answer"] == "chrome_profile logs Julius" for m in sent_messages)

