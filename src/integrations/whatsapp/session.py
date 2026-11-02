"""
Julius WhatsApp Integration — Session Manager.

Handles persistent session state, profile directory management,
and recovery after crashes/restarts.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .models import HealthState

logger = logging.getLogger(__name__)


class WhatsAppSession:
    """
    Manages persistent WhatsApp Web session state.

    The session survives process restarts, server restarts, and
    Chromium restarts by persisting state to disk alongside the
    Chromium profile directory.
    """

    def __init__(self, profile_dir: str) -> None:
        self._profile_dir = Path(profile_dir).expanduser().resolve()
        self._state_file = self._profile_dir / ".julius_wa_session.json"
        self._state: Dict[str, Any] = {
            "authenticated": False,
            "last_connected_at": 0.0,
            "last_disconnected_at": 0.0,
            "total_sessions": 0,
            "current_health": HealthState.DISABLED.value,
            "account_hint": "",  # redacted phone/name hint
        }
        self._load_state()

    @property
    def is_authenticated(self) -> bool:
        return self._state.get("authenticated", False)

    @property
    def health(self) -> HealthState:
        return HealthState(self._state.get("current_health", "disabled"))

    @health.setter
    def health(self, state: HealthState) -> None:
        self._state["current_health"] = state.value
        self._save_state()

    @property
    def account_hint(self) -> str:
        return self._state.get("account_hint", "")

    @property
    def last_connected_at(self) -> float:
        return self._state.get("last_connected_at", 0.0)

    def mark_connected(self, account_hint: str = "") -> None:
        """Mark session as authenticated and connected."""
        self._state["authenticated"] = True
        self._state["last_connected_at"] = time.time()
        self._state["total_sessions"] = self._state.get("total_sessions", 0) + 1
        self._state["current_health"] = HealthState.CONNECTED.value
        if account_hint:
            # Redact: keep only first 3 and last 2 chars
            if len(account_hint) > 5:
                self._state["account_hint"] = (
                    account_hint[:3] + "•" * (len(account_hint) - 5) + account_hint[-2:]
                )
            else:
                self._state["account_hint"] = account_hint
        self._save_state()
        logger.info("WhatsApp session marked as connected")

    def mark_disconnected(self, reason: str = "") -> None:
        """Mark session as disconnected."""
        self._state["last_disconnected_at"] = time.time()
        self._state["current_health"] = HealthState.STOPPED.value
        self._save_state()
        logger.info("WhatsApp session marked as disconnected: %s", reason)

    def mark_session_expired(self) -> None:
        """Mark session as expired (requires QR re-scan)."""
        self._state["authenticated"] = False
        self._state["current_health"] = HealthState.SESSION_EXPIRED.value
        self._save_state()
        logger.warning("WhatsApp session expired — QR re-scan required")

    def clear(self) -> None:
        """Clear all session state."""
        self._state = {
            "authenticated": False,
            "last_connected_at": 0.0,
            "last_disconnected_at": 0.0,
            "total_sessions": 0,
            "current_health": HealthState.DISABLED.value,
            "account_hint": "",
        }
        self._save_state()
        logger.info("WhatsApp session state cleared")

    def get_status_dict(self) -> Dict[str, Any]:
        """Get session status for API/UI display."""
        return {
            "authenticated": self.is_authenticated,
            "health": self.health.value,
            "account_hint": self.account_hint,
            "last_connected_at": self._state.get("last_connected_at", 0),
            "last_disconnected_at": self._state.get("last_disconnected_at", 0),
            "total_sessions": self._state.get("total_sessions", 0),
        }

    def _load_state(self) -> None:
        """Load persisted state from disk."""
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text(encoding="utf-8"))
                self._state.update(data)
                logger.debug("Loaded WhatsApp session state from %s", self._state_file)
            except Exception as e:
                logger.warning("Failed to load session state: %s", e)

    def _save_state(self) -> None:
        """Persist state to disk."""
        try:
            self._profile_dir.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps(self._state, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.error("Failed to save session state: %s", e)
