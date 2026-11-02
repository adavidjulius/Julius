"""
Minimalist Julius welcome and empty state view.

Principles:
- Bold, large aesthetic 'JULIUS' wordmark.
- Clean empty canvas with no distracting sub-quotes or filler text.
- Hides once conversation starts.
"""

from __future__ import annotations

from typing import Optional
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from rich.text import Text
from ..config import JuliusConfig


JULIUS_BANNER = """\
╔═════╗ ╔╗   ╔╗ ╔╗      ╔═════╗ ╔╗   ╔╗ ╔═════╗
╚══╗  ║ ║║   ║║ ║║      ╚═╗ ╔═╝ ║║   ║║ ║ ╔═══╝
   ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ║ ╚═══╗
   ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ╚═══╗ ║
╔══╝  ║ ║╚═══╝║ ║╚════╗ ╔═╝ ╚═╗ ║╚═══╝║ ╔═══╝ ║
╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝"""


class WelcomeView(Widget):
    """Calm empty state / greeting screen with monochromatic outline banner."""

    DEFAULT_CSS = """
    WelcomeView {
        width: 100%;
        height: 100%;
        layout: vertical;
        align: center middle;
        content-align: center middle;
    }
    .wordmark-banner {
        color: #ffffff;
        text-style: bold;
        text-align: center;
        content-align: center middle;
        width: 100%;
    }
    WelcomeView.scrolled-header {
        height: auto;
        padding-top: 1;
        padding-bottom: 1;
    }
    """

    def __init__(self, config: Optional[JuliusConfig] = None, **kwargs) -> None:
        super().__init__(id="welcome-view", **kwargs)
        self.config = config

    def compose(self) -> ComposeResult:
        # Centered bold monochromatic outline Julius wordmark banner
        yield Static(Text(JULIUS_BANNER, justify="center"), classes="wordmark-banner")
