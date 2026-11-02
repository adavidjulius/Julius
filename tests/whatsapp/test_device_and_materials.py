"""
Unit tests for Device Action Agent, Academic Materials Dispatch, and Peer Safety.
"""

import pytest
from pathlib import Path
from src.integrations.whatsapp.device_agent import (
    is_device_query,
    get_device_network_ip,
    generate_device_action_response,
)
from src.integrations.whatsapp.materials import (
    find_matching_document,
    get_materials_dir,
    MATERIALS_CATALOG,
)
from src.integrations.whatsapp.safety import SafetyGate
from src.integrations.whatsapp.models import WhatsAppMessage, Confidence


def test_device_query_detection():
    # IP address questions
    assert is_device_query("send me the IP address")
    assert is_device_query("what is your ip?")
    assert is_device_query("hostel wifi ip")
    assert is_device_query("server ip")
    assert is_device_query("Yeah, it’s still connected on the Hostel Wi-Fi. You can see and send me the IP address because David wanted urgently.")
    
    # Routine questions that should NOT be device queries
    assert not is_device_query("what class do we have tomorrow?")
    assert not is_device_query("did you complete calculus record?")
    assert not is_device_query("hello da machi")


def test_device_action_response_generation():
    ip = get_device_network_ip()
    assert ip  # IP must not be empty
    
    # Alex status
    alex_resp = generate_device_action_response("send me the ip", "Contact Alex")
    assert ip in alex_resp
    assert "port 8080" in alex_resp.lower() or "device ip" in alex_resp.lower()
    
    # Charlie status
    charlie_resp = generate_device_action_response("what's the ip?", "Contact Charlie")
    assert ip in charlie_resp


def test_materials_discovery():
    materials_dir = get_materials_dir()
    assert materials_dir.exists()

    # Create temporary sample files if absent for test validation
    tt_file = materials_dir / "First_Semester_Timetable_2026.pdf"
    phys_file = materials_dir / "Engineering_Physics_PH23C11_Notes.pdf"
    created = []
    for f in [tt_file, phys_file]:
        if not f.exists():
            f.write_text("DUMMY_TEST_CONTENT", encoding="utf-8")
            created.append(f)

    try:
        # Timetable matching
        doc = find_matching_document("send timetable")
        assert doc is not None
        assert "timetable" in doc["id"]

        # Physics material matching
        doc_phys = find_matching_document("physics material")
        assert doc_phys is not None
        assert doc_phys["id"] == "physics_notes"

        # Non-materials query
        assert find_matching_document("are you coming to canteen?") is None
    finally:
        for f in created:
            if f.exists():
                f.unlink()


def test_target_peer_casual_urgency_does_not_escalate():
    safety = SafetyGate()
    
    # Message from Contact Alex with 'urgently'
    msg = WhatsAppMessage(
        id="test-1",
        chat_id="alex@s.whatsapp.net",
        chat_name="Contact Alex",
        sender_id="alex@s.whatsapp.net",
        sender_name="Contact Alex",
        timestamp=100.0,
        text="Yeah, it’s still connected on the Wi-Fi. You can see and send me the IP address because team wanted urgently.",
    )
    
    conf, reason = safety.evaluate_message(msg)
    # Should NOT be LOW (which triggers escalation)
    assert conf != Confidence.LOW
    assert not safety.should_escalate(conf, Confidence.HIGH)

    # Message with image thumbnail base64 from Kevin
    kevin_msg = WhatsAppMessage(
        id="test-2",
        chat_id="kevin@s.whatsapp.net",
        chat_name="Contact Kevin",
        sender_id="kevin@s.whatsapp.net",
        sender_name="Contact Kevin",
        timestamp=101.0,
        text="Check out the schematic\n/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEABERERESERMVFRMaHBkcGiYjICAjJjoqLSotKjpYN0A3N0A3WE5fTUhNX06MbmJiboyiiIGIosWwsMX46/j///8BERERERIRExUVExocGRwaJiMgICMmOiotKi0qOlg3QDc3QDdYTl9NSE1fToxuYmJujKKIgYiixbCwxfjr+P/////CABEIAGAARAMBIgACEQEDEQH/xAAuAAADAQEBAQAAAAAAAAAAAAAAAgMBBAUGAQEBAQAAAAAAAAAAAAAAAAAAAQL/2gAIAQEAAT8AkeYrNPUPmuYnrX5rNPUKzT1L81mnrX5o3E07wp79u0AWOhMUrBlDDYir8jiG1MB16n6UC+byRjGlS8asKE467y1Hc0WAI+pimGh0nSrru2KkzDaA1Z8NPaK4kH8U0KdWHT20C5d5HdjSvzY2rJgFDDUs1Hc0+6e+kUMYO0VxlhUKEdTVrw09ooXCbzJGgUGhkXeVERpQFydV6fzV2VwOOzGhdRmImubL/QNM1w9xGc67ChctkxmJ8uzir7WeIusBryx/JpCxLFsYKiKg4iSKuibZA/auW+Q7p3/quW0EYnaK7ycxoMELULjqJOkGrBY2lLb1xwi64HRB9jXCsVclmGOAimdechyEBTR/urpIiPWtdaRQxg7RS8NaUyB2cfrfuDztj7Glz9UDERU798bGnYgoJ3ZqveNb/wC/cUhJyn1EVYJ55XSBbB7eNDNdugKTFsGPmlz84ECNak698bGrpIQsCCRMVdP6gxtlp+1LdaMh7q4I5X2YnXDt24pzBjliiLmb6mOlLkAZboelXiMYJ3JrBQ0i4N6Fu2B4grg1UXjDA9ztd1Fy4pBJnQ5ERSK5EltCorz7x2PSryhwoLdTXIWd20muQkda4VFS5InVe274zH6iraNiDrqorltJMvtRss2J1MEmjaaTofmjaJBEGrVsq0wf9Y7W4S4WYgW9TuZmkXFFXyAH+D//xAAYEQEAAwEAAAAAAAAAAAAAAAABEBEgQP/aAAgBAgEBPwCQtyZGuH//xAAZEQACAwEAAAAAAAAAAAAAAAABERAiMED/2gAIAQMBAT8AkGyyfD//2Q==",
    )
    s_conf, s_reason = safety.evaluate_message(kevin_msg)
    assert s_conf != Confidence.LOW
    assert not safety.should_escalate(s_conf, Confidence.HIGH)

    # Message with debugging terms (diagnose/symptom) from peer should NOT escalate to approval
    debug_msg = WhatsAppMessage(
        id="test-3",
        chat_id="alex@s.whatsapp.net",
        chat_name="Contact Alex",
        sender_id="alex@s.whatsapp.net",
        sender_name="Contact Alex",
        timestamp=102.0,
        text="Can you give the code for David to D bug the bug? Need to diagnose the server symptom.",
    )
    d_conf, d_reason = safety.evaluate_message(debug_msg)
    assert d_conf != Confidence.LOW
    assert not safety.should_escalate(d_conf, Confidence.HIGH)


def test_connected_devices_and_code_query():
    from src.integrations.whatsapp.device_agent import (
        get_connected_network_devices,
        generate_device_action_response,
        execute_safe_terminal_command,
    )
    # Connected devices
    assert is_device_query("What are the other devices which is connected?")
    assert is_device_query("what devices connected there")
    dev_resp = generate_device_action_response("What are the other devices which is connected?", "Contact Alex")
    assert "devices" in dev_resp.lower() or "ip neigh" in dev_resp.lower()

    # Code query
    assert is_device_query("Can you show me what is the code inside julius.PY?")
    code_resp = generate_device_action_response("what is the code inside julius.py?", "Contact Alex")
    assert "julius" in code_resp.lower()

    # Safe command execution
    out = execute_safe_terminal_command("echo hello_julius")
    assert "hello_julius" in out

    # Blocked destructive command
    blocked_out = execute_safe_terminal_command("rm -rf /")
    assert "blocked" in blocked_out.lower()


def test_branch_timetable_queries():
    from src.integrations.whatsapp.materials import (
        find_timetable_for_query,
        get_all_timetables_summary,
        BRANCH_TIMETABLES,
    )
    # All branches exist
    assert "automobile" in BRANCH_TIMETABLES
    assert "it1" in BRANCH_TIMETABLES
    assert "it2" in BRANCH_TIMETABLES
    assert "ece" in BRANCH_TIMETABLES
    assert "cse" in BRANCH_TIMETABLES

    # Gova's timetable query
    gova_tt = find_timetable_for_query("what is gova's timetable?")
    assert gova_tt is not None
    assert "Automobile" in gova_tt
    assert "Room 205" in gova_tt

    # Sumanth's timetable query
    sumanth_tt = find_timetable_for_query("tell me sumanth timetable")
    assert sumanth_tt is not None
    assert "IT Batch 1" in sumanth_tt
    assert "Room 001" in sumanth_tt

    # All timetables query
    all_tt = find_timetable_for_query("list all guys timetable")
    assert all_tt is not None
    assert "Automobile" in all_tt
    assert "IT Batch 1" in all_tt
    assert "ECE" in all_tt
    assert "CSE" in all_tt
