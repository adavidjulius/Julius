"""
Julius WhatsApp Integration — Adaptive Message Debouncer.

Accumulates rapid-fire messages within a per-chat time window before
dispatching to the router. Prevents wasted LLM calls when a contact
sends multiple quick messages (e.g. "dei" / "where are you" / "coming?").

Strategy:
- Each new incoming message resets the chat's debounce timer.
- When the timer fires (no new message within the window), all
  accumulated messages are merged and dispatched as one turn.
- The window is adaptive: frequent senders get a shorter window.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

from .models import WhatsAppMessage

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

DEFAULT_DEBOUNCE_WINDOW_S = 2.5  # seconds to wait for more messages
MIN_DEBOUNCE_WINDOW_S = 1.0     # minimum window for fast typers
MAX_DEBOUNCE_WINDOW_S = 5.0     # maximum window for slow contexts
MAX_ACCUMULATED_MESSAGES = 10   # safety cap on accumulated messages
MAX_PENDING_CHATS = 200         # prevent unbounded memory growth


@dataclass
class _PendingBurst:
    """State for a single chat's pending message burst."""
    messages: List[WhatsAppMessage] = field(default_factory=list)
    timer_handle: Optional[asyncio.TimerHandle] = None
    first_message_time: float = 0.0
    chat_name: str = ""


class MessageDebouncer:
    """
    Per-chat adaptive message debouncer.

    Usage:
        debouncer = MessageDebouncer(dispatch_fn=router.route_message)
        debouncer.enqueue(message)  # called from listener

    When the debounce window expires, all accumulated messages for that
    chat are merged into a single WhatsAppMessage and dispatched.
    """

    def __init__(
        self,
        dispatch_fn: Callable[[WhatsAppMessage], Coroutine[Any, Any, None]],
        default_window: float = DEFAULT_DEBOUNCE_WINDOW_S,
    ) -> None:
        self._dispatch_fn = dispatch_fn
        self._default_window = default_window
        self._pending: OrderedDict[str, _PendingBurst] = OrderedDict()
        self._chat_avg_gap: Dict[str, float] = {}  # adaptive: running avg gap
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def enqueue(self, message: WhatsAppMessage) -> None:
        """
        Enqueue an incoming message for debounced dispatch.

        If a burst is already pending for this chat, the message is appended
        and the timer is reset. Otherwise a new burst is started.
        """
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                # No event loop — dispatch immediately as fallback
                asyncio.ensure_future(self._dispatch_fn(message))
                return

        chat_key = message.chat_name.lower().strip()
        now = time.time()

        if chat_key in self._pending:
            burst = self._pending[chat_key]
            # Cancel existing timer
            if burst.timer_handle:
                burst.timer_handle.cancel()

            # Update adaptive gap
            if burst.messages:
                last_ts = burst.messages[-1].timestamp
                gap = now - last_ts
                self._update_avg_gap(chat_key, gap)

            burst.messages.append(message)

            # Safety cap
            if len(burst.messages) >= MAX_ACCUMULATED_MESSAGES:
                self._fire_burst(chat_key)
                return
        else:
            # Evict oldest pending chat if at capacity
            if len(self._pending) >= MAX_PENDING_CHATS:
                oldest_key, oldest_burst = self._pending.popitem(last=False)
                if oldest_burst.timer_handle:
                    oldest_burst.timer_handle.cancel()
                # Fire the evicted burst
                asyncio.ensure_future(self._dispatch_merged(oldest_key, oldest_burst))

            burst = _PendingBurst(
                messages=[message],
                first_message_time=now,
                chat_name=message.chat_name,
            )
            self._pending[chat_key] = burst

        window = self._compute_window(chat_key)
        burst.timer_handle = self._loop.call_later(
            window, self._fire_burst, chat_key
        )

    def _compute_window(self, chat_key: str) -> float:
        """Compute adaptive debounce window based on the contact's typing speed."""
        avg_gap = self._chat_avg_gap.get(chat_key)
        if avg_gap is None:
            return self._default_window

        # If they type fast (avg gap < 1.5s), use a shorter window
        # If they type slow (avg gap > 4s), use a longer window
        adaptive = min(max(avg_gap * 1.5, MIN_DEBOUNCE_WINDOW_S), MAX_DEBOUNCE_WINDOW_S)
        return adaptive

    def _update_avg_gap(self, chat_key: str, gap: float) -> None:
        """Exponential moving average of inter-message gaps."""
        prev = self._chat_avg_gap.get(chat_key)
        if prev is None:
            self._chat_avg_gap[chat_key] = gap
        else:
            # EMA with α=0.3
            self._chat_avg_gap[chat_key] = 0.3 * gap + 0.7 * prev

    def _fire_burst(self, chat_key: str) -> None:
        """Timer callback: dispatch the accumulated burst for a chat."""
        burst = self._pending.pop(chat_key, None)
        if burst is None or not burst.messages:
            return

        if burst.timer_handle:
            burst.timer_handle.cancel()

        asyncio.ensure_future(self._dispatch_merged(chat_key, burst))

    async def _dispatch_merged(self, chat_key: str, burst: _PendingBurst) -> None:
        """Merge burst messages and dispatch as a single WhatsAppMessage."""
        messages = burst.messages
        if not messages:
            return

        if len(messages) == 1:
            # Single message — dispatch as-is
            merged = messages[0]
        else:
            # Multiple messages — merge text with newlines
            combined_text = "\n".join(m.text.strip() for m in messages if m.text.strip())
            # Use the LAST message as the base (most recent dedup_key, timestamp)
            base = messages[-1]
            merged = WhatsAppMessage(
                id=base.id,
                chat_id=base.chat_id,
                chat_name=base.chat_name,
                sender_id=base.sender_id,
                sender_name=base.sender_name,
                timestamp=base.timestamp,
                text=combined_text,
                quoted_message_id=base.quoted_message_id,
                quoted_text=base.quoted_text,
                is_group=base.is_group,
                is_from_me=base.is_from_me,
                message_type=base.message_type,
                attachment_metadata=base.attachment_metadata,
                raw_reference=base.raw_reference,
            )
            logger.info(
                "Debounced %d messages for '%s' into single turn (%d chars)",
                len(messages), burst.chat_name, len(combined_text),
            )

        try:
            await self._dispatch_fn(merged)
        except Exception as e:
            logger.error("Debouncer dispatch error for '%s': %s", burst.chat_name, e)

    @property
    def pending_count(self) -> int:
        """Number of chats with pending debounce bursts."""
        return len(self._pending)

    def cancel_all(self) -> int:
        """Cancel all pending debounce timers. Returns count cancelled."""
        count = 0
        for key in list(self._pending.keys()):
            burst = self._pending.pop(key, None)
            if burst and burst.timer_handle:
                burst.timer_handle.cancel()
                count += 1
        return count

