"""
Julius WhatsApp Integration — Answer Verifier.

Grounds and verifies agent responses before sending.
Ensures:
- No "fake success" ("Sent", "Done", "Saved") if backend action failed.
- Explains exact failure or missing data truthfully.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from .models import ActionReceipt, ReceiptStatus

logger = logging.getLogger(__name__)


class AnswerVerifier:
    """Verifies that user-facing text truthfully reflects backend execution."""

    @staticmethod
    def verify_and_ground(
        reply_text: str,
        action_receipt: Optional[ActionReceipt] = None,
        context_facts: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Verify reply text against action receipt and facts.
        Replaces fabricated claims with truthful status if necessary.
        """
        if not reply_text:
            return ""

        clean_reply = reply_text.strip()
        rep_low = clean_reply.lower()

        # Check for claims of success
        claims_sent = any(w in rep_low for w in ["sent", "i've sent", "i have sent", "sending you", "here is the", "here's the", "attached"])
        claims_saved = any(w in rep_low for w in ["saved", "stored", "kept it in memory"])

        if action_receipt:
            status = action_receipt.execution_status
            if status == ReceiptStatus.NOT_FOUND:
                err = action_receipt.result.get("error", "The requested item was not found in verified storage.")
                logger.info("[ANSWER_VERIFIER] Intercepted response for NOT_FOUND: substituting truthful explanation.")
                return err

            elif status == ReceiptStatus.AMBIGUOUS:
                prompt = action_receipt.result.get("prompt", "Multiple items match your request. Which one do you mean?")
                return prompt

            elif status in (ReceiptStatus.FAILED, ReceiptStatus.BLOCKED):
                err = action_receipt.result.get("error", "The operation could not be completed.")
                if claims_sent:
                    return f"I found the file, but could not confirm sending it through WhatsApp Web: {err}"
                elif claims_saved:
                    return f"Could not save file to workspace memory: {err}"
                return f"Could not complete action: {err}"

        # If claims to have sent something but no receipt exists
        if claims_sent and not action_receipt:
            # Check if this was just a greeting or promise to send
            if "i will send" in rep_low or "let me send" in rep_low or "will share" in rep_low:
                return clean_reply
            # If claimed "sent" without action
            if any(w in rep_low for w in ["sent it", "i sent", "sent the"]):
                logger.warning("[ANSWER_VERIFIER] Suppressed unverified 'Sent' claim without receipt.")
                return "I located the details, but no file was dispatched."

        return clean_reply
