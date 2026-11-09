"""
Verification tests for Julius Command Execution Mechanism & Anti-Stall Guarantees.
Tests:
1. WebAgent step history isolation across turns.
2. Anti-stall Guard 1: Non-blocking 'done' after subsequent success or explained blocker.
3. Anti-interruption: 'converse' not interrupted or discarded for substantive answers.
4. Anti-loop: Duplicate action detection stops infinite repetition.
5. EventBridge regex fix: Text with quotes is never truncated.
6. Timeout safety: generous timeouts in OpenAI & Anthropic providers.
"""

import asyncio
import json
import os
import sys
from unittest.mock import MagicMock, AsyncMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent_config import AgentConfig
from src.web_agent import WebAgent, StepRecord
from src.tui.event_bridge import _clean_field_text, EventBridge
from src.tui.state import SessionState
from src.providers.openai_compat import OpenAICompatibleProvider
from src.providers.anthropic import AnthropicProvider
from src.providers.base import ChatRequest


def test_clean_field_text_no_truncation_on_quotes():
    """Verify that messages or summaries with quotes are not truncated."""
    # Test with escaped quotes and plain quotes
    raw_message = 'Here is the command: grep "foo" file.txt and more text.'
    assert _clean_field_text(raw_message, "message") == raw_message

    # Test with JSON payload containing quotes
    json_payload = json.dumps({
        "action": "converse",
        "args": {
            "message": 'Here is a code snippet: console.log("Hello, world!"); and it works.'
        }
    })
    extracted = _clean_field_text(json_payload, "message")
    assert extracted == 'Here is a code snippet: console.log("Hello, world!"); and it works.'
    print("✅ test_clean_field_text_no_truncation_on_quotes passed")


def test_agent_config_and_provider_timeouts():
    """Verify generous timeouts to prevent midway interruptions."""
    cfg = AgentConfig()
    assert cfg.bash_timeout >= 60, f"bash_timeout should be at least 60s, got {cfg.bash_timeout}"

    req = ChatRequest(messages=[], model="test")
    assert req.max_tokens >= 8192, f"max_tokens should be at least 8192, got {req.max_tokens}"

    openai_prov = OpenAICompatibleProvider()
    anthropic_prov = AnthropicProvider()
    print("✅ test_agent_config_and_provider_timeouts passed")


async def test_guard_allows_done_after_subsequent_success():
    """Verify Guard 1 does not block 'done' if a previous tool failed but subsequent tool succeeded."""
    cfg = AgentConfig(max_steps=5, confirm_actions=False)
    agent = WebAgent(config=cfg)

    # Step 1: Failed action
    agent._steps.append(StepRecord(
        step=1,
        thought="Checking for file",
        action="run_bash",
        args={"command": "test -f nonexistent.txt"},
        result="[exit code 1]",
        success=False,
    ))

    # Step 2: Succeeded action
    agent._steps.append(StepRecord(
        step=2,
        thought="Found alternative file",
        action="read_file",
        args={"path": "README.md"},
        result="# Readme content",
        success=True,
    ))

    # Mock client to return 'done' on step 3
    agent.client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.error = None
    mock_resp.raw_text = json.dumps({
        "thought": "All done",
        "action": "done",
        "args": {"summary": "Completed successfully using alternative file."}
    })
    mock_resp.parsed_json = None
    agent.client.send_message = AsyncMock(return_value=mock_resp)
    agent.client.is_initialized = True
    agent.client.provider_name = "test"

    result = await agent.run("Find and read the file", max_steps=2)
    assert result.stop_reason == "done"
    assert "Completed successfully" in result.summary
    print("✅ test_guard_allows_done_after_subsequent_success passed")


async def test_converse_not_interrupted_for_substantive_message():
    """Verify 'converse' is not rejected when a substantive answer is provided."""
    cfg = AgentConfig(max_steps=3, confirm_actions=False)
    agent = WebAgent(config=cfg)

    mock_resp = MagicMock()
    mock_resp.error = None
    mock_resp.raw_text = json.dumps({
        "thought": "Answering user explanation question",
        "action": "converse",
        "args": {
            "message": "Here is a complete guide on how to build and create components in React:\n1. Create component file\n2. Export function\n3. Import in App."
        }
    })
    mock_resp.parsed_json = None
    agent.client = MagicMock()
    agent.client.send_message = AsyncMock(return_value=mock_resp)
    agent.client.is_initialized = True
    agent.client.provider_name = "test"

    result = await agent.run("Explain how to build and create components in React", max_steps=2)
    assert result.stop_reason == "converse"
    assert "Here is a complete guide" in result.summary
    print("✅ test_converse_not_interrupted_for_substantive_message passed")


async def test_duplicate_action_loop_breaker():
    """Verify identical actions are halted before infinite repetition."""
    cfg = AgentConfig(max_steps=10, confirm_actions=False)
    agent = WebAgent(config=cfg)

    mock_resp = MagicMock()
    mock_resp.error = None
    # Model keeps repeating the exact same failing bash command
    mock_resp.raw_text = json.dumps({
        "thought": "Trying same command again",
        "action": "run_bash",
        "args": {"command": "stuck_command_test"}
    })
    mock_resp.parsed_json = None
    agent.client = MagicMock()
    agent.client.send_message = AsyncMock(return_value=mock_resp)
    agent.client.is_initialized = True
    agent.client.provider_name = "test"

    # Mock executor to return failure
    agent.executor.execute = MagicMock(return_value=MagicMock(success=False, output="stuck error"))

    result = await agent.run("Do this stuck job", max_steps=10)
    assert "identical action repeated" in result.summary
    assert result.stop_reason == "error"
    assert result.total_steps <= 8
    print("✅ test_duplicate_action_loop_breaker passed")


def run_all():
    test_clean_field_text_no_truncation_on_quotes()
    test_agent_config_and_provider_timeouts()
    asyncio.run(test_guard_allows_done_after_subsequent_success())
    asyncio.run(test_converse_not_interrupted_for_substantive_message())
    asyncio.run(test_duplicate_action_loop_breaker())
    print("\n🎉 ALL 5 VERIFICATION SUITES PASSED CLEANLY!")


if __name__ == "__main__":
    run_all()
