"""
Tests for ultra-low latency, autonomous WhatsApp agent modifications.
Verifies:
1. Zero typing delays by default in WhatsAppSender
2. Rapid back-and-forth auto-replies (elimination of 15s debounce)
3. Target contact automatic seeding (MIT Gova and MIT Sundaramoorthy)
4. Contact alias and flexible matching in policy engine
5. Contiguous message sequence aggregation in listener
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.integrations.whatsapp.config import WhatsAppConfig
from src.integrations.whatsapp.listener import _chat_matches, WhatsAppEventListener
from src.integrations.whatsapp.models import ChatConfig, ChatMode, Confidence, WhatsAppMessage
from src.integrations.whatsapp.policy import ChatPolicyEngine
from src.integrations.whatsapp.safety import SafetyGate
from src.integrations.whatsapp.sender import WhatsAppSender
from src.integrations.whatsapp.service import WhatsAppService


def test_zero_typing_delay_defaults():
    config = WhatsAppConfig()
    assert config.typing_delay_short_min == 0.0
    assert config.typing_delay_short_max == 0.0
    assert config.typing_delay_medium_min == 0.0
    assert config.typing_delay_medium_max == 0.0
    assert config.typing_delay_long_min == 0.0
    assert config.typing_delay_long_max == 0.0


@pytest.mark.asyncio
async def test_sender_does_not_sleep_when_typing_delay_is_false():
    browser = MagicMock()
    browser.is_connected = True
    browser.navigate_to_chat = AsyncMock(return_value=True)
    browser.type_and_send = AsyncMock(return_value=True)
    storage = MagicMock()
    storage.check_rate_limit = MagicMock(return_value=True)
    config = WhatsAppConfig()

    sender = WhatsAppSender(browser=browser, storage=storage, config=config)

    start = time.time()
    success = await sender.send_message("MIT Gova", "Hey da, finished the sheet!", typing_delay=False)
    duration = time.time() - start

    assert success is True
    # Verify call executed immediately without artificial 1-2s delay
    assert duration < 0.2


@pytest.mark.asyncio
async def test_rapid_back_and_forth_not_debounced(tmp_path):
    """Verify that multiple consecutive messages within 2 seconds are NOT dropped by a 15s debounce."""
    service = WhatsAppService(
        config=WhatsAppConfig(profile_dir=str(tmp_path / "wa-profile")),
        db_path=str(tmp_path / "wa.db"),
    )
    service.save_chat_config(ChatConfig(chat_name="MIT Gova", mode=ChatMode.AUTO))

    sent_messages = []

    async def generate(_: str, **kwargs) -> str:
        return f"Reply #{len(sent_messages) + 1}"

    async def fake_send(*args, **kwargs):
        sent_messages.append(kwargs.get("text"))
        return True

    service.set_reply_generator(generate)
    service._sender.send_message = fake_send

    msg1 = WhatsAppMessage(
        id="m1", raw_reference="m1", chat_id="c_gova", chat_name="MIT Gova",
        sender_id="gova", sender_name="MIT Gova", timestamp=time.time(), text="dei machan",
    )
    await service._on_incoming_message(msg1)

    # Immediate second message (100ms later)
    await asyncio.sleep(0.1)
    msg2 = WhatsAppMessage(
        id="m2", raw_reference="m2", chat_id="c_gova", chat_name="MIT Gova",
        sender_id="gova", sender_name="MIT Gova", timestamp=time.time(), text="did you finish EG?",
    )
    await service._on_incoming_message(msg2)

    assert len(sent_messages) == 2
    assert sent_messages[0] == "Reply #1"
    assert sent_messages[1] == "Reply #2"


def test_target_contacts_auto_seeded(tmp_path):
    """Verify that priority peers are automatically seeded in AUTO mode."""
    service = WhatsAppService(
        config=WhatsAppConfig(profile_dir=str(tmp_path / "wa-profile")),
        db_path=str(tmp_path / "wa.db"),
    )
    expected_peers = [
        "Contact Alex",
        "Contact Alexander",
        "Contact Charlie",
        "Contact Dave",
        "Contact Eve",
        "Contact Frank",
        "Contact Grace",
        "Contact Henry",
        "Contact Ian",
        "Contact Jack",
        "Contact Kevin",
        "Contact Leo",
        "Contact Max",
        "Contact Nathan",
        "User (Self)",
    ]
    for peer in expected_peers:
        cfg = service._policy.get_chat_config(peer)
        assert cfg is not None, f"Expected {peer} to be seeded"
        assert cfg.mode == ChatMode.AUTO
        assert cfg.enabled is True
        assert cfg.memory_enabled is True
        assert cfg.context_window >= 30


def test_flexible_chat_alias_matching(tmp_path):
    """Verify policy and listener match chat aliases for all contacts."""
    assert _chat_matches("Contact Alex", "Alex") is True
    assert _chat_matches("Contact Alexander", "Alexander") is True
    assert _chat_matches("Contact Charlie", "Charlie") is True
    assert _chat_matches("Contact Dave", "Dave") is True
    assert _chat_matches("Contact Eve", "Eve") is True
    assert _chat_matches("Contact Frank", "Frank") is True
    assert _chat_matches("Contact Grace", "Grace") is True
    assert _chat_matches("Contact Henry", "Henry") is True
    assert _chat_matches("Contact Ian", "Ian") is True
    assert _chat_matches("Contact Jack", "Jack") is True
    assert _chat_matches("Contact Kevin", "Kevin") is True

    service = WhatsAppService(
        config=WhatsAppConfig(profile_dir=str(tmp_path / "wa-profile")),
        db_path=str(tmp_path / "wa.db"),
    )
    # Looking up aliases resolves their auto configs
    assert service._policy.get_chat_config("Alex") is not None
    assert service._policy.get_chat_config("Alexander") is not None
    assert service._policy.get_chat_config("Charlie") is not None
    assert service._policy.get_chat_config("Dave") is not None
    assert service._policy.get_chat_config("Eve") is not None
    assert service._policy.get_chat_config("Frank") is not None
    assert service._policy.get_chat_config("Grace") is not None
    assert service._policy.get_chat_config("Henry") is not None
    assert service._policy.get_chat_config("Ian") is not None


def test_safety_gate_does_not_escalate_routine_peer_questions():
    gate = SafetyGate()
    msg = WhatsAppMessage(
        id="q1", chat_id="c1", chat_name="Contact Alex", sender_id="s1", sender_name="Contact Alex",
        timestamp=time.time(), text="where are you da?",
    )
    conf, reason = gate.evaluate_message(msg)
    resp_conf, resp_reason = gate.evaluate_response("in room da, studying", msg)

    assert gate.should_escalate(conf, resp_conf) is False


@pytest.mark.asyncio
async def test_listener_target_peer_not_flagged_as_group(tmp_path):
    """Verify that messages from all priority peers are never treated as group messages."""
    browser = MagicMock()
    storage = MagicMock()
    storage.is_message_replied = MagicMock(return_value=False)
    storage.is_own_message = MagicMock(return_value=False)

    listener = WhatsAppEventListener(browser=browser, storage=storage)

    test_peers = [
        ("Contact Alex", "Where are you"),
        ("Contact Alexander", "lab code available?"),
        ("Contact Charlie", "sheet completed?"),
        ("Contact Dave", "are you at desk?"),
        ("Contact Grace", "assessment schedule?"),
        ("Contact Henry", "doubt in architecture"),
        ("Contact Ian", "coffee break?"),
        ("Contact Jack", "meeting ready?"),
    ]

    for peer_name, sample_text in test_peers:
        received = []
        listener._callbacks = [lambda m: received.append(m)]
        msg_data = {
            "sender": peer_name,
            "text": sample_text,
            "timestamp": "10:20 pm",
            "message_id": f"msg_{peer_name[:4]}",
        }
        await listener._process_incoming_message(peer_name, msg_data)

        assert len(received) == 1, f"Failed for {peer_name}"
        assert received[0].text == sample_text
        assert received[0].is_group is False
        assert received[0].chat_name == peer_name


def test_language_policy_in_context_prompt():
    from src.integrations.whatsapp.context import ConversationContext, detect_preferred_language
    storage = MagicMock()
    storage.get_recent_messages = MagicMock(return_value=[])
    storage.get_conversation_summary = MagicMock(return_value=None)
    storage.get_conversation_memory = MagicMock(return_value=None)
    storage.get_chat_history_stats = MagicMock(return_value={})

    # Test language detection helper
    assert detect_preferred_language("Are you coming to library?") == "english"
    assert detect_preferred_language("Where are you heading bro?") == "english"
    assert detect_preferred_language("Did you finish the EG sheet?") == "english"
    assert detect_preferred_language("machi enna panra") == "tanglish"
    assert detect_preferred_language("enga irukka da?") == "tanglish"
    assert detect_preferred_language("assignment mudinjutha?") == "tanglish"
    assert detect_preferred_language("எப்படி இருக்க?") == "tamil"
    assert detect_preferred_language("வணக்கம் டா") == "tamil"

    builder = ConversationContext(storage=storage)
    cfg = ChatConfig(chat_name="Contact Alex", mode=ChatMode.AUTO)

    # 1. English incoming message (Default)
    msg_en = WhatsAppMessage(
        id="m1", chat_id="c1", chat_name="Contact Alex", sender_id="s1", sender_name="Contact Alex",
        timestamp=time.time(), text="Are you coming to office?",
    )
    chat_msgs_en = builder.build_chat_messages(msg_en, cfg)
    assert len(chat_msgs_en) >= 2
    system_content_en = chat_msgs_en[0]["content"]
    assert "CONVERSE EXCLUSIVELY IN CASUAL, FLUENT ENGLISH" in system_content_en
    assert "MESSAGE REACTIONS (EMOJIS) WITH MEANING & CONTEXT" in system_content_en
    assert "GIFS & STICKERS (WITH MEANING AND CONTEXT ONLY)" in system_content_en

    prompt_en = builder.build_prompt(msg_en, cfg)
    assert "CONVERSE EXCLUSIVELY IN CASUAL ENGLISH" in prompt_en

    # 2. Tanglish incoming message - still instructs English reply
    msg_ta_latn = WhatsAppMessage(
        id="m2", chat_id="c1", chat_name="Contact Alex", sender_id="s1", sender_name="Contact Alex",
        timestamp=time.time(), text="machi enna panra da",
    )
    chat_msgs_ta_latn = builder.build_chat_messages(msg_ta_latn, cfg)
    assert "CONVERSE EXCLUSIVELY IN CASUAL, FLUENT ENGLISH" in chat_msgs_ta_latn[0]["content"]
    prompt_ta_latn = builder.build_prompt(msg_ta_latn, cfg)
    assert "CONVERSE EXCLUSIVELY IN CASUAL ENGLISH" in prompt_ta_latn

    # 3. Tamil incoming message - still instructs English reply
    msg_ta_script = WhatsAppMessage(
        id="m3", chat_id="c1", chat_name="Contact Alex", sender_id="s1", sender_name="Contact Alex",
        timestamp=time.time(), text="எப்படி இருக்க மச்சான்?",
    )
    chat_msgs_ta_script = builder.build_chat_messages(msg_ta_script, cfg)
    assert "CONVERSE EXCLUSIVELY IN CASUAL, FLUENT ENGLISH" in chat_msgs_ta_script[0]["content"]
    prompt_ta_script = builder.build_prompt(msg_ta_script, cfg)
    assert "CONVERSE EXCLUSIVELY IN CASUAL ENGLISH" in prompt_ta_script


@pytest.mark.asyncio
async def test_reaction_gif_and_sticker_parsing_and_routing():
    from src.integrations.whatsapp.router import WhatsAppMessageRouter as MessageRouter

    policy = MagicMock()
    policy.should_process_message = MagicMock(return_value=True)
    policy.get_chat_config = MagicMock(return_value=ChatConfig(chat_name="Contact Alex", mode=ChatMode.AUTO))

    storage = MagicMock()
    storage.is_message_replied = MagicMock(return_value=False)
    storage.save_audit_entry = MagicMock()
    storage.mark_message_replied = MagicMock()

    safety = MagicMock()
    safety.evaluate_message = MagicMock(return_value=(Confidence.HIGH, "safe"))
    safety.evaluate_response = MagicMock(return_value=(Confidence.HIGH, "safe"))
    safety.should_escalate = MagicMock(return_value=False)

    sender = MagicMock()
    sender.send_message = AsyncMock(return_value=True)
    sender.react_to_message = AsyncMock(return_value=True)
    sender.send_gif = AsyncMock(return_value=True)
    sender.send_sticker = AsyncMock(return_value=True)

    approval_queue = MagicMock()
    context = MagicMock()
    context.build_prompt = MagicMock(return_value="prompt")
    context.build_chat_messages = MagicMock(return_value=[{"role": "user", "content": "hi"}])

    router = MessageRouter(
        policy=policy,
        sender=sender,
        storage=storage,
        config=WhatsAppConfig(),
        context=context,
        persona=MagicMock(),
        training=MagicMock(),
        safety=safety,
        approval_queue=approval_queue,
    )

    # 1. Test [REACT: 😂] parsing and routing
    router._generate_reply = AsyncMock(return_value="[REACT: 😂] haha that was hilarious bro!")
    msg = WhatsAppMessage(
        id="m_react", chat_id="c1", chat_name="Contact Alex", sender_id="s1", sender_name="Contact Alex",
        timestamp=time.time(), text="roast",
    )
    await router.route_message(msg)
    await asyncio.sleep(0.05)
    sender.react_to_message.assert_awaited_with("Contact Alex", "😂")
    sender.send_message.assert_awaited_with(chat_name="Contact Alex", text="haha that was hilarious bro!", chat_id="c1")

    # 2. Test [GIF: celebration] parsing and routing
    sender.send_message.reset_mock()
    router._generate_reply = AsyncMock(return_value="[GIF: celebration] we finished the exams bro!")
    msg_gif = WhatsAppMessage(
        id="m_gif", chat_id="c1", chat_name="Contact Alex", sender_id="s1", sender_name="Contact Alex",
        timestamp=time.time(), text="exams over",
    )
    await router.route_message(msg_gif)
    await asyncio.sleep(0.05)
    sender.send_gif.assert_awaited_with("Contact Alex", "celebration")
    sender.send_message.assert_awaited_with(chat_name="Contact Alex", text="we finished the exams bro!", chat_id="c1")

    # 3. Test [STICKER] parsing and routing
    sender.send_message.reset_mock()
    router._generate_reply = AsyncMock(return_value="[STICKER] chill bro")
    msg_stk = WhatsAppMessage(
        id="m_stk", chat_id="c1", chat_name="Contact Alex", sender_id="s1", sender_name="Contact Alex",
        timestamp=time.time(), text="sticker me",
    )
    await router.route_message(msg_stk)
    await asyncio.sleep(0.05)
    sender.send_sticker.assert_awaited_with("Contact Alex", "")
    sender.send_message.assert_awaited_with(chat_name="Contact Alex", text="chill bro", chat_id="c1")


def test_david_julius_authentic_profile():
    from src.integrations.whatsapp.context import ConversationContext
    storage = MagicMock()
    storage.get_recent_messages = MagicMock(return_value=[])
    storage.get_conversation_summary = MagicMock(return_value=None)
    storage.get_conversation_memory = MagicMock(return_value=None)
    storage.get_chat_history_stats = MagicMock(return_value={})

    builder = ConversationContext(storage=storage)
    msg = WhatsAppMessage(
        id="m1", chat_id="c1", chat_name="Contact Alex", sender_id="s1", sender_name="Contact Alex",
        timestamp=time.time(), text="Who are you?",
    )
    cfg = ChatConfig(chat_name="Contact Alex", mode=ChatMode.AUTO)
    chat_msgs = builder.build_chat_messages(msg, cfg)
    sys_content = chat_msgs[0]["content"]

    assert "Julius WhatsApp Assistant" in sys_content
    assert "Julius" in sys_content
    assert "ESCALATE_TO_DAVID" not in sys_content


def test_is_self_chat():
    from src.integrations.whatsapp.config import is_self_chat
    assert is_self_chat("User (YOU)") is True
    assert is_self_chat("User (You)") is True
    assert is_self_chat("User(YOU)") is True
    assert is_self_chat("User") is True
    assert is_self_chat("You") is True
    assert is_self_chat("Message yourself") is True
    assert is_self_chat("My Note (You)") is True
    assert is_self_chat("Contact Alex") is False
    assert is_self_chat("Contact Alexander") is False


def test_storage_pending_inquiries(tmp_path):
    import sqlite3
    from src.integrations.whatsapp.storage import WhatsAppStorage
    db_file = str(tmp_path / "test_inq.db")
    storage = WhatsAppStorage(db_path=db_file)

    inq_id = storage.add_pending_inquiry(
        friend_chat_name="Contact Alex",
        friend_sender_name="Contact Alex",
        question="Did you book the train ticket for Friday?",
    )
    assert inq_id is not None

    pending = storage.get_latest_pending_inquiry()
    assert pending is not None
    assert pending["id"] == inq_id
    assert pending["friend_chat_name"] == "Contact Alex"
    assert "train ticket" in pending["question"]
    assert pending["status"] == "pending"

    storage.resolve_pending_inquiry(inq_id, "Yes, booked train ticket in S3 coach.")
    resolved = storage.get_latest_pending_inquiry()
    assert resolved is None  # no more pending inquiries

    inquiries = storage.get_pending_inquiries(limit=5)
    assert len(inquiries) == 1
    assert inquiries[0]["status"] == "answered"
    assert "S3 coach" in inquiries[0]["answer"]


@pytest.mark.asyncio
async def test_router_escalation_and_self_chat_resolution(tmp_path):
    from src.integrations.whatsapp.router import WhatsAppMessageRouter
    from src.integrations.whatsapp.config import WhatsAppConfig, DAVID_SELF_CHAT_NAME
    from src.integrations.whatsapp.storage import WhatsAppStorage
    from src.integrations.whatsapp.models import WhatsAppMessage, ChatConfig, ChatMode

    storage = WhatsAppStorage(db_path=str(tmp_path / "test_router_esc.db"))
    policy = MagicMock()
    policy.should_process = MagicMock(return_value=True)
    policy.get_chat_config = MagicMock(return_value=ChatConfig(chat_name="Contact Alex", mode=ChatMode.AUTO))
    sender = MagicMock()
    sender.send_message = AsyncMock(return_value=True)
    context = MagicMock()
    persona = MagicMock()
    training = MagicMock()
    safety = MagicMock()
    safety.evaluate_message = MagicMock(return_value=(Confidence.HIGH, "ok"))
    safety.evaluate_response = MagicMock(return_value=(Confidence.HIGH, "ok"))
    safety.should_escalate = MagicMock(return_value=False)
    queue = MagicMock()

    # Reply with legacy ESCALATE_TO_DAVID token
    llm_mock = AsyncMock(return_value="[ESCALATE_TO_DAVID: asking about Friday trip] wait da, let me check and tell you in a bit")

    router = WhatsAppMessageRouter(
        policy=policy,
        sender=sender,
        storage=storage,
        config=WhatsAppConfig(),
        context=context,
        persona=persona,
        training=training,
        safety=safety,
        approval_queue=queue,
        generate_reply_fn=llm_mock,
    )

    # 1. Incoming message from contact
    msg_from_friend = WhatsAppMessage(
        id="f1", chat_id="alex", chat_name="Contact Alex",
        sender_id="alex_s", sender_name="Contact Alex",
        timestamp=time.time(), text="Alex, are you joining the trip on Friday?",
    )
    await router.route_message(msg_from_friend)

    # Verify: token stripped, holding reply sent to contact ONLY (no alert sent to user)
    assert sender.send_message.call_count == 1
    call_friend = sender.send_message.call_args_list[0]
    assert call_friend.kwargs["chat_name"] == "Contact Alex"
    assert "wait da" in call_friend.kwargs["text"]
    assert "[ESCALATE_TO_DAVID" not in call_friend.kwargs["text"]

    # 2. User texts in self-chat — receives acknowledgment without cross-chat forwarding
    sender.send_message.reset_mock()
    msg_from_david = WhatsAppMessage(
        id="d1", chat_id="self", chat_name="User (Self)",
        sender_id="me", sender_name="User",
        timestamp=time.time(), text="yes da, I am coming on Friday trip",
    )
    await router.route_message(msg_from_david)

    assert sender.send_message.call_count == 1
    call_self = sender.send_message.call_args_list[0]
    assert call_self.kwargs["chat_name"] == "User (Self)"
    assert "Noted" in call_self.kwargs["text"]


@pytest.mark.asyncio
async def test_concurrent_multi_chat_processing(tmp_path):
    """
    Verify that when two contacts text simultaneously (e.g. Contact Alex and Contact Kevin),
    both are processed and replied to concurrently in parallel without blocking each other.
    """
    service = WhatsAppService(
        config=WhatsAppConfig(profile_dir=str(tmp_path / "wa-profile")),
        db_path=str(tmp_path / "wa.db"),
    )
    service.save_chat_config(ChatConfig(chat_name="Contact Alex", mode=ChatMode.AUTO))
    service.save_chat_config(ChatConfig(chat_name="Contact Kevin", mode=ChatMode.AUTO))

    sent_replies = {}
    active_concurrent_count = 0
    max_concurrent_seen = 0

    async def concurrent_generate(prompt: str, **kwargs) -> str:
        nonlocal active_concurrent_count, max_concurrent_seen
        active_concurrent_count += 1
        max_concurrent_seen = max(max_concurrent_seen, active_concurrent_count)
        # Simulate slight LLM inference time
        await asyncio.sleep(0.05)
        active_concurrent_count -= 1
        if "Contact Kevin" in prompt:
            return "Hello Kevin, what's up da?"
        return "Hey Alex, coming to library now"

    async def fake_send(chat_name: str, text: str, **kwargs):
        sent_replies[chat_name] = text
        return True

    service.set_reply_generator(concurrent_generate)
    service._sender.send_message = fake_send

    msg_alex = WhatsAppMessage(
        id="m_alex_1", raw_reference="m_alex_1", chat_id="c_alex", chat_name="Contact Alex",
        sender_id="alex", sender_name="Contact Alex", timestamp=time.time(), text="Where are you da?",
    )
    msg_kevin = WhatsAppMessage(
        id="m_kevin_1", raw_reference="m_kevin_1", chat_id="c_kevin", chat_name="Contact Kevin",
        sender_id="kevin", sender_name="Contact Kevin", timestamp=time.time(), text="Hello user",
    )

    # Launch both routes simultaneously
    await asyncio.gather(
        service._on_incoming_message(msg_alex),
        service._on_incoming_message(msg_kevin),
    )

    # Verify both received distinct, correct replies
    assert "Contact Alex" in sent_replies
    assert sent_replies["Contact Alex"] == "Hey Alex, coming to library now"
    assert "Contact Kevin" in sent_replies
    assert sent_replies["Contact Kevin"] == "Hello Kevin, what's up da?"

    # Verify both executed concurrently in parallel (overlap occurred)
    assert max_concurrent_seen == 2


@pytest.mark.asyncio
async def test_internal_bridge_multi_chat_scan(tmp_path):
    """
    Verify that WhatsAppEventListener._listen_loop detects multiple unreplied chats
    from browser.get_active_unreplied_chats in one cycle and dispatches them in parallel.
    """
    browser = MagicMock()
    browser.is_connected = True
    browser.get_active_unreplied_chats = AsyncMock(return_value=[
        {
            "chat_id": "c_alex@c.us",
            "chat_name": "Contact Alex",
            "is_group": False,
            "last_message": {"id": "m1", "sender": "Contact Alex", "text": "hey", "timestamp": time.time(), "media_type": "text"},
            "recent_messages": [{"id": "m1", "sender": "Contact Alex", "text": "hey", "timestamp": time.time(), "is_from_me": False, "media_type": "text"}],
        },
        {
            "chat_id": "c_kevin@c.us",
            "chat_name": "Contact Kevin",
            "is_group": False,
            "last_message": {"id": "m2", "sender": "Contact Kevin", "text": "Hello user", "timestamp": time.time(), "media_type": "text"},
            "recent_messages": [{"id": "m2", "sender": "Contact Kevin", "text": "Hello user", "timestamp": time.time(), "is_from_me": False, "media_type": "text"}],
        },
    ])
    browser.get_current_chat_name = AsyncMock(return_value=None)
    browser.get_unread_tab_count = AsyncMock(return_value=0)

    from src.integrations.whatsapp.storage import WhatsAppStorage
    storage = WhatsAppStorage(db_path=str(tmp_path / "listener_test.db"))
    listener = WhatsAppEventListener(browser=browser, storage=storage, poll_interval=0.01)

    dispatched_messages = []
    listener.subscribe(lambda msg: dispatched_messages.append(msg))

    # Run listener for 1 iteration
    listener._running = True
    task = asyncio.create_task(listener._listen_loop())
    await asyncio.sleep(0.08)
    await listener.stop()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(dispatched_messages) == 2
    chat_names = {m.chat_name for m in dispatched_messages}
    assert "Contact Alex" in chat_names
    assert "Contact Kevin" in chat_names





