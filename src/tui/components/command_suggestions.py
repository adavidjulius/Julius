"""
Command suggestions autocomplete popup for Julius composer.
Displays matching slash commands directly above the composer when typing '/' or '/<prefix>'.
"""

from __future__ import annotations

from typing import List, Tuple, Optional
from rich.text import Text
from textual import events
from textual.widgets import Static

from src.tui.commands import COMMAND_SUGGESTIONS as COMMANDS


class CommandSuggestions(Static):
    """Calm, floating-style suggestions popup displayed directly above Composer."""

    DEFAULT_CSS = """
    CommandSuggestions {
        display: none;
        width: 100%;
        height: auto;
        max-height: 8;
        background: #18181b;
        border: round #3e3e42;
        padding: 0 1;
        margin-bottom: 1;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-size: 0 0;
    }

    CommandSuggestions.visible {
        display: block;
    }

    CommandSuggestions:hover {
        scrollbar-size-vertical: 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.matches: List[Tuple[str, str]] = []
        self.selected_index: int = 0
        self._current_window_start: int = 0

    @property
    def is_visible(self) -> bool:
        """Check if suggestions popup is currently displayed."""
        return self.has_class("visible") and bool(self.matches)

    def hide(self) -> None:
        """Hide the suggestions popup and clear state without redundant DOM thrashing."""
        if not self.has_class("visible") and not self.matches:
            return
        self.matches = []
        self.selected_index = 0
        self._current_window_start = 0
        self.remove_class("visible")
        self.update("")

    def update_query(self, query: str) -> bool:
        """Update suggestion matches based on composer query."""
        if not query or not query.startswith("/"):
            if self.has_class("visible") or self.matches:
                self.hide()
            return False

        lines = query.split("\n")
        # Only suggest when typing a single-line slash command
        if len(lines) != 1:
            self.hide()
            return False

        line = lines[0]
        # Must start with / and not contain spaces anywhere (space means command is finished)
        if not line.startswith("/") or " " in line:
            self.hide()
            return False

        prefix = line.strip().lower()
        # Find all commands that start with the typed prefix (e.g. /h -> /help)
        self.matches = [
            (cmd, desc) for cmd, desc in COMMANDS
            if cmd.lower().startswith(prefix)
        ]

        if not self.matches:
            self.hide()
            return False

        self.selected_index = max(0, min(self.selected_index, len(self.matches) - 1))
        self.add_class("visible")
        self._render_suggestions()
        return True

    def _render_suggestions(self) -> None:
        """Render matching suggestions with gold accent indicator and windowing."""
        max_visible = 5
        total = len(self.matches)
        if total <= max_visible:
            self._current_window_start = 0
            visible = list(enumerate(self.matches))
        else:
            self._current_window_start = max(0, min(self.selected_index - max_visible // 2, total - max_visible))
            visible = [
                (self._current_window_start + idx, self.matches[self._current_window_start + idx])
                for idx in range(max_visible)
            ]

        content = Text()
        content.append("Commands", style="bold #86868b")
        content.append("  (Tab to complete · ↑/↓ to navigate · Enter to run)\n", style="dim #555555")

        for display_idx, (real_idx, (cmd, desc)) in enumerate(visible):
            if real_idx == self.selected_index:
                content.append("❯ ", style="bold #c8b896")
                content.append(f"{cmd:<10}", style="bold #c8b896")
                content.append(" · ", style="dim #86868b")
                content.append(desc, style="bold #f5f5f7")
            else:
                content.append("  ", style="")
                content.append(f"{cmd:<10}", style="bold #38bdf8")
                content.append(" · ", style="dim #86868b")
                content.append(desc, style="#86868b")
            if display_idx < len(visible) - 1:
                content.append("\n")

        self.update(content)

    def select_prev(self) -> None:
        """Navigate to previous suggestion item."""
        if self.matches:
            self.selected_index = (self.selected_index - 1) % len(self.matches)
            self._render_suggestions()

    def select_next(self) -> None:
        """Navigate to next suggestion item."""
        if self.matches:
            self.selected_index = (self.selected_index + 1) % len(self.matches)
            self._render_suggestions()

    def get_selected_command(self) -> Optional[str]:
        """Return the command string of the currently highlighted suggestion."""
        if self.matches and 0 <= self.selected_index < len(self.matches):
            return self.matches[self.selected_index][0]
        return None

    def on_click(self, event: events.Click) -> None:
        """Handle click on a suggestion line to autocomplete into composer."""
        event.stop()
        y = getattr(event, "offset", None)
        line_idx = (y.y - 1) if y else -1
        real_idx = self._current_window_start + line_idx
        if 0 <= real_idx < len(self.matches):
            chosen = self.matches[real_idx][0]
            try:
                composer = self.screen.query_one("#composer-input")
                composer.text = chosen + " "
                composer.move_cursor((0, len(composer.text)))
                composer.focus()
            except Exception:
                pass
            self.hide()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Highlight suggestion on hover."""
        y = getattr(event, "offset", None)
        line_idx = (y.y - 1) if y else -1
        real_idx = self._current_window_start + line_idx
        if 0 <= real_idx < len(self.matches) and real_idx != self.selected_index:
            self.selected_index = real_idx
            self._render_suggestions()
