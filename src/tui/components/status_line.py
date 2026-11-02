"""
Calm status line widget for Julius.

Design requirements:
- Exactly one dim line below the input field.
- Model name on the left (plain words, no badges or checkmarks).
- Short hint on the right ('? for help').
- Fades out while the user types, and smoothly fades back after 1.5s idle.
- Respects reduced-motion settings.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Label

from ..motion import animate_fade, is_reduced_motion


class StatusLine(Widget):
    """Quiet, single-line telemetry status at the bottom of the column."""

    DEFAULT_CSS = """
    StatusLine {
        height: 1;
        width: 100%;
        layout: horizontal;
        color: #86868b;
        background: transparent;
        margin-top: 0;
        padding: 0 1;
    }
    #status-hint {
        width: auto;
        color: #48484a;
        text-align: left;
    }
    #status-hint:hover {
        color: #f5f5f7;
    }
    #status-model {
        width: 1fr;
        color: #86868b;
        text-align: right;
    }
    #status-model:hover {
        color: #f5f5f7;
    }
    #status-model.loading {
        color: #c8b896;
        text-align: right;
    }
    #status-model.loading:hover {
        color: #ded2b8;
        text-style: underline;
    }
    """

    SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, model_name: str = "", hint_text: str = "? for help", **kwargs) -> None:
        super().__init__(id="status-line", **kwargs)
        self.model_name = ""
        self.hint_text = hint_text or "? for help"
        self._running_text = ""
        self._running_start_time: float = 0.0
        self._fade_timer: Optional[asyncio.TimerHandle] = None
        self._is_dimmed = False
        self._spinner_timer = None
        self._spinner_index = 0
        self._is_active_loading = False

    def compose(self) -> ComposeResult:
        yield Label(self.hint_text, id="status-hint")
        yield Label("", id="status-model")

    def update_model(self, model_name: str) -> None:
        """Update active model label (kept blank per user request)."""
        self.model_name = ""
        try:
            label = self.query_one("#status-model", Label)
            if not self._is_active_loading:
                label.update("")
        except Exception:
            pass

    def update_running(self, running_text: str) -> None:
        """Update bottom-left running action indicator."""
        prev_loading = self._is_active_loading
        self._running_text = running_text.strip()
        self._is_active_loading = bool(self._running_text)
        if self._is_active_loading:
            if not prev_loading or not self._running_start_time:
                self._running_start_time = time.time()
        else:
            self._running_start_time = 0.0

        try:
            label = self.query_one("#status-model", Label)
        except Exception:
            return

        if self._is_active_loading:
            label.add_class("loading")
            if not self._spinner_timer:
                self._spinner_timer = self.set_interval(0.1, self._spin)
            self._render_running()
        else:
            label.remove_class("loading")
            if self._spinner_timer:
                self._spinner_timer.stop()
                self._spinner_timer = None
            label.update("")

    def update_hint(self, hint_text: str) -> None:
        """Update right-side hint (e.g. '? for help' or 'Y Allow • N Decline')."""
        self.hint_text = hint_text or "? for help"
        try:
            label = self.query_one("#status-hint", Label)
            label.update(self.hint_text)
        except Exception:
            pass

    def _spin(self) -> None:
        """Advance spinner animation frame."""
        if not self._is_active_loading:
            return
        self._spinner_index = (self._spinner_index + 1) % len(self.SPINNER_FRAMES)
        self._render_running()

    def _render_running(self) -> None:
        """Render running status with loading spinner frame and elapsed seconds on the bottom-left."""
        try:
            label = self.query_one("#status-model", Label)
            frame = self.SPINNER_FRAMES[self._spinner_index]
            elapsed_str = ""
            if self._running_start_time > 0:
                elapsed = max(0.0, time.time() - self._running_start_time)
                if elapsed >= 0.5:
                    elapsed_str = f" [dim #86868b]({elapsed:.1f}s)[/dim #86868b]"
            rendered = f"[#c8b896]{frame}[/#c8b896] [dim #f5f5f7]{self._running_text}[/dim #f5f5f7]{elapsed_str}"
            label.update(rendered)
        except Exception:
            pass

    def on_click(self, event: events.Click) -> None:
        """Click on the bottom-left running status opens inspector modal; bottom-right opens help."""
        event.stop()
        app = self.app
        widget = getattr(event, "widget", None)
        target_id = getattr(widget, "id", None)

        if target_id == "status-model" or (self._is_active_loading and target_id != "status-hint"):
            if hasattr(app, "action_open_active_action_modal"):
                app.action_open_active_action_modal()
        else:
            if "? for help" in self.hint_text:
                if hasattr(app, "action_open_help"):
                    app.action_open_help()
            elif hasattr(app, "action_open_active_action_modal"):
                app.action_open_active_action_modal()

    def on_user_typing(self) -> None:
        """Fade out status line while user types, schedule fade back in 1.5s."""
        # When an action is active, keep loading status visible to avoid losing track of execution
        if self._is_active_loading:
            return

        if not self._is_dimmed:
            self._is_dimmed = True
            animate_fade(self, 0.0)

        # Cancel any pending return timer and schedule new 1.5s timer
        if self._fade_timer:
            self._fade_timer.cancel()

        loop = asyncio.get_event_loop()
        self._fade_timer = loop.call_later(1.5, self._restore_visibility)

    def _restore_visibility(self) -> None:
        """Fade back in after user is idle."""
        self._is_dimmed = False
        animate_fade(self, 1.0)
