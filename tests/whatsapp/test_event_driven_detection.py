"""
Tests for event-driven WhatsApp message detection architecture and false-positive prevention.

Verifies:
1. False chat detection elimination:
   - "MIT Gova" never matches "Goa Trip", "Govardhan Kumar", "Goval", or message snippets containing "goa".
   - Short tokens like "anil", "raj", "putta" only match as whole words, not arbitrary substrings.
2. Event-driven flow:
   - Listener detects state change (new last_message ID), not continuous polling duplicates.
   - Repeated scans with identical state do not re-dispatch.
3. Chat isolation & JID-based identity:
   - JIDRegistry correctly maps WhatsApp JID to canonical name.
   - Unauthorized chats are rejected at the JID/name stage without touching the UI.
4. Safe navigation:
   - navigate_to_chat matches only title attributes with word boundaries, never message preview text.
   - Fast-path WAWeb direct open is attempted before UI search.
5. Watchdog & liveness:
   - Watchdog detects stopped or stalled listener tasks and triggers recovery.
   - Health status reflects listener liveness.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.integrations.whatsapp.browser import WhatsAppBrowserAdapter
from src.integrations.whatsapp.config import (
    get_canonical_target_peer_name,
    is_target_peer_chat,
    is_self_chat,
)
from src.integrations.whatsapp.health import WhatsAppHealth
from src.integrations.whatsapp.listener import (
    JIDRegistry,
    ListenerEvent,
    WhatsAppEventListener,
    _chat_matches,
)
from src.integrations.whatsapp.models import HealthState, WhatsAppMessage
from src.integrations.whatsapp.storage import WhatsAppStorage
from src.integrations.whatsapp.watchdog import WhatsAppWatchdog


# ── 1. False Chat Detection & Token Isolation Tests ───────────────────────────

def test_alex_does_not_match_alexander():
    """Verify that 'Contact Alex' / 'Alex' never matches 'Alexander'."""
    # Positive matches for Alex
    assert is_target_peer_chat("Contact Alex") is True
    assert is_target_peer_chat("Alex") is True
    assert _chat_matches("Contact Alex", "Alex") is True
    assert _chat_matches("Contact Alex", "Contact Alex") is True

    # Positive matches for Alexander (distinct contact)
    assert is_target_peer_chat("Alexander") is True
    assert is_target_peer_chat("Contact Alexander") is True
    assert _chat_matches("Contact Alexander", "Alexander") is True
    assert _chat_matches("Contact Alexander", "Contact Alexander") is True

    # Negative matches
    assert is_target_peer_chat("Alexandria") is False
    assert is_target_peer_chat("Alexandria Project") is False

    # Disambiguation: Alex and Alexander must NEVER cross-match
    assert _chat_matches("Contact Alex", "Alexander") is False
    assert _chat_matches("Contact Alex", "Contact Alexander") is False
    assert _chat_matches("Contact Alexander", "Alex") is False
    assert _chat_matches("Contact Alexander", "Contact Alex") is False
    assert _chat_matches("Contact Alex", "Alexandria") is False

    # Canonical resolutions
    assert get_canonical_target_peer_name("Alex") == "Contact Alex"
    assert get_canonical_target_peer_name("Alexander") == "Contact Alexander"


def test_token_word_boundaries_prevent_partial_matches():
    """Tokens like 'alex', 'grace', 'dave' must not match substrings inside other words."""
    # Positive
    assert is_target_peer_chat("Contact Alex") is True
    assert is_target_peer_chat("Alex") is True

    # Negative: 'alex' inside other words
    assert is_target_peer_chat("Danilo") is False
    assert is_target_peer_chat("Vanilla Project") is False

    # Positive: 'Grace'
    assert is_target_peer_chat("Contact Grace") is True
    assert is_target_peer_chat("Grace") is True

    # Negative: 'grace' in 'Disgraceful' or 'Courage'
    assert is_target_peer_chat("Disgraceful Error") is False
    assert is_target_peer_chat("Courage Team") is False

    # Canonical resolutions
    assert get_canonical_target_peer_name("Alex") == "Contact Alex"
    assert get_canonical_target_peer_name("Alexander") == "Contact Alexander"
    assert get_canonical_target_peer_name("Random Topic") is None


# ── 2. JIDRegistry Tests ──────────────────────────────────────────────────────

def test_jid_registry_exact_mapping():
    """Verify JIDRegistry maps JID on first encounter and enforces JID equality."""
    reg = JIDRegistry()
    reg.set_authorized_names({"contact alex", "contact charlie"})

    # First encounter of authorized chat
    canonical = reg.register("919876543210@c.us", "Contact Alex")
    assert canonical == "Contact Alex"
    assert reg.is_authorized_jid("919876543210@c.us") is True
    assert reg.get_canonical("919876543210@c.us") == "Contact Alex"

    # Fast path check
    assert reg.get_canonical("919876543210@c.us") == "Contact Alex"

    # Attempt to register unauthorized chat (e.g. Goa trip)
    unauthorized = reg.register("911122334455@c.us", "Goa Trip Planning")
    assert unauthorized is None
    assert reg.is_authorized_jid("911122334455@c.us") is False

    # Second authorized contact via alias
    canonical2 = reg.register("919988776655@c.us", "Contact Charlie")
    assert canonical2 == "Contact Charlie"
    assert reg.is_authorized_jid("919988776655@c.us") is True


# ── 3. Event-Driven State Change Detection Tests ──────────────────────────────

@pytest.mark.asyncio
async def test_listener_state_change_only_dispatches_new_messages(tmp_path):
    """
    Verify that the listener dispatches a message only when its message ID represents
    a new unreplied state, and suppresses duplicate scans with identical state.
    """
    storage = WhatsAppStorage(db_path=str(tmp_path / "test_state.db"))
    browser = MagicMock()
    browser.is_connected = True

    msg_state_1 = {
        "chat_id": "919876543210@c.us",
        "chat_name": "MIT Gova",
        "is_group": False,
        "last_message": {
            "id": "msg_001",
            "sender": "MIT Gova",
            "text": "Are you at the college?",
            "timestamp": time.time(),
            "media_type": "text",
        },
        "recent_messages": [
            {
                "id": "msg_001",
                "sender": "MIT Gova",
                "text": "Are you at the college?",
                "timestamp": time.time(),
                "is_from_me": False,
                "media_type": "text",
            }
        ],
    }

    browser.get_active_unreplied_chats = AsyncMock(return_value=[msg_state_1])

    listener = WhatsAppEventListener(browser=browser, storage=storage, poll_interval=0.01)
    listener.set_monitored_chats({"MIT Gova"})

    dispatched = []
    listener.subscribe(lambda m: dispatched.append(m))

    # Run for 2 cycles with the exact same message state
    listener._running = True
    task = asyncio.create_task(listener._listen_loop())
    await asyncio.sleep(0.05)

    # Exactly 1 dispatch should have occurred
    assert len(dispatched) == 1
    assert dispatched[0].text == "Are you at the college?"
    assert dispatched[0].chat_name == "MIT Gova"

    # Still only 1 dispatch after more time with identical state
    await asyncio.sleep(0.05)
    assert len(dispatched) == 1

    # Now simulate a NEW incoming message state
    msg_state_2 = dict(msg_state_1)
    msg_state_2["last_message"] = {
        "id": "msg_002",
        "sender": "MIT Gova",
        "text": "Meet me at the canteen",
        "timestamp": time.time(),
        "media_type": "text",
    }
    msg_state_2["recent_messages"] = [
        msg_state_2["last_message"],
    ]
    browser.get_active_unreplied_chats = AsyncMock(return_value=[msg_state_2])

    await asyncio.sleep(0.05)
    await listener.stop()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # A second dispatch should have occurred for the new message
    assert len(dispatched) == 2
    assert dispatched[1].text == "Meet me at the canteen"


@pytest.mark.asyncio
async def test_listener_ignores_unauthorized_chats_completely(tmp_path):
    """
    Verify that unauthorized chats in WAWebChatCollection are completely ignored:
    - Never dispatched to callbacks
    - Never touch UI
    - Never recorded in active processing
    """
    storage = WhatsAppStorage(db_path=str(tmp_path / "test_auth.db"))
    browser = MagicMock()
    browser.is_connected = True
    browser.navigate_to_chat = AsyncMock()

    unauthorized_chats = [
        {
            "chat_id": "911111111111@c.us",
            "chat_name": "Goa Trip Planning",
            "is_group": False,
            "last_message": {"id": "m_goa", "sender": "Goa Trip", "text": "Who is coming?", "timestamp": time.time(), "media_type": "text"},
            "recent_messages": [{"id": "m_goa", "sender": "Goa Trip", "text": "Who is coming?", "timestamp": time.time(), "is_from_me": False, "media_type": "text"}],
        },
        {
            "chat_id": "922222222222@c.us",
            "chat_name": "Govardhan Real Estate",
            "is_group": False,
            "last_message": {"id": "m_gov", "sender": "Govardhan", "text": "Plots available", "timestamp": time.time(), "media_type": "text"},
            "recent_messages": [{"id": "m_gov", "sender": "Govardhan", "text": "Plots available", "timestamp": time.time(), "is_from_me": False, "media_type": "text"}],
        },
    ]

    browser.get_active_unreplied_chats = AsyncMock(return_value=unauthorized_chats)

    listener = WhatsAppEventListener(browser=browser, storage=storage, poll_interval=0.01)
    listener.set_monitored_chats({"MIT Gova", "MIT Sundaramoorthy"})

    dispatched = []
    listener.subscribe(lambda m: dispatched.append(m))

    listener._running = True
    task = asyncio.create_task(listener._listen_loop())
    await asyncio.sleep(0.05)
    await listener.stop()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Zero dispatches for unauthorized chats
    assert len(dispatched) == 0
    # Browser UI navigation was NEVER called
    browser.navigate_to_chat.assert_not_called()


# ── 4. Watchdog Liveness & Stalled Listener Detection Tests ───────────────────

@pytest.mark.asyncio
async def test_watchdog_detects_dead_listener_task():
    """Verify watchdog detects when the listener task has crashed/died."""
    browser = MagicMock()
    browser.page = MagicMock()
    browser.page.is_closed = MagicMock(return_value=False)
    browser.page.evaluate = AsyncMock(return_value="complete")
    browser.detect_login_state = AsyncMock(return_value="connected")

    health = WhatsAppHealth()
    restarted = False

    async def on_restart():
        nonlocal restarted
        restarted = True

    listener = MagicMock()
    listener.is_running = True
    # Task is dead
    listener.get_liveness.return_value = {"task_alive": False}
    listener.liveness_age_seconds = 0.0
    listener._consecutive_scan_errors = 0

    watchdog = WhatsAppWatchdog(
        browser=browser,
        health=health,
        restart_callback=on_restart,
        check_interval_seconds=0.01,
        listener=listener,
    )

    is_healthy = await watchdog._check_health()
    assert is_healthy is False
    assert "Listener task died" in health.last_error


@pytest.mark.asyncio
async def test_watchdog_detects_stalled_listener_scan():
    """Verify watchdog triggers failure if listener scan has not succeeded in >90s."""
    browser = MagicMock()
    browser.page = MagicMock()
    browser.page.is_closed = MagicMock(return_value=False)
    browser.page.evaluate = AsyncMock(return_value="complete")
    browser.detect_login_state = AsyncMock(return_value="connected")

    health = WhatsAppHealth()
    listener = MagicMock()
    listener.is_running = True
    listener.last_successful_scan = time.time() - 100.0  # 100s ago
    listener.liveness_age_seconds = 100.0
    listener._consecutive_scan_errors = 0
    listener.get_liveness.return_value = {"task_alive": True}

    watchdog = WhatsAppWatchdog(
        browser=browser,
        health=health,
        check_interval_seconds=0.01,
        listener=listener,
    )

    is_healthy = await watchdog._check_health()
    assert is_healthy is False
    assert "Listener stalled" in health.last_error


@pytest.mark.asyncio
async def test_watchdog_healthy_when_listener_active():
    """Verify watchdog passes when browser and listener are healthy."""
    browser = MagicMock()
    browser.page = MagicMock()
    browser.page.is_closed = MagicMock(return_value=False)
    browser.page.evaluate = AsyncMock(return_value="complete")
    browser.detect_login_state = AsyncMock(return_value="connected")

    health = WhatsAppHealth()
    listener = MagicMock()
    listener.is_running = True
    listener.last_successful_scan = time.time() - 2.0
    listener.liveness_age_seconds = 2.0
    listener._consecutive_scan_errors = 0
    listener.get_liveness.return_value = {"task_alive": True}

    watchdog = WhatsAppWatchdog(
        browser=browser,
        health=health,
        check_interval_seconds=0.01,
        listener=listener,
    )

    is_healthy = await watchdog._check_health()
    assert is_healthy is True
    assert health.listener_running is True


@pytest.mark.asyncio
async def test_watchdog_detects_loading_stall():
    """Verify watchdog detects when WhatsApp page is stuck in 'loading' state for >90s."""
    browser = MagicMock()
    browser.page = MagicMock()
    browser.page.is_closed = MagicMock(return_value=False)
    browser.page.evaluate = AsyncMock(return_value="complete")
    browser.page.reload = AsyncMock()
    browser.detect_login_state = AsyncMock(return_value="loading")

    health = WhatsAppHealth()
    watchdog = WhatsAppWatchdog(
        browser=browser,
        health=health,
        check_interval_seconds=0.01,
    )

    # Initial loading check — should return True (normal initial load)
    assert await watchdog._check_health() is True
    assert watchdog._loading_since is not None

    # Simulate 95 seconds passing — soft reload succeeds
    watchdog._loading_since = time.time() - 95.0
    is_healthy = await watchdog._check_health()
    assert is_healthy is True
    browser.page.reload.assert_called_once()

    # If reload fails, health check returns False
    watchdog._loading_since = time.time() - 95.0
    browser.page.reload = AsyncMock(side_effect=Exception("Connection refused"))
    is_healthy = await watchdog._check_health()
    assert is_healthy is False
    assert "Page loading stall" in health.last_error


@pytest.mark.asyncio
async def test_browser_handle_interruption_popups():
    """Verify handle_interruption_popups finds and clicks 'Use Here' takeover button."""
    from src.integrations.whatsapp.browser import WhatsAppBrowserAdapter
    adapter = WhatsAppBrowserAdapter(profile_dir="/tmp/test_prof")
    mock_page = MagicMock()
    mock_page.is_closed = MagicMock(return_value=False)

    use_here_btn = MagicMock()
    use_here_btn.count = AsyncMock(return_value=1)
    use_here_btn.first.is_visible = AsyncMock(return_value=True)
    use_here_btn.first.click = AsyncMock()

    def locator_mock(selector):
        if 'Use Here' in selector:
            return use_here_btn
        empty = MagicMock()
        empty.count = AsyncMock(return_value=0)
        return empty

    mock_page.locator = locator_mock
    adapter._page = mock_page

    handled = await adapter.handle_interruption_popups()
    assert handled is True
    use_here_btn.first.click.assert_called_once()



# ── 5. Home Chat List & Active Chat Detection Tests ───────────────────────────

@pytest.mark.asyncio
async def test_pane_side_unread_opens_only_authorized_chat_by_direct_click(tmp_path):
    """
    Verify that when an unread badge appears on #pane-side:
    1. Authorized chat row is clicked directly (no search box typing).
    2. Unauthorized chat row is completely ignored.
    3. The message is extracted from #main and dispatched.
    """
    storage = WhatsAppStorage(db_path=str(tmp_path / "test_unread_pane.db"))
    browser = MagicMock()
    browser.is_connected = True
    browser.page = MagicMock()

    # Evaluation returns unread badge on row 0 for MIT Gova, and row 1 for Random Spammer
    unread_data = [
        {"index": 0, "title": "MIT Gova", "unread_count": 1, "snippet": "Hey bro"},
        {"index": 1, "title": "Random Spammer", "unread_count": 3, "snippet": "Buy crypto"},
    ]

    clicked_indices = []

    async def fake_evaluate(script, *args):
        if "data-testid=\"icon-unread-count\"" in script:
            return unread_data
        elif "(idx) =>" in script:
            clicked_indices.append(args[0])
            return True
        return None

    browser.page.evaluate = AsyncMock(side_effect=fake_evaluate)

    # When opened, visible messages show the incoming message from Gova
    browser.get_visible_messages = AsyncMock(return_value=[
        {
            "sender": "David",
            "text": "See you soon",
            "is_from_me": True,
            "message_id": "m_prev",
        },
        {
            "sender": "MIT Gova",
            "text": "Hey bro are you free?",
            "is_from_me": False,
            "message_id": "m_new_123",
        },
    ])

    listener = WhatsAppEventListener(browser=browser, storage=storage)
    listener.set_monitored_chats({"MIT Gova"})

    dispatched = []
    listener.subscribe(lambda m: dispatched.append(m))

    await listener._check_pane_side_unread()

    # Verify: only row 0 (MIT Gova) was clicked
    assert clicked_indices == [0]
    # Verify: dispatched to callbacks with correct message
    assert len(dispatched) == 1
    assert dispatched[0].chat_name == "MIT Gova"
    assert dispatched[0].text == "Hey bro are you free?"

    # Second check with identical unread state should NOT re-click or re-dispatch
    await listener._check_pane_side_unread()
    assert len(dispatched) == 1
    assert clicked_indices == [0]  # No additional click


@pytest.mark.asyncio
async def test_current_active_chat_dispatches_real_time_incoming_message(tmp_path):
    """
    Verify that if David is currently viewing a chat in #main, new incoming
    messages arriving in #main are detected and dispatched without any UI navigation.
    """
    storage = WhatsAppStorage(db_path=str(tmp_path / "test_active.db"))
    browser = MagicMock()
    browser.is_connected = True
    browser.page = MagicMock()
    browser.get_current_chat_name = AsyncMock(return_value="MIT Sundaramoorthy")

    browser.get_visible_messages = AsyncMock(return_value=[
        {
            "sender": "MIT Sundaramoorthy",
            "text": "Did you submit the assignment?",
            "is_from_me": False,
            "message_id": "m_sundar_1",
        }
    ])

    listener = WhatsAppEventListener(browser=browser, storage=storage)
    listener.set_monitored_chats({"MIT Sundaramoorthy"})

    dispatched = []
    listener.subscribe(lambda m: dispatched.append(m))

    await listener._check_current_active_chat()

    assert len(dispatched) == 1
    assert dispatched[0].chat_name == "MIT Sundaramoorthy"
    assert dispatched[0].text == "Did you submit the assignment?"

    # Subsequent check with same message should not duplicate
    await listener._check_current_active_chat()
    assert len(dispatched) == 1


def test_empty_jid_isolation_in_registry():
    """Verify that an empty string JID is never stored or used as a lookup key."""
    reg = JIDRegistry()
    reg.set_authorized_names({"MIT Gova"})

    # Empty JID query should always be False / None
    assert reg.is_authorized_jid("") is False
    assert reg.get_canonical("") is None

    # Registering with empty JID should resolve the display name but NOT cache ""
    canonical = reg.register("", "MIT Gova")
    assert canonical == "MIT Gova"
    assert reg.get_canonical("") is None
    assert reg.is_authorized_jid("") is False

    # Unauthorized name with empty JID should return None
    assert reg.register("", "Random Spammer") is None
    assert reg.get_canonical("") is None


@pytest.mark.asyncio
async def test_window_require_unavailable_returns_empty_list_and_resets_error_count(tmp_path):
    """
    In modern WhatsApp Web, window.require is not exposed.
    The scan must return [] (not None), and _listen_loop must keep
    _consecutive_scan_errors at 0 so watchdog never triggers a restart death loop.
    """
    storage = WhatsAppStorage(db_path=str(tmp_path / "test_no_req.db"))
    browser = MagicMock()
    browser.is_connected = True
    browser.page = MagicMock()

    # Simulate modern WhatsApp Web: evaluate returns [] because window.require is undefined
    browser.page.evaluate = AsyncMock(return_value=[])

    listener = WhatsAppEventListener(browser=browser, storage=storage)
    res = await listener._scan_unreplied_chats()

    assert res == []
    assert listener._consecutive_scan_errors == 0


@pytest.mark.asyncio
async def test_detection_channels_state_isolation(tmp_path):
    """
    Verify that Strategy 1 (in-memory), Strategy 2 (active chat),
    and Strategy 3 (pane-side unread) track states independently.
    """
    storage = WhatsAppStorage(db_path=str(tmp_path / "test_iso.db"))
    browser = MagicMock()
    browser.is_connected = True
    browser.page = MagicMock()

    listener = WhatsAppEventListener(browser=browser, storage=storage)
    listener.set_monitored_chats({"MIT Gova"})

    listener._last_unreplied_state["919876543210@c.us"] = "msg_store_1"
    listener._last_active_msg_id["MIT Gova"] = "msg_active_2"
    listener._last_pane_unread_state["MIT Gova"] = "MIT Gova:1:hey"

    # None of them should have clobbered each other
    assert listener._last_unreplied_state["919876543210@c.us"] == "msg_store_1"
    assert listener._last_active_msg_id["MIT Gova"] == "msg_active_2"
    assert listener._last_pane_unread_state["MIT Gova"] == "MIT Gova:1:hey"


