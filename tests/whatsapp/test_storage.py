"""Tests for WhatsApp SQLite persistence layer."""

import pytest
from src.integrations.whatsapp.models import (
    AuditEntry,
    ChatConfig,
    ChatMode,
    SentMessageRecord,
    WhatsAppMessage,
)
from src.integrations.whatsapp.storage import WhatsAppStorage


@pytest.fixture
def storage(tmp_path):
    db_path = str(tmp_path / "test_wa_storage.db")
    return WhatsAppStorage(db_path=db_path)


def test_save_and_get_chat_config(storage):
    config = ChatConfig(chat_name="Project X", mode=ChatMode.AUTO, max_messages_per_hour=15)
    storage.save_chat_config(config)

    loaded = storage.get_chat_config("Project X")
    assert loaded is not None
    assert loaded.chat_name == "Project X"
    assert loaded.mode == ChatMode.AUTO
    assert loaded.max_messages_per_hour == 15

    # Case insensitive lookup
    loaded_lower = storage.get_chat_config("project x")
    assert loaded_lower is not None
    assert loaded_lower.chat_name == "Project X"


def test_delete_chat_config(storage):
    config = ChatConfig(chat_name="Temp Chat")
    storage.save_chat_config(config)
    assert storage.get_chat_config("Temp Chat") is not None

    deleted = storage.delete_chat_config("Temp Chat")
    assert deleted is True
    assert storage.get_chat_config("Temp Chat") is None


def test_audit_log_persistence(storage):
    entry = AuditEntry(
        chat_name="Alice",
        sender_name="Alice",
        mode="approval",
        generated_reply="Hi Alice",
        final_reply="Hi Alice!",
        approved=True,
        sent=True,
    )
    storage.save_audit_entry(entry)

    entries = storage.get_audit_entries(limit=10)
    assert len(entries) >= 1
    assert entries[0].chat_name == "Alice"
    assert entries[0].approved is True


def test_sent_message_loop_prevention_tracking(storage):
    text = "Hello world loop check"
    h = SentMessageRecord.compute_hash(text)
    record = SentMessageRecord(message_id="sent_1", chat_id="chat_1", content_hash=h, text=text)
    storage.record_sent_message(record)

    # Should detect recently sent
    is_recent = storage.is_recently_sent_by_me(chat_id="chat_1", text=text, window_seconds=60)
    assert is_recent is True

    # Different text should not match
    is_different = storage.is_recently_sent_by_me(chat_id="chat_1", text="Different message", window_seconds=60)
    assert is_different is False


def test_rate_limiting_counters(storage):
    key = "test_rate_key"
    # Under limit
    for _ in range(5):
        assert storage.check_rate_limit(key, max_count=5, window_seconds=60) is True

    # Exceeds limit
    assert storage.check_rate_limit(key, max_count=5, window_seconds=60) is False
