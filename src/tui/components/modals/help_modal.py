"""
Keyboard shortcuts and help reference modal (?).
"""

from __future__ import annotations

from typing import Optional
from rich.table import Table
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static


SHORTCUTS = [
    ("Enter", "Send prompt"),
    ("Shift+Enter", "Insert new line"),
    ("Esc", "Cancel action / Dismiss modal"),
    ("↑ / ↓", "Navigate prompt history"),
    ("Ctrl+I", "Inspect running action & live terminal output"),
    ("Ctrl+T", "Expand / collapse thinking reasoning"),
    ("Ctrl+Y", "Copy last assistant answer (with toast)"),
    ("Ctrl+O", "Expand / collapse tool execution steps"),
    ("F2", "Switch reasoning model"),
    ("⌥ + Drag", "Native text selection (macOS)"),
    ("?", "Toggle this shortcut guide"),
]


class HelpModal(ModalScreen[None]):
    """Calm keyboard shortcut and navigation reference."""

    DEFAULT_CSS = """
    HelpModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #help-card {
        width: 78;
        max-width: 92%;
        height: auto;
        max-height: 85%;
        background: #18181b;
        border: round #c8b896;
        padding: 1 2;
        layout: vertical;
    }

    #help-title {
        color: #f5f5f7;
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 0;
    }

    #help-subtitle {
        color: #c8b896;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }

    #help-table {
        width: 100%;
        height: auto;
        background: #0d0d0f;
        border: round #3e3e42;
        padding: 0 1;
        margin-bottom: 1;
    }

    #help-footer {
        color: #86868b;
        text-align: center;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-card"):
            yield Label("Keyboard Shortcuts", id="help-title")
            yield Label("Quick keys and navigation controls", id="help-subtitle")
            yield Static(id="help-table")
            yield Label("[Esc] or [?] Dismiss", id="help-footer")

    def on_mount(self) -> None:
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold #f5f5f7", width=16)
        table.add_column(style="#86868b")

        for key, desc in SHORTCUTS:
            table.add_row(key, desc)

        self.query_one("#help-table", Static).update(table)

    def on_key(self, event: events.Key) -> None:
        if event.key in ("escape", "question_mark"):
            event.stop()
            self.dismiss(None)
