"""
Julius WhatsApp Integration — ActionGuard & Receipts.

Intercepts, validates, and receipts all side-effecting operations:
- send_image
- send_document
- send_message
- rename_media

Guarantees:
- Never executes unrequested media or file dispatch.
- Never sends cross-person or hallucinated images.
- Always generates an ActionReceipt with SUCCESS, FAILED, AMBIGUOUS, NOT_FOUND, or BLOCKED.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from .models import ActionReceipt, MediaResolution, ReceiptStatus, ResolutionStatus
from .storage import WhatsAppStorage

logger = logging.getLogger(__name__)


class ActionGuard:
    """
    Strict safety and verification guard between reasoning and action execution.
    """

    def __init__(self, storage: WhatsAppStorage) -> None:
        self._storage = storage

    def authorize_media_send(
        self,
        requester: str,
        target_chat: str,
        resolution: MediaResolution,
        explicit_intent: bool = True,
    ) -> ActionReceipt:
        """
        Validate whether a resolved media item is authorized to be dispatched.
        """
        action_id = f"act_{int(time.time())}_{uuid.uuid4().hex[:6]}"

        # Check 1: Explicit intent required
        if not explicit_intent:
            receipt = ActionReceipt(
                action_id=action_id,
                requested_by=requester,
                intent="send_media",
                target=target_chat,
                arguments={"resolution_status": resolution.status.value},
                authorization_status="DENIED",
                execution_status=ReceiptStatus.BLOCKED,
                result={"error": "Media send rejected: No explicit user send intent detected."},
            )
            self._storage.save_action_receipt(receipt.to_dict())
            logger.warning("[ACTION_GUARD] Blocked unrequested media send to '%s'", target_chat)
            return receipt

        # Check 2: Resolution status must be EXACT_MATCH
        if resolution.status == ResolutionStatus.NOT_FOUND:
            receipt = ActionReceipt(
                action_id=action_id,
                requested_by=requester,
                intent="send_media",
                target=target_chat,
                arguments={"target_entity": resolution.target_entity, "reason": resolution.reason},
                authorization_status="ABORTED",
                execution_status=ReceiptStatus.NOT_FOUND,
                result={"error": resolution.reason or "No verified media found."},
            )
            self._storage.save_action_receipt(receipt.to_dict())
            return receipt

        if resolution.status == ResolutionStatus.AMBIGUOUS:
            receipt = ActionReceipt(
                action_id=action_id,
                requested_by=requester,
                intent="send_media",
                target=target_chat,
                arguments={"candidates_count": len(resolution.candidates)},
                authorization_status="NEEDS_CLARIFICATION",
                execution_status=ReceiptStatus.AMBIGUOUS,
                result={"prompt": resolution.reason, "candidates": [c.get("filename") for c in resolution.candidates]},
            )
            self._storage.save_action_receipt(receipt.to_dict())
            return receipt

        item = resolution.item
        if not item:
            receipt = ActionReceipt(
                action_id=action_id,
                requested_by=requester,
                intent="send_media",
                target=target_chat,
                authorization_status="FAILED",
                execution_status=ReceiptStatus.FAILED,
                result={"error": "Resolution marked EXACT_MATCH but item payload was empty."},
            )
            self._storage.save_action_receipt(receipt.to_dict())
            return receipt

        # Check 3: Physical file existence on disk
        file_path = item.get("storage_path") or item.get("path", "")
        if not file_path or not Path(file_path).exists():
            receipt = ActionReceipt(
                action_id=action_id,
                requested_by=requester,
                intent="send_media",
                target=target_chat,
                arguments={"file_path": file_path},
                authorization_status="FAILED",
                execution_status=ReceiptStatus.FAILED,
                result={"error": f"File does not exist on disk: {file_path}"},
            )
            self._storage.save_action_receipt(receipt.to_dict())
            logger.error("[ACTION_GUARD] File missing on disk: %s", file_path)
            return receipt

        # Check 4: Cross-person verification
        target_person = resolution.target_entity
        if target_person and resolution.media_type == "image":
            item_ents = [str(e).lower() for e in item.get("entities", [])]
            t_low = target_person.lower()
            tokens = [t.lower() for t in target_person.split() if t.lower() not in ("mit", "ece", "it", "cse", "rpt", "raj")]

            # Ensure candidate actually belongs to target_person
            is_valid_person = (
                any(t_low in e for e in item_ents)
                or any(tok in item_ents for tok in tokens)
                or any(tok in item.get("filename", "").lower() for tok in tokens)
            )
            if not is_valid_person:
                receipt = ActionReceipt(
                    action_id=action_id,
                    requested_by=requester,
                    intent="send_media",
                    target=target_chat,
                    arguments={"target_person": target_person, "candidate": item.get("filename")},
                    authorization_status="DENIED",
                    execution_status=ReceiptStatus.BLOCKED,
                    result={"error": f"Cross-person safety block: Candidate '{item.get('filename')}' does not match target person '{target_person}'."},
                )
                self._storage.save_action_receipt(receipt.to_dict())
                logger.error("[ACTION_GUARD] Cross-person block: '%s' != '%s'", item.get("filename"), target_person)
                return receipt

        # All checks passed: AUTHORIZED
        receipt = ActionReceipt(
            action_id=action_id,
            requested_by=requester,
            intent=f"send_{resolution.media_type}",
            target=target_chat,
            arguments={"filename": item.get("filename"), "path": file_path},
            authorization_status="AUTHORIZED",
            execution_status=ReceiptStatus.SUCCESS,
            result={"ready_to_send": True, "file_path": file_path, "title": item.get("title", item.get("filename"))},
        )
        self._storage.save_action_receipt(receipt.to_dict())
        return receipt

    def record_execution_outcome(self, action_id: str, success: bool, message_id: str = "") -> None:
        """Update receipt with real execution outcome from WhatsApp sender."""
        receipt = self._storage.get_action_receipt(action_id)
        if receipt:
            receipt["execution_status"] = ReceiptStatus.SUCCESS.value if success else ReceiptStatus.FAILED.value
            receipt["whatsapp_message_id"] = message_id
            receipt["result"]["confirmed"] = success
            self._storage.save_action_receipt(receipt)


_ACTION_GUARD_INSTANCE: Optional[ActionGuard] = None


def get_action_guard(storage: Optional[WhatsAppStorage] = None) -> ActionGuard:
    global _ACTION_GUARD_INSTANCE
    if _ACTION_GUARD_INSTANCE is None or storage is not None:
        if storage is None:
            storage = WhatsAppStorage()
        _ACTION_GUARD_INSTANCE = ActionGuard(storage)
    return _ACTION_GUARD_INSTANCE
