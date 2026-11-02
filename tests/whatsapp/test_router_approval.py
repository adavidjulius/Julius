"""Tests for WhatsApp approval queue and message router logic."""

import pytest
from src.integrations.whatsapp.approval import ApprovalQueue
from src.integrations.whatsapp.models import Confidence, WhatsAppMessage


def test_approval_queue_lifecycle():
    queue = ApprovalQueue(expiry_seconds=300.0)

    msg = WhatsAppMessage(
        id="m_app_1", chat_id="c_app_1", chat_name="Carol", sender_id="s_app_1",
        sender_name="Carol", timestamp=1700000000.0, text="Can we reschedule?",
    )

    # 1. Add item
    item = queue.add(incoming_message=msg, draft_reply="Sure, does Thursday work?", confidence=Confidence.HIGH, reason="Routine request")
    assert queue.pending_count == 1
    assert item.status == "pending"

    # 2. Get pending items
    pending = queue.get_pending()
    assert len(pending) == 1
    assert pending[0].id == item.id

    # 3. Edit and approve
    approved = queue.approve_with_edit(item.id, "Sure, does Friday at 2 PM work better?")
    assert approved is not None
    assert approved.status == "approved"
    assert approved.draft_reply == "Sure, does Friday at 2 PM work better?"
    assert queue.pending_count == 0


def test_approval_queue_rejection():
    queue = ApprovalQueue()

    msg = WhatsAppMessage(
        id="m_app_2", chat_id="c_app_2", chat_name="Dan", sender_id="s_app_2",
        sender_name="Dan", timestamp=1700000000.0, text="Are you available?",
    )

    item = queue.add(incoming_message=msg, draft_reply="Yes!", confidence=Confidence.MEDIUM)
    assert queue.pending_count == 1

    rejected = queue.reject(item.id)
    assert rejected is not None
    assert rejected.status == "rejected"
    assert queue.pending_count == 0


def test_approval_queue_clear_all():
    queue = ApprovalQueue()
    for i in range(3):
        msg = WhatsAppMessage(
            id=f"m_{i}", chat_id=f"c_{i}", chat_name=f"User {i}", sender_id=f"s_{i}",
            sender_name=f"User {i}", timestamp=1700000000.0, text=f"Test {i}",
        )
        queue.add(incoming_message=msg, draft_reply="Reply", confidence=Confidence.MEDIUM)

    assert queue.pending_count == 3
    cleared = queue.clear_all()
    assert cleared == 3
    assert queue.pending_count == 0
