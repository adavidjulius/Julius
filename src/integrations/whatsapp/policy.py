"""
Julius WhatsApp Integration — Chat Policy Engine.

Enforces allowlist-based access control. Default: ALL CHATS = DENY.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional, Set

from .config import WhatsAppConfig
from .models import ChatConfig, ChatMode, GroupTrigger, WhatsAppMessage
from .storage import WhatsAppStorage

logger = logging.getLogger(__name__)


class ChatPolicyEngine:
    """
    Evaluates per-chat configuration and determines whether
    Julius should respond to a message.

    Default policy: ALL CHATS = DENY.
    Only explicitly configured and enabled chats receive responses.
    """

    def __init__(self, storage: WhatsAppStorage, config: WhatsAppConfig) -> None:
        self._storage = storage
        self._config = config
        self._cache: Dict[str, ChatConfig] = {}
        self._refresh_cache()

    def _refresh_cache(self) -> None:
        """Refresh the in-memory chat config cache."""
        configs = self._storage.get_all_chat_configs()
        self._cache = {c.chat_name.lower(): c for c in configs}

    def get_chat_config(self, chat_name: str) -> Optional[ChatConfig]:
        """Get config for a chat. Returns None for unconfigured chats."""
        key = chat_name.lower().strip()
        config = self._cache.get(key)
        if config is None:
            # Re-check DB in case of recent additions
            config = self._storage.get_chat_config(chat_name)
            if config:
                self._cache[key] = config

        # Flexible alias matching for contacts (e.g. "Contact Alex" <-> "Alex", "Alexander" <-> "Contact Alexander")
        if config is None:
            from .config import get_canonical_target_peer_name
            canonical = get_canonical_target_peer_name(chat_name)
            if canonical and canonical.lower() in self._cache:
                return self._cache[canonical.lower()]

            key_words = [w for w in key.split() if len(w) >= 4 and w not in ("the", "dept", "team", "eng")]
            for stored_key, stored_cfg in self._cache.items():
                # Strict disambiguation: Alex and Alexander must never match each other
                if ("alexander" in key and "alex" in stored_key) or ("alexander" in stored_key and "alex" in key):
                    continue
                if len(stored_key) <= 3 and stored_key not in key.split():
                    continue
                if len(key) <= 3 and key not in stored_key.split():
                    continue
                if stored_key in key or key in stored_key:
                    return stored_cfg
                tokens = [t for t in stored_key.split() if len(t) >= 4 and t not in ("mit", "the", "dept", "it", "ece")]
                if any(t in key for t in tokens):
                    return stored_cfg
                if any(t.startswith(kw) or kw.startswith(t) for t in tokens for kw in key_words):
                    return stored_cfg

        return config

    def should_process(self, message: WhatsAppMessage) -> bool:
        """
        Determine whether Julius should process this message.

        STRICT WHITELIST POLICY — Default: DENY ALL.
        Only messages from explicitly configured and enabled chats are processed.
        NO auto-enrollment of unknown contacts or groups under ANY circumstance.

        Returns False for:
        - Unconfigured chats (NEVER auto-enrolled)
        - Disabled chats
        - Chats in OFF mode
        - Messages outside allowed hours
        - Group messages that don't match trigger rules
        - Own outgoing messages
        """
        from .config import is_self_chat

        # Ignore invalid/too-short chat names, bots, or tab headers
        c_clean = (message.chat_name or "").lower().strip()
        if len(c_clean) <= 2:
            return False
        if c_clean in ("unread", "all", "groups", "favorites", "whatsapp", "meta", "support", "help"):
            return False

        # Filter out obvious marketing/broadcast messages or OTPs
        msg_text_lower = (message.text or "").lower()
        spam_indicators = [
            "health insurance",
            "free home visit",
            "salary secrets",
            "zoom.us",
            "webinar",
            "dear customer",
            "claim support",
            "promo code",
            "unsubscribe",
            "otp is",
            "verification code",
        ]
        if any(ind in msg_text_lower for ind in spam_indicators):
            logger.info("Ignoring promotional/broadcast message in '%s'", message.chat_name)
            return False

        # Never process our own messages in peer chats (allow self-chat)
        if message.is_from_me and not is_self_chat(message.chat_name):
            return False

        # Allow David's self-chat unconditionally
        if is_self_chat(message.chat_name):
            return True

        # ── STRICT WHITELIST GATE ─────────────────────────────────────
        # Look up chat config. If not found, DENY unconditionally.
        # NO auto-enrollment. NO exceptions.
        config = self.get_chat_config(message.chat_name)
        if config is None:
            logger.info(
                "STRICT DENY: Message from unconfigured chat '%s' (sender=%s, is_group=%s). "
                "Not in whitelist — ignoring.",
                message.chat_name, message.sender_name, message.is_group,
            )
            return False

        if not config.enabled:
            logger.debug("Chat '%s' is disabled, ignoring.", message.chat_name)
            return False

        if config.mode == ChatMode.OFF:
            logger.debug("Chat '%s' is in OFF mode, ignoring.", message.chat_name)
            return False

        # Check allowed hours
        if not self._is_within_allowed_hours(config):
            logger.debug("Outside allowed hours for chat: %s", message.chat_name)
            return False

        # ALL group chats require explicit trigger match, regardless of target peer status
        if message.is_group and not self._group_trigger_matches(message, config):
            logger.debug("Group trigger not matched for '%s' in '%s'",
                         message.sender_name, message.chat_name)
            return False

        return True

    def get_mode(self, chat_name: str) -> ChatMode:
        """Get the operating mode for a chat."""
        config = self.get_chat_config(chat_name)
        if config is None:
            return self._config.unknown_chats_mode
        return config.mode

    def reload(self) -> None:
        """Reload configs from storage."""
        self._refresh_cache()

    def get_all_configs(self) -> List[ChatConfig]:
        """Get all chat configs."""
        self._refresh_cache()
        return list(self._cache.values())

    def get_enabled_chat_names(self) -> Set[str]:
        """Get the set of enabled chat names for the listener."""
        self._refresh_cache()
        return {
            config.chat_name
            for config in self._cache.values()
            if config.enabled and config.mode != ChatMode.OFF
        }

    def add_chat(self, config: ChatConfig) -> None:
        """Add or update a chat configuration."""
        self._storage.save_chat_config(config)
        self._cache[config.chat_name.lower()] = config
        logger.info("Chat '%s' configured: mode=%s, enabled=%s",
                     config.chat_name, config.mode.value, config.enabled)

    def remove_chat(self, chat_name: str) -> bool:
        """Remove a chat from the allowlist."""
        removed = self._storage.delete_chat_config(chat_name)
        self._cache.pop(chat_name.lower(), None)
        if removed:
            logger.info("Chat '%s' removed from allowlist", chat_name)
        return removed

    def _is_within_allowed_hours(self, config: ChatConfig) -> bool:
        """Check if current time is within the chat's allowed hours."""
        if config.allowed_hours_start is None or config.allowed_hours_end is None:
            return True  # No restriction

        current_hour = datetime.now().hour
        start = config.allowed_hours_start
        end = config.allowed_hours_end

        if start <= end:
            return start <= current_hour < end
        else:
            # Wraps around midnight
            return current_hour >= start or current_hour < end

    def _group_trigger_matches(self, message: WhatsAppMessage, config: ChatConfig) -> bool:
        """Check if a group message matches the configured trigger."""
        trigger = config.group_trigger

        if trigger == GroupTrigger.NEVER:
            return False

        if trigger == GroupTrigger.EVERY_RELEVANT:
            return True

        if trigger == GroupTrigger.WHEN_MENTIONED:
            # Check if the user's name or common references are mentioned
            text_lower = message.text.lower()
            mention_keywords = ["julius", "david", "@david", "@julius"]
            return any(kw in text_lower for kw in mention_keywords)

        if trigger == GroupTrigger.WHEN_REPLYING_TO_ME:
            # Check if the message is a reply to one of our messages
            return message.quoted_text is not None  # simplified: any reply

        return False
