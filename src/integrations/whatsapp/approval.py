"""
Julius WhatsApp Integration — Approval Queue.

Manages pending message approvals. Users can approve, edit,
reject, or regenerate drafts.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from .models import ApprovalItem, AuditEntry, Confidence, WhatsAppMessage

logger = logging.getLogger(__name__)


class ApprovalQueue:
    """
    Manages the pending reply approval queue.

    Items stay in the queue until the user acts on them
    (send, edit, reject) or they expire after a timeout.
    """

    def __init__(self, expiry_seconds: float = 3600.0) -> None:
        self._queue: Dict[str, ApprovalItem] = {}
        self._expiry_seconds = expiry_seconds
        self._callbacks: List[Callable] = []

    @property
    def pending_count(self) -> int:
        self._prune_expired()
        return sum(1 for item in self._queue.values() if item.status == "pending")

    def subscribe(self, callback: Callable) -> None:
        """Register a callback for queue changes (new items, approvals, rejections)."""
        self._callbacks.append(callback)

    def add(
        self,
        incoming_message: WhatsAppMessage,
        draft_reply: str,
        confidence: Confidence,
        reason: str = "",
    ) -> ApprovalItem:
        """Add a new item to the approval queue."""
        item = ApprovalItem(
            incoming_message=incoming_message,
            draft_reply=draft_reply,
            confidence=confidence,
            reason=reason,
            chat_name=incoming_message.chat_name,
            chat_id=incoming_message.chat_id,
        )
        self._queue[item.id] = item
        logger.info(
            "Approval queued [%s] for '%s' from %s: %s...",
            item.id, item.chat_name, incoming_message.sender_name,
            draft_reply[:50],
        )
        self._notify("new", item)
        return item

    def get_pending(self) -> List[ApprovalItem]:
        """Get all pending approval items, newest first."""
        self._prune_expired()
        return sorted(
            [item for item in self._queue.values() if item.status == "pending"],
            key=lambda x: x.created_at,
            reverse=True,
        )

    def get_item(self, item_id: str) -> Optional[ApprovalItem]:
        """Get a specific approval item."""
        return self._queue.get(item_id)

    def approve(self, item_id: str) -> Optional[ApprovalItem]:
        """Mark an item as approved."""
        item = self._queue.get(item_id)
        if item and item.status == "pending":
            item.status = "approved"
            self._notify("approved", item)
            return item
        return None

    def approve_with_edit(self, item_id: str, edited_text: str) -> Optional[ApprovalItem]:
        """Approve with an edited reply text."""
        item = self._queue.get(item_id)
        if item and item.status == "pending":
            item.draft_reply = edited_text
            item.status = "approved"
            self._notify("approved_edited", item)
            return item
        return None

    def update_draft(self, item_id: str, draft_reply: str) -> Optional[ApprovalItem]:
        """Update a pending draft without consuming its approval state."""
        item = self._queue.get(item_id)
        if item and item.status == "pending":
            item.draft_reply = draft_reply
            self._notify("updated", item)
            return item
        return None

    def reject(self, item_id: str) -> Optional[ApprovalItem]:
        """Reject a draft reply."""
        item = self._queue.get(item_id)
        if item and item.status == "pending":
            item.status = "rejected"
            self._notify("rejected", item)
            return item
        return None

    def clear_all(self) -> int:
        """Clear all pending items. Returns count cleared."""
        count = sum(1 for item in self._queue.values() if item.status == "pending")
        for item in self._queue.values():
            if item.status == "pending":
                item.status = "expired"
        self._notify("cleared", None)
        return count

    def to_audit_entry(self, item: ApprovalItem, sent: bool = False, edited: bool = False) -> AuditEntry:
        """Convert an approval item to an audit entry."""
        return AuditEntry(
            chat_name=item.chat_name,
            chat_id=item.chat_id,
            sender_name=item.incoming_message.sender_name if item.incoming_message else "",
            incoming_message_id=item.incoming_message.id if item.incoming_message else None,
            mode="approval",
            generated_reply=item.draft_reply,
            final_reply=item.draft_reply,
            edited_by_user=edited,
            sent=sent,
            rejected=item.status == "rejected",
            approved=item.status == "approved",
            confidence=item.confidence.value,
            reason_code=item.reason,
        )

    def _prune_expired(self) -> None:
        """Mark expired items."""
        now = time.time()
        for item in self._queue.values():
            if (
                item.status == "pending"
                and (now - item.created_at) > self._expiry_seconds
            ):
                item.status = "expired"

    def _notify(self, action: str, item: Optional[ApprovalItem]) -> None:
        """Notify subscribers of queue changes."""
        for cb in self._callbacks:
            try:
                cb(action, item)
            except Exception as e:
                logger.error("Approval callback error: %s", e)
