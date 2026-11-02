"""
Julius WhatsApp Integration — Message Sender.

Sends messages through the WhatsApp Web UI with natural typing delays
and loop prevention. Records all outgoing messages.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import time
import uuid
from typing import List, Optional

from .browser import WhatsAppBrowserAdapter
from .config import WhatsAppConfig
from .models import SentMessageRecord
from .storage import WhatsAppStorage

logger = logging.getLogger(__name__)


class WhatsAppSender:
    """
    Sends messages via WhatsApp Web with natural behavior.

    Features:
    - Natural typing delay based on message length
    - Records all sent messages for dedup/loop prevention
    - Multi-message support (max 3 consecutive)
    - Rate limiting checks
    """

    def __init__(
        self,
        browser: WhatsAppBrowserAdapter,
        storage: WhatsAppStorage,
        config: WhatsAppConfig,
        adapter: Optional[Any] = None,
    ) -> None:
        self._browser = browser
        self._storage = storage
        self._config = config
        if adapter is not None:
            self._adapter = adapter
        else:
            from .adapter import WhatsAppAdapter
            self._adapter = WhatsAppAdapter(browser)
        self._paused = False
        self._last_send_time: float = 0.0
        self._total_sends: int = 0
        self._dom_lock = asyncio.Lock()

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def total_sends(self) -> int:
        return self._total_sends

    @property
    def last_send_time(self) -> float:
        return self._last_send_time

    def pause(self) -> None:
        """Pause all outgoing messages."""
        self._paused = True
        logger.info("WhatsApp sender PAUSED")

    def resume(self) -> None:
        """Resume outgoing messages."""
        self._paused = False
        logger.info("WhatsApp sender RESUMED")

    async def send_message(
        self,
        chat_name: str,
        text: str,
        chat_id: str = "",
        typing_delay: bool = False,
    ) -> bool:
        """
        Send a single message to a chat.

        Args:
            chat_name: Display name of the chat
            text: Message text to send
            chat_id: Chat identifier for recording
            typing_delay: Whether to simulate typing delay (default False for instant response)

        Returns:
            True if message was sent successfully
        """
        if self._paused:
            logger.warning("Send blocked: sender is paused")
            return False

        if not self._browser.is_connected:
            logger.error("Cannot send: browser not connected")
            return False

        if not text.strip():
            logger.warning("Cannot send empty message")
            return False

        # Rate limit check
        rate_key_chat = f"chat:{chat_name}"
        rate_key_global = "global"
        if not self._storage.check_rate_limit(
            rate_key_chat, self._config.max_auto_replies_per_chat_per_hour
        ):
            logger.warning("Rate limited: too many messages to '%s'", chat_name)
            return False
        if not self._storage.check_rate_limit(
            rate_key_global, self._config.max_auto_replies_global_per_hour
        ):
            logger.warning("Rate limited: global message limit reached")
            return False

        # ── STRICT WHITELIST GATE (last line of defense) ──────────────
        # NEVER send a message to anyone not explicitly in the allowed list.
        # This is the absolute final safety check before any outbound message.
        from .config import is_self_chat, is_target_peer_chat
        is_allowed = is_self_chat(chat_name) or is_target_peer_chat(chat_name)
        if not is_allowed:
            cfg = self._storage.get_chat_config(chat_name)
            if cfg and cfg.enabled:
                is_allowed = True
        if not is_allowed:
            logger.critical(
                "SENDER BLOCKED: Refusing to send message to '%s' — NOT in whitelist! "
                "Text: %s...",
                chat_name, text[:50],
            )
            return False

        # Fast path: Direct send via WhatsApp Web internal bridge (sub-30ms, no UI navigation!)
        direct_sent = False
        if hasattr(self._browser, "send_direct_message"):
            direct_target = chat_id or chat_name
            try:
                res = self._browser.send_direct_message(direct_target, text)
                if asyncio.iscoroutine(res):
                    direct_sent = await res
                elif isinstance(res, bool):
                    direct_sent = res
                if not direct_sent and chat_id and chat_name and chat_id != chat_name:
                    res2 = self._browser.send_direct_message(chat_name, text)
                    if asyncio.iscoroutine(res2):
                        direct_sent = await res2
                    elif isinstance(res2, bool):
                        direct_sent = res2
            except Exception as e:
                logger.debug("Direct send check error: %s", e)

        success = direct_sent
        if not success:
            # Fallback path: Navigate in UI and type via Lexical editor (protected by DOM lock)
            async with self._dom_lock:
                navigated = await self._browser.navigate_to_chat(chat_name, jid=chat_id)
                if not navigated:
                    logger.error("Failed to navigate to chat '%s'", chat_name)
                    return False

                # Natural typing delay (if explicitly enabled and delay > 0)
                if typing_delay:
                    delay = self._compute_typing_delay(text)
                    if delay > 0:
                        logger.debug("Typing delay: %.1fs for %d chars", delay, len(text))
                        await asyncio.sleep(delay)

                # Send the message with strict recipient verification
                success = await self._browser.type_and_send(text, expected_chat=chat_name)
        if success:
            # Record for loop prevention
            stable_chat_id = chat_id or hashlib.sha256(
                chat_name.lower().strip().encode("utf-8")
            ).hexdigest()[:16]
            record = SentMessageRecord(
                message_id=str(uuid.uuid4())[:12],
                chat_id=stable_chat_id,
                content_hash=SentMessageRecord.compute_hash(text),
                timestamp=time.time(),
                text=text,
            )
            self._storage.record_sent_message(record)

            # Persist to message history so future LLM prompts know what David said
            from .models import MessageType, WhatsAppMessage
            wa_sent = WhatsAppMessage(
                id=f"sent_{record.message_id}",
                chat_id=stable_chat_id,
                chat_name=chat_name,
                sender_id="me",
                sender_name="David",
                timestamp=record.timestamp,
                text=text,
                is_group=isinstance(stable_chat_id, str) and stable_chat_id.endswith("@g.us"),
                is_from_me=True,
                message_type=MessageType.TEXT,
                raw_reference=record.message_id,
            )
            self._storage.save_message(wa_sent)

            self._last_send_time = time.time()
            self._total_sends += 1
            logger.info("Message sent to '%s': %s...", chat_name, text[:50])
        else:
            logger.error("Failed to send message to '%s'", chat_name)

        return success

    async def send_multi_message(
        self,
        chat_name: str,
        messages: List[str],
        chat_id: str = "",
    ) -> bool:
        """
        Send multiple consecutive messages (natural multi-message style).

        Max 3 messages. Each gets a natural inter-message delay.
        """
        if len(messages) > 3:
            logger.warning("Truncating multi-message to 3 (was %d)", len(messages))
            messages = messages[:3]

        for i, text in enumerate(messages):
            success = await self.send_message(
                chat_name=chat_name,
                text=text,
                chat_id=chat_id,
                typing_delay=False,
            )
            if not success:
                return False

            # Minimal pause between consecutive messages for DOM settlement
            if i < len(messages) - 1:
                await asyncio.sleep(0.05)

        return True

    async def react_to_message(self, chat_name: str, emoji: str) -> bool:
        """React to the last incoming message in chat_name with an emoji (👍, ❤️, 😂, 😮, 😢, 🙏)."""
        if not self._browser.is_connected:
            return False
        navigated = await self._browser.navigate_to_chat(chat_name)
        if not navigated:
            return False
        success = await self._browser.react_to_message(emoji)
        if success:
            logger.info("Reacted with '%s' to message in '%s'", emoji, chat_name)
        return success

    async def send_sticker(self, chat_name: str, theme: str = "") -> bool:
        """Send a fitting sticker to chat_name."""
        if not self._browser.is_connected:
            return False
        navigated = await self._browser.navigate_to_chat(chat_name)
        if not navigated:
            return False
        success = await self._browser.send_sticker(theme)
        if success:
            logger.info("Sent sticker to '%s'", chat_name)
            self._last_send_time = time.time()
            self._total_sends += 1
        return success

    async def send_gif(self, chat_name: str, search_query: str) -> bool:
        """Search and send a fitting GIF via GIPHY to chat_name."""
        if not self._browser.is_connected:
            return False
        navigated = await self._browser.navigate_to_chat(chat_name)
        if not navigated:
            return False
        success = await self._browser.send_gif(search_query)
        if success:
            logger.info("Sent GIF (%s) to '%s'", search_query, chat_name)
            self._last_send_time = time.time()
            self._total_sends += 1
        return success

    async def send_document(
        self, chat_name: str, file_path: str, caption: str = "", chat_id: str = ""
    ) -> bool:
        """Send a document or PDF file to chat_name using WhatsAppAdapter."""
        return await self.send_media(
            chat_name=chat_name,
            file_path=file_path,
            media_type="document",
            caption=caption,
            chat_id=chat_id,
        )

    async def send_image(
        self, chat_name: str, file_path: str, caption: str = "", chat_id: str = ""
    ) -> bool:
        """Send an image/photo file to chat_name using WhatsAppAdapter."""
        return await self.send_media(
            chat_name=chat_name,
            file_path=file_path,
            media_type="image",
            caption=caption,
            chat_id=chat_id,
        )

    async def send_media(
        self,
        chat_name: str,
        file_path: str,
        media_type: str = "auto",
        caption: str = "",
        chat_id: str = "",
    ) -> bool:
        """Send media (image, document, PDF) to chat_name using verified WhatsAppAdapter protocol."""
        if self._paused or not self._browser.is_connected:
            return False

        from .config import is_self_chat, is_target_peer_chat
        is_allowed = is_self_chat(chat_name) or is_target_peer_chat(chat_name)
        if not is_allowed:
            cfg = self._storage.get_chat_config(chat_name)
            if cfg and cfg.enabled:
                is_allowed = True
        if not is_allowed:
            logger.critical(
                "SENDER BLOCKED: Refusing to send %s to '%s' — NOT in whitelist!",
                media_type,
                chat_name,
            )
            return False

        async with self._dom_lock:
            # First try the robust WhatsAppAdapter 11-step protocol
            success = False
            try:
                success = await self._adapter.send_media(
                    chat_name=chat_name,
                    file_path=file_path,
                    media_type=media_type,
                    caption=caption,
                    jid=chat_id,
                )
            except Exception as e:
                logger.warning(
                    "[MEDIA] WhatsAppAdapter send_media failed with exception: %s. Falling back to browser directly.",
                    e,
                )

            # Fallback to browser method if adapter failed or not supported
            if not success and hasattr(self._browser, "send_document") and media_type in ("document", "pdf"):
                try:
                    success = await self._browser.send_document(
                        chat_name=chat_name, file_path=file_path, caption=caption, jid=chat_id
                    )
                except Exception as be:
                    logger.debug("Browser send_document fallback failed: %s", be)
            elif not success and hasattr(self._browser, "send_image") and media_type == "image":
                try:
                    success = await self._browser.send_image(
                        chat_name=chat_name, file_path=file_path, caption=caption, jid=chat_id
                    )
                except Exception as be:
                    logger.debug("Browser send_image fallback failed: %s", be)

            if success:
                self._last_send_time = time.time()
                self._total_sends += 1
                logger.info(
                    "Successfully dispatched %s '%s' to '%s'",
                    media_type,
                    file_path,
                    chat_name,
                )
            return success

    def _compute_typing_delay(self, text: str) -> float:
        """Calculate a natural typing delay based on message length."""
        word_count = len(text.split())

        if word_count <= 5:  # short reply
            return random.uniform(
                self._config.typing_delay_short_min,
                self._config.typing_delay_short_max,
            )
        elif word_count <= 20:  # medium reply
            return random.uniform(
                self._config.typing_delay_medium_min,
                self._config.typing_delay_medium_max,
            )
        else:  # longer reply
            return random.uniform(
                self._config.typing_delay_long_min,
                self._config.typing_delay_long_max,
            )
