"""
Tests for Julius WhatsApp Deep Conversation, Learning, Media & Context Upgrade.

Covers:
1. MIT Monish auto-chat registration, alias resolution, and context isolation.
2. PersonalKnowledgeEngine: fact extraction, status lifecycle, contradiction resolution, and superseding.
3. ConversationStateMachine: termination signals ("bye", "gtg", "talk later", "gn"), ENDING -> ENDED transition, reply suppression, and clean reopening.
4. CommunicationStyleLearner: multi-turn linguistic feature extraction and style profile adaptation.
5. WhatsAppAdapter & Media Protocol: file validation, selector strategies, preview synchronization, and transmission.
6. End-to-end Router Integration: context enrichment with structured facts, anti-hallucination guidelines, and state transitions.
"""

from __future__ import annotations

import os
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.whatsapp.adapter import (
    ATTACH_BUTTON_STRATEGY,
    DOCUMENT_INPUT_STRATEGY,
    IMAGE_INPUT_STRATEGY,
    PREVIEW_CAPTION_STRATEGY,
    PREVIEW_DIALOG_STRATEGY,
    PREVIEW_SEND_BUTTON_STRATEGY,
    WhatsAppAdapter,
)
from src.integrations.whatsapp.config import (
    TARGET_PEERS_CONFIG,
    WhatsAppConfig,
    is_target_peer_chat,
)
from src.integrations.whatsapp.context import ConversationContext
from src.integrations.whatsapp.conversation_state import (
    ConversationStateMachine,
)
from src.integrations.whatsapp.knowledge import PersonalKnowledgeEngine
from src.integrations.whatsapp.models import (
    ChatConfig,
    ChatMode,
    ConversationState,
    MemoryCategory,
    MemoryStatus,
    PersonMemory,
    WhatsAppMessage,
)
from src.integrations.whatsapp.persona import PersonaEngine
from src.integrations.whatsapp.policy import ChatPolicyEngine
from src.integrations.whatsapp.router import WhatsAppMessageRouter
from src.integrations.whatsapp.sender import WhatsAppSender
from src.integrations.whatsapp.storage import WhatsAppStorage
from src.integrations.whatsapp.style_learner import CommunicationStyleLearner


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def storage(temp_db):
    return WhatsAppStorage(db_path=temp_db)


# ── 1. Contact Configuration & Max Auto-Chat ─────────────────────────────

def test_mit_monish_configured():
    """Verify Contact Max is in TARGET_PEERS_CONFIG with correct aliases."""
    max_entry = None
    for peer in TARGET_PEERS_CONFIG:
        if peer["canonical"] == "Contact Max":
            max_entry = peer
            break

    assert max_entry is not None
    assert "Max" in max_entry["aliases"]
    assert "Contact Max" in max_entry["aliases"]
    assert "max" in max_entry["tokens"]
    assert max_entry["dept"] == "RPT"

    assert is_target_peer_chat("Contact Max") is True
    assert is_target_peer_chat("Max") is True


def test_monish_context_isolation(storage):
    """Verify memory and context for Max is completely isolated from other peers."""
    knowledge = PersonalKnowledgeEngine(storage)

    # Max tells us something
    msg_max = WhatsAppMessage(
        id="m_001",
        chat_id="max_id",
        chat_name="Contact Max",
        sender_id="max_id",
        sender_name="Contact Max",
        timestamp=time.time(),
        text="I live in City A with my brother",
    )
    knowledge.extract_and_update_knowledge(msg_max)

    # Charlie tells us something else
    msg_charlie = WhatsAppMessage(
        id="m_002",
        chat_id="charlie_id",
        chat_name="Contact Charlie",
        sender_id="charlie_id",
        sender_name="Contact Charlie",
        timestamp=time.time(),
        text="I live in City B",
    )
    knowledge.extract_and_update_knowledge(msg_charlie)

    # Query memories for Max
    max_mems = storage.get_person_memories("Contact Max")
    assert len(max_mems) == 1
    assert "City A" in max_mems[0].fact

    # Query memories for Charlie
    charlie_mems = storage.get_person_memories("Contact Charlie")
    assert len(charlie_mems) == 1
    assert "City B" in charlie_mems[0].fact

    # Strict separation: Max's search does not return Charlie's fact
    relevant_to_max = storage.search_relevant_memories("Contact Max", "where do you live")
    assert any("City A" in m.fact for m in relevant_to_max)
    assert not any("City B" in m.fact for m in relevant_to_max)


# ── 2. Knowledge Evolution & Contradiction Resolution ───────────────────────

def test_knowledge_evolution_superseding(storage):
    """Verify that when a contact moves city, the old fact is superseded and the new fact is active."""
    knowledge = PersonalKnowledgeEngine(storage)

    # Day 1: User says "I live in Chennai"
    msg1 = WhatsAppMessage(
        id="msg_day1",
        chat_id="c1",
        chat_name="Contact Max",
        sender_id="s1",
        sender_name="Max",
        timestamp=time.time() - 86400,
        text="I live in Chennai.",
    )
    knowledge.extract_and_update_knowledge(msg1)

    mems1 = storage.get_person_memories("Contact Max", status=MemoryStatus.CURRENT.value)
    assert len(mems1) == 1
    assert "Chennai" in mems1[0].fact
    assert mems1[0].status == MemoryStatus.CURRENT.value
    old_id = mems1[0].id

    # Day 5: User says "I moved to Bangalore yesterday"
    msg2 = WhatsAppMessage(
        id="msg_day5",
        chat_id="c1",
        chat_name="Contact Max",
        sender_id="s1",
        sender_name="Max",
        timestamp=time.time(),
        text="I moved to Bangalore yesterday.",
    )
    knowledge.extract_and_update_knowledge(msg2)

    # Verify old fact is superseded
    all_mems = storage.get_person_memories("Contact Max")
    assert len(all_mems) == 2

    superseded = [m for m in all_mems if m.id == old_id][0]
    assert superseded.status == MemoryStatus.SUPERSEDED.value

    current = [m for m in all_mems if m.id != old_id][0]
    assert current.status == MemoryStatus.CURRENT.value
    assert "Bangalore" in current.fact
    assert superseded.superseded_by == current.id

    # Verify relevant memory search only surfaces active facts
    active_search = storage.search_relevant_memories("Contact Max", "Bangalore")
    assert len(active_search) == 1
    assert "Bangalore" in active_search[0].fact


def test_knowledge_planned_vs_current(storage):
    """Verify tentative/planned statements do not overwrite current facts."""
    knowledge = PersonalKnowledgeEngine(storage)

    # Current fact: "I live in Chennai"
    msg1 = WhatsAppMessage(
        id="msg_cur",
        chat_id="c1",
        chat_name="Contact Max",
        sender_id="s1",
        sender_name="Max",
        timestamp=time.time() - 500,
        text="I live in Chennai.",
    )
    knowledge.extract_and_update_knowledge(msg1)

    # Tentative fact: "I am thinking of moving to Bangalore"
    msg2 = WhatsAppMessage(
        id="msg_plan",
        chat_id="c1",
        chat_name="Contact Max",
        sender_id="s1",
        sender_name="Max",
        timestamp=time.time(),
        text="I am thinking of moving to Bangalore next year.",
    )
    knowledge.extract_and_update_knowledge(msg2)

    all_mems = storage.get_person_memories("Contact Max")
    assert len(all_mems) == 2

    # Both should be preserved: Current is still CURRENT, Planned is PLANNED
    current_facts = [m for m in all_mems if m.status == MemoryStatus.CURRENT.value]
    planned_facts = [m for m in all_mems if m.status == MemoryStatus.PLANNED.value]

    assert len(current_facts) == 1
    assert "Chennai" in current_facts[0].fact
    assert len(planned_facts) == 1
    assert "Bangalore" in planned_facts[0].fact


def test_user_correction_detection(storage):
    """Verify detection of user corrections."""
    knowledge = PersonalKnowledgeEngine(storage)
    assert knowledge.is_user_correction("No bro, that's not what I meant") is True
    assert knowledge.is_user_correction("Actually no, I study in IT 2") is True
    assert knowledge.is_user_correction("Sounds good to me") is False


# ── 3. Conversation State Machine & Ending Transitions ───────────────────────

def test_conversation_state_lifecycle_and_endings(storage):
    """Verify state machine moves to ENDING on bye, then to ENDED on outgoing reply, and suppresses further replies."""
    sm = ConversationStateMachine(storage)

    # 1. First message -> GREETING or ACTIVE
    state1, is_ending1 = sm.on_incoming_message("Contact Max", "Max", "Hey David, what's up?")
    assert state1.state in (ConversationState.GREETING.value, ConversationState.ACTIVE.value)
    assert is_ending1 is False
    assert sm.should_suppress_replies("Contact Max") is False

    # Outgoing reply keeps it ACTIVE
    sm.on_outgoing_message_sent("Contact Max", "Hey bro, working on Julius")
    assert sm.get_state("Contact Max").state == ConversationState.ACTIVE.value

    # 2. Friend says "ok bye da" -> ENDING
    state2, is_ending2 = sm.on_incoming_message("Contact Max", "Max", "ok bye da")
    assert state2.state == ConversationState.ENDING.value
    assert is_ending2 is True
    assert "bye" in state2.termination_phrase

    # Outgoing farewell reply transitions ENDING -> ENDED
    sm.on_outgoing_message_sent("Contact Max", "ok da see ya!")
    ended_state = sm.get_state("Contact Max")
    assert ended_state.state == ConversationState.ENDED.value

    # In ENDED state, should_suppress_replies is True
    assert sm.should_suppress_replies("Contact Max") is True

    # 3. Friend messages again later -> REOPENED -> ACTIVE
    state3, is_ending3 = sm.on_incoming_message("Contact Max", "Max", "Hey David you free?")
    assert state3.state == ConversationState.ACTIVE.value
    assert is_ending3 is False
    assert sm.should_suppress_replies("Contact Max") is False


def test_termination_signals():
    """Verify diverse termination signals are accurately recognized."""
    sm = ConversationStateMachine(MagicMock())

    positive_signals = [
        "bye", "goodbye", "cya", "see ya", "see you later",
        "gtg", "gotta go", "talk later", "catch you later",
        "good night", "gn", "gud night", "ok bye", "bye da",
        "bye bro", "take care", "tc",
    ]
    for sig in positive_signals:
        is_term, phrase = sm.is_termination_signal(sig)
        assert is_term is True, f"Failed to recognize termination: '{sig}'"

    negative_signals = [
        "What time is class?",
        "Did you submit the EG record?",
        "Why did you say goodbye earlier?",
        "I will buy a new laptop tomorrow",
    ]
    for sig in negative_signals:
        is_term, _ = sm.is_termination_signal(sig)
        assert is_term is False, f"False positive termination on: '{sig}'"


# ── 4. Communication Style Learner ──────────────────────────────────────────

def test_communication_style_learner(storage):
    """Verify linguistic features are extracted and latent profile evolves."""
    persona = PersonaEngine(storage)
    learner = CommunicationStyleLearner(storage, persona)

    # Initial profile is default
    initial_profile = persona.get_profile("Contact Max")
    assert initial_profile.formality in ("low", "casual")

    # User sends several heavy slang/Tanglish messages with emojis and laughs
    messages = [
        "dei machi semma comedy 😂 lol",
        "bro enna solra what da 😂🤣",
        "serida machan vera level haha",
    ]
    for i, txt in enumerate(messages):
        msg = WhatsAppMessage(
            id=f"style_msg_{i}",
            chat_id="c1",
            chat_name="Contact Max",
            sender_id="s1",
            sender_name="Max",
            timestamp=time.time() + i,
            text=txt,
        )
        obs = learner.observe_turn(msg)
        assert obs is not None
        assert obs.slang_score > 0
        if i in (0, 1):
            assert obs.emoji_count > 0

    # Verify style observations are stored
    stored_obs = storage.get_recent_style_observations("Contact Max", limit=10)
    assert len(stored_obs) == 3

    # Verify profile updated to reflect casual/slang vibe
    updated_profile = persona.get_profile("Contact Max")
    assert updated_profile.formality in ("very casual", "casual")
    assert updated_profile.emoji_frequency in ("frequent", "moderate")


# ── 5. WhatsApp Adapter & Media Transmission ────────────────────────────────

@pytest.mark.asyncio
async def test_send_media_file_validation():
    """Verify adapter validates file existence before touching the browser."""
    mock_browser = MagicMock()
    mock_browser.is_connected = True
    adapter = WhatsAppAdapter(mock_browser)

    # Missing file fails immediately
    success = await adapter.send_media(
        chat_name="Contact Max",
        file_path="/non/existent/path/notes.pdf",
        media_type="document",
    )
    assert success is False


@pytest.mark.asyncio
async def test_send_media_successful_protocol():
    """Verify complete 11-step transmission protocol via WhatsAppAdapter."""
    # Create a temporary real file
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
        tf.write(b"%PDF-1.4 dummy pdf content for testing")
        temp_pdf_path = tf.name

    try:
        mock_browser = MagicMock()
        mock_browser.is_connected = True
        mock_browser.navigate_to_chat = AsyncMock(return_value=True)

        mock_page = AsyncMock()
        mock_browser.page = mock_page

        # Mock DOM element interactions
        mock_attach_btn = AsyncMock()
        mock_file_input = AsyncMock()
        mock_preview_dialog = AsyncMock()
        mock_caption_box = AsyncMock()
        mock_send_btn = AsyncMock()

        # Mock locator chaining
        mock_page.locator = MagicMock()
        mock_locator_instance = AsyncMock()
        mock_page.locator.return_value = mock_locator_instance

        # Return file inputs
        mock_locator_instance.count = AsyncMock(side_effect=[0, 2, 2, 2, 2, 2, 2])
        mock_locator_instance.first = mock_attach_btn
        mock_locator_instance.last = mock_file_input
        mock_locator_instance.nth = MagicMock(return_value=mock_file_input)
        mock_file_input.get_attribute = AsyncMock(return_value="*")
        mock_attach_btn.is_visible = AsyncMock(return_value=True)
        mock_file_input.set_input_files = AsyncMock(return_value=None)
        mock_preview_dialog.is_visible = AsyncMock(return_value=True)
        mock_caption_box.is_visible = AsyncMock(return_value=True)
        mock_send_btn.is_visible = AsyncMock(return_value=True)

        adapter = WhatsAppAdapter(mock_browser)

        # Mock the internal locator helpers to test the protocol sequence cleanly
        adapter._mount_attachment_menu = AsyncMock()
        adapter._locate_file_input = AsyncMock(return_value=mock_file_input)
        adapter._wait_for_preview = AsyncMock(return_value=True)
        adapter._inject_caption = AsyncMock(return_value=True)
        adapter._dispatch_preview_send = AsyncMock(return_value=True)
        adapter._wait_for_preview_dismissal = AsyncMock(return_value=True)
        adapter.verify_message_sent = AsyncMock(return_value=True)

        success = await adapter.send_media(
            chat_name="Contact Max",
            file_path=temp_pdf_path,
            media_type="document",
            caption="Here is the timetable",
        )

        assert success is True
        from pathlib import Path
        adapter._mount_attachment_menu.assert_awaited_once()
        adapter._locate_file_input.assert_awaited_once()
        mock_file_input.set_input_files.assert_awaited_once_with(str(Path(temp_pdf_path).resolve()))
        adapter._wait_for_preview.assert_awaited_once()
        adapter._inject_caption.assert_awaited_once_with(mock_page, "Here is the timetable")
        adapter._dispatch_preview_send.assert_awaited_once()
        adapter.verify_message_sent.assert_awaited_once()

    finally:
        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)


# ── 6. End-to-End Context Enrichment & Termination Wrapping ──────────────────

@pytest.mark.asyncio
async def test_context_includes_structured_memories_and_ending(storage):
    """Verify build_context injects structured facts and ending directives into the prompt."""
    knowledge = PersonalKnowledgeEngine(storage)
    sm = ConversationStateMachine(storage)
    context_mgr = ConversationContext(storage)

    # 1. Seed active knowledge for Monish
    msg_fact = WhatsAppMessage(
        id="fact_01",
        chat_id="c_max",
        chat_name="Contact Max",
        sender_id="s_max",
        sender_name="Max",
        timestamp=time.time() - 100,
        text="I live in Bangalore now.",
    )
    knowledge.extract_and_update_knowledge(msg_fact)

    # 2. Incoming message is a farewell
    farewell_msg = WhatsAppMessage(
        id="msg_farewell",
        chat_id="c_max",
        chat_name="Contact Max",
        sender_id="s_max",
        sender_name="Max",
        timestamp=time.time(),
        text="ok bye da, will talk later",
    )
    sm.on_incoming_message("Contact Max", "Max", farewell_msg.text)

    chat_cfg = ChatConfig(chat_name="Contact Max", mode=ChatMode.AUTO)
    ctx = context_mgr.build_context(farewell_msg, chat_cfg)

    assert "person_memories" in ctx
    assert len(ctx["person_memories"]) > 0
    assert any("Bangalore" in m["fact"] for m in ctx["person_memories"])

    assert "conversation_state" in ctx
    assert ctx["conversation_state"]["state"] in ("ENDING", "ending")

    # Build prompt and verify facts and ending instructions are included
    prompt = context_mgr.build_prompt_from_ctx(farewell_msg, chat_cfg, None, ctx)
    assert "Bangalore" in prompt
    assert "CONVERSATION STATE: ENDING" in prompt
    assert "HALLUCINATION PREVENTION" in prompt or "ANTI-HALLUCINATION" in prompt


@pytest.mark.asyncio
async def test_router_farewell_clean_wrapup(storage):
    """Verify router automatically wraps up when an ending message arrives."""
    mock_browser = MagicMock()
    mock_browser.is_connected = True
    config = WhatsAppConfig()

    sender = WhatsAppSender(browser=mock_browser, storage=storage, config=config)
    sender.send_message = AsyncMock(return_value=True)

    policy = ChatPolicyEngine(storage=storage, config=config)
    context_mgr = ConversationContext(storage=storage)
    persona = PersonaEngine(storage=storage)
    training = MagicMock()
    safety = MagicMock()
    safety.evaluate_message.return_value = (MagicMock(value="high"), "safe")
    safety.evaluate_response.return_value = (MagicMock(value="high"), "safe")
    safety.should_escalate.return_value = False
    approval_queue = MagicMock()

    # Configure Monish in AUTO mode
    storage.save_chat_config(ChatConfig(chat_name="Contact Max", mode=ChatMode.AUTO, enabled=True))

    router = WhatsAppMessageRouter(
        policy=policy,
        sender=sender,
        storage=storage,
        config=config,
        context=context_mgr,
        persona=persona,
        training=training,
        safety=safety,
        approval_queue=approval_queue,
        generate_reply_fn=AsyncMock(return_value="bye da take care!"),
    )

    incoming_farewell = WhatsAppMessage(
        id="fw_001",
        chat_id="c_max",
        chat_name="Contact Max",
        sender_id="s_max",
        sender_name="Max",
        timestamp=time.time(),
        text="see you later bro, bye",
    )

    await router.route_message(incoming_farewell)

    # Verify reply was sent
    sender.send_message.assert_awaited_once()
    sent_text = sender.send_message.await_args.kwargs["text"]
    assert any(w in sent_text.lower() for w in ["bye", "take care", "see you", "later"])

    # Verify conversation state transitioned to ENDED
    state = router.state_machine.get_state("Contact Max")
    assert state.state == ConversationState.ENDED.value
    assert router.state_machine.should_suppress_replies("Contact Max") is True
