"""
Julius WhatsApp Integration — Safety Gate.

Auto-mode safety escalation. Detects messages that require human
approval even when the chat is in auto mode.
"""

from __future__ import annotations

import logging
import re
from typing import List, Tuple

from .models import Confidence, WhatsAppMessage

logger = logging.getLogger(__name__)

# Pattern categories that require human approval
_FINANCIAL_PATTERNS = [
    r"(?:send|transfer|pay|deposit|₹|rs\.?|usd|\$|€|£)\s*\d",
    r"\d+\s*(?:rupees|dollars|euros|pounds|bucks|lakhs?|crores?|k\b)",
    r"(?:upi|gpay|paytm|phonepe|bank\s*transfer|wire)",
    r"(?:credit\s*card|debit\s*card|account\s*number)",
    r"(?:loan|debt|borrow|lend|owe|investment|stock|crypto)",
]

_COMMITMENT_PATTERNS = [
    r"(?:promise|commit|guarantee|swear|pledge)",
    r"(?:i(?:'ll| will)\s+(?:definitely|surely|certainly|absolutely))",
    r"(?:book|reserve|confirm)\s+(?:ticket|flight|hotel|table|appointment|slot)",
    r"(?:sign|agree)\s+(?:contract|agreement|deal|document)",
    r"(?:deadline|due\s*date|submit\s*by|before\s+\d)",
]

_LEGAL_MEDICAL_PATTERNS = [
    r"(?:lawyer|attorney|court|judge|sue|legal|lawsuit)",
    r"(?:diagnos|prescri|medic|doctor|hospital|treatment|symptom)",
    r"(?:insurance|policy|claim|coverage)",
]

_SENSITIVE_PATTERNS = [
    r"(?:password|secret|confidential|private|ssn|social\s*security)",
    r"(?:break\s*up|divorce|cheating|affair)",
    r"(?:pretend|impersonate|act\s*as|pose\s*as)",
    r"(?:don'?t\s+tell|keep\s+(?:it\s+)?secret|between\s+us)",
]

_URGENCY_PATTERNS = [
    r"(?:urgent|emergency|asap|right\s*now|immediately|critical)",
]


class SafetyGate:
    """
    Evaluates incoming messages and generated responses for safety.

    In auto mode, certain message categories automatically escalate
    to human approval. The gate also classifies response confidence.
    """

    def __init__(self) -> None:
        self._compiled_patterns = self._compile_patterns()

    def evaluate_message(self, message: WhatsAppMessage) -> Tuple[Confidence, str]:
        """
        Evaluate an incoming message and return confidence + reason.

        Returns:
            (Confidence, reason_string)
        """
        text = message.text.lower()
        # Strip long base64 blobs or attachment hashes to avoid false positives
        eval_text = re.sub(r"[a-z0-9+/=]{40,}", "", text)

        from .config import is_target_peer_chat, is_self_chat
        is_trusted = is_target_peer_chat(message.chat_name) or is_self_chat(message.chat_name)

        # Check each high-risk pattern category (financial, commitments, credentials, legal/medical)
        for pattern, reason in self._compiled_patterns:
            # Trusted college friends can use casual urgency, commitments, sensitive terms, or debugging terms without escalation
            if is_trusted and reason in (
                "Urgent matter",
                "Commitment/booking/promise",
                "Legal/medical matter",
                "Sensitive/confidential content",
            ):
                continue
            if pattern.search(eval_text):
                return Confidence.LOW, reason

        # Simple factual questions = HIGH confidence
        if self._is_simple_question(text):
            return Confidence.HIGH, "Simple factual question"

        # Short casual messages = HIGH confidence
        word_count = len(text.split())
        if word_count <= 10 and not any(c in text for c in "?!"):
            return Confidence.HIGH, "Short casual message"

        # Medium-length or questions = MEDIUM
        if "?" in text or word_count > 15:
            return Confidence.MEDIUM, "Question or longer message"

        return Confidence.HIGH, "Standard message"

    def evaluate_response(self, response: str, message: WhatsAppMessage) -> Tuple[Confidence, str]:
        """
        Evaluate a generated response for safety before sending.

        Returns:
            (Confidence, reason_string)
        """
        response_lower = response.lower()
        from .config import is_target_peer_chat, is_self_chat
        is_trusted = is_target_peer_chat(message.chat_name) or is_self_chat(message.chat_name)

        # Strict profanity block
        profanity_pattern = re.compile(
            r"\b(?:fuck|fucking|fucker|shit|bitch|bastard|asshole|wtf|wth|damn|crap|dick|pussy|piss|slut|whore|motherfuck|motherfucking)\b",
            re.IGNORECASE,
        )
        if profanity_pattern.search(response_lower):
            return Confidence.LOW, "Response contains profanity or swear words"

        # Check if response contains financial/commitment language
        for pattern, reason in self._compiled_patterns:
            if is_trusted and reason in (
                "Urgent matter",
                "Commitment/booking/promise",
                "Legal/medical matter",
                "Sensitive/confidential content",
            ):
                continue
            if pattern.search(response_lower):
                return Confidence.LOW, f"Response contains: {reason}"

        # Check if response is making promises
        if not is_trusted and any(phrase in response_lower for phrase in [
            "i promise", "i guarantee", "i'll pay", "i'll send",
            "i'll transfer", "i'll book", "i'll sign",
        ]):
            return Confidence.LOW, "Response makes commitments"

        # Very long response might be over-explaining
        if len(response.split()) > 60:
            return Confidence.MEDIUM, "Unusually long response"

        return Confidence.HIGH, "Response appears safe"

    def should_escalate(
        self,
        message_confidence: Confidence,
        response_confidence: Confidence,
    ) -> bool:
        """
        Determine if this interaction should be escalated to human approval.

        Returns True only if either the message or response has LOW confidence (high risk).
        """
        if message_confidence == Confidence.LOW:
            return True
        if response_confidence == Confidence.LOW:
            return True
        return False

    def check_escalation(
        self,
        message: WhatsAppMessage,
        response: str = "",
    ) -> Tuple[bool, str]:
        """
        Convenience check: evaluates message and optional response.
        Returns (should_escalate, reason).
        """
        msg_conf, msg_reason = self.evaluate_message(message)
        if msg_conf == Confidence.LOW:
            return True, msg_reason

        if response:
            resp_conf, resp_reason = self.evaluate_response(response, message)
            if resp_conf == Confidence.LOW:
                return True, resp_reason
            if self.should_escalate(msg_conf, resp_conf):
                return True, f"{msg_reason}; {resp_reason}"

        return False, ""

    def classify_confidence(self, text: str) -> Confidence:
        """Classify confidence of a message or response text."""
        dummy = WhatsAppMessage(
            id="temp", chat_id="temp", chat_name="temp", sender_id="temp", sender_name="temp",
            timestamp=0.0, text=text,
        )
        conf, _ = self.evaluate_message(dummy)
        return conf

    def _is_simple_question(self, text: str) -> bool:
        """Check if this is a simple factual question."""
        simple_patterns = [
            r"^(?:what|when|where|how|who|which)\s+(?:time|day|date)",
            r"^(?:are you|you)\s+(?:coming|free|available|busy|there|home|here)",
            r"^(?:did you|have you)\s+(?:eat|sleep|reach|see|get|finish)",
            r"^(?:what's|whats|wats)\s+(?:up|happening|going on)",
        ]
        for pat in simple_patterns:
            if re.search(pat, text):
                return True
        return False

    def _compile_patterns(self) -> List[Tuple[re.Pattern, str]]:
        """Compile all safety patterns."""
        compiled = []

        for pat in _FINANCIAL_PATTERNS:
            compiled.append((re.compile(pat, re.IGNORECASE), "Financial/payment matter"))

        for pat in _COMMITMENT_PATTERNS:
            compiled.append((re.compile(pat, re.IGNORECASE), "Commitment/booking/promise"))

        for pat in _LEGAL_MEDICAL_PATTERNS:
            compiled.append((re.compile(pat, re.IGNORECASE), "Legal/medical matter"))

        for pat in _SENSITIVE_PATTERNS:
            compiled.append((re.compile(pat, re.IGNORECASE), "Sensitive/confidential content"))

        for pat in _URGENCY_PATTERNS:
            compiled.append((re.compile(pat, re.IGNORECASE), "Urgent matter"))

        return compiled
