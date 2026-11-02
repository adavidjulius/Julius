"""Tests for backend LLM communication reliability, think block isolation, and stall detection."""

import pytest
import json
from src.agent_prompts import extract_json_block
from src.llm_web_client import WebLLMClient
from src.web_agent import WebAgent
from src.chat_providers.deepseek import DeepSeekProvider


def test_extract_json_block_ignores_deepseek_think_tags():
    """Verify extract_json_block extracts valid JSON while ignoring leaked <think> blocks."""
    raw = (
        "<think>\n"
        "Let's consider what action to perform.\n"
        "Maybe a run_bash with {'command': 'wrong'}?\n"
        "No, we should read the configuration.\n"
        "</think>\n"
        "```json\n"
        "{\n"
        '  "thought": "Reading config file",\n'
        '  "action": "read_file",\n'
        '  "args": {"path": "config.json"}\n'
        "}\n"
        "```\n"
        "I hope this helps!"
    )
    data = extract_json_block(raw)
    assert data["action"] == "read_file"
    assert data["args"]["path"] == "config.json"
    assert data["thought"] == "Reading config file"
    assert "wrong" not in str(data)


def test_extract_json_block_handles_multiple_code_blocks_correctly():
    """Verify extract_json_block prefers the final action block over example code blocks."""
    raw = (
        "Here is an example code block:\n"
        "```json\n"
        "{\"sample\": true}\n"
        "```\n"
        "Here is the actual execution command:\n"
        "```json\n"
        "{\n"
        '  "thought": "Run test suite",\n'
        '  "action": "run_bash",\n'
        '  "args": {"command": "pytest"}\n'
        "}\n"
        "```"
    )
    data = extract_json_block(raw)
    assert data["action"] == "run_bash"
    assert data["args"]["command"] == "pytest"


def test_llm_web_client_extract_json_filters_thinking():
    """Verify WebLLMClient._extract_json discards thinking blocks."""
    raw = (
        "<think>Random reasoning thoughts here</think>\n"
        "{\n"
        '  "thought": "Finished task",\n'
        '  "action": "done",\n'
        '  "args": {"summary": "Completed successfully"}\n'
        "}"
    )
    data = WebLLMClient._extract_json(raw)
    assert data is not None
    assert data["action"] == "done"
    assert data["args"]["summary"] == "Completed successfully"


def test_web_agent_parse_action_sanitizes_payload():
    """Verify WebAgent._parse_action strips leaked thinking tags from thought and summary."""
    class MockResponse:
        parsed_json = None
        raw_text = (
            "<think>Leaked inner voice</think>\n"
            "```json\n"
            "{\n"
            '  "thought": "<think>inner thought</think>Actual clean thought",\n'
            '  "action": "done",\n'
            '  "args": {"summary": "<think>reasoning</think>Final task completed"}\n'
            "}\n"
            "```\n"
            "Some trailing page text"
        )

    data = WebAgent._parse_action(MockResponse())
    assert data is not None
    assert data["action"] == "done"
    assert data["thought"] == "Actual clean thought"
    assert data["args"]["summary"] == "Final task completed"
    assert "<think>" not in str(data)


def test_deepseek_looks_complete_supports_single_and_batch_actions():
    """Verify DeepSeekProvider._looks_complete detects both Shape A and Shape B actions."""
    shape_a = '{"thought": "test", "action": "run_bash", "args": {"command": "ls"}}'
    shape_b = '{"thought": "test", "actions": [{"action": "read_file", "args": {"path": "a"}}]}'
    invalid = '{"thought": "still thinking"'

    assert DeepSeekProvider._looks_complete(shape_a)
    assert DeepSeekProvider._looks_complete(shape_b)
    assert not DeepSeekProvider._looks_complete(invalid)


def test_is_json_or_protocol_accurately_detects_leaked_action_payloads():
    """Verify is_json_or_protocol identifies raw JSON action streams, prefixes, and repeated turns."""
    from src.agent_prompts import is_json_or_protocol

    # The exact strings from user's screenshot
    screenshot_leak = (
        'json{ "thought": "I\'ll start by finding the image on the Desktop and checking what '
        'Playwright scripts or Gmail automation exist in the project.", "actions": [ { "id": "a1", '
        '"action": "run_bash", "args": { "command": "ls -la ~/Desktop | grep -i lahan" } } ], "mode": "parallel" }'
    )
    repeated_leak = screenshot_leak + screenshot_leak + '{"thought": "second step", "actions": []}'
    prefix_fragment = 'json{ "thought": "Finding image"'
    fenced_leak = '```json\n{"action": "run_bash", "args": {"command": "ls"}}\n```'

    assert is_json_or_protocol(screenshot_leak) is True
    assert is_json_or_protocol(repeated_leak) is True
    assert is_json_or_protocol(prefix_fragment) is True
    assert is_json_or_protocol(fenced_leak) is True

    # User-facing text must NOT be falsely identified as protocol
    user_confirmation = "Action 'run_bash' requested access outside the workspace folder. Allow un-sandboxed access across your Mac? (y/n)"
    normal_answer = "I have located your image on the Desktop at ~/Desktop/lahanandnaveeen.jpg."
    code_snippet = "```python\ndef test():\n    print('Hello World')\n```"

    assert is_json_or_protocol(user_confirmation) is False
    assert is_json_or_protocol(normal_answer) is False
    assert is_json_or_protocol(code_snippet) is False


def test_thinking_dot_sanitizes_raw_json_and_think_tags():
    """Verify ThinkingDot strips raw JSON wrappers and reasoning tags from thoughts."""
    from src.tui.components.message import ThinkingDot

    dot = ThinkingDot("Thinking")
    raw_th = '<think>some private thought</think>json{ "thought": "Checking scripts for Gmail automation", "actions": [] }'
    dot.update_label("Thinking — Checking scripts", full_thought=raw_th)

    assert "<think>" not in dot.full_thought
    assert "json{" not in dot.full_thought
    assert "Checking scripts for Gmail automation" in dot.full_thought


def test_assistant_message_suppresses_raw_json_rendering():
    """Verify AssistantMessage does not render when provided internal action JSON."""
    from src.tui.components.message import AssistantMessage

    leaked_json = 'json{ "thought": "Find file", "actions": [ { "id": "a1", "action": "run_bash" } ] }'
    msg = AssistantMessage(leaked_json)
    msg._update_renderable()
    # Content is suppressed so render() is empty
    assert str(msg.render()) == ""
    # Contrast with normal text
    normal = AssistantMessage("Hello user")
    normal._update_renderable()
    assert str(normal.render()) != ""


@pytest.mark.asyncio
async def test_sweep_leaked_json_messages_cleans_conv_area():
    """Verify JuliusApp._sweep_leaked_json_messages removes leaked JSON messages from conversation area."""
    from textual.app import App, ComposeResult
    from textual.containers import ScrollableContainer
    from src.tui.app import JuliusApp
    from src.tui.components.message import AssistantMessage, UserMessage

    app = JuliusApp()
    async with app.run_test() as pilot:
        conv_area = app.query_one("#conversation-area", ScrollableContainer)
        # Mount a valid user message
        u_msg = UserMessage("send email")
        conv_area.mount(u_msg)

        # Mount a leaked JSON message
        leaked_msg = AssistantMessage('json{ "thought": "Find file", "actions": [ { "id": "a1", "action": "run_bash" } ] }')
        conv_area.mount(leaked_msg)

        # Mount an innocent message
        innocent_msg = AssistantMessage("Allow action run_bash?")
        conv_area.mount(innocent_msg)
        await pilot.pause()

        # Execute sweep
        app._sweep_leaked_json_messages(conv_area)
        await pilot.pause()

        # Leaked message must be removed, valid messages preserved
        remaining_messages = [c for c in conv_area.children if isinstance(c, AssistantMessage)]
        for r in remaining_messages:
            assert "json{" not in r.content

