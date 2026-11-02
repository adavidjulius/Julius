"""Tests for WhatsApp auto-mode safety gate and escalation."""

import pytest
from src.integrations.whatsapp.models import Confidence, WhatsAppMessage
from src.integrations.whatsapp.safety import SafetyGate


@pytest.fixture
def safety_gate():
    return SafetyGate()


def test_routine_message_no_escalation(safety_gate):
    msg = WhatsAppMessage(
        id="1", chat_id="c1", chat_name="Friend", sender_id="s1", sender_name="Friend",
        timestamp=1700000000.0, text="Are you free for lunch tomorrow?", is_group=False, is_from_me=False,
    )
    should_escalate, reason = safety_gate.check_escalation(msg, "Yeah I should be free around 1 PM!")
    assert should_escalate is False
    assert reason == ""


def test_financial_pattern_escalates(safety_gate):
    msg = WhatsAppMessage(
        id="2", chat_id="c1", chat_name="Friend", sender_id="s1", sender_name="Friend",
        timestamp=1700000000.0, text="Can you send 500 rupees via GPay?", is_group=False, is_from_me=False,
    )
    should_escalate, reason = safety_gate.check_escalation(msg, "Sending it right now")
    assert should_escalate is True
    assert "Financial" in reason or "commitment" in reason.lower()


def test_commitment_pattern_escalates(safety_gate):
    msg = WhatsAppMessage(
        id="3", chat_id="c1", chat_name="Colleague", sender_id="s2", sender_name="Colleague",
        timestamp=1700000000.0, text="Can you sign the agreement and submit by 5pm?", is_group=False, is_from_me=False,
    )
    should_escalate, reason = safety_gate.check_escalation(msg, "I will definitely sign and agree to the contract")
    assert should_escalate is True


def test_confidence_classification(safety_gate):
    # Short routine confirmation -> HIGH
    conf = safety_gate.classify_confidence("Ok sounds good! See you then.")
    assert conf == Confidence.HIGH

    # Question or complex message -> MEDIUM/LOW
    conf_complex = safety_gate.classify_confidence("Could you perhaps clarify what time the meeting starts tomorrow?")
    assert conf_complex in (Confidence.MEDIUM, Confidence.LOW)
