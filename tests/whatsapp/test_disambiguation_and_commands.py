"""
Tests for Gova vs Govardhan disambiguation, Monish RPT department, and verified command execution.
"""

from __future__ import annotations

import re
import pytest

from src.integrations.whatsapp.config import (
    TARGET_PEERS_CONFIG,
    get_canonical_target_peer_name,
    is_target_peer_chat,
)
from src.integrations.whatsapp.device_agent import (
    extract_command_from_query,
    execute_safe_terminal_command,
    generate_device_action_response,
    is_admin_peer,
    is_device_query,
)
from src.integrations.whatsapp.listener import _chat_matches
from src.integrations.whatsapp.materials import (
    BRANCH_TIMETABLES,
    find_timetable_for_query,
)


# ── 1. Alex vs Alexander Disambiguation Tests ─────────────────────────────────

def test_gova_and_govardhan_are_separate_peers():
    """Verify Contact Alex and Contact Alexander exist as two distinct canonical entries."""
    alex = next((p for p in TARGET_PEERS_CONFIG if p["canonical"] == "Contact Alex"), None)
    alexander = next((p for p in TARGET_PEERS_CONFIG if p["canonical"] == "Contact Alexander"), None)

    assert alex is not None, "Contact Alex must exist in TARGET_PEERS_CONFIG"
    assert alexander is not None, "Contact Alexander must exist in TARGET_PEERS_CONFIG"
    assert alex["canonical"] != alexander["canonical"]
    assert alex["dept"] == "Engineering"
    assert "alex" in alex["tokens"]
    assert "alexander" in alexander["tokens"]


def test_canonical_resolution_disambiguation():
    """Verify alias and token resolution yields distinct canonical names."""
    assert get_canonical_target_peer_name("Alex") == "Contact Alex"
    assert get_canonical_target_peer_name("Contact Alex") == "Contact Alex"

    assert get_canonical_target_peer_name("Alexander") == "Contact Alexander"
    assert get_canonical_target_peer_name("Contact Alexander") == "Contact Alexander"


def test_chat_matches_never_crosses_gova_and_govardhan():
    """Verify _chat_matches never considers Alex and Alexander as the same chat."""
    # Positive matches
    assert _chat_matches("Contact Alex", "Alex") is True
    assert _chat_matches("Contact Alex", "Contact Alex") is True
    assert _chat_matches("Contact Alexander", "Alexander") is True
    assert _chat_matches("Contact Alexander", "Contact Alexander") is True

    # Cross-matches MUST be False
    assert _chat_matches("Contact Alex", "Alexander") is False
    assert _chat_matches("Contact Alex", "Contact Alexander") is False
    assert _chat_matches("Contact Alexander", "Alex") is False
    assert _chat_matches("Contact Alexander", "Contact Alex") is False
    assert _chat_matches("Alex", "Alexander") is False
    assert _chat_matches("Alexander", "Alex") is False


def test_admin_peer_privilege_isolation():
    """Verify only authorized peers have admin status, NEVER Alexander."""
    # Positive admin peers
    assert is_admin_peer("Contact Alex") is True
    assert is_admin_peer("Alex") is True
    assert is_admin_peer("User") is True
    assert is_admin_peer("Admin User") is True

    # Alexander MUST NOT have admin privileges
    assert is_admin_peer("Alexander") is False
    assert is_admin_peer("Contact Alexander") is False


def test_personalized_banter_separation():
    """Verify distinct peers receive appropriate status responses."""
    resp_alex = generate_device_action_response("what is your ip", "Contact Alex")
    assert "port 8080" in resp_alex.lower() or "device ip" in resp_alex.lower() or "alex" in resp_alex.lower()

    resp_alexander = generate_device_action_response("what is your ip", "Contact Alexander")
    assert "deii gova" not in resp_alexander.lower()
    assert "alexander" in resp_alexander.lower() or "port 8080" in resp_alexander.lower()


# ── 2. Max Department Tests ────────────────────────────────────────────────

def test_monish_department_is_rpt():
    """Verify Max is registered in RPT department in configs and materials."""
    max_p = next((p for p in TARGET_PEERS_CONFIG if p["canonical"] == "Contact Max"), None)
    assert max_p is not None
    assert max_p["dept"] == "RPT"
    assert "RPT" in max_p["notes"]


def test_monish_rpt_timetable_lookup():
    """Verify timetable queries for Max or RPT return the RPT schedule."""
    assert "rpt" in BRANCH_TIMETABLES
    assert BRANCH_TIMETABLES["rpt"]["friend"] in ("Contact Max", "MIT Monish")

    resp_rpt = find_timetable_for_query("send rpt timetable")
    assert resp_rpt is not None
    assert "Rubber and Plastics" in resp_rpt


# ── 3. Real Command Execution & Anti-Hallucination Tests ───────────────────────

def test_extract_command_from_query_variants():
    """Verify command trigger patterns cleanly extract shell commands without fluff."""
    assert extract_command_from_query("run: ls -la") == "ls -la"
    assert extract_command_from_query("run command: git status") == "git status"
    assert extract_command_from_query("test command: python3 --version") == "python3 --version"
    assert extract_command_from_query("can you run: df -h") == "df -h"
    assert extract_command_from_query("test and give: uptime") == "uptime"
    assert extract_command_from_query("run `ps aux`") == "ps aux"
    assert extract_command_from_query("terminal: whoami") == "whoami"
    assert extract_command_from_query("hello friend") is None


def test_is_device_query_recognizes_all_command_variants():
    """Verify is_device_query triggers on any command invocation."""
    assert is_device_query("run: ls -la") is True
    assert is_device_query("test command: git status") is True
    assert is_device_query("can you run: uname -a") is True
    assert is_device_query("terminal: free -m") is True


def test_real_command_execution():
    """Verify safe shell commands actually execute and return real output."""
    output = execute_safe_terminal_command("echo 'JULIUS_TEST_VERIFIED'")
    assert "JULIUS_TEST_VERIFIED" in output


def test_blocked_destructive_commands():
    """Verify destructive commands are blocked before execution."""
    assert "strictly blocked" in execute_safe_terminal_command("rm -rf /")
    assert "strictly blocked" in execute_safe_terminal_command("shutdown -h now")
    assert "strictly blocked" in execute_safe_terminal_command("format c:")


def test_non_admin_command_execution_rejection():
    """Verify non-admin users cannot execute terminal commands."""
    resp = generate_device_action_response("run: echo 123", "Contact Alexander")
    assert "admin" in resp.lower()

    resp_admin = generate_device_action_response("run: echo 'ADMIN_EXEC_OK'", "Contact Alex")
    assert "ADMIN_EXEC_OK" in resp_admin


# ── 4. Nathan Auto List & Media Save Tests ─────────────────────────────────

def test_latchuman_in_auto_target_peers():
    """Verify Contact Nathan is recognized and resolves to canonical target peer."""
    assert is_target_peer_chat("Nathan") is True
    assert is_target_peer_chat("Contact Nathan") is True
    assert get_canonical_target_peer_name("Nathan") == "Contact Nathan"
    assert get_canonical_target_peer_name("Contact Nathan") == "Contact Nathan"


def test_image_naming_logic():
    """Verify clean, meaningful filenames are extracted from context hints."""
    from src.integrations.whatsapp.media_manager import get_media_manager
    mgr = get_media_manager()
    import base64
    sample_b64 = "data:image/jpeg;base64," + base64.b64encode(b"realistic jpeg header content fake image" * 10).decode()

    rec1 = mgr.save_image_from_base64_text(
        text=sample_b64,
        sender_name="Contact Alex",
        context_hint="This image is Alex casual photo save it",
    )
    assert rec1 is not None
    assert "alex_casual" in rec1["filename"]

    rec2 = mgr.save_image_from_base64_text(
        text=sample_b64,
        sender_name="Contact Kevin",
        context_hint="Kevin presentation photo in classroom",
    )
    assert rec2 is not None
    assert "kevin_presentation" in rec2["filename"]

