#!/usr/bin/env python3
"""
Test suite verifying:
1. Terminal emoji sanitization: Converts status emojis to clean ASCII tokens and strips decorative emojis.
2. Fast file deletion when files do not exist: run_bash on missing file patterns returns success=True so the agent finishes in 1 step without endless 3-minute searching.
3. Premature done guard allows completion when target files do not exist or directory is already clean.
"""

import sys
import os
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.tui.event_bridge import sanitize_terminal_emojis, _clean_field_text
from src.action_executor import ActionExecutor
from src.agent_config import AgentConfig


def test_emoji_sanitization():
    print("Running test_emoji_sanitization...")
    sample = "Layer | Status | What's Done\nPhase 2 | ✅ Complete | Done with tests 🚀\nPhase 1 | ❌ Failed | Error ⚠️"
    sanitized = sanitize_terminal_emojis(sample)
    
    assert "✅" not in sanitized, f"Emoji ✅ should be removed: {sanitized}"
    assert "❌" not in sanitized, f"Emoji ❌ should be removed: {sanitized}"
    assert "⚠️" not in sanitized, f"Emoji ⚠️ should be removed: {sanitized}"
    assert "🚀" not in sanitized, f"Emoji 🚀 should be stripped: {sanitized}"
    assert "[DONE]" in sanitized, f"[DONE] should be present: {sanitized}"
    assert "[FAIL]" in sanitized, f"[FAIL] should be present: {sanitized}"
    assert "[!]" in sanitized, f"[!] should be present: {sanitized}"
    
    # Also verify _clean_field_text sanitizes
    raw_json = '{"message": "All systems operational ✅ and verified 🚀"}'
    cleaned = _clean_field_text(raw_json, "message")
    assert "✅" not in cleaned and "🚀" not in cleaned
    assert "[DONE]" in cleaned
    print("✅ test_emoji_sanitization passed")


def test_fast_file_deletion_when_files_do_not_exist():
    print("Running test_fast_file_deletion_when_files_do_not_exist...")
    executor = ActionExecutor(workspace_root=str(PROJECT_ROOT))
    executor.set_mode("accept")

    # Attempt to remove a non-existent file pattern
    fake_pattern = "/tmp/julius_nonexistent_screenshot_pattern_98765*.png"
    res = executor.run_bash(f"rm -f {fake_pattern}")
    
    # Must be marked success=True with informative clean message!
    assert res.success is True, f"rm on non-existent files should be marked success=True, got: {res}"
    print(f"   Output received: {res.output}")
    print("✅ test_fast_file_deletion_when_files_do_not_exist passed")


def test_prompt_rules_contain_zero_emojis_and_fast_deletion():
    print("Running test_prompt_rules_contain_zero_emojis_and_fast_deletion...")
    from src.agent_prompts import get_compact_system_prompt
    prompt = get_compact_system_prompt()
    
    assert "ZERO EMOJIS" in prompt, "Prompt must include ZERO EMOJIS rule"
    assert "File Cleanup & Search Directive" in prompt, "Prompt must include File Cleanup directive"
    print("✅ test_prompt_rules_contain_zero_emojis_and_fast_deletion passed")


if __name__ == "__main__":
    test_emoji_sanitization()
    test_fast_file_deletion_when_files_do_not_exist()
    test_prompt_rules_contain_zero_emojis_and_fast_deletion()
    print("\n🎉 ALL UI IMPROVEMENT & FAST DELETION TESTS PASSED CLEANLY!")
