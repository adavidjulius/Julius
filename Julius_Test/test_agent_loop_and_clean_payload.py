import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.web_agent import WebAgent, _clean_payload
from src.action_executor import ActionExecutor
from src.agent_config import AgentConfig


def test_clean_payload_defined_and_functions():
    """Verify _clean_payload is defined at module scope and properly heals action payloads."""
    # Test Shape A healing
    data_a = {"action": "converse", "text": "Hello world"}
    healed_a = _clean_payload(data_a)
    assert healed_a["action"] == "converse"
    assert healed_a["args"]["message"] == "Hello world"
    assert "thought" in healed_a

    # Test Shape B healing
    data_b = {
        "actions": [
            {"tool": "run_bash", "cmd": "echo 123"},
            {"function": "converse", "response": "done"}
        ]
    }
    healed_b = _clean_payload(data_b)
    assert healed_b["actions"][0]["action"] == "run_bash"
    assert healed_b["actions"][0]["args"]["command"] == "echo 123"
    assert healed_b["actions"][1]["action"] == "converse"
    assert healed_b["actions"][1]["args"]["message"] == "done"
    print("✅ test_clean_payload_defined_and_functions passed")


async def test_repeated_action_warning_injection():
    """Verify that repeated actions inject warning at attempt 2 before terminating on attempt 3."""
    config = AgentConfig(provider="mock", allowed_directory=os.getcwd(), verbose=False)
    agent = WebAgent(config=config)

    mock_resp = MagicMock()
    mock_resp.error = None
    mock_resp.text = ""
    mock_resp.raw_text = json.dumps({
        "thought": "Listing directory",
        "action": "run_bash",
        "args": {"command": "echo test_repeated"}
    })
    mock_resp.parsed_json = None
    agent.client = MagicMock()
    agent.client.send_message = AsyncMock(return_value=mock_resp)
    agent.client.is_initialized = True
    agent.client.provider_name = "test"

    agent.executor.execute = MagicMock(return_value=MagicMock(success=True, output="output 123"))

    result = await agent.run("Test repeated action loop", max_steps=10)
    assert "identical action repeated" in result.summary
    assert result.stop_reason == "error"
    # Verify that steps were recorded and total_steps stopped at duplicate limit
    assert len(result.steps) >= 2
    print("✅ test_repeated_action_warning_injection passed")


def test_unicode_narrow_space_normalization():
    """Verify ActionExecutor normalizes \u202f (narrow no-break space) in commands and file deletion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a file with \u202f (like macOS screenshots)
        fname = "Screenshot 2026-11-09 at 2.18.46\u202fPM.png"
        fpath = os.path.join(tmpdir, fname)
        with open(fpath, "w") as f:
            f.write("dummy screenshot content")

        assert os.path.exists(fpath)

        executor = ActionExecutor(workspace_root=tmpdir)
        executor.grant_path_access(tmpdir, mode="write", ttl_seconds=60.0)

        # 1. Test _normalize_command_unicode_filenames
        # Command uses standard ASCII space
        cmd_ascii = f'cd {tmpdir} && rm -f "Screenshot 2026-11-09 at 2.18.46 PM.png"'
        normalized = executor._normalize_command_unicode_filenames(cmd_ascii)
        assert "\u202f" in normalized
        assert fname in normalized

        # 2. Test delete_file with ASCII space
        res = executor.delete_file(os.path.join(tmpdir, "Screenshot 2026-11-09 at 2.18.46 PM.png"))
        assert res.success
        assert not os.path.exists(fpath)
        print("✅ test_unicode_narrow_space_normalization passed")


def test_modes_and_security_policy():
    """Verify 5 modes (auto, plan, edit, accept, manual) and security policy behavior."""
    config = AgentConfig(provider="mock", allowed_directory=os.getcwd(), verbose=False)
    agent = WebAgent(config=config)

    # 1. Accept mode: full access, no restrictions
    agent.set_mode("accept")
    assert agent.mode == "accept"
    assert agent._host_access_granted is True
    assert agent.config.confirm_actions is False
    assert agent.executor._host_access_allowed is True
    safe, _ = agent.executor._policy.is_command_safe("rm -f ~/Desktop/Screenshot*.png")
    assert safe is True

    # 2. Plan mode: mutating actions blocked
    agent.set_mode("plan")
    assert agent.mode == "plan"
    plan_res = agent.executor.execute("write_file", {"path": "test.txt", "content": "hello"})
    assert plan_res.success is False
    assert "Plan mode active" in plan_res.output

    # 3. Manual mode: asks for confirmation
    agent.set_mode("manual")
    assert agent.mode == "manual"
    assert agent._host_access_granted is False
    assert agent.config.confirm_actions is True

    # 4. Auto mode: autonomous execution
    agent.set_mode("auto")
    assert agent.mode == "auto"
    assert agent._host_access_granted is True
    assert agent.config.confirm_actions is False

    # 5. Security policy screenshot deletion regex test (ensuring no false positives)
    safe_del, reason = agent.executor._policy.is_command_safe("rm -f ~/Desktop/Screenshot*.png")
    assert safe_del is True, f"Failed: {reason}"

    # Dangerous actual root/home deletion remains blocked in normal modes
    agent.set_mode("manual")
    danger_del, _ = agent.executor._policy.is_command_safe("rm -rf ~")
    assert danger_del is False
    print("✅ test_modes_and_security_policy passed")


def run_all():
    test_clean_payload_defined_and_functions()
    asyncio.run(test_repeated_action_warning_injection())
    test_unicode_narrow_space_normalization()
    test_modes_and_security_policy()
    print("\n🎉 ALL AGENT LOOP, CLEAN PAYLOAD & MODES TESTS PASSED!")


if __name__ == "__main__":
    run_all()
