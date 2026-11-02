"""
ConversationArea component:
Auto-hiding scrollbar container that makes full use of terminal width when idle,
temporarily revealing a 1-cell scrollbar during active user scrolling.
"""

from __future__ import annotations

from textual.containers import ScrollableContainer


class ConversationArea(ScrollableContainer):
    """
    High-performance conversation container with stable layout geometry.
    Maintains constant content width across idle and scrolling states
    to eliminate costly multi-message markdown reflows.
    """

    DEFAULT_CSS = """
    ConversationArea {
        height: 1fr;
        width: 1fr;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-size: 0 0;
        scrollbar-gutter: stable;
        scrollbar-color: #3e3e42;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def watch_scroll_y(self, old_val: float, new_val: float) -> None:
        """Reveal 1-cell scrollbar during active scrolling; hide when idle at top."""
        if new_val > 0:
            self.styles.scrollbar_size_vertical = 1
        else:
            self.styles.scrollbar_size_vertical = 0
