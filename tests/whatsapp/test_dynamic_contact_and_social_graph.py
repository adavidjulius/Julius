"""
Tests for WhatsApp Dynamic Contact Memory, Interconnected Social Graph,
and 1-on-1 Contact Auto-Enrollment.
"""

import tempfile
import time
import pytest

from src.integrations.whatsapp.config import WhatsAppConfig, is_self_chat
from src.integrations.whatsapp.context import (
    ConversationContext,
    detect_preferred_language,
    reflect_and_update_contact_profile,
)
from src.integrations.whatsapp.models import (
    ChatConfig,
    ChatMode,
    Confidence,
    ContactProfile,
    WhatsAppMessage,
)
from src.integrations.whatsapp.policy import ChatPolicyEngine
from src.integrations.whatsapp.storage import WhatsAppStorage


@pytest.fixture
def temp_storage(tmp_path):
    return WhatsAppStorage(db_path=str(tmp_path / "test_whatsapp.db"))


def test_contact_profile_persistence(temp_storage):
    """Test creating, saving, and retrieving a dynamic ContactProfile."""
    profile = ContactProfile(
        chat_name="Rajesh",
        display_name="Rajesh IT",
        contact_type="classmate",
        tone_style="playful, humorous",
        slang_used=["machi", "da"],
        favorite_topics=["calculus", "hostel life"],
        last_status_update="in hostel room chillin",
        interconnected_notes="chillin in hostel room",
        important_facts=["stays in Bhavani hostel room 204"],
        total_messages_exchanged=5,
        updated_at=time.time(),
    )
    temp_storage.save_contact_profile(profile)

    loaded = temp_storage.get_contact_profile("Rajesh")
    assert loaded is not None
    assert loaded.chat_name == "Rajesh"
    assert loaded.display_name == "Rajesh IT"
    assert "machi" in loaded.slang_used
    assert "calculus" in loaded.favorite_topics
    assert loaded.last_status_update == "in hostel room chillin"

    # Test token search fallback
    loaded_token = temp_storage.get_contact_profile("MIT Rajesh")
    assert loaded_token is not None
    assert loaded_token.chat_name == "Rajesh"


def test_interconnected_social_graph_query(temp_storage):
    """Test finding peer status across contacts."""
    sundar_profile = ContactProfile(
        chat_name="MIT Sundaramoorthy",
        display_name="Sundaramoorthy",
        contact_type="close friend",
        tone_style="casual",
        last_status_update="studying in room for calculus exam",
        interconnected_notes="studying in room for calculus exam",
        updated_at=time.time(),
    )
    temp_storage.save_contact_profile(sundar_profile)

    # When Friend A asks "where is Sundar?"
    peer_status = temp_storage.find_peer_status("sundar")
    assert peer_status is not None
    assert "Sundaramoorthy" in peer_status["peer_name"]
    assert "calculus exam" in peer_status["status"]


def test_reflect_and_update_contact_profile(temp_storage):
    """Test dynamic learning from conversation exchange."""
    chat_name = "MIT Putta Reddy Guru Rakesh Reddy"
    user_text = "machi enna panra 😂 in hostel room doing calculus"
    bot_reply = "chillin in room da, just finished drawing EG sheet"

    reflect_and_update_contact_profile(
        storage=temp_storage,
        chat_name=chat_name,
        sender_name="Putta Reddy",
        user_text=user_text,
        bot_reply=bot_reply,
    )

    profile = temp_storage.get_contact_profile(chat_name)
    assert profile is not None
    assert "machi" in profile.slang_used
    assert "calculus" in profile.favorite_topics
    assert "playful" in profile.tone_style or "casual" in profile.tone_style
    assert "hostel" in profile.last_status_update or "calculus" in profile.last_status_update


def test_context_builder_with_dynamic_profile_and_social_graph(temp_storage):
    """Test prompt assembly includes dynamic profile and mutual friend updates."""
    # Seed peer status
    temp_storage.save_contact_profile(
        ContactProfile(
            chat_name="MIT Gova",
            display_name="Gova",
            last_status_update="at makerspace working on project",
            interconnected_notes="at makerspace working on project",
        )
    )

    # Seed contact profile for Naveen
    temp_storage.save_contact_profile(
        ContactProfile(
            chat_name="MIT Naveen Raj ECE",
            display_name="Naveen Raj",
            slang_used=["machan", "da"],
            favorite_topics=["circuit lab", "hostel"],
            tone_style="energetic college friend",
        )
    )

    context_mgr = ConversationContext(temp_storage)
    incoming = WhatsAppMessage(
        id="msg_test_01",
        chat_id="chat_naveen",
        chat_name="MIT Naveen Raj ECE",
        sender_id="naveen",
        sender_name="Naveen Raj",
        timestamp=time.time(),
        text="machan where is Gova?",
    )
    cfg = ChatConfig(chat_name="MIT Naveen Raj ECE", mode=ChatMode.AUTO)

    prompt = context_mgr.build_prompt(incoming, cfg)
    assert "Naveen Raj" in prompt
    assert "DYNAMIC PROFILE FOR NAVEEN RAJ" in prompt
    assert "machan" in prompt
    assert "MUTUAL PEER SOCIAL CONTEXT" in prompt
    assert "Gova" in prompt
    assert "makerspace" in prompt


def test_policy_strictly_denies_unconfigured_contacts(temp_storage):
    """Test policy strictly denies unconfigured contacts and never auto-enrolls them."""
    config = WhatsAppConfig()
    policy = ChatPolicyEngine(storage=temp_storage, config=config)

    # Unknown contact texts
    msg = WhatsAppMessage(
        id="msg_rajesh_01",
        chat_id="chat_rajesh",
        chat_name="Rajesh",
        sender_id="rajesh",
        sender_name="Rajesh",
        timestamp=time.time(),
        text="Jolly yaah irukaa",
        is_group=False,
    )

    # STRICT: Should be denied (not auto-enrolled)
    assert policy.should_process(msg) is False

    # Check that config was NOT created in storage
    cfg = policy.get_chat_config("Rajesh")
    assert cfg is None

    # Group chat from unconfigured group should also be denied
    group_msg = WhatsAppMessage(
        id="msg_group_01",
        chat_id="chat_calculus_group",
        chat_name="IT Batch 2 Calculus Group",
        sender_id="student_1",
        sender_name="Tarun",
        timestamp=time.time(),
        text="Tutorial 1 pdf uploaded",
        is_group=True,
    )
    assert policy.should_process(group_msg) is False


def test_self_chat_detection():
    """Verify all variations of David Julius self-chat match."""
    assert is_self_chat("David Julius") is True
    assert is_self_chat("David Julius U") is True
    assert is_self_chat("David Julius u") is True
    assert is_self_chat("David Julius (YOU)") is True
    assert is_self_chat("David Julius (You)") is True
    assert is_self_chat("David Julius(YOU)") is True
    assert is_self_chat("You") is True
    assert is_self_chat("U") is False  # Must not match single letter promo accounts
    assert is_self_chat("u") is False
    assert is_self_chat("Message yourself") is True
    assert is_self_chat("MIT Gova") is False
    assert is_self_chat("Rajesh") is False
