"""
Unit tests verifying fix for thinking panel JSON leakage and step duration.
"""

import pytest
from rich.text import Text
from src.agent_prompts import is_json_or_protocol
from src.tui.components.message import ThinkingDot
from src.tui.components.tool_summary import ToolSummary, format_step_duration
from src.tui.state import ToolExecutionRecord


def test_is_json_or_protocol_catches_code_fences_and_openers():
    """Ensure bare markdown fences, JSON openers, and protocol keywords return True."""
    assert is_json_or_protocol("```") is True
    assert is_json_or_protocol("```json") is True
    assert is_json_or_protocol("```json\n") is True
    assert is_json_or_protocol("json") is True
    assert is_json_or_protocol("{") is True
    assert is_json_or_protocol("{}") is True
    assert is_json_or_protocol('{"thought": "test"}') is True
    assert is_json_or_protocol('{"action": "converse"}') is True


def test_sanitize_thought_strips_fences_and_raw_json():
    """Ensure _sanitize_thought never returns raw fences or JSON syntax."""
    # Fences and syntax must return empty string
    assert ThinkingDot._sanitize_thought("```") == ""
    assert ThinkingDot._sanitize_thought("```json") == ""
    assert ThinkingDot._sanitize_thought("json") == ""
    assert ThinkingDot._sanitize_thought("{") == ""
    assert ThinkingDot._sanitize_thought("{}") == ""
    assert ThinkingDot._sanitize_thought('{"action": "converse"}') == ""
    assert ThinkingDot._sanitize_thought('```json\n{"action": "converse"}\n```') == ""

    # Valid inner thoughts must be extracted cleanly
    assert ThinkingDot._sanitize_thought('{"thought": "Writing erotic story"}') == "Writing erotic story"
    assert ThinkingDot._sanitize_thought('```json\n{"thought": "Analyzing request"}\n```') == "Analyzing request"
    assert ThinkingDot._sanitize_thought("<think>Analyzing user prompt</think>") == "Analyzing user prompt"
    assert ThinkingDot._sanitize_thought("Thought: Creating character dialogue") == "Creating character dialogue"


def test_format_summary_never_produces_json_fences():
    """Ensure format_summary never returns 'Thinking — ```json' or syntax snippets."""
    assert ThinkingDot.format_summary("```json") == "Thinking"
    assert ThinkingDot.format_summary("```") == "Thinking"
    assert ThinkingDot.format_summary("json") == "Thinking"
    assert ThinkingDot.format_summary("{") == "Thinking"
    assert ThinkingDot.format_summary("{}") == "Thinking"
    assert ThinkingDot.format_summary('{"action": "done"}') == "Thinking"
    assert ThinkingDot.format_summary("Thinking — ```json") == "Thinking"

    # Clean thoughts should format properly
    summary = ThinkingDot.format_summary("Thought: Composing narrative for user")
    assert summary == "Thinking — Composing narrative for user"


def test_thinking_dot_render_never_shows_leaked_fences():
    """Ensure expanded ThinkingDot render() never prints '● ```' or '● ```json'."""
    dot = ThinkingDot("Thinking")
    # Simulate bad chunks arriving
    dot.append_thought("```")
    dot.append_thought("```json")
    dot.append_thought("json")
    dot.expanded = True

    rendered_text = dot.render().plain
    assert "● ```" not in rendered_text
    assert "● ```json" not in rendered_text
    assert "Thinking — ```json" not in rendered_text


def test_tool_summary_duration_formatting():
    """Ensure format_step_duration formats real elapsed time accurately."""
    assert format_step_duration(0.0) == "0.1s"
    assert format_step_duration(0.12) == "0.1s"
    assert format_step_duration(14.54) == "14.5s"
    assert format_step_duration(35.2) == "35.2s"
    assert format_step_duration(75.0) == "1m 15s"
    assert format_step_duration(120.0) == "2m"


def test_tool_summary_computes_actual_duration():
    """Ensure ToolSummary uses total_duration_s if provided or sums tool durations."""
    tool1 = ToolExecutionRecord(
        tool_name="run_bash",
        summary="Ran bash command",
        duration_s=12.4,
        success=True,
        command="python script.py",
    )
    tool2 = ToolExecutionRecord(
        tool_name="read_file",
        summary="Read output",
        duration_s=3.6,
        success=True,
        command="read_file(path='out.txt')",
    )

    # 1. When total_duration_s is passed (e.g. wall clock elapsed time 18.5s)
    ts = ToolSummary([tool1, tool2], total_duration_s=18.5)
    assert ts.total_duration_s == 18.5

    # 2. When total_duration_s is not passed, sum of tools (16.0s) should be used, NOT 0.2s
    ts2 = ToolSummary([tool1, tool2])
    assert ts2.total_duration_s == 16.0
    assert format_step_duration(ts2.total_duration_s) == "16.0s"


@pytest.mark.asyncio
async def test_user_selected_deepseek_is_primary_without_ollama_hijack():
    """Verify that when user switches to deepseek, it connects directly without Ollama interception even if OLLAMA_HOST is set."""
    from unittest.mock import AsyncMock, patch
    from src.llm_web_client import WebLLMClient

    client = WebLLMClient()

    with patch.dict("os.environ", {"OLLAMA_HOST": "http://192.168.0.221:11434"}):
        with patch.object(client, "_check_ollama_health", new=AsyncMock(return_value=True)) as mock_health:
            await client.initialize(provider_name="deepseek")
            # Primary engine must NOT be hijacked to Ollama!
            assert client.is_initialized is True
            assert client._use_api is True
            mock_health.assert_not_called()


@pytest.mark.asyncio
async def test_user_selected_ollama_model_alias():
    """Verify that when user chooses an Ollama model alias (e.g. 'lexi'), Ollama is used with that model."""
    from unittest.mock import AsyncMock, patch
    from src.llm_web_client import WebLLMClient

    client = WebLLMClient()

    with patch.object(client, "_check_ollama_health", new=AsyncMock(return_value=True)):
        await client.initialize(provider_name="lexi")
        assert client.is_initialized is True
        assert client._use_api is True
        assert client._ollama_model == "lexi"
        assert "ollama" in client.provider_name

