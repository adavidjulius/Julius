"""
Active Action modal.
Allows inspecting active in-flight bash commands and tool actions, viewing live elapsed time and streaming output,
and immediately cancelling/skipping stuck or lagging actions.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from rich import box
from rich.panel import Panel
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Label, Static


class TerminalOutputBox(ScrollableContainer, Static):
    """
    Terminal output viewer with auto-hiding scrollbar and auto-scroll.
    Scrollbar is invisible by default (scrollbar-size: 0 0),
    revealed on hover, and temporarily revealed during active user scrolling.
    """

    DEFAULT_CSS = """
    TerminalOutputBox {
        width: 100%;
        height: 8;
        background: #0d0d0f;
        border: round #3e3e42;
        padding: 0 1;
        margin-bottom: 1;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-size: 0 0;
        scrollbar-gutter: auto;
    }

    TerminalOutputBox:hover {
        scrollbar-size-vertical: 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._inner_static = Static("", id="terminal-inner-text")
        self._hide_scrollbar_timer = None

    def compose(self) -> ComposeResult:
        yield self._inner_static

    def update(self, content: Any) -> None:
        """Update terminal output content and scroll to latest lines."""
        self._inner_static.update(content)
        self.scroll_end(animate=False)

    def render(self) -> Any:
        return self._inner_static.render()

    def watch_scroll_y(self, old_val: float, new_val: float) -> None:
        super().watch_scroll_y(old_val, new_val)
        if old_val != new_val and self.is_mounted:
            self._show_scrollbar_temporarily()

    def _show_scrollbar_temporarily(self) -> None:
        if self.is_scrollable:
            self.styles.scrollbar_size_vertical = 1
            if self._hide_scrollbar_timer:
                self._hide_scrollbar_timer.stop()
            self._hide_scrollbar_timer = self.set_timer(1.2, self._hide_scrollbar)

    def _hide_scrollbar(self) -> None:
        self.styles.scrollbar_size_vertical = 0
        self._hide_scrollbar_timer = None


class ActiveActionModal(ModalScreen[None]):
    """Modal displaying active in-flight action telemetry, live terminal output, and cancellation controls."""

    DEFAULT_CSS = """
    ActiveActionModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #action-inspector-card {
        width: 78;
        max-width: 92%;
        height: auto;
        max-height: 85%;
        background: #18181b;
        border: round #c8b896;
        padding: 1 2;
        layout: vertical;
    }

    .inspector-header {
        height: 1;
        width: 100%;
        align-horizontal: center;
        margin-bottom: 1;
    }

    #inspector-title {
        color: #f5f5f7;
        text-style: bold;
        text-align: center;
        width: 100%;
    }

    #inspector-status {
        width: 100%;
        text-align: center;
        color: #c8b896;
        text-style: bold;
        margin-bottom: 1;
    }

    #inspector-command-box {
        width: 100%;
        height: auto;
        max-height: 5;
        background: #0d0d0f;
        border: round #3e3e42;
        padding: 0 1;
        margin-bottom: 1;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-size: 0 0;
    }

    #inspector-command-box:hover {
        scrollbar-size-vertical: 1;
    }

    #inspector-output-box {
        width: 100%;
        height: 8;
        background: #0d0d0f;
        border: round #3e3e42;
        padding: 0 1;
        margin-bottom: 1;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-size: 0 0;
        scrollbar-gutter: auto;
    }

    #inspector-output-box:hover {
        scrollbar-size-vertical: 1;
    }

    .inspector-actions {
        height: 1;
        width: 100%;
        layout: horizontal;
        align-horizontal: center;
        margin-top: 1;
    }

    #cancel-action-btn {
        width: auto;
        background: #b91c1c;
        color: #ffffff;
        text-style: bold;
        padding: 0 2;
        margin-right: 2;
    }

    #cancel-action-btn:hover {
        background: #dc2626;
    }

    #cancel-action-btn.disabled {
        background: #2a2020;
        color: #555555;
        text-style: none;
    }

    #cancel-action-btn.disabled:hover {
        background: #2a2020;
        color: #555555;
    }

    #dismiss-modal-btn {
        width: auto;
        background: #2c2c2e;
        color: #f5f5f7;
        padding: 0 2;
    }

    #dismiss-modal-btn:hover {
        background: #3e3e42;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._refresh_timer = None
        self._is_running: bool = False
        self._last_cmd: Optional[str] = None
        self._last_output: Optional[str] = None
        self._last_status_key: Optional[tuple] = None

    def compose(self) -> ComposeResult:
        with Vertical(id="action-inspector-card"):
            with Horizontal(classes="inspector-header"):
                yield Label("Active Action", id="inspector-title")

            yield Static(id="inspector-status")
            yield Static(id="inspector-command-box")
            yield TerminalOutputBox(id="inspector-output-box")

            with Horizontal(classes="inspector-actions"):
                yield Label("⏹ Cancel Action", id="cancel-action-btn", classes="disabled")
                yield Label("Close", id="dismiss-modal-btn")

    def on_mount(self) -> None:
        self._refresh_live_status()
        self._refresh_timer = self.set_interval(0.8, self._refresh_live_status)

    @staticmethod
    def _format_terminal_output(raw: str) -> Text:
        """Format raw terminal output, resolving carriage returns and parsing ANSI styling."""
        if not raw:
            return Text("")
        # Clean terminal output: resolve carriage returns (\r) used by progress spinners
        lines = raw.replace("\r\n", "\n").split("\n")
        processed_lines = []
        for line in lines:
            if "\r" in line:
                parts = line.split("\r")
                non_empty = [p for p in parts if p.strip()]
                line = non_empty[-1] if non_empty else parts[-1]
            processed_lines.append(line)
        clean_text = "\n".join(processed_lines)
        # Cap display to last 8000 characters to ensure silky smooth TUI rendering
        if len(clean_text) > 8000:
            clean_text = clean_text[-8000:]
        try:
            return Text.from_ansi(clean_text)
        except Exception:
            return Text(clean_text, style="#f5f5f7")

    def _refresh_live_status(self) -> None:
        """Query app for live action details and update view with calm diff rendering."""
        app = self.app
        info = {}
        if hasattr(app, "get_active_action_info"):
            info = app.get_active_action_info()

        is_running = info.get("is_running", False)
        act = info.get("action", "") or "run_bash"
        cmd = info.get("command", "")
        elapsed = info.get("elapsed", 0.0)
        output = info.get("output", "")

        self._is_running = is_running

        status_widget = self.query_one("#inspector-status", Static)
        cmd_widget = self.query_one("#inspector-command-box", Static)
        out_widget = self.query_one("#inspector-output-box", Static)
        cancel_btn = self.query_one("#cancel-action-btn", Label)

        # Update cancel button state
        if is_running:
            cancel_btn.remove_class("disabled")
        else:
            cancel_btn.add_class("disabled")

        # Status update: clean, no "Idle / No action actively running" dump text
        status_key = (is_running, act, int(elapsed), bool(cmd))
        if status_key != self._last_status_key:
            self._last_status_key = status_key
            if is_running:
                status_text = Text.assemble(
                    ("● ", "bold #22c55e"),
                    (f"Running ({act})", "bold #f5f5f7"),
                    ("  •  ", "dim"),
                    (f"{elapsed:.1f}s elapsed", "bold #c8b896"),
                    ("  (Click 'Cancel Action' below if stuck)", "dim #86868b"),
                )
            elif cmd:
                status_text = Text.assemble(
                    ("✓ ", "bold #22c55e"),
                    ("Completed", "bold #a1a1aa"),
                    (f"  •  {elapsed:.1f}s", "dim #86868b") if elapsed > 0 else ("", ""),
                )
            else:
                status_text = Text("")
            status_widget.update(status_text)

        # Command display diff check: no "No command currently executing" dump text
        if cmd != self._last_cmd:
            self._last_cmd = cmd
            if cmd:
                cmd_text = Text.assemble(
                    ("$ ", "bold #c8b896"),
                    (cmd, "bold #38bdf8"),
                )
            else:
                cmd_text = Text("$ ", style="dim #86868b")
            cmd_widget.update(cmd_text)

        # Output display diff check: real ANSI terminal formatting, no "No output to display." dump text
        if output != self._last_output or (is_running and not self._last_output):
            self._last_output = output
            if output:
                out_text = self._format_terminal_output(output)
            elif is_running:
                out_text = Text.assemble(
                    ("$ ", "dim #c8b896"),
                    ("Process executing... output will stream here", "dim #86868b"),
                )
            else:
                out_text = Text("")
            out_widget.update(out_text)

    def on_click(self, event: events.Click) -> None:
        """Handle clicks on buttons within modal."""
        widget = getattr(event, "widget", None)
        target_id = getattr(widget, "id", None)
        if target_id == "cancel-action-btn":
            event.stop()
            # Only perform cancellation when a job is actually running!
            if self._is_running:
                self._handle_cancel()
        elif target_id == "dismiss-modal-btn":
            event.stop()
            self.dismiss(None)

    def _handle_cancel(self) -> None:
        """Cancel active action via app and close modal."""
        app = self.app
        if hasattr(app, "cancel_active_action"):
            app.cancel_active_action()
        if hasattr(app, "_show_toast"):
            app._show_toast("Cancelled active action")
        self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        """Dismiss on Escape or Q."""
        if event.key in ("escape", "q"):
            event.stop()
            self.dismiss(None)
