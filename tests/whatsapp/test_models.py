"""Tests for WhatsApp integration models and data types."""

import pytest
from src.integrations.whatsapp.models import (
    ApprovalItem,
    ChatConfig,
    ChatMode,
    Confidence,
    GroupTrigger,
    HealthState,
    MessageType,
    SentMessageRecord,
    StyleProfile,
    TrainingExample,
    WhatsAppMessage,
)


def test_whatsapp_message_creation_and_dict():
    msg = WhatsAppMessage(
        id="msg123",
        chat_id="chat456",
        chat_name="Alice",
        sender_id="user789",
        sender_name="Alice",
        timestamp=1700000000.0,
        text="Hello Julius!",
        is_group=False,
        is_from_me=False,
    )
    assert msg.id == "msg123"
    assert msg.message_type == MessageType.TEXT
    d = msg.to_dict()
    assert d["chat_name"] == "Alice"
    assert d["text"] == "Hello Julius!"
    assert d["is_group"] is False
    assert len(msg.dedup_key) == 32


def test_chat_config_defaults_and_serialization():
    config = ChatConfig(chat_name="Bob")
    assert config.mode == ChatMode.APPROVAL
    assert config.enabled is True
    assert config.group_trigger == GroupTrigger.WHEN_MENTIONED

    d = config.to_dict()
    assert d["chat_name"] == "Bob"
    assert d["mode"] == "approval"

    restored = ChatConfig.from_dict(d)
    assert restored.chat_name == "Bob"
    assert restored.mode == ChatMode.APPROVAL


def test_approval_item_workflow():
    item = ApprovalItem(
        chat_name="Alice",
        draft_reply="Hey Alice, I am working on it now.",
        confidence=Confidence.HIGH,
        reason="Routine greeting and status update",
    )
    assert item.status == "pending"
    d = item.to_dict()
    assert d["draft_reply"] == "Hey Alice, I am working on it now."
    assert d["confidence"] == "high"


def test_style_profile_defaults_and_dict():
    profile = StyleProfile(name="test_user")
    assert profile.tone == "casual"
    assert "corporate language" in profile.avoid_patterns

    d = profile.to_dict()
    restored = StyleProfile.from_dict(d)
    assert restored.name == "test_user"
    assert restored.tone == "casual"


def test_sent_message_record_hash():
    text = "Let's meet tomorrow at 10 AM"
    hash_val = SentMessageRecord.compute_hash(text)
    assert len(hash_val) == 32
    assert hash_val == SentMessageRecord.compute_hash(text)
