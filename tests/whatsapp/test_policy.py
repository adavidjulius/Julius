"""Tests for WhatsApp chat policy engine and allowlist rules."""

import pytest
from src.integrations.whatsapp.config import WhatsAppConfig
from src.integrations.whatsapp.models import ChatConfig, ChatMode, GroupTrigger, WhatsAppMessage
from src.integrations.whatsapp.policy import ChatPolicyEngine
from src.integrations.whatsapp.storage import WhatsAppStorage


@pytest.fixture
def policy_engine(tmp_path):
    db_path = str(tmp_path / "test_wa.db")
    storage = WhatsAppStorage(db_path=db_path)
    config = WhatsAppConfig(unknown_chats_mode=ChatMode.OFF)
    return ChatPolicyEngine(storage=storage, config=config)


def test_default_deny_unconfigured_chat(policy_engine):
    msg = WhatsAppMessage(
        id="m1", chat_id="c1", chat_name="Stranger", sender_id="s1", sender_name="Stranger",
        timestamp=1700000000.0, text="Hey there", is_group=False, is_from_me=False,
    )
    # Unconfigured chat must be denied
    assert policy_engine.should_process(msg) is False


def test_allowlist_configured_chat(policy_engine):
    chat = ChatConfig(chat_name="Alice", mode=ChatMode.APPROVAL, enabled=True)
    policy_engine.add_chat(chat)

    msg = WhatsAppMessage(
        id="m2", chat_id="c2", chat_name="Alice", sender_id="s2", sender_name="Alice",
        timestamp=1700000000.0, text="Hello Julius", is_group=False, is_from_me=False,
    )
    assert policy_engine.should_process(msg) is True


def test_ignore_own_messages(policy_engine):
    chat = ChatConfig(chat_name="Alice", mode=ChatMode.APPROVAL, enabled=True)
    policy_engine.add_chat(chat)

    msg = WhatsAppMessage(
        id="m3", chat_id="c2", chat_name="Alice", sender_id="me", sender_name="Me",
        timestamp=1700000000.0, text="I am replying", is_group=False, is_from_me=True,
    )
    assert policy_engine.should_process(msg) is False


def test_group_trigger_when_mentioned(policy_engine):
    group = ChatConfig(
        chat_name="Engineers",
        mode=ChatMode.AUTO,
        enabled=True,
        group_trigger=GroupTrigger.WHEN_MENTIONED,
    )
    policy_engine.add_chat(group)

    msg_unmentioned = WhatsAppMessage(
        id="m4", chat_id="g1", chat_name="Engineers", sender_id="s3", sender_name="Dave",
        timestamp=1700000000.0, text="Who is fixing the bug?", is_group=True, is_from_me=False,
    )
    assert policy_engine.should_process(msg_unmentioned) is False

    msg_mentioned = WhatsAppMessage(
        id="m5", chat_id="g1", chat_name="Engineers", sender_id="s3", sender_name="Dave",
        timestamp=1700000000.0, text="@Julius can you check the bug?", is_group=True, is_from_me=False,
    )
    assert policy_engine.should_process(msg_mentioned) is True
