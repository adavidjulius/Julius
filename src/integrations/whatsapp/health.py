"""
Julius WhatsApp Integration — Health Status Reporting.

Tracks and reports the operational health of the WhatsApp subsystem:
browser status, connection state, listener status, last event/send
timestamps, uptime, error counters, and queue depths.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .models import HealthState

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """Comprehensive health snapshot for the WhatsApp integration."""
    state: HealthState = HealthState.DISABLED
    browser_alive: bool = False
    page_ready: bool = False
    authenticated: bool = False
    listener_running: bool = False
    watchdog_running: bool = False
    active_chat_count: int = 0
    pending_approvals_count: int = 0
    uptime_seconds: float = 0.0
    started_at: Optional[float] = None
    last_event_at: Optional[float] = None
    last_send_at: Optional[float] = None
    last_heartbeat: float = field(default_factory=time.time)
    restart_count: int = 0
    last_error: Optional[str] = None
    recent_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "browser_alive": self.browser_alive,
            "page_ready": self.page_ready,
            "authenticated": self.authenticated,
            "listener_running": self.listener_running,
            "watchdog_running": self.watchdog_running,
            "active_chat_count": self.active_chat_count,
            "pending_approvals_count": self.pending_approvals_count,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "started_at": self.started_at,
            "last_event_at": self.last_event_at,
            "last_send_at": self.last_send_at,
            "last_heartbeat": self.last_heartbeat,
            "restart_count": self.restart_count,
            "last_error": self.last_error,
            "recent_errors": self.recent_errors[-10:],
        }


class WhatsAppHealth:
    """Manages health state, metrics, and diagnostics."""

    def __init__(self) -> None:
        self._state: HealthState = HealthState.DISABLED
        self._started_at: Optional[float] = None
        self._browser_alive: bool = False
        self._page_ready: bool = False
        self._authenticated: bool = False
        self._listener_running: bool = False
        self._watchdog_running: bool = False
        self._last_event_at: Optional[float] = None
        self._last_send_at: Optional[float] = None
        self._restart_count: int = 0
        self._recent_errors: List[str] = []
        self._last_error: Optional[str] = None
        self._active_chat_count: int = 0
        self._pending_approvals_count: int = 0

    @property
    def state(self) -> HealthState:
        return self._state

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def listener_running(self) -> bool:
        return self._listener_running

    def set_state(self, state: HealthState) -> None:
        if self._state != state:
            logger.info("WhatsApp health state transition: %s -> %s", self._state.value, state.value)
            self._state = state

    def record_start(self) -> None:
        self._started_at = time.time()
        self._state = HealthState.STARTING

    def record_stop(self) -> None:
        self._state = HealthState.STOPPED
        self._browser_alive = False
        self._page_ready = False
        self._listener_running = False
        self._watchdog_running = False

    def update_browser(self, alive: bool, ready: bool = False) -> None:
        self._browser_alive = alive
        self._page_ready = ready
        if not alive:
            self._authenticated = False

    def set_authenticated(self, authenticated: bool) -> None:
        self._authenticated = authenticated
        if authenticated:
            self._state = HealthState.CONNECTED
        elif self._state == HealthState.CONNECTED:
            self._state = HealthState.SESSION_EXPIRED

    def set_listener_running(self, running: bool) -> None:
        self._listener_running = running

    def set_watchdog_running(self, running: bool) -> None:
        self._watchdog_running = running

    def record_event(self) -> None:
        self._last_event_at = time.time()

    def record_send(self) -> None:
        self._last_send_at = time.time()

    def record_restart(self) -> None:
        self._restart_count += 1
        self._state = HealthState.RECONNECTING

    def record_error(self, message: str) -> None:
        self._last_error = message
        timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")
        self._recent_errors.append(f"[{timestamp_str}] {message}")
        if len(self._recent_errors) > 50:
            self._recent_errors.pop(0)

    def update_counts(self, active_chats: int = 0, pending_approvals: int = 0) -> None:
        self._active_chat_count = active_chats
        self._pending_approvals_count = pending_approvals

    def get_snapshot(self) -> HealthStatus:
        uptime = (time.time() - self._started_at) if self._started_at else 0.0
        return HealthStatus(
            state=self._state,
            browser_alive=self._browser_alive,
            page_ready=self._page_ready,
            authenticated=self._authenticated,
            listener_running=self._listener_running,
            watchdog_running=self._watchdog_running,
            active_chat_count=self._active_chat_count,
            pending_approvals_count=self._pending_approvals_count,
            uptime_seconds=uptime,
            started_at=self._started_at,
            last_event_at=self._last_event_at,
            last_send_at=self._last_send_at,
            last_heartbeat=time.time(),
            restart_count=self._restart_count,
            last_error=self._last_error,
            recent_errors=list(self._recent_errors),
        )

    def to_dict(self) -> Dict[str, Any]:
        return self.get_snapshot().to_dict()
