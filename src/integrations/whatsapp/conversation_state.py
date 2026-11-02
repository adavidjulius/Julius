"""
Julius WhatsApp Integration — Conversation State Engine.

Tracks and manages the conversational lifecycle per contact:
NEW -> GREETING -> ACTIVE -> TOPIC_DISCUSSION -> WAITING_FOR_REPLY -> ENDING -> ENDED -> REOPENED.

Core Responsibilities:
- Accurate semantic and pattern detection for conversational endings ("bye", "gtg", "talk later", etc.).
- State persistence per chat via WhatsAppStorage.
- Prevents the bot from continuing to talk after a conversation has ended.
- Cleanly reopens conversations when the friend messages again later.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional, Tuple

from .models import ConversationState, ConversationStateRecord
from .storage import WhatsAppStorage

logger = logging.getLogger(__name__)

# Patterns that signal the conversation is concluding
_TERMINATION_PATTERNS = [
    r"\b(?:bye|goodbye|cya|tata)\b",
    r"\b(?:see\s+ya|see\s+you(?:\s+later|\s+tomorrow|\s+soon)?)\b",
    r"\b(?:gtg|gotta\s+go|got\s+to\s+go)\b",
    r"\b(?:talk\s+later|talk\s+to\s+you\s+later|catch\s+you\s+later|catch\s+u\s+later|catch\s+ya\s+later)\b",
    r"\b(?:i(?:'ll|\s+will)\s+talk\s+later)\b",
    r"\b(?:good\s*night|gn|gud\s*nyt|gud\s*night|sweet\s*dreams)\b",
    r"\b(?:ok\s*bye|okda\s*bye|bye\s*da|bye\s*bro|bye\s*machan|bye\s*machi)\b",
    r"\b(?:going\s+to\s+sleep|sleep\s+now|heading\s+to\s+bed|gonna\s+sleep)\b",
    r"\b(?:take\s*care|tc)\b",
]

_COMPILED_TERMINATION_PATTERNS = [
    re.compile(pat, re.IGNORECASE) for pat in _TERMINATION_PATTERNS
]

# Patterns that indicate a greeting/start
_GREETING_PATTERNS = [
    r"^(?:hi|hey|hello|vanakkam|dei|machi|machan|thala|yo|sup|whats\s*up|wassup)\b",
]
_COMPILED_GREETING_PATTERNS = [
    re.compile(pat, re.IGNORECASE) for pat in _GREETING_PATTERNS
]


class ConversationStateMachine:
    """Manages the state transitions for WhatsApp conversations."""

    def __init__(self, storage: WhatsAppStorage) -> None:
        self._storage = storage

    def is_termination_signal(self, text: str) -> Tuple[bool, str]:
        """Check if incoming text is a farewell or conversation ending signal.

        Returns (is_ending, matched_phrase).
        """
        clean = text.strip().lower()
        if not clean:
            return False, ""

        # Questions about why/when someone said goodbye or left are inquiries, not farewells
        if "?" in clean and any(clean.startswith(q) for q in ("why", "how", "when", "who", "what", "did", "are")):
            return False, ""

        words = clean.split()
        if len(words) > 15:
            return False, ""

        for pat in _COMPILED_TERMINATION_PATTERNS:
            match = pat.search(clean)
            if match:
                # If message ends with question mark and isn't a direct sign-off, avoid false positive
                if clean.endswith("?") and not any(w in clean for w in ("ok bye?", "bye?")):
                    continue
                return True, match.group(0)

        return False, ""

    def is_greeting_signal(self, text: str) -> bool:
        """Check if incoming text begins with a standard greeting."""
        clean = text.strip().lower()
        for pat in _COMPILED_GREETING_PATTERNS:
            if pat.search(clean):
                return True
        return False

    def get_state(self, chat_name: str) -> ConversationStateRecord:
        """Retrieve existing state or create a fresh NEW state record."""
        rec = self._storage.get_conversation_state(chat_name)
        if not rec:
            rec = ConversationStateRecord(
                chat_name=chat_name,
                state=ConversationState.NEW.value,
                last_message_at=time.time(),
            )
            self._storage.save_conversation_state(rec)
        return rec

    def on_incoming_message(
        self, chat_name: str, sender_name: str, text: str
    ) -> Tuple[ConversationStateRecord, bool]:
        """Process an incoming message and update conversation state.

        Returns:
            (updated_state_record, is_ending_turn)
            where is_ending_turn indicates the agent should wrap up and end.
        """
        now = time.time()
        current = self.get_state(chat_name)
        old_state = current.state
        new_state = old_state
        is_ending = False
        termination_phrase = ""

        # Check for termination signal
        ending_detected, phrase = self.is_termination_signal(text)

        if old_state == ConversationState.ENDED.value:
            # Reopening an ended conversation!
            new_state = ConversationState.REOPENED.value
            logger.info(
                "[STATE] Contact: %s | Reopening ended conversation after arrival of new text",
                chat_name,
            )
            # If the reopening message is already a bye (unlikely but possible)
            if ending_detected:
                new_state = ConversationState.ENDING.value
                is_ending = True
                termination_phrase = phrase
            else:
                new_state = ConversationState.ACTIVE.value

        elif ending_detected:
            # Peer wants to conclude conversation
            new_state = ConversationState.ENDING.value
            is_ending = True
            termination_phrase = phrase
            logger.info(
                "[STATE] Contact: %s | Termination detected ('%s') -> transitioning to ENDING",
                chat_name,
                phrase,
            )

        elif old_state in (
            ConversationState.NEW.value,
            ConversationState.GREETING.value,
            ConversationState.REOPENED.value,
        ):
            if self.is_greeting_signal(text):
                new_state = ConversationState.GREETING.value
            else:
                new_state = ConversationState.ACTIVE.value

        elif old_state == ConversationState.WAITING_FOR_REPLY.value:
            new_state = ConversationState.ACTIVE.value

        else:
            new_state = ConversationState.ACTIVE.value

        current.previous_state = old_state
        current.state = new_state
        current.last_message_at = now
        current.last_sender = sender_name
        current.turn_count += 1
        if termination_phrase:
            current.termination_phrase = termination_phrase

        self._storage.save_conversation_state(current)
        logger.info(
            "[STATE] Contact: %s | State transition: %s -> %s (turns=%d)",
            chat_name,
            old_state,
            new_state,
            current.turn_count,
        )
        return current, is_ending

    def on_outgoing_message_sent(self, chat_name: str, text: str) -> ConversationStateRecord:
        """Update conversation state after our reply has been successfully sent.

        If we were in ENDING state, our farewell reply completes the wrap-up,
        so we transition to ENDED.
        """
        now = time.time()
        current = self.get_state(chat_name)
        old_state = current.state

        if old_state == ConversationState.ENDING.value:
            current.state = ConversationState.ENDED.value
            logger.info(
                "[STATE] Contact: %s | Farewell sent. Transitioning ENDING -> ENDED (conversation closed)",
                chat_name,
            )
        elif old_state in (
            ConversationState.ACTIVE.value,
            ConversationState.GREETING.value,
            ConversationState.NEW.value,
            ConversationState.REOPENED.value,
        ):
            # Check if our own message asked a question
            if "?" in text:
                current.state = ConversationState.WAITING_FOR_REPLY.value
            else:
                current.state = ConversationState.ACTIVE.value

        current.previous_state = old_state
        current.last_message_at = now
        current.last_sender = "David Julius"
        self._storage.save_conversation_state(current)
        return current

    def should_suppress_replies(self, chat_name: str) -> bool:
        """Check if chat is in ENDED state and should not receive unsolicited replies."""
        rec = self.get_state(chat_name)
        return rec.state == ConversationState.ENDED.value
