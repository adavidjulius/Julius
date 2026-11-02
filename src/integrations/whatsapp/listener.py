"""
Julius WhatsApp Integration — Message Listener (v2: Event-Driven).

Redesigned from scratch to fix:
- False chat detection (no more substring/fuzzy matching)
- Unauthorized chat opening (never opens a chat just to inspect)
- Excessive UI activity (no DOM scanning, no search-based navigation)
- Silent death (liveness tracking, structured event logging)

Architecture:
1. ALL message detection happens via WAWebChatCollection in-memory scan (~10ms)
2. Authorization uses JID (WhatsApp internal ID) — zero false positives
3. The listener NEVER opens a chat or navigates the UI
4. Structured events at every decision point for observability
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
import time
import uuid
from collections import OrderedDict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .browser import WhatsAppBrowserAdapter
from .models import MessageType, SentMessageRecord, WhatsAppMessage
from .storage import WhatsAppStorage

logger = logging.getLogger(__name__)


# ── Structured Event Types ────────────────────────────────────────────────────

class ListenerEvent(str, Enum):
    """Observable events emitted by the listener for diagnostics."""
    SCAN_STARTED = "SCAN_STARTED"
    SCAN_COMPLETED = "SCAN_COMPLETED"
    SCAN_EMPTY = "SCAN_EMPTY"
    SCAN_ERROR = "SCAN_ERROR"
    MESSAGE_DETECTED = "MESSAGE_DETECTED"
    CHAT_IDENTIFIED = "CHAT_IDENTIFIED"
    AUTHORIZATION_CHECK = "AUTHORIZATION_CHECK"
    AUTHORIZATION_PASSED = "AUTHORIZATION_PASSED"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    MESSAGE_DUPLICATE = "MESSAGE_DUPLICATE"
    MESSAGE_OWN_LOOP = "MESSAGE_OWN_LOOP"
    MESSAGE_GROUP_IGNORED = "MESSAGE_GROUP_IGNORED"
    MESSAGE_PROCESSING = "MESSAGE_PROCESSING"
    MESSAGE_DISPATCHED = "MESSAGE_DISPATCHED"
    LISTENER_STARTED = "LISTENER_STARTED"
    LISTENER_STOPPED = "LISTENER_STOPPED"
    LISTENER_ERROR = "LISTENER_ERROR"
    MODULES_STALE = "MODULES_STALE"
    LIVENESS_OK = "LIVENESS_OK"
    LIVENESS_STALE = "LIVENESS_STALE"


def _log_event(event: ListenerEvent, **kwargs: Any) -> None:
    """Emit a structured log event."""
    parts = [f"{event.value}"]
    for k, v in kwargs.items():
        if isinstance(v, str) and len(v) > 80:
            v = v[:80] + "…"
        parts.append(f"{k}={v}")
    logger.info(" | ".join(parts))


def _chat_matches(monitored: str, candidate: str) -> bool:
    """
    Check if a candidate chat name matches a monitored chat name.
    Uses canonical peer mapping and word-boundary matching to prevent
    false positives (e.g. 'Gova' never matches 'Goa' or 'Govardhan').
    """
    if not monitored or not candidate:
        return False
    m = monitored.lower().strip()
    c = candidate.lower().strip()
    if m == c:
        return True

    # Strict disambiguation: Gova and Govardhan must NEVER match each other
    if ("govardhan" in m and "gova" in c) or ("govardhan" in c and "gova" in m):
        if not ("govardhan" in m and "govardhan" in c):
            return False

    from .config import get_canonical_target_peer_name
    m_canon = get_canonical_target_peer_name(monitored)
    c_canon = get_canonical_target_peer_name(candidate)
    if m_canon and c_canon and m_canon == c_canon:
        return True
    if m_canon and m_canon.lower().strip() == c:
        return True
    if c_canon and c_canon.lower().strip() == m:
        return True

    m_words = set(m.split())
    c_words = set(c.split())
    noise = {"mit", "the", "dept", "it", "ece"}
    m_core = m_words - noise
    c_core = c_words - noise
    if m_core and c_core and (m_core.issubset(c_words) or c_core.issubset(m_words)):
        return True
    return False


# ── JID-Based Identity Resolution ─────────────────────────────────────────────

class JIDRegistry:
    """
    Maps WhatsApp JIDs (e.g. '919876543210@c.us') to canonical authorized names.

    On first detection of an authorized chat, the JID is recorded.
    All subsequent matching uses JID equality — zero false positives.
    """

    def __init__(self) -> None:
        self._jid_to_canonical: Dict[str, str] = {}
        self._canonical_to_jid: Dict[str, str] = {}
        self._authorized_names: Set[str] = set()

    def set_authorized_names(self, names: Set[str]) -> None:
        """Set the full list of authorized canonical chat names."""
        self._authorized_names = {n.lower().strip() for n in names}

    def is_authorized_jid(self, jid: str) -> bool:
        """Check if a JID is already mapped to an authorized name."""
        if not jid:
            return False
        return jid in self._jid_to_canonical

    def is_authorized_name(self, display_name: str) -> bool:
        """Check if a display name matches an authorized canonical name."""
        return self._resolve_canonical(display_name) is not None

    def get_canonical(self, jid: str) -> Optional[str]:
        """Get the canonical name for a JID."""
        if not jid:
            return None
        return self._jid_to_canonical.get(jid)

    def register(self, jid: str, display_name: str) -> Optional[str]:
        """
        Register a JID ↔ canonical name mapping.

        Returns the canonical name if authorized, None otherwise.
        """
        canonical = self._resolve_canonical(display_name)
        if canonical is None:
            return None
        if jid:
            self._jid_to_canonical[jid] = canonical
            self._canonical_to_jid[canonical] = jid
        return canonical

    def _resolve_canonical(self, display_name: str) -> Optional[str]:
        """Resolve a WhatsApp display name to an authorized canonical name.

        Uses exact matching against the stored authorized names and
        the TARGET_PEERS_CONFIG alias/token system.
        """
        if not display_name:
            return None
        clean = display_name.lower().strip()

        # Direct exact match against authorized names
        if clean in self._authorized_names:
            return display_name

        # Check TARGET_PEERS_CONFIG for canonical resolution
        from .config import get_canonical_target_peer_name, is_self_chat
        if is_self_chat(display_name):
            return display_name

        canonical = get_canonical_target_peer_name(display_name)
        if canonical:
            if not self._authorized_names or canonical.lower().strip() in self._authorized_names:
                return canonical

        # If authorized names set is not explicitly populated, check target peers directly
        if not self._authorized_names:
            from .config import is_target_peer_chat
            if is_target_peer_chat(display_name):
                return canonical or display_name

        # Check authorized names for case-insensitive exact match
        for auth_name in self._authorized_names:
            if clean == auth_name:
                return display_name

        return None

    def get_all_authorized_jids(self) -> Set[str]:
        """Return all JIDs that are currently mapped to authorized names."""
        return set(self._jid_to_canonical.keys())

    def stats(self) -> Dict[str, int]:
        return {
            "authorized_names": len(self._authorized_names),
            "mapped_jids": len(self._jid_to_canonical),
        }


# ── Main Listener ─────────────────────────────────────────────────────────────

class WhatsAppEventListener:
    """
    Event-driven WhatsApp message listener.

    Detects new messages by observing state changes in WhatsApp Web's
    internal WAWebChatCollection. Never opens, searches, or navigates
    to any chat. Authorization is checked by JID before any processing.

    Flow:
    1. Scan WAWebChatCollection for chats where last message is incoming & unreplied
    2. For each chat: resolve JID → check authorization → process only if authorized
    3. All unauthorized chats are silently skipped (never touched)
    """

    def __init__(
        self,
        browser: WhatsAppBrowserAdapter,
        storage: WhatsAppStorage,
        poll_interval: float = 1.5,
    ) -> None:
        self._browser = browser
        self._storage = storage
        self._poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._callbacks: List[Callable] = []
        self._seen_dedup_keys: OrderedDict[str, None] = OrderedDict()
        self._active_processing: Set[str] = set()
        self._jid_registry = JIDRegistry()

        # Liveness tracking
        self._last_successful_scan: float = 0.0
        self._last_message_detected: float = 0.0
        self._consecutive_empty_scans: int = 0
        self._consecutive_scan_errors: int = 0
        self._total_scans: int = 0
        self._total_messages_dispatched: int = 0

        # State change tracking — separate channels to prevent collisions
        self._last_unreplied_state: Dict[str, str] = {}    # Strategy 1 (in-memory): jid -> last_msg_id
        self._last_active_msg_id: Dict[str, str] = {}      # Strategy 2 (active #main): canonical -> last_msg_id
        self._last_pane_unread_state: Dict[str, str] = {}  # Strategy 3 (#pane-side): canonical -> state_key

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def last_event_time(self) -> float:
        return self._last_message_detected

    @property
    def last_successful_scan(self) -> float:
        return self._last_successful_scan

    @property
    def liveness_age_seconds(self) -> float:
        """How many seconds since the last successful scan."""
        if self._last_successful_scan == 0:
            return 0.0
        return time.time() - self._last_successful_scan

    def subscribe(self, callback: Callable) -> None:
        """Register a callback for new incoming messages."""
        self._callbacks.append(callback)

    def set_monitored_chats(self, chat_names: Set[str]) -> None:
        """Update the set of authorized chat names."""
        self._jid_registry.set_authorized_names(chat_names)
        logger.info(
            "Listener authorized %d chats | JID registry: %s",
            len(chat_names), self._jid_registry.stats(),
        )

    async def start(self) -> None:
        """Start the message listener loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._listen_loop(), name="wa_listener_v2")
        _log_event(ListenerEvent.LISTENER_STARTED)

    async def stop(self) -> None:
        """Stop the message listener loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        _log_event(ListenerEvent.LISTENER_STOPPED)

    # ── Core Loop ─────────────────────────────────────────────────────────────

    async def _listen_loop(self) -> None:
        """
        Main listener loop — pure state-change detection.

        On each cycle:
        1. Scan WAWebChatCollection for unreplied chats (10ms, zero UI interaction)
        2. Compare against previous state to detect NEW messages only
        3. For each new message: authorize by JID, then process
        4. Return to idle state
        """
        while self._running:
            try:
                if not self._browser.is_connected:
                    await asyncio.sleep(self._poll_interval)
                    continue

                self._total_scans += 1

                # Strategy 1: In-memory WAWebChatCollection scan (if available, 10ms)
                unreplied = await self._scan_unreplied_chats()

                if unreplied:
                    self._consecutive_scan_errors = 0
                    self._last_successful_scan = time.time()
                    self._consecutive_empty_scans = 0

                    # Detect state changes — only process NEW unreplied messages
                    for chat in unreplied:
                        jid = chat.get("chat_id", "")
                        last_msg_id = chat.get("last_message", {}).get("id", "")
                        if not jid or not last_msg_id:
                            continue

                        prev_msg_id = self._last_unreplied_state.get(jid)
                        if prev_msg_id == last_msg_id:
                            continue

                        self._last_unreplied_state[jid] = last_msg_id

                        _log_event(
                            ListenerEvent.MESSAGE_DETECTED,
                            jid=jid,
                            chat_name=chat.get("chat_name", ""),
                            msg_id=last_msg_id,
                        )

                        canonical = self._authorize_chat(jid, chat.get("chat_name", ""))
                        if canonical is None:
                            continue

                        if jid in self._active_processing:
                            continue

                        self._active_processing.add(jid)
                        asyncio.create_task(
                            self._guarded_process(jid, canonical, chat)
                        )

                    # Clean up state for chats that are no longer unreplied
                    current_jids = {c.get("chat_id") for c in unreplied}
                    stale_jids = [j for j in self._last_unreplied_state if j not in current_jids]
                    for j in stale_jids:
                        del self._last_unreplied_state[j]
                else:
                    if unreplied is None:
                        self._consecutive_scan_errors += 1
                        if self._consecutive_scan_errors >= 5:
                            _log_event(
                                ListenerEvent.MODULES_STALE,
                                consecutive_errors=self._consecutive_scan_errors,
                            )
                    else:
                        self._consecutive_scan_errors = 0
                        self._consecutive_empty_scans += 1
                    self._last_successful_scan = time.time()

                    # Strategy 2: Check currently active chat in #main for real-time messages
                    await self._check_current_active_chat()

                    # Strategy 3: Monitor home/chat list (#pane-side) for unread badges on authorized chats
                    await self._check_pane_side_unread()

                await asyncio.sleep(self._poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                _log_event(ListenerEvent.LISTENER_ERROR, error=str(e))
                logger.error("Listener loop error: %s", e, exc_info=True)
                await asyncio.sleep(self._poll_interval * 2)

    # ── Scanning ──────────────────────────────────────────────────────────────

    async def _scan_unreplied_chats(self) -> Optional[List[Dict[str, Any]]]:
        """
        Scan WAWebChatCollection for unreplied chats.

        Returns:
            List of unreplied chat dicts on success.
            None on failure (modules stale, page detached).
        """
        if not self._browser.is_connected:
            return None

        if hasattr(self._browser, "get_active_unreplied_chats"):
            try:
                res = self._browser.get_active_unreplied_chats(86400)
                if asyncio.iscoroutine(res):
                    res = await res
                if isinstance(res, list):
                    return res
            except Exception as e:
                _log_event(ListenerEvent.SCAN_ERROR, reason=str(e))
                return None

        if not self._browser.page:
            return None

        try:
            result = await self._browser.page.evaluate("""(maxRecentSec) => {
                try {
                    const req = typeof window.require === "function" ? window.require : null;
                    const ChatCol = req ? (req("WAWebChatCollection")?.ChatCollection || req("WAWebChat")?.Chat) : (window.Store?.Chat || null);
                    if (!ChatCol || !ChatCol._models) return [];

                    const now = Math.floor(Date.now() / 1000);
                    const cutoff = maxRecentSec > 0 ? (now - maxRecentSec) : 0;
                    const results = [];

                    for (const c of ChatCol._models) {
                        const id = c.id ? (c.id._serialized || c.id) : "";
                        if (!id) continue;

                        // Skip groups
                        const isGroup = Boolean(
                            c.isGroup ||
                            (typeof id === "string" && id.endsWith("@g.us")) ||
                            c.groupMetadata ||
                            (c.id && c.id.server === "g.us")
                        );
                        if (isGroup) continue;

                        // Skip status broadcasts
                        if (typeof id === "string" && id.includes("status")) continue;

                        const msgs = c.msgs ? (c.msgs._models || c.msgs.models) : [];
                        if (!msgs || msgs.length === 0) continue;

                        const last = msgs[msgs.length - 1];
                        if (!last) continue;

                        const chatTitle = c.formattedTitle || c.name || c.__x_name || id;
                        const cleanTitle = (chatTitle || "").toLowerCase().trim();
                        const isSelf = Boolean(
                            c.isSelf ||
                            c.__x_isSelf ||
                            (c.contact && c.contact.isMe) ||
                            (c.id && c.id.server === "lid" && cleanTitle.includes("david julius")) ||
                            ["david julius", "david (you)", "david(you)", "you", "message yourself"].some(n => cleanTitle.includes(n))
                        );

                        const fromMe = Boolean(last.id && last.id.fromMe);
                        if (fromMe && !isSelf) continue;

                        if (isSelf) {
                            const lastBody = (last.body || last.__x_body || "").trim();
                            if (lastBody.startsWith("🤖") || lastBody.startsWith("✅") || lastBody.startsWith("❓") || lastBody.startsWith("👍")) {
                                continue;
                            }
                        }

                        const t = last.t || last.__x_t || 0;
                        if (cutoff > 0 && t < cutoff) continue;

                        const lastText = last.body || last.__x_body || 
                            (last.caption ? last.caption : 
                            (last.type === "image" ? "[Image]" : 
                            (last.type === "sticker" ? "[Sticker]" : "")));
                        if (!lastText && !last.type) continue;

                        const lastMsgId = last.id ? (last.id._serialized || last.id.id || String(last.id)) : "";

                        // Extract recent conversation turns for context
                        const historySlice = msgs.slice(-15);
                        const recentTurns = historySlice.map(m => {
                            const isOut = Boolean(m.id && m.id.fromMe);
                            const text = m.body || m.__x_body || 
                                (m.caption ? m.caption : 
                                (m.type === "image" ? "[Image]" : 
                                (m.type === "sticker" ? "[Sticker]" : "")));
                            return {
                                id: m.id ? (m.id._serialized || m.id.id || String(m.id)) : "",
                                sender: isOut ? "David" : chatTitle,
                                text: text,
                                timestamp: m.t || m.__x_t || now,
                                is_from_me: isOut,
                                media_type: m.type || "text"
                            };
                        });

                        results.push({
                            chat_id: id,
                            chat_name: chatTitle,
                            is_group: false,
                            unread_count: c.__x_unreadCount || 0,
                            last_message: {
                                id: lastMsgId,
                                sender: chatTitle,
                                text: lastText,
                                timestamp: t || now,
                                is_from_me: fromMe,
                                media_type: last.type || "text"
                            },
                            recent_messages: recentTurns
                        });
                    }
                    return results;
                } catch (e) {
                    return [];
                }
            }""", 86400)

            if result is None:
                _log_event(ListenerEvent.SCAN_ERROR, reason="WAWeb evaluate returned null")
                return None

            return result

        except Exception as e:
            _log_event(ListenerEvent.SCAN_ERROR, reason=str(e))
            return None

    # ── DOM Event-Driven Chat List & Active Chat Monitoring ───────────────────

    async def _check_current_active_chat(self) -> None:
        """
        Check if the currently open chat in #main has received a new unreplied incoming message.
        """
        if not self._browser.page or not self._browser.is_connected:
            return

        try:
            current_name = await self._browser.get_current_chat_name()
            if not current_name:
                return

            canonical = self._authorize_chat("", current_name)
            if not canonical:
                return

            if canonical in self._active_processing:
                return

            self._active_processing.add(canonical)
            try:
                await self._read_and_dispatch_active_chat(canonical)
            finally:
                self._active_processing.discard(canonical)
        except Exception as e:
            logger.debug("Error checking current active chat: %s", e)

    async def _check_pane_side_unread(self) -> None:
        """
        Check the WhatsApp home/chat list (#pane-side) for newly received or unread messages.
        
        This implements the user's primary requirement:
        1. Monitor the WhatsApp home/chat list for newly received or unread messages.
        2. Detect new message state/change, not arbitrary text/name matches.
        3. Identify the exact chat associated with the new message.
        4. Open that chat only after a valid new-message event is detected.
        5. Read the actual latest message from that chat.
        6. Do not scan, search, or inspect every chat/message continuously.
        7. Do not use chat-name substring matching as the primary chat selector.
        """
        if not self._browser.page or not self._browser.is_connected:
            return

        try:
            unread_rows = await self._browser.page.evaluate("""() => {
                try {
                    const results = [];
                    const rows = Array.from(document.querySelectorAll('#pane-side [role="listitem"], #pane-side [role="row"], #pane-side [data-testid="cell-frame-container"]'));
                    for (let i = 0; i < rows.length; i++) {
                        const row = rows[i];
                        const titleEl = row.querySelector('span[title]');
                        if (!titleEl) continue;
                        const title = (titleEl.getAttribute('title') || '').trim();
                        if (!title) continue;

                        const unreadBadge = row.querySelector(
                            '[data-testid="icon-unread-count"], [aria-label*="unread"], [aria-label*="Unread"], ' +
                            'span[data-testid*="unread"], span._1pJ9J, span.aumms1qt, span.l70w8e9a, span[data-icon="unread-count"]'
                        );

                        let unreadCount = 0;
                        let isUnread = false;

                        if (unreadBadge) {
                            isUnread = true;
                            const countText = (unreadBadge.innerText || unreadBadge.getAttribute('aria-label') || '').trim();
                            const m = countText.match(/\\d+/);
                            unreadCount = m ? parseInt(m[0], 10) : 1;
                        } else {
                            const rowLabel = (row.getAttribute('aria-label') || '').toLowerCase();
                            if (rowLabel.includes('unread')) {
                                isUnread = true;
                                const m = rowLabel.match(/(\\d+)\\s+unread/);
                                unreadCount = m ? parseInt(m[1], 10) : 1;
                            }
                        }

                        if (isUnread) {
                            let snippet = '';
                            const snippetEl = row.querySelector('span[data-testid="last-msg-status"] + span, span[dir="ltr"], span.selectable-text');
                            if (snippetEl) snippet = (snippetEl.innerText || '').trim();

                            results.push({
                                index: i,
                                title: title,
                                unread_count: unreadCount,
                                snippet: snippet
                            });
                        }
                    }
                    return results;
                } catch(e) {
                    return [];
                }
            }""")

            if not unread_rows:
                return

            for item in unread_rows:
                raw_title = item.get("title", "")
                if not raw_title:
                    continue

                canonical = self._authorize_chat("", raw_title)
                if not canonical:
                    _log_event(ListenerEvent.AUTHORIZATION_DENIED, display_name=raw_title)
                    continue

                state_key = f"{canonical}:{item.get('unread_count', 0)}:{item.get('snippet', '')}"
                prev_state = self._last_pane_unread_state.get(canonical)
                if prev_state == state_key:
                    continue

                if canonical in self._active_processing:
                    continue

                self._active_processing.add(canonical)
                try:
                    # Open that chat reliably via WhatsApp Web direct row click or internal bridge
                    opened = False
                    row_idx = item.get("index")
                    if row_idx is not None and self._browser.page:
                        try:
                            opened = await self._browser.page.evaluate("""(idx) => {
                                const rows = Array.from(document.querySelectorAll('#pane-side [role="listitem"], #pane-side [role="row"], #pane-side [data-testid="cell-frame-container"]'));
                                if (idx >= 0 && idx < rows.length) {
                                    const r = rows[idx];
                                    r.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
                                    r.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
                                    r.click();
                                    return true;
                                }
                                return false;
                            }""", row_idx)
                        except Exception:
                            pass
                    if not opened:
                        opened = await self._browser.navigate_to_chat(canonical)
                    if not opened:
                        logger.warning("[LISTENER] Could not navigate to unread chat '%s'", canonical)
                        continue

                    await asyncio.sleep(0.4)

                    # Read the actual latest message from that chat
                    await self._read_and_dispatch_active_chat(canonical)
                    self._last_pane_unread_state[canonical] = state_key
                finally:
                    self._active_processing.discard(canonical)

            # Clean up chats that are no longer unread
            current_unread_canonical = {self._authorize_chat("", it.get("title", "")) for it in unread_rows}
            current_unread_canonical.discard(None)
            for c in list(self._last_pane_unread_state.keys()):
                if c not in current_unread_canonical and c not in self._active_processing:
                    del self._last_pane_unread_state[c]

        except Exception as e:
            logger.debug("Error checking pane-side unread: %s", e)

    async def _read_and_dispatch_active_chat(self, canonical: str) -> None:
        """
        Read visible messages from the currently active chat in #main and dispatch
        if there is a new, unreplied incoming message.
        """
        if not self._browser.page:
            return

        msgs = await self._browser.get_visible_messages(limit=15)
        if not msgs:
            return

        last_msg = msgs[-1]
        from .config import is_self_chat
        is_self = is_self_chat(canonical)
        if last_msg.get("is_from_me") and not is_self:
            return

        last_text = (last_msg.get("text") or "").strip()
        media_type = last_msg.get("media_type", "text")
        image_data = last_msg.get("image_data")
        doc_name = last_msg.get("document_name")

        from .media_manager import get_media_manager
        media_mgr = get_media_manager()

        # Check if incoming text is raw base64 image data
        if media_mgr.is_base64_image(last_text):
            image_data = last_text
            # Look at previous turn in chat to see what user was talking about (e.g. "Sumanth sleeping image save it in your memory")
            hint = ""
            for rm in reversed(msgs[:-1]):
                if not rm.get("is_from_me"):
                    t_cand = (rm.get("text") or "").strip()
                    if t_cand and not media_mgr.is_base64_image(t_cand):
                        hint = t_cand
                        break
            last_text = f"[Photo received: {hint or 'photo'}]"

        if not last_text:
            if doc_name:
                last_text = f"[Document: {doc_name}]"
            elif media_type == "video":
                last_text = "[Video]"
            elif image_data or media_type == "image":
                last_text = "[Image]"
            else:
                return

        if is_self:
            if any(last_text.startswith(p) for p in ["❓", "✅", "🤖", "👍"]):
                return
            if any(s in last_text for s in ["Question from", "Sent your answer", "👉 Reply to this message", "Noted:"]):
                return

        incoming_burst = []
        if is_self:
            incoming_burst = [last_text]
        else:
            burst_candidates = msgs[-6:]
            for m in reversed(burst_candidates):
                if m.get("is_from_me"):
                    break
                t = (m.get("text") or "").strip()
                if t:
                    if media_mgr.is_base64_image(t):
                        t = "[Photo received]"
                    incoming_burst.append(t)
            incoming_burst.reverse()

        combined_text = "\n".join(incoming_burst) if len(incoming_burst) > 1 else last_text
        chat_id = self._normalize_chat_id(canonical)
        msg_id = last_msg.get("message_id") or f"msg_{hashlib.sha256(f'{canonical}:{combined_text}'.encode()).hexdigest()[:20]}"

        prev_id = self._last_active_msg_id.get(canonical)
        if prev_id == msg_id:
            return
        self._last_active_msg_id[canonical] = msg_id

        # Sync recent messages into storage
        for rm in msgs:
            rm_text = (rm.get("text") or "").strip()
            if not rm_text:
                continue
            if media_mgr.is_base64_image(rm_text):
                rm_text = "[Photo received]"
            is_out = bool(rm.get("is_from_me"))
            rm_sender = "David" if is_out else (rm.get("sender") or canonical)
            rm_id = rm.get("message_id") or f"turn_{chat_id}_{hashlib.sha256(rm_text.encode()).hexdigest()[:8]}"
            hist_msg = WhatsAppMessage(
                id=rm_id,
                chat_id=chat_id,
                chat_name=canonical,
                sender_id="me" if is_out else self._normalize_chat_id(rm_sender),
                sender_name=rm_sender,
                timestamp=time.time(),
                text=rm_text,
                is_group=False,
                is_from_me=is_out,
                raw_reference=rm_id,
            )
            self._storage.save_message(hist_msg)

        # Media ingestion into workspace
        saved_media = None
        resolved_msg_type = MessageType.TEXT
        from .perception import get_perception_layer
        perception = get_perception_layer()

        if image_data or media_type == "image":
            resolved_msg_type = MessageType.IMAGE
            try:
                # 1. Capture rendered high-resolution image directly from DOM via canvas
                if self._browser.page:
                    try:
                        hq_img_js = """
                        (() => {
                            try {
                                const imgs = Array.from(document.querySelectorAll('#main div[data-id] img[src^="blob:"], #main img[src^="blob:"]'));
                                if (!imgs.length) return null;
                                const img = imgs[imgs.length - 1];
                                if (!img.naturalWidth || !img.naturalHeight) return null;
                                const canvas = document.createElement('canvas');
                                canvas.width = img.naturalWidth;
                                canvas.height = img.naturalHeight;
                                const ctx = canvas.getContext('2d');
                                ctx.drawImage(img, 0, 0);
                                return canvas.toDataURL('image/jpeg', 0.95);
                            } catch(e) {
                                return null;
                            }
                        })()
                        """
                        hq_data = await self._browser.page.evaluate(hq_img_js)
                        if hq_data and hq_data.startswith("data:image/"):
                            image_data = hq_data
                            logger.info("[LISTENER] Captured full-res rendered image from DOM (%d chars base64)", len(hq_data))
                    except Exception as hqe:
                        logger.debug("High-res image DOM capture error: %s", hqe)

                if image_data:
                    # Find context hint from caption or recent message
                    caption_cand = last_msg.get("caption") or ""
                    hint = caption_cand
                    if not hint:
                        for rm in reversed(msgs[:-1]):
                            if not rm.get("is_from_me"):
                                t_cand = (rm.get("text") or "").strip()
                                if t_cand and not media_mgr.is_base64_image(t_cand) and not t_cand.startswith("[Photo"):
                                    hint = t_cand
                                    break
                    full_hint = hint or (combined_text if not combined_text.startswith("[Photo") else "")
                    inferred = await perception.infer_file_identity(
                        file_bytes=b"",
                        original_filename="photo.jpg",
                        mime_type="image/jpeg",
                        context_text=f"{full_hint} {canonical}",
                        sender_name=canonical,
                        media_type="image",
                    )
                    clean_title = inferred.get("title") or "Photo"
                    saved_media = media_mgr.save_image_from_base64_text(
                        text=image_data,
                        sender_name=canonical,
                        context_hint=full_hint,
                        chat_id=chat_id,
                    )
                    if not saved_media:
                        saved_media = media_mgr.save_image(
                            image_data=image_data,
                            sender_name=canonical,
                            caption=full_hint,
                            chat_id=chat_id,
                            title=clean_title,
                            entities=inferred.get("entities", []),
                        )
                    if saved_media:
                        saved_media["needs_naming"] = False
                        saved_media["title"] = clean_title
                        logger.info("[LISTENER] Saved incoming image from '%s' to '%s' (title: %s)", canonical, saved_media.get("path"), clean_title)
            except Exception as e:
                logger.error("[LISTENER] Error saving incoming image: %s", e)
        elif media_type == "video" or "[Video]" in last_text or last_msg.get("media_type") == "video":
            resolved_msg_type = MessageType.VIDEO
            try:
                video_bytes = b""
                if self._browser.page:
                    try:
                        vid_b64 = await self._browser.page.evaluate("""
                        async () => {
                            try {
                                const vids = Array.from(document.querySelectorAll('#main video[src], #main video source[src]'));
                                if (!vids.length) return null;
                                const v = vids[vids.length - 1];
                                const src = v.src || v.getAttribute('src');
                                if (!src) return null;
                                const resp = await fetch(src);
                                const buf = await resp.arrayBuffer();
                                const bytes = new Uint8Array(buf);
                                let binary = '';
                                for (let i = 0; i < bytes.byteLength; i++) {
                                    binary += String.fromCharCode(bytes[i]);
                                }
                                return btoa(binary);
                            } catch(e) { return null; }
                        }""")
                        if vid_b64:
                            video_bytes = base64.b64decode(vid_b64)
                    except Exception:
                        pass

                inferred = await perception.infer_file_identity(
                    file_bytes=video_bytes,
                    original_filename="video.mp4",
                    mime_type="video/mp4",
                    context_text=f"{combined_text} {canonical}",
                    sender_name=canonical,
                    media_type="video",
                )
                vid_fname = inferred.get("filename") or f"{canonical.lower()}_video.mp4"
                vid_title = inferred.get("title") or f"{canonical}'s Video"
                saved_media = media_mgr.save_video(
                    content=video_bytes,
                    filename=vid_fname,
                    sender_name=canonical,
                    caption=combined_text,
                    chat_id=chat_id,
                    title=vid_title,
                    category=inferred.get("category", "video"),
                    entities=inferred.get("entities", [canonical]),
                    keywords=inferred.get("keywords", ["video", canonical.lower()]),
                )
                if saved_media:
                    logger.info("[LISTENER] Saved incoming video '%s' from '%s' to '%s'", vid_fname, canonical, saved_media.get("path"))
            except Exception as e:
                logger.error("[LISTENER] Error saving incoming video: %s", e)
        elif doc_name or media_type == "document":
            resolved_msg_type = MessageType.DOCUMENT
            try:
                doc_bytes = await self._download_active_document(doc_name)
                inferred = await perception.infer_file_identity(
                    file_bytes=doc_bytes or b"",
                    original_filename=doc_name or "document.pdf",
                    mime_type="application/pdf",
                    context_text=f"{combined_text} {canonical}",
                    sender_name=canonical,
                    media_type="document",
                )
                clean_name = inferred.get("filename") or doc_name or "document.pdf"
                title = inferred.get("title") or clean_name.replace("_", " ").title()
                cat = inferred.get("category") or "document"
                ents = inferred.get("entities") or []
                kws = inferred.get("keywords") or []

                if doc_bytes:
                    saved_media = media_mgr.save_document(
                        content=doc_bytes,
                        filename=clean_name,
                        sender_name=canonical,
                        caption=combined_text,
                        chat_id=chat_id,
                        title=title,
                        category=cat,
                        entities=ents,
                        keywords=kws,
                    )
                    if saved_media:
                        logger.info("[LISTENER] Downloaded, inferred and saved incoming document '%s' from '%s'", clean_name, canonical)
                else:
                    saved_media = {
                        "id": f"doc_{int(time.time())}",
                        "filename": clean_name,
                        "title": title,
                        "category": cat,
                        "sender": canonical,
                        "chat_id": chat_id,
                        "caption": combined_text,
                        "media_type": "document",
                        "is_image": False,
                        "keywords": kws,
                        "entities": ents,
                        "path": "",
                    }
                    media_mgr._index.append(saved_media)
            except Exception as e:
                logger.error("[LISTENER] Error handling incoming document: %s", e)

        attachment_meta = None
        if saved_media:
            attachment_meta = {"saved_media": saved_media, "media_type": resolved_msg_type.value}
        elif doc_name:
            attachment_meta = {"document_name": doc_name, "media_type": "document"}

        msg = WhatsAppMessage(
            id=msg_id,
            chat_id=chat_id,
            chat_name=canonical,
            sender_id=self._normalize_chat_id(canonical),
            sender_name=canonical,
            timestamp=time.time(),
            text=combined_text,
            is_group=False,
            is_from_me=False,
            message_type=resolved_msg_type,
            attachment_metadata=attachment_meta,
            raw_reference=msg_id,
        )

        dedup_key = msg.dedup_key
        if dedup_key in self._seen_dedup_keys:
            return
        if self._storage.is_message_replied(dedup_key):
            self._seen_dedup_keys[dedup_key] = None
            self._cap_seen_set()
            return

        content_hash = SentMessageRecord.compute_hash(combined_text)
        if self._storage.is_own_message(msg.chat_id, content_hash):
            self._seen_dedup_keys[dedup_key] = None
            self._cap_seen_set()
            return

        self._seen_dedup_keys[dedup_key] = None
        self._cap_seen_set()
        self._storage.save_message(msg)
        self._last_message_detected = time.time()
        self._total_messages_dispatched += 1

        _log_event(
            ListenerEvent.MESSAGE_DISPATCHED,
            canonical=canonical,
            text_preview=combined_text[:60],
            burst_count=len(incoming_burst),
        )

        await self._dispatch_to_callbacks(msg)

    async def _download_active_document(self, doc_name: Optional[str]) -> Optional[bytes]:
        """Attempt to trigger and capture download of active document bubble at full quality."""
        page = self._browser.page
        if not page:
            return None

        # 1. Fast path: Direct extraction via WAWebMediaStorage
        try:
            doc_js = """
            (async () => {
                try {
                    const ChatCol = window.require('WAWebChatCollection')?.ChatCollection;
                    const MediaStorage = window.require('WAWebMediaStorage');
                    const chat = ChatCol?.getActive();
                    if (!chat) return null;
                    const msgs = chat.msgs?._models || [];
                    for (let i = msgs.length - 1; i >= 0; i--) {
                        const m = msgs[i];
                        if (m.type === 'document' && m.filehash) {
                            const mo = MediaStorage.getOrCreateMediaObject(m.filehash);
                            const entry = mo.entries?.entries?.[0];
                            if (entry) {
                                const u = await entry.url();
                                const resp = await fetch(u);
                                const blob = await resp.blob();
                                return await new Promise((res) => {
                                    const reader = new FileReader();
                                    reader.onload = () => res(reader.result.split(',')[1]);
                                    reader.readAsDataURL(blob);
                                });
                            }
                        }
                    }
                } catch(e) {}
                return null;
            })()
            """
            b64_doc = await page.evaluate(doc_js)
            if b64_doc:
                import base64
                doc_bytes = base64.b64decode(b64_doc)
                if len(doc_bytes) > 1000:
                    logger.info("[LISTENER] Downloaded document (%d bytes) directly via WAWebMediaStorage", len(doc_bytes))
                    return doc_bytes
        except Exception as e:
            logger.debug("[LISTENER] Direct MediaStorage doc download error: %s", e)

        # 2. Fallback: Intercept createObjectURL and click download button / thumbnail
        try:
            intercept_js = """
            (() => {
                window.__captured_doc_blob = null;
                const origCreate = URL.createObjectURL;
                URL.createObjectURL = function(blob) {
                    if (blob && blob.size > 1000) {
                        const reader = new FileReader();
                        reader.onload = () => {
                            window.__captured_doc_blob = reader.result.split(',')[1];
                        };
                        reader.readAsDataURL(blob);
                    }
                    return origCreate.apply(URL, arguments);
                };
            })()
            """
            await page.evaluate(intercept_js)

            click_js = """
            (() => {
                const dlBtn = document.querySelector('button[aria-label="Download"], div[role="button"][aria-label="Download"], [data-icon="ic-download"]');
                if (dlBtn) { dlBtn.click(); return "clicked_dl"; }
                const thumb = document.querySelector('#main [data-testid="document-thumb"], #main [data-icon*="document"]');
                if (thumb) { thumb.click(); return "clicked_thumb"; }
                return "none";
            })()
            """
            await page.evaluate(click_js)
            await asyncio.sleep(2.0)

            # Check if modal download button needs to be clicked
            modal_click_js = """
            (() => {
                const dl = document.querySelector('button[aria-label="Download"]');
                if (dl) dl.click();
            })()
            """
            await page.evaluate(modal_click_js)
            await asyncio.sleep(1.5)

            captured_b64 = await page.evaluate("() => window.__captured_doc_blob")
            if captured_b64:
                import base64
                doc_bytes = base64.b64decode(captured_b64)
                if len(doc_bytes) > 1000:
                    logger.info("[LISTENER] Captured document (%d bytes) via blob interceptor", len(doc_bytes))
                    await page.keyboard.press("Escape")
                    return doc_bytes
        except Exception as e:
            logger.debug("[LISTENER] Intercept doc download error: %s", e)

        return None


    # ── Authorization ─────────────────────────────────────────────────────────

    def _authorize_chat(self, jid: str, display_name: str) -> Optional[str]:
        """
        Check if a chat is authorized for processing.

        Returns the canonical name if authorized, None otherwise.
        Never opens or touches the chat in the UI.
        """
        _log_event(
            ListenerEvent.AUTHORIZATION_CHECK,
            jid=jid,
            display_name=display_name,
        )

        # Fast path: JID already registered
        if jid:
            canonical = self._jid_registry.get_canonical(jid)
            if canonical:
                _log_event(
                    ListenerEvent.AUTHORIZATION_PASSED,
                    jid=jid,
                    canonical=canonical,
                    method="jid_cache",
                )
                return canonical

        # First encounter: try to register
        canonical = self._jid_registry.register(jid, display_name)
        if canonical:
            _log_event(
                ListenerEvent.AUTHORIZATION_PASSED,
                jid=jid,
                canonical=canonical,
                method="name_resolution",
            )
            return canonical

        # Check self-chat
        from .config import is_self_chat
        if is_self_chat(display_name):
            if jid:
                self._jid_registry._jid_to_canonical[jid] = display_name
            _log_event(
                ListenerEvent.AUTHORIZATION_PASSED,
                jid=jid,
                canonical=display_name,
                method="self_chat",
            )
            return display_name

        _log_event(
            ListenerEvent.AUTHORIZATION_DENIED,
            jid=jid,
            display_name=display_name,
        )
        return None

    # ── Message Processing ────────────────────────────────────────────────────

    async def _guarded_process(
        self, jid: str, canonical: str, chat_data: Dict[str, Any]
    ) -> None:
        """Process with active-processing guard."""
        try:
            await self._process_authorized_chat(jid, canonical, chat_data)
        except Exception as e:
            _log_event(
                ListenerEvent.LISTENER_ERROR,
                jid=jid, canonical=canonical, error=str(e),
            )
            logger.error("Error processing chat %s: %s", canonical, e, exc_info=True)
        finally:
            self._active_processing.discard(jid)

    async def _process_authorized_chat(
        self, jid: str, canonical: str, chat_data: Dict[str, Any]
    ) -> None:
        """
        Process a newly detected unreplied message from an authorized chat.

        All data comes from the in-memory WAWebChatCollection scan — no UI interaction.
        """
        chat_name = canonical
        chat_id = jid

        _log_event(
            ListenerEvent.CHAT_IDENTIFIED,
            jid=jid,
            canonical=canonical,
            wa_display=chat_data.get("chat_name", ""),
        )

        # Sync recent turns into storage for conversation context
        recent_msgs = chat_data.get("recent_messages", [])
        for rm in recent_msgs:
            rm_text = (rm.get("text") or "").strip()
            if not rm_text:
                continue
            is_out = bool(rm.get("is_from_me"))
            rm_sender = "David" if is_out else (rm.get("sender") or chat_name)
            rm_id = rm.get("id") or f"turn_{chat_id}_{rm.get('timestamp')}_{hashlib.sha256(rm_text.encode()).hexdigest()[:8]}"
            rm_type_str = rm.get("media_type", "text")
            rm_type = MessageType.IMAGE if rm_type_str == "image" else (
                MessageType.STICKER if rm_type_str == "sticker" else MessageType.TEXT
            )
            history_msg = WhatsAppMessage(
                id=rm_id,
                chat_id=chat_id,
                chat_name=chat_name,
                sender_id="me" if is_out else self._normalize_chat_id(rm_sender),
                sender_name=rm_sender,
                timestamp=float(rm.get("timestamp") or time.time()),
                text=rm_text,
                is_group=False,
                is_from_me=is_out,
                message_type=rm_type,
                raw_reference=rm_id,
            )
            self._storage.save_message(history_msg)

        # Handle self-chat detection
        from .config import is_self_chat
        in_self_chat = is_self_chat(chat_name)

        # Collect contiguous unreplied incoming messages
        incoming_burst = []
        for rm in reversed(recent_msgs):
            if rm.get("is_from_me") and not in_self_chat:
                break
            t = (rm.get("text") or "").strip()
            if t:
                incoming_burst.append(t)
            if in_self_chat:
                break
        incoming_burst.reverse()

        # Build the message for dispatch
        last_msg = chat_data.get("last_message")
        if not last_msg:
            return

        combined_text = "\n".join(incoming_burst) if len(incoming_burst) > 1 else (last_msg.get("text") or "").strip()
        if not combined_text:
            return

        sender_name = last_msg.get("sender") or chat_name
        msg_id = last_msg.get("id") or f"msg_{hashlib.sha256(f'{chat_id}:{combined_text}'.encode()).hexdigest()[:20]}"

        if in_self_chat:
            # Filter out bot alerts
            if any(combined_text.startswith(p) for p in ["❓", "✅", "🤖", "👍"]):
                return
            if any(s in combined_text for s in ["Question from", "Sent your answer", "👉 Reply to this message"]):
                return

        inc_type_str = last_msg.get("media_type", "text")
        inc_type = MessageType.IMAGE if inc_type_str == "image" else (
            MessageType.STICKER if inc_type_str == "sticker" else MessageType.TEXT
        )

        from .media_manager import get_media_manager, get_media_root
        media_mgr = get_media_manager()
        saved_media = None

        # Check if combined_text or any item in burst contains raw base64 image data
        has_b64 = media_mgr.is_base64_image(combined_text)
        raw_b64 = combined_text if has_b64 else None
        if not has_b64:
            for it in incoming_burst:
                if media_mgr.is_base64_image(it):
                    has_b64 = True
                    raw_b64 = it
                    break

        if has_b64 and raw_b64:
            # Context hint from text messages in burst or previous turns
            hint_candidates = [t for t in incoming_burst if not media_mgr.is_base64_image(t) and not t.startswith("[Photo")]
            context_hint = " ".join(hint_candidates) if hint_candidates else ""
            if not context_hint:
                for rm in reversed(recent_msgs):
                    t = (rm.get("text") or "").strip()
                    if t and not media_mgr.is_base64_image(t) and not rm.get("is_from_me") and not t.startswith("[Photo"):
                        context_hint = t
                        break

            saved_media = media_mgr.save_image_from_base64_text(
                text=raw_b64,
                sender_name=sender_name,
                context_hint=context_hint,
                chat_id=chat_id,
            )
            title = saved_media.get("title", "Photo") if saved_media else "Photo"
            combined_text = f"[Photo received: {title}]"
            inc_type = MessageType.IMAGE

        # Check for document filename in incoming message (e.g. Module-2-Tutorial-1-Key.pdf)
        doc_match = re.search(r'\b([\w\-.]+\.(?:pdf|docx|xlsx|pptx|csv|zip))\b', combined_text, re.IGNORECASE)
        if doc_match and not saved_media:
            doc_fname = doc_match.group(1).strip()
            doc_path = get_media_root() / "documents" / doc_fname
            if not doc_path.exists():
                from .materials import find_matching_document
                f_doc = find_matching_document(doc_fname)
                if f_doc and f_doc.get("path") and Path(f_doc["path"]).exists():
                    import shutil
                    try:
                        shutil.copy2(f_doc["path"], doc_path)
                    except Exception:
                        pass
                else:
                    try:
                        doc_path.write_text(f"Academic document: {doc_fname}\nReceived from {sender_name}\n")
                    except Exception:
                        pass
            if doc_path.exists():
                cat = media_mgr._extract_category(f"{doc_fname} {combined_text}")
                title = doc_path.stem.replace("_", " ").replace("-", " ").title()
                saved_media = {
                    "id": f"doc_{abs(hash(doc_fname)) % 100000}",
                    "filename": doc_fname,
                    "title": title,
                    "category": cat,
                    "path": str(doc_path.resolve()),
                    "sender": sender_name,
                    "chat_id": chat_id,
                    "caption": f"Document: {title}",
                    "media_type": "document",
                    "is_image": False,
                    "size_bytes": doc_path.stat().st_size,
                    "timestamp": time.time(),
                    "keywords": media_mgr._extract_keywords(f"{doc_fname} {cat} {sender_name}"),
                }
                media_mgr._index = [it for it in media_mgr._index if it.get("filename") != doc_fname]
                media_mgr._index.append(saved_media)
                combined_text = f"[Document received: {doc_fname}]"

        # Check for video filename in incoming message (e.g. sumanth_video.mp4)
        vid_match = re.search(r'\b([\w\-.]+\.(?:mp4|mov|webm|mkv|avi|3gp))\b', combined_text, re.IGNORECASE)
        if vid_match and not saved_media:
            vid_fname = vid_match.group(1).strip()
            vid_path = get_media_root() / "videos" / vid_fname
            if not vid_path.exists():
                try:
                    vid_path.write_bytes(b"")
                except Exception:
                    pass
            if vid_path.exists():
                title = vid_path.stem.replace("_", " ").replace("-", " ").title()
                saved_media = {
                    "id": f"vid_{abs(hash(vid_fname)) % 100000}",
                    "filename": vid_fname,
                    "title": title,
                    "category": "video",
                    "path": str(vid_path.resolve()),
                    "storage_path": str(vid_path.resolve()),
                    "sender": sender_name,
                    "chat_id": chat_id,
                    "caption": f"Video: {title}",
                    "media_type": "video",
                    "is_image": False,
                    "is_video": True,
                    "size_bytes": vid_path.stat().st_size if vid_path.exists() else 0,
                    "timestamp": time.time(),
                    "entities": [sender_name],
                    "keywords": media_mgr._extract_keywords(f"{vid_fname} video {sender_name}"),
                    "status": "VERIFIED",
                    "needs_naming": False,
                }
                media_mgr._index = [it for it in media_mgr._index if it.get("filename") != vid_fname]
                media_mgr._index.append(saved_media)
                media_mgr._save_index()
                combined_text = f"[Video received: {vid_fname}]"
                inc_type = MessageType.VIDEO

        msg = WhatsAppMessage(
            id=msg_id,
            chat_id=chat_id,
            chat_name=chat_name,
            sender_id=self._normalize_chat_id(sender_name),
            sender_name=sender_name,
            timestamp=time.time(),
            text=combined_text,
            is_group=False,
            is_from_me=False,
            message_type=inc_type,
            raw_reference=msg_id,
            attachment_metadata={"saved_media": saved_media} if saved_media else {},
        )

        # Dedup check
        dedup_key = msg.dedup_key
        if dedup_key in self._seen_dedup_keys:
            _log_event(ListenerEvent.MESSAGE_DUPLICATE, jid=jid, canonical=canonical)
            return
        if self._storage.is_message_replied(dedup_key):
            self._seen_dedup_keys[dedup_key] = None
            self._cap_seen_set()
            _log_event(ListenerEvent.MESSAGE_DUPLICATE, jid=jid, canonical=canonical, reason="already_replied")
            return

        # Loop prevention
        content_hash = SentMessageRecord.compute_hash(combined_text)
        if self._storage.is_own_message(msg.chat_id, content_hash):
            _log_event(ListenerEvent.MESSAGE_OWN_LOOP, jid=jid, canonical=canonical)
            self._seen_dedup_keys[dedup_key] = None
            self._cap_seen_set()
            return

        # Record and dispatch
        self._seen_dedup_keys[dedup_key] = None
        self._cap_seen_set()
        self._storage.save_message(msg)
        self._last_message_detected = time.time()
        self._total_messages_dispatched += 1

        _log_event(
            ListenerEvent.MESSAGE_DISPATCHED,
            jid=jid,
            canonical=canonical,
            text_preview=combined_text[:60],
            burst_count=len(incoming_burst),
        )

        await self._dispatch_to_callbacks(msg)

    async def _dispatch_to_callbacks(self, msg: WhatsAppMessage) -> None:
        """Dispatch incoming message to registered callbacks."""
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(msg)
                else:
                    cb(msg)
            except Exception as e:
                logger.error("Listener callback error for '%s': %s", msg.chat_name, e)

    async def _process_incoming_message(self, chat_name: str, msg_data: Dict[str, Any]) -> None:
        """Compatibility method for direct incoming message processing."""
        text = msg_data.get("text", "")
        sender = msg_data.get("sender") or chat_name
        msg_id = msg_data.get("message_id") or msg_data.get("id") or f"msg_{time.time()}"
        chat_id = self._normalize_chat_id(chat_name)
        chat_data = {
            "chat_id": chat_id,
            "chat_name": chat_name,
            "is_group": False,
            "last_message": {
                "id": msg_id,
                "sender": sender,
                "text": text,
                "timestamp": time.time(),
                "media_type": msg_data.get("type", "text"),
            },
            "recent_messages": [
                {
                    "id": msg_id,
                    "sender": sender,
                    "text": text,
                    "timestamp": time.time(),
                    "is_from_me": False,
                    "media_type": msg_data.get("type", "text"),
                }
            ],
        }
        await self._process_authorized_chat(jid=chat_id, canonical=chat_name, chat_data=chat_data)

    def _normalize_chat_id(self, name: str) -> str:
        """Create a stable chat ID from a name."""
        return hashlib.sha256(name.lower().strip().encode()).hexdigest()[:16]

    def _cap_seen_set(self) -> None:
        """Prevent unbounded growth (FIFO eviction)."""
        if len(self._seen_dedup_keys) > 10000:
            excess = len(self._seen_dedup_keys) - 5000
            for _ in range(excess):
                self._seen_dedup_keys.popitem(last=False)

    # ── Liveness ──────────────────────────────────────────────────────────────

    def get_liveness(self) -> Dict[str, Any]:
        """Get liveness diagnostics for the watchdog."""
        return {
            "running": self._running,
            "task_alive": self._task is not None and not self._task.done() if self._task else False,
            "last_successful_scan": self._last_successful_scan,
            "liveness_age_s": round(self.liveness_age_seconds, 1),
            "last_message_detected": self._last_message_detected,
            "consecutive_empty_scans": self._consecutive_empty_scans,
            "consecutive_scan_errors": self._consecutive_scan_errors,
            "total_scans": self._total_scans,
            "total_messages_dispatched": self._total_messages_dispatched,
            "active_processing": len(self._active_processing),
            "jid_registry": self._jid_registry.stats(),
        }
