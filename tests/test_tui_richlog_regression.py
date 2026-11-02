"""
Regression test suite for Julius TUI RichLog.write and StreamPanel event handling.

Guards against:
- TypeError: RichLog.write() got an unexpected keyword argument 'end'
- Passing any unsupported keyword arguments to RichLog.write()
- Incomplete line buffering or broken streaming semantics
"""

import inspect
import json
import pytest
from textual.app import App, ComposeResult
from textual.widgets import RichLog

from src.tui.app import StreamPanel, JuliusTUI, JuliusTUI


def test_textual_richlog_write_signature_lacks_end_parameter():
    """Verify that the installed Textual version's RichLog.write does NOT accept 'end'."""
    sig = inspect.signature(RichLog.write)
    assert "end" not in sig.parameters, (
        f"RichLog.write unexpectedly has 'end' parameter: {sig}"
    )


def test_calling_richlog_write_with_end_raises_type_error():
    """Verify that calling RichLog.write with end='' raises TypeError in installed Textual."""
    sig = inspect.signature(RichLog.write)
    with pytest.raises(TypeError, match="unexpected keyword argument 'end'"):
        sig.bind(None, "test text", end="")


@pytest.mark.asyncio
async def test_stream_panel_handles_all_event_types_without_invalid_kwargs():
    """Verify StreamPanel.add_event handles every event type without RichLog.write kwargs errors."""

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield StreamPanel(id="stream-panel")

    app = TestApp()
    async with app.run_test() as pilot:
        panel = app.query_one("#stream-panel", StreamPanel)

        # Track all calls to panel.write
        original_write = panel.write
        write_calls = []

        def spy_write(*args, **kwargs):
            # Strict check against RichLog.write signature
            sig = inspect.signature(RichLog.write)
            try:
                sig.bind(panel, *args, **kwargs)
            except TypeError as exc:
                pytest.fail(f"Invalid arguments passed to RichLog.write: args={args}, kwargs={kwargs}, error={exc}")
            write_calls.append((args, kwargs))
            return original_write(*args, **kwargs)

        panel.write = spy_write

        # 1. step_start
        panel.add_event("step_start", {"step": 1})
        # 2. streaming tokens (deltas)
        panel.add_event("stream", {"text": "Analyzing "})
        panel.add_event("stream", {"text": "task requirements...\nNext line begins"})
        # 3. stream_end
        panel.add_event("stream_end", {})
        # 4. thought
        panel.add_event("thought", {"text": "I will execute a bash command."})
        # 5. action
        panel.add_event("action", {"name": "run_bash", "args": {"command": "echo test"}})
        # 6. result
        panel.add_event("result", {"output": "test", "success": True})
        # 7. heal events
        panel.add_event("heal_start", {"command": "fix cmd"})
        panel.add_event("heal_success", {"summary": "fixed"})
        panel.add_event("heal_failed", {"summary": "failed"})
        # 8. status
        panel.add_event("status", {"message": "Processing..."})
        # 9. error
        panel.add_event("error", {"message": "Sample error"})
        # 10. done
        panel.add_event("done", {"summary": "Completed successfully."})

        assert len(write_calls) > 0, "Expected write calls to be recorded"
        for args, kwargs in write_calls:
            assert "end" not in kwargs, f"Forbidden 'end' kwarg found in write call: {kwargs}"


@pytest.mark.asyncio
async def test_stream_panel_cumulative_and_delta_streaming():
    """Verify that both cumulative (web scraper) and delta streaming preserve text without duplication."""
    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield StreamPanel(id="stream-panel")

    app = TestApp()
    async with app.run_test() as pilot:
        panel = app.query_one("#stream-panel", StreamPanel)
        logged_texts = []

        original_write = panel.write

        def capture_write(content, **kwargs):
            logged_texts.append(str(content))
            return original_write(content, **kwargs)

        panel.write = capture_write

        # Cumulative stream simulation (as emitted by Gemini / DeepSeek page polling)
        panel.add_event("stream", {"text": "Thinking"})
        panel.add_event("stream", {"text": "Thinking about"})
        panel.add_event("stream", {"text": "Thinking about Raspberry Pi.\n"})
        panel.add_event("stream_end", {})

        joined = "\n".join(logged_texts)
        assert "Thinking about Raspberry Pi." in joined
        # Must not have duplicated prefixes like "ThinkingThinking about"
        assert "ThinkingThinking" not in joined
