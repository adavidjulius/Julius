"""
Composer input widget for Julius.

Design requirements:
- Rounded border (border: round).
- Placeholder: "Ask Julius anything". No command list inside.
- Border is dim when idle and uses the accent color when focused.
- 3 lines tall by default, dynamically grows up to 8 lines max.
- Enter sends prompt, Shift+Enter creates a newline.
- Up / Down arrow cycles prompt history when at boundary or empty.
- Emits Composer.Submitted(text) on send.
- Emits Composer.UserTyping() to inform status line to fade out.
"""

from __future__ import annotations

import time
from typing import List, Optional, Any
from textual import events
from textual.message import Message
from textual.widgets import TextArea


class Composer(TextArea):
    """Calm, auto-growing multi-line input field."""

    class Submitted(Message):
        """Posted when the user presses Enter (without Shift)."""
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class UserTyping(Message):
        """Posted when user types into the composer."""
        pass

    DEFAULT_CSS = """
    Composer {
        width: 100%;
        height: 3;
        min-height: 3;
        max-height: 10;
        border: round #c8b896;
        background: transparent;
        color: #f5f5f7;
        padding: 0 1;
        overflow-x: hidden;
        pointer: default;
    }
    Composer:focus {
        border: round #c8b896;
    }
    Composer > .text-area--cursor-line {
        background: transparent;
    }
    Composer > .text-area--cursor-gutter {
        background: transparent;
    }
    Composer .text-area--cursor {
        background: #c8b896;
        color: #121214;
        text-style: bold;
    }
    """

    def __init__(self, **kwargs) -> None:
        raw_placeholder = kwargs.pop("placeholder", "Ask Julius anything")
        super().__init__(
            text="",
            placeholder=raw_placeholder,
            show_line_numbers=False,
            soft_wrap=True,
            **kwargs,
        )
        self._raw_placeholder: str = raw_placeholder
        self.prompt_history: List[str] = []
        self.prompt_history_index: int = -1
        self._current_saved_draft: str = ""
        self._current_target_height: Optional[int] = 3
        self.styles.height = 3
        self._cached_suggestions_widget: Optional[Any] = None
        self._last_user_typing_post: float = 0.0

    def _get_command_suggestions(self) -> Optional[Any]:
        """Look up command suggestions widget from screen if available (cached)."""
        if self._cached_suggestions_widget is not None and getattr(self._cached_suggestions_widget, "is_mounted", True):
            return self._cached_suggestions_widget
        try:
            self._cached_suggestions_widget = self.screen.query_one("#command-suggestions")
            return self._cached_suggestions_widget
        except Exception:
            return None

    def on_key(self, event: events.Key) -> None:
        # Check if awaiting confirmation (instant single key press Y/N without typing or enter)
        app = self.app
        if getattr(app, "is_awaiting_confirmation", False):
            key_char = (event.character or event.key or "").lower()
            if key_char in ("y", "n"):
                event.prevent_default()
                event.stop()
                if hasattr(app, "handle_confirmation_choice"):
                    app.handle_confirmation_choice(key_char == "y")
                return

        # Check if command suggestions popup is visible and handle suggestion navigation
        sugg = self._get_command_suggestions()
        if sugg and getattr(sugg, "is_visible", False):
            if event.key == "up":
                event.prevent_default()
                event.stop()
                sugg.select_prev()
                return
            elif event.key == "down":
                event.prevent_default()
                event.stop()
                sugg.select_next()
                return
            elif event.key == "tab":
                chosen = sugg.get_selected_command()
                if chosen:
                    event.prevent_default()
                    event.stop()
                    self.text = chosen + " "
                    self.move_cursor((0, len(self.text)))
                    sugg.hide()
                    self._recalculate_height()
                    return
            elif event.key == "escape":
                event.prevent_default()
                event.stop()
                sugg.hide()
                return
            elif event.key == "enter":
                # Autocomplete the highlighted command and submit
                chosen = sugg.get_selected_command()
                if chosen:
                    event.prevent_default()
                    event.stop()
                    sugg.hide()
                    self.text = ""
                    self._recalculate_height()
                    if not self.prompt_history or self.prompt_history[-1] != chosen:
                        self.prompt_history.append(chosen)
                    self.prompt_history_index = -1
                    self._current_saved_draft = ""
                    self.post_message(self.Submitted(chosen))
                    return

        # Notify typing activity (throttled to avoid event bus flooding during fast typing)
        now = time.monotonic()
        if now - self._last_user_typing_post > 0.5:
            self._last_user_typing_post = now
            self.post_message(self.UserTyping())

        # 1. Enter key: Submit unless Shift is held
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            text_to_send = self.text.strip()
            if text_to_send:
                if sugg:
                    sugg.hide()
                # Append to prompt history
                if not self.prompt_history or self.prompt_history[-1] != text_to_send:
                    self.prompt_history.append(text_to_send)
                self.prompt_history_index = -1
                self._current_saved_draft = ""
                # Clear input
                self.text = ""
                self._recalculate_height()
                self.post_message(self.Submitted(text_to_send))
            return

        elif event.key == "shift+enter":
            event.prevent_default()
            event.stop()
            self.insert("\n")
            self._recalculate_height()
            return

        # 2. Up arrow: Previous history when cursor is at top row or input is empty
        elif event.key == "up":
            if self._is_at_first_line():
                if self.prompt_history:
                    if self.prompt_history_index == -1:
                        self._current_saved_draft = self.text
                        self.prompt_history_index = len(self.prompt_history) - 1
                    elif self.prompt_history_index > 0:
                        self.prompt_history_index -= 1

                    if 0 <= self.prompt_history_index < len(self.prompt_history):
                        event.prevent_default()
                        event.stop()
                        self.text = self.prompt_history[self.prompt_history_index]
                        self.move_cursor((self.document.line_count - 1, len(self.document.get_line(self.document.line_count - 1))))
                        self._recalculate_height()
                        return

        # 3. Down arrow: Next history when cursor is at bottom row
        elif event.key == "down":
            if self._is_at_last_line():
                if self.prompt_history_index != -1:
                    event.prevent_default()
                    event.stop()
                    self.prompt_history_index += 1
                    if self.prompt_history_index >= len(self.prompt_history):
                        self.prompt_history_index = -1
                        self.text = self._current_saved_draft
                    else:
                        self.text = self.prompt_history[self.prompt_history_index]
                    self.move_cursor((self.document.line_count - 1, len(self.document.get_line(self.document.line_count - 1))))
                    self._recalculate_height()
                    return

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self._recalculate_height()
        self._update_centered_placeholder()
        sugg = self._get_command_suggestions()
        if sugg:
            sugg.update_query(self.text)

    def on_resize(self, event: events.Resize) -> None:
        self._recalculate_height()
        self._update_centered_placeholder()

    def watch_placeholder(self, new_val: str) -> None:
        """Capture raw placeholder changes when set without leading whitespace padding."""
        stripped = new_val.strip()
        if stripped and (not hasattr(self, "_raw_placeholder") or stripped != self._raw_placeholder.strip()):
            self._raw_placeholder = stripped
            self._update_centered_placeholder()

    def _update_centered_placeholder(self) -> None:
        """Center the placeholder text inside the input box when empty without mutating during render_line."""
        if not self.text and getattr(self, "_raw_placeholder", None):
            cw = max(10, self.content_size.width or (self.size.width - 4))
            pad = max(0, (cw - len(self._raw_placeholder)) // 2)
            centered = " " * pad + self._raw_placeholder
            if self.placeholder != centered:
                self.placeholder = centered

    def _is_at_first_line(self) -> bool:
        """Return True if cursor is on row 0 or text is empty."""
        if not self.text:
            return True
        return self.cursor_location[0] == 0

    def _is_at_last_line(self) -> bool:
        """Return True if cursor is on the last line."""
        if not self.text:
            return True
        return self.cursor_location[0] >= self.document.line_count - 1

    def _recalculate_height(self) -> None:
        """Dynamically adjust widget height between 3 and 10 rows only when height actually changes."""
        lines = 1
        # 1. Use wrapped document visual height if available
        if hasattr(self, "wrapped_document") and self.wrapped_document:
            try:
                lines = max(lines, self.wrapped_document.height)
            except Exception:
                pass

        # 2. Check physical newline count
        if hasattr(self, "document") and self.document:
            lines = max(lines, self.document.line_count)

        # 3. Fallback calculation based on available content width
        avail_w = max(15, (self.content_size.width or self.size.width) - 2)
        if self.text:
            calc_lines = sum(max(1, (len(l) + avail_w - 1) // avail_w) for l in self.text.split("\n"))
            lines = max(lines, calc_lines)

        # Auto-clamping rule: when terminal rows are below 18, cap input height strictly at 2 lines
        max_allowed = 10
        try:
            screen_h = self.screen.size.height if hasattr(self, "screen") and self.screen else 0
            if screen_h and screen_h < 18:
                max_allowed = 4  # 2 lines of content + 2 for top/bottom border
        except Exception:
            pass

        # Content lines + 2 for top/bottom border
        target_height = min(max_allowed, max(3, lines + 2))
        if getattr(self, "_current_target_height", None) != target_height:
            self._current_target_height = target_height
            self.styles.height = target_height
