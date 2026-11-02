"""
Interactive CommandBox widget for Julius.

Features:
- Dynamically sized to fit the command content (width: auto, max-width: 92%).
- Top-right corner interactive copy button [📋 Copy].
- When clicked, copies the command to the system clipboard via platform_compat.copy_to_clipboard.
- Animates copy icon to [✓ Copied!] in bold green for 2 seconds, then resets back to [📋 Copy].
"""

from __future__ import annotations

import asyncio
from typing import Optional

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.events import Click
from textual.widget import Widget
from textual.widgets import Label, Static

from src.platform_compat import copy_to_clipboard


class CommandBox(Widget):
    """Dynamically-sized command box with top-right copy button."""

    DEFAULT_CSS = """
    CommandBox {
        width: auto;
        max-width: 92%;
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
        background: #1c1c1e;
        border: round #3e3e42;
        padding: 0 1;
    }
    .command-header {
        height: 1;
        width: 100%;
        layout: horizontal;
        align-horizontal: right;
        margin-bottom: 0;
    }
    .command-lang {
        width: 1fr;
        color: #86868b;
        text-style: dim;
    }
    .copy-btn {
        width: auto;
        color: #c8b896;
        text-style: bold;
        background: transparent;
        padding: 0 1;
    }
    .copy-btn:hover {
        background: #2c2c2e;
        color: #f5f5f7;
    }
    .command-code {
        width: 100%;
        height: auto;
        padding-bottom: 1;
    }
    """

    def __init__(self, command: str, language: str = "bash", **kwargs) -> None:
        super().__init__(**kwargs)
        self.command = command.strip()
        self.language = language
        self._reset_timer: Optional[asyncio.TimerHandle] = None

    def compose(self) -> ComposeResult:
        with Horizontal(classes="command-header"):
            yield Label(self.language, classes="command-lang")
            yield Label("📋 Copy", classes="copy-btn", id="copy-btn")

        syntax = Syntax(
            self.command,
            self.language,
            theme="github-dark",
            word_wrap=True,
            padding=0,
        )
        yield Static(syntax, classes="command-code")

    def on_click(self, event: Click) -> None:
        """Handle click on copy button."""
        try:
            copy_label = self.query_one("#copy-btn", Label)
            if event.target == copy_label or copy_label in getattr(event.target, "ancestors_with_self", []):
                event.stop()
                self._do_copy()
        except Exception:
            pass

    def _do_copy(self) -> None:
        """Copy command to system clipboard and show tick animation."""
        success = copy_to_clipboard(self.command)
        try:
            copy_label = self.query_one("#copy-btn", Label)
            if success:
                copy_label.update("✓ Copied!")
                copy_label.styles.color = "#22c55e"
            else:
                copy_label.update("✕ Error")
                copy_label.styles.color = "#ef4444"

            if self._reset_timer:
                self._reset_timer.cancel()

            loop = asyncio.get_event_loop()
            self._reset_timer = loop.call_later(2.0, self._reset_copy_label)
        except Exception:
            pass

    def _reset_copy_label(self) -> None:
        try:
            copy_label = self.query_one("#copy-btn", Label)
            copy_label.update("📋 Copy")
            copy_label.styles.color = "#c8b896"
        except Exception:
            pass
