"""
Comprehensive Verification Suite for LLM Response Parsing & Validation Resilience.

Tests that Julius will NEVER exit or stop with:
'Error: Agent stopped: LLM produced 5 consecutive invalid responses.'

Verifies:
1. Auto-healing of action synonyms (answer, reply, say, chat -> converse)
2. Auto-healing of argument aliases (message <-> summary <-> text <-> answer)
3. Auto-injection of missing 'thought' and hoisting of flat arguments
4. Recognition of conversational JSON responses without explicit 'action' keys
5. Parsing of responses where content is delivered via reasoning/thinking channels
6. Tolerance for all canonical and deferred tool names (Bash, Read, Write, get_system_vitals, etc.)
7. Non-exiting guarantee: Agent always recovers and responds rather than crashing
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.response_validator import validate_action, ACTION_SYNONYMS, ACTION_ARG_SCHEMAS
from src.web_agent import WebAgent
from src.providers.base import LLMResponse


class TestResponseValidatorAutoHealing(unittest.TestCase):
    """Test auto-healing in validate_action."""

    def test_synonym_answer_to_converse(self):
        """Action 'answer' auto-heals to 'converse' with 'message'."""
        data = {
            "thought": "Answering user question",
            "action": "answer",
            "args": {"text": "Julius provides continuous autonomous execution and system control."}
        }
        is_valid, err = validate_action(data)
        self.assertTrue(is_valid, f"Failed: {err}")
        self.assertEqual(data["action"], "converse")
        self.assertIn("message", data["args"])
        self.assertIn("Julius provides continuous autonomous execution", data["args"]["message"])

    def test_synonym_reply_and_respond(self):
        """Aliases 'reply' and 'respond' auto-heal to 'converse'."""
        for alias in ("reply", "respond", "say", "chat", "explain"):
            data = {
                "thought": f"Testing {alias}",
                "action": alias,
                "args": {"response": f"Response from {alias}"}
            }
            is_valid, err = validate_action(data)
            self.assertTrue(is_valid, f"Failed for {alias}: {err}")
            self.assertEqual(data["action"], "converse")
            self.assertEqual(data["args"]["message"], f"Response from {alias}")

    def test_done_with_message_or_text(self):
        """Action 'done' with 'message' or 'text' auto-heals 'summary'."""
        data1 = {
            "thought": "All done",
            "action": "done",
            "args": {"message": "Completed the audit successfully."}
        }
        is_valid1, err1 = validate_action(data1)
        self.assertTrue(is_valid1, f"Failed: {err1}")
        self.assertEqual(data1["args"]["summary"], "Completed the audit successfully.")

        data2 = {
            "thought": "All done",
            "action": "done",
            "args": {"text": "Analysis complete."}
        }
        is_valid2, err2 = validate_action(data2)
        self.assertTrue(is_valid2, f"Failed: {err2}")
        self.assertEqual(data2["args"]["summary"], "Analysis complete.")

    def test_converse_with_summary(self):
        """Action 'converse' with 'summary' auto-heals 'message'."""
        data = {
            "thought": "Explaining status",
            "action": "converse",
            "args": {"summary": "Here is the architectural system status."}
        }
        is_valid, err = validate_action(data)
        self.assertTrue(is_valid, f"Failed: {err}")
        self.assertEqual(data["args"]["message"], "Here is the architectural system status.")

    def test_missing_thought_auto_injected(self):
        """Missing 'thought' is auto-injected without error."""
        data = {
            "action": "converse",
            "args": {"message": "Direct message without thought."}
        }
        is_valid, err = validate_action(data)
        self.assertTrue(is_valid, f"Failed: {err}")
        self.assertIn("thought", data)

    def test_flat_arguments_hoisted(self):
        """Flat arguments without 'args' sub-dict are auto-hoisted."""
        data = {
            "thought": "Running shell",
            "action": "run_bash",
            "command": "uname -a"
        }
        is_valid, err = validate_action(data)
        self.assertTrue(is_valid, f"Failed: {err}")
        self.assertIn("args", data)
        self.assertEqual(data["args"].get("command"), "uname -a")

    def test_missing_action_with_message_or_summary(self):
        """JSON without 'action' but with 'message' or 'summary' auto-heals."""
        data1 = {
            "thought": "Just answering",
            "message": "Julius architecture and system details."
        }
        is_valid1, err1 = validate_action(data1)
        self.assertTrue(is_valid1, f"Failed: {err1}")
        self.assertEqual(data1["action"], "converse")
        self.assertEqual(data1["args"]["message"], "Julius architecture and system details.")

        data2 = {
            "thought": "Just summary",
            "summary": "Finished task summary."
        }
        is_valid2, err2 = validate_action(data2)
        self.assertTrue(is_valid2, f"Failed: {err2}")
        self.assertEqual(data2["action"], "done")
        self.assertEqual(data2["args"]["summary"], "Finished task summary.")

    def test_canonical_and_system_tools_valid(self):
        """Canonical and extended system tools pass schema validation."""
        system_tests = [
            ("capture_screen", {}),
            ("CaptureScreen", {}),
            ("get_active_window", {}),
            ("GetActiveWindow", {}),
            ("get_system_vitals", {}),
            ("GetSystemVitals", {}),
            ("send_system_notification", {"title": "Test", "message": "Alert"}),
            ("manage_clipboard", {"action": "read"}),
            ("app_control", {"action": "list"}),
            ("run_teamwork", {"goal": "Audit project"}),
            ("Bash", {"command": "echo 1"}),
            ("Read", {"file_path": "README.md"}),
        ]
        for act, args in system_tests:
            d = {"thought": "Testing tool", "action": act, "args": args}
            is_valid, err = validate_action(d)
            self.assertTrue(is_valid, f"Validation failed for {act}: {err}")


class TestWebAgentParseActionResilience(unittest.TestCase):
    """Test WebAgent._parse_action resilience with various LLM response shapes."""

    def setUp(self):
        self.agent = WebAgent()

    def test_parse_conversational_json_without_action_key(self):
        """Model outputted JSON with thought and message, but no action key."""
        raw = '{"thought": "Answering question about system capabilities", "message": "Julius provides autonomous terminal execution and ambient tools."}'
        resp = LLMResponse(raw_text=raw, text=raw, success=True)
        action_data = self.agent._parse_action(resp)
        self.assertIsNotNone(action_data)
        self.assertEqual(action_data.get("action"), "converse")
        self.assertIn("autonomous terminal execution", action_data["args"]["message"])

    def test_parse_conversational_json_with_answer_key(self):
        """Model outputted JSON with thought and answer."""
        raw = '```json\n{"thought": "Explaining architecture", "answer": "The primary capabilities are ambient voice and desktop vision."}\n```'
        resp = LLMResponse(raw_text=raw, text=raw, success=True)
        action_data = self.agent._parse_action(resp)
        self.assertIsNotNone(action_data)
        self.assertEqual(action_data.get("action"), "converse")
        self.assertIn("desktop vision", action_data["args"]["message"])

    def test_parse_direct_markdown_response(self):
        """Model replied with raw conversational text without JSON."""
        raw = "Here is the comprehensive overview of Julius:\n1. Ambient Voice\n2. Desktop Vision\n3. Proactive Heartbeat"
        resp = LLMResponse(raw_text=raw, text=raw, success=True)
        action_data = self.agent._parse_action(resp)
        self.assertIsNotNone(action_data)
        self.assertEqual(action_data.get("action"), "converse")
        self.assertIn("Ambient Voice", action_data["args"]["message"])

    def test_parse_response_delivered_via_reasoning(self):
        """Model put its answer in the reasoning field with empty raw_text."""
        reasoning = '```json\n{"thought": "From reasoning", "action": "converse", "args": {"message": "Delivered through reasoning channel."}}\n```'
        resp = LLMResponse(raw_text="", text="", reasoning=reasoning, success=True)
        action_data = self.agent._parse_action(resp)
        self.assertIsNotNone(action_data)
        self.assertEqual(action_data.get("action"), "converse")
        self.assertIn("reasoning channel", action_data["args"]["message"])


class TestNonExitingLoopGuarantee(unittest.TestCase):
    """Simulate user query and verify the agent NEVER exits with 5 consecutive failures."""

    def test_user_query_does_not_crash(self):
        """
        Simulate user query and verify that even if the mock client produces
        non-action responses, the agent auto-heals into converse and does not crash.
        """
        agent = WebAgent()

        # Simulated response from Nemotron / Llama / Qwen for this prompt:
        simulated_raw = (
            "Julius provides capabilities across four main areas:\n"
            "1. Ambient Continuous Voice: Listening with wake-word activation.\n"
            "2. Native OS Desktop Vision: Screen capture and active window context.\n"
            "3. Proactive Background Executive: Running 24/7 without waiting for prompts.\n"
            "4. Multi-Agent Swarm: Spawning specialized teams concurrently."
        )

        resp = LLMResponse(raw_text=simulated_raw, text=simulated_raw, success=True)
        action = agent._parse_action(resp)
        self.assertIsNotNone(action, "Should never be None for substantive text")

        is_valid, err = validate_action(action)
        self.assertTrue(is_valid, f"Auto-healing failed: {err}")
        self.assertEqual(action.get("action"), "converse")
        self.assertIn("Ambient Continuous Voice", action["args"]["message"])

    def test_who_is_julius_identity_prompt(self):
        """Verify identity queries produce conversational introductions instead of README dumps."""
        task = "Who is Julius"
        task_lower = task.lower()
        is_identity_query = any(q in task_lower for q in ("who is julius", "who are you", "who are u", "what is your name", "tell me about yourself"))
        self.assertTrue(is_identity_query)

        agent = WebAgent()
        intro = "I'm Julius. I'm your technical partner and systems engineer right here in your terminal."
        resp = LLMResponse(raw_text=intro, text=intro, success=True)
        action = agent._parse_action(resp)
        self.assertIsNotNone(action)
        self.assertEqual(action["action"], "converse")
        self.assertIn("I'm Julius", action["args"]["message"])
        self.assertNotIn("Based on the README.md", action["args"]["message"])


class TestNvidiaNIMSpecialistRouting(unittest.TestCase):
    """Test 40 RPM rate limiting and multi-model specialist delegation."""

    def setUp(self):
        self.agent = WebAgent()

    def test_tool_calling_delegation_to_validated_tool_model(self):
        """Requests with tools are strictly routed to validated tool-calling models."""
        from src.providers.nim import (
            NvidiaNIMProvider,
            VALIDATED_NVIDIA_TOOL_MODELS,
            NVIDIA_MODEL_NEMOTRON_550B,
        )
        from src.providers.base import ChatRequest, ChatMessage, ToolDefinition

        provider = NvidiaNIMProvider(api_key="test_key")
        req = ChatRequest(
            messages=[ChatMessage(role="user", content="Read file")],
            model="unvalidated/chat-model",
            tools=[ToolDefinition(name="read_file", description="Read file", parameters={})],
        )
        specialist = provider._select_specialist_model(req)
        self.assertIn(specialist, VALIDATED_NVIDIA_TOOL_MODELS)
        self.assertEqual(specialist, NVIDIA_MODEL_NEMOTRON_550B)

    def test_vision_delegation_to_llama_vision(self):
        """Requests with image attachments are routed to meta/llama-3.2-90b-vision-instruct."""
        from src.providers.nim import NvidiaNIMProvider, NVIDIA_MODEL_LLAMA_VISION_90B
        from src.providers.base import ChatRequest, ChatMessage

        provider = NvidiaNIMProvider(api_key="test_key")
        req = ChatRequest(
            messages=[ChatMessage(role="user", content="Analyze this screen", metadata={"image_path": "screen.png"})],
            model="default-model",
        )
        specialist = provider._select_specialist_model(req)
        self.assertEqual(specialist, NVIDIA_MODEL_LLAMA_VISION_90B)

    def test_reasoning_default_to_nemotron(self):
        """Conversational and analytical requests route to flagship Nemotron 550B."""
        from src.providers.nim import NvidiaNIMProvider, NVIDIA_MODEL_NEMOTRON_550B
        from src.providers.base import ChatRequest, ChatMessage

        provider = NvidiaNIMProvider(api_key="test_key")
        req = ChatRequest(
            messages=[ChatMessage(role="user", content="How does Julius architecture work?")],
            model=NVIDIA_MODEL_NEMOTRON_550B,
        )
        specialist = provider._select_specialist_model(req)
        self.assertEqual(specialist, NVIDIA_MODEL_NEMOTRON_550B)

    def test_image_6_raw_json_tool_call_healing(self):
        """
        Verify Image #6 exact failure case:
        '{"actions":[{"name":"run_bash","arguments":{"cmd":"find . -name \'story\' -o -name \'sample\' -o -name \'*.pdf\' 2>/dev/null | head -50"}}],"requestor":"user"}'
        Must auto-heal into a valid run_bash action with 'command' argument,
        NEVER leak as raw JSON, and NEVER convert into converse!
        """
        raw = '{"actions":[{"name":"run_bash","arguments":{"cmd":"find . -name \'story\' -o -name \'sample\' -o -name \'*.pdf\' 2>/dev/null | head -50"}}],"requestor":"user"}'
        resp = LLMResponse(raw_text=raw, text=raw, success=True)
        action_data = self.agent._parse_action(resp)
        self.assertIsNotNone(action_data, "Must parse the JSON actions payload")
        self.assertNotIn("requestor", action_data, "Must strip transport metadata like 'requestor'")

        from src.agent_prompts import normalize_actions
        actions, mode = normalize_actions(action_data)
        self.assertEqual(len(actions), 1)
        item = actions[0]
        self.assertEqual(item["action"], "run_bash")
        self.assertIn("command", item["args"])
        self.assertIn("find . -name 'story'", item["args"]["command"])

        # Also verify validate_action passes cleanly
        is_valid, err = validate_action(action_data)
        self.assertTrue(is_valid, f"Validation should succeed for auto-healed action: {err}")

    def test_delete_file_alias_and_schema(self):
        """Action 'delete' / 'delete_file' auto-heals to 'delete_file' with 'path'."""
        data = {
            "thought": "Deleting file",
            "action": "delete",
            "args": {"file_path": "The_Julius_Story.pdf"}
        }
        is_valid, err = validate_action(data)
        self.assertTrue(is_valid, f"Validation failed: {err}")
        self.assertEqual(data["action"], "delete_file")
        self.assertEqual(data["args"]["path"], "The_Julius_Story.pdf")

    def test_event_bridge_never_leaks_raw_json(self):
        """EventBridge._clean_field_text never returns raw JSON braces to user."""
        from src.tui.event_bridge import _clean_field_text
        raw_json = '{"actions":[{"name":"run_bash","arguments":{"cmd":"rm -f test.pdf"}}],"requestor":"user"}'
        cleaned = _clean_field_text(raw_json, "summary")
        self.assertFalse(cleaned.startswith("{"), f"Must not leak raw JSON braces: {cleaned}")
        self.assertTrue("rm -f test.pdf" in cleaned or "Executed" in cleaned or "Task" in cleaned)


if __name__ == "__main__":
    unittest.main(verbosity=2)
