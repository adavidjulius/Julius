"""
Julius TUI Package: Next-Gen Julius Terminal Interface.
"""

try:
    from .app import JuliusApp, StreamPanel, JuliusTUI
except ImportError:
    JuliusApp = None  # type: ignore
    StreamPanel = None  # type: ignore
    JuliusTUI = None  # type: ignore
from .theme import ThemeTokens, get_theme, DARK_THEME, LIGHT_THEME
from .motion import MotionPresets, is_reduced_motion
from .markdown import (
    JuliusMarkdown,
    render_julius_markdown,
    AppleMarkdown,
    render_apple_markdown,
)
from .state import SessionState
from .event_bridge import EventBridge

__all__ = [
    "JuliusApp",
    "StreamPanel",
    "JuliusTUI",
    "ThemeTokens",
    "get_theme",
    "DARK_THEME",
    "LIGHT_THEME",
    "MotionPresets",
    "is_reduced_motion",
    "JuliusMarkdown",
    "render_julius_markdown",
    "AppleMarkdown",
    "render_apple_markdown",
    "SessionState",
    "EventBridge",
]
