"""
Minimalist design tokens and adaptive light/dark theme system for Julius.

Design Principles:
- Single calm column, generous whitespace, zero decorative clutter.
- Exactly ONE accent color (calm Julius Blue: #0a84ff dark / #007aff light).
- Exactly 3 text tones: text, text_dim, text_faint.
- Layered surfaces (bg, surface, raised) derived by ~4% and ~8% lightness shifts.
- High contrast: >= 4.5:1 body text contrast in both light and dark themes.
- Adaptive startup detection: OSC 11 query -> COLORFGBG -> fallback to dark.
- Full NO_COLOR and 16-color ANSI support.
"""

from __future__ import annotations

import os
import select
import sys

try:
    import termios
    import tty
except ImportError:
    termios = None  # type: ignore
    tty = None      # type: ignore

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SquircleRadii:
    """Corner radii for continuous G2 squircles per Brand Book v3.1.0 §9.2."""
    xs: str = "4px"
    sm: str = "6px"
    md: str = "8px"
    lg: str = "10px"
    xl: str = "16px"
    pill: str = "9999px"


SQUIRCLE_RADII = SquircleRadii()


@dataclass(frozen=True)
class ThemeTokens:
    """Semantic tokens for Julius UI. Never use hardcoded colors in widgets."""
    name: str
    bg: str
    surface: str
    raised: str
    text: str
    text_dim: str
    text_faint: str
    accent: str
    success: str
    warning: str
    error: str
    border_idle: str
    border_focused: str
    scrim: str
    is_dark: bool = True
    is_no_color: bool = False
    brand_gold: str = "#c8b896"
    brand_crimson: str = "#731a1a"
    brand_obsidian: str = "#1a1a1a"
    brand_electric_green: str = "#7ed321"
    brand_green_deep: str = "#006a25"
    brand_green_glow: str = "rgba(126, 211, 33, 0.35)"
    brand_slate_badge: str = "#0f172a"
    radius: SquircleRadii = SQUIRCLE_RADII


# ── Julius Dark Theme (default) ──────────────────────────────────────────────
DARK_THEME = ThemeTokens(
    name="dark",
    bg="#121214",           # Julius System Dark
    surface="#1c1c1e",      # +4% lightness shift
    raised="#2c2c2e",       # +8% lightness shift
    text="#f5f5f7",         # Julius primary text (15.6:1 contrast against bg)
    text_dim="#86868b",     # Julius secondary text (4.9:1 contrast against bg)
    text_faint="#48484a",   # Tertiary/subtle text
    accent="#c8b896",       # Dusty 100-year-old antique paper / parchment rgba(200, 184, 150)
    success="#30d158",      # Julius System Green
    warning="#ffd60a",      # Julius System Yellow
    error="#ff453a",        # Julius System Red
    border_idle="#3e3e42",  # Crisp defined idle border
    border_focused="#c8b896", # Focused dusty antique paper border
    scrim="rgba(0, 0, 0, 0.65)",
    is_dark=True,
    is_no_color=False,
    brand_gold="#c8b896",
    brand_crimson="#731a1a",
    brand_obsidian="#1a1a1a",
    brand_electric_green="#7ed321",
    brand_green_deep="#006a25",
    brand_green_glow="rgba(126, 211, 33, 0.35)",
    brand_slate_badge="#0f172a",
    radius=SQUIRCLE_RADII,
)

# ── Julius Light Theme ────────────────────────────────────────────────────────
LIGHT_THEME = ThemeTokens(
    name="light",
    bg="#f5f5f7",           # Julius System Light
    surface="#e5e5ea",      # Subtle inset surface
    raised="#d1d1d6",       # Raised card surface
    text="#1d1d1f",         # Primary dark text (14.8:1 contrast against bg)
    text_dim="#6e6e73",     # Secondary text (4.8:1 contrast against bg)
    text_faint="#aeaeb2",   # Tertiary/subtle text
    accent="#007aff",       # Julius System Blue (light)
    success="#34c759",      # Julius System Green (light)
    warning="#c8b896",      # Dusty aged parchment tone
    error="#ff3b30",        # Julius System Red (light)
    border_idle="#c7c7cc",  # Crisp defined idle light border
    border_focused="#007aff", # Focused light accent
    scrim="rgba(0, 0, 0, 0.35)",
    is_dark=False,
    is_no_color=False,
    brand_gold="#c8b896",
    brand_crimson="#731a1a",
    brand_obsidian="#1a1a1a",
    brand_electric_green="#7ed321",
    brand_green_deep="#006a25",
    brand_green_glow="rgba(126, 211, 33, 0.35)",
    brand_slate_badge="#0f172a",
    radius=SQUIRCLE_RADII,
)

# Aliases
JULIUS_DARK_THEME = DARK_THEME
JULIUS_LIGHT_THEME = LIGHT_THEME
APPLE_DARK_THEME = DARK_THEME
APPLE_LIGHT_THEME = LIGHT_THEME

# ── NO_COLOR / ANSI 16-Color Fallback ───────────────────────────────────────
NO_COLOR_THEME = ThemeTokens(
    name="no_color",
    bg="default",
    surface="default",
    raised="default",
    text="default",
    text_dim="dim",
    text_faint="dim",
    accent="default",
    success="default",
    warning="default",
    error="default",
    border_idle="dim",
    border_focused="default",
    scrim="default",
    is_dark=True,
    is_no_color=True,
    brand_gold="default",
    brand_crimson="default",
    brand_obsidian="default",
    brand_electric_green="default",
    brand_green_deep="default",
    brand_green_glow="default",
    brand_slate_badge="default",
    radius=SQUIRCLE_RADII,
)


def query_terminal_osc11(timeout_seconds: float = 0.04) -> Optional[str]:
    """
    Query terminal emulator for background color using OSC 11 with short timeout.
    Returns 'light', 'dark', or None if unsupported or timeout expires.
    """
    if termios is None or tty is None or not sys.stdin.isatty() or not sys.stdout.isatty():
        return None
    try:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            # Send OSC 11 query
            sys.stdout.write("\033]11;?\033\\")
            sys.stdout.flush()

            r, _, _ = select.select([fd], [], [], timeout_seconds)
            if not r:
                return None
            response = sys.stdin.read(24)
            if "rgb:" in response:
                parts = response.split("rgb:")[1].split("/")[0:3]
                r_val = int(parts[0][:2], 16)
                g_val = int(parts[1][:2], 16)
                b_val = int(parts[2][:2], 16)
                luminance = 0.299 * r_val + 0.587 * g_val + 0.114 * b_val
                return "light" if luminance > 128 else "dark"
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        pass
    return None


def check_colorfgbg_env() -> Optional[str]:
    """
    Check COLORFGBG environment variable (e.g. '15;0' or '0;15').
    Standard convention: 0-6,8 is dark, 7,15 is light background.
    """
    val = os.environ.get("COLORFGBG", "").strip()
    if val:
        parts = val.split(";")
        try:
            bg_num = int(parts[-1])
            return "light" if bg_num in (7, 15) else "dark"
        except (ValueError, IndexError):
            pass
    return None


def detect_color_scheme() -> str:
    """
    Detect terminal light or dark theme in order:
    1. NO_COLOR env var -> 'no_color'
    2. Terminal background query via OSC 11
    3. COLORFGBG environment variable
    4. Fall back to 'dark'
    """
    if os.environ.get("NO_COLOR"):
        return "no_color"

    detected = query_terminal_osc11()
    if detected in ("light", "dark"):
        return detected

    cfgbg = check_colorfgbg_env()
    if cfgbg in ("light", "dark"):
        return cfgbg

    return "dark"


def get_theme(name: str = "auto") -> ThemeTokens:
    """Resolve theme tokens by name ('auto', 'dark', 'light', 'no_color')."""
    if os.environ.get("NO_COLOR"):
        return NO_COLOR_THEME

    normalized = name.lower().strip()
    if normalized == "auto":
        detected = detect_color_scheme()
        if detected == "light":
            return LIGHT_THEME
        elif detected == "no_color":
            return NO_COLOR_THEME
        return DARK_THEME
    elif normalized == "light":
        return LIGHT_THEME
    elif normalized == "no_color":
        return NO_COLOR_THEME
    return DARK_THEME


def generate_tcss(theme: ThemeTokens) -> str:
    """Generate Textual CSS for the Julius interface."""
    if theme.is_no_color:
        return """
        * {
            pointer: default;
        }

        Screen, Container, ScrollableContainer, ConversationArea, Composer, TextArea {
            pointer: default;
        }

        Screen {
            layout: vertical;
            padding: 0 2;
            margin: 0;
            background: default;
        }

        #main-column {
            width: 1fr;
            height: 1fr;
            layout: vertical;
            background: default;
            padding: 0;
            margin: 0;
        }

        ConversationArea, #conversation-area {
            height: 1fr;
            width: 1fr;
            overflow-y: auto;
            overflow-x: hidden;
            scrollbar-size: 0 0;
            scrollbar-gutter: auto;
        }

        #welcome-view {
            width: 1fr;
            height: 100%;
            align: center middle;
            content-align: center middle;
            text-align: center;
        }

        #welcome-view.scrolled-header {
            height: auto;
            padding-top: 1;
            padding-bottom: 1;
        }

        .wordmark-banner {
            color: #ffffff;
            text-style: bold;
            text-align: center;
            content-align: center middle;
            width: 1fr;
        }

        #toast-notification {
            display: none;
        }

        UserMessage {
            width: auto;
            max-width: 100%;
            height: auto;
            margin-top: 1;
            margin-bottom: 1;
            margin-left: 8;
            margin-right: 8;
            padding: 0 1;
            background: transparent;
            border: round default;
        }

        AssistantMessage {
            width: 1fr;
            height: auto;
            margin-top: 1;
            margin-bottom: 1;
            margin-left: 8;
            margin-right: 8;
            padding: 0 1;
            background: transparent;
        }

        ToolSummary {
            width: 1fr;
            height: auto;
            margin-top: 1;
            margin-bottom: 1;
            margin-left: 8;
            margin-right: 8;
            padding: 0 1;
        }

        ThinkingDot, .thinking-indicator, #thinking-indicator {
            width: 1fr;
            height: auto;
            min-height: 1;
            margin-top: 1;
            margin-bottom: 1;
            margin-left: 8;
            margin-right: 8;
            padding: 0 1;
        }

        Composer, #composer-input, #composer-container {
            width: 1fr;
            height: auto;
            min-height: 3;
            max-height: 8;
            border: round default;
            background: transparent;
            margin-top: 0;
            padding: 0 1;
        }

        Composer > .text-area--cursor-line {
            background: transparent;
        }

        Composer > .text-area--cursor-gutter {
            background: transparent;
        }

        #status-line {
            height: 1;
            width: 1fr;
            layout: horizontal;
            padding: 0 1;
        }

        #status-hint {
            width: auto;
            color: default;
            text-align: left;
        }

        #status-model {
            width: 1fr;
            color: default;
            text-align: right;
        }

        #terminal-too-small-warning {
            width: 1fr;
            height: 1fr;
            content-align: center middle;
            text-align: center;
            display: none;
        }
        """

    return f"""
    * {{
        pointer: default;
    }}

    Screen, Container, ScrollableContainer, ConversationArea, Composer, TextArea {{
        pointer: default;
    }}

    Screen {{
        layout: vertical;
        padding: 0 2;
        margin: 0;
        background: {theme.bg};
    }}

    #main-column {{
        width: 1fr;
        height: 1fr;
        layout: vertical;
        background: {theme.bg};
        padding: 0;
        margin: 0;
    }}

    ConversationArea, #conversation-area {{
        height: 1fr;
        width: 1fr;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-size: 0 0;
        scrollbar-gutter: auto;
        scrollbar-color: {theme.text_faint} {theme.bg};
        scrollbar-color-hover: {theme.text_dim} {theme.bg};
        scrollbar-color-active: {theme.accent} {theme.bg};
        background: {theme.bg};
    }}

    /* Welcome view when conversation is empty: dead center */
    #welcome-view {{
        width: 1fr;
        height: 100%;
        background: {theme.bg};
        align: center middle;
        content-align: center middle;
        text-align: center;
    }}

    #welcome-view.scrolled-header {{
        height: auto;
        padding-top: 1;
        padding-bottom: 1;
    }}

    .wordmark-banner {{
        color: {"#000000" if theme.name == "light" else "#ffffff"};
        text-style: bold;
        text-align: center;
        content-align: center middle;
        width: 1fr;
    }}

    .wordmark {{
        color: {theme.text_dim};
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }}

    /* User Message: Defined outer box with rounded corners matching the composer, dynamically sized */
    UserMessage {{
        width: auto;
        max-width: 100%;
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
        margin-left: 8;
        margin-right: 8;
        padding: 0 1;
        background: transparent;
        border: round {theme.border_idle};
        color: {theme.text};
    }}

    /* Assistant Message: No box, plain text on base background */
    AssistantMessage {{
        width: 1fr;
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
        margin-left: 8;
        margin-right: 8;
        padding: 0 1;
        background: {theme.bg};
        color: {theme.text};
    }}

    /* Tool summary: Collapsible quiet dim line */
    ToolSummary {{
        width: 1fr;
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
        margin-left: 8;
        margin-right: 8;
        padding: 0 1;
        color: {theme.text_dim};
    }}

    ToolSummary:focus {{
        color: {theme.accent};
    }}

    /* Thinking indicator: Calm single-line reasoning status */
    ThinkingDot, .thinking-indicator, #thinking-indicator {{
        width: 1fr;
        height: auto;
        min-height: 1;
        margin-top: 1;
        margin-bottom: 1;
        margin-left: 8;
        margin-right: 8;
        padding: 0 1;
        color: {theme.text_dim};
    }}


    /* Composer: Rounded input, defined outer box, matching brand gold #C8B896 rounded corners */
    Composer, #composer-input, #composer-container {{
        width: 1fr;
        height: auto;
        min-height: 3;
        max-height: 8;
        border: round {theme.brand_gold};
        background: transparent;
        color: {theme.text};
        margin-top: 0;
        padding: 0 1;
    }}

    Composer:focus, #composer-input:focus, #composer-container:focus-within {{
        border: round {theme.border_focused};
    }}

    Composer > .text-area--cursor-line {{
        background: transparent;
    }}

    Composer > .text-area--cursor-gutter {{
        background: transparent;
    }}

    Composer .text-area--cursor {{
        background: {theme.accent};
        color: {theme.bg};
        text-style: bold;
    }}

    /* Status line: One dim line below input */
    #status-line {{
        height: 1;
        width: 1fr;
        layout: horizontal;
        color: {theme.text_dim};
        background: {theme.bg};
        margin-top: 0;
        padding: 0 1;
    }}

    #status-hint {{
        width: auto;
        color: {theme.text_faint};
        text-align: left;
    }}

    #status-hint:hover {{
        color: {theme.text};
    }}

    #status-model {{
        width: 1fr;
        color: {theme.text_dim};
        text-align: right;
    }}

    #status-model:hover {{
        color: {theme.text};
    }}

    #status-model.loading {{
        color: {theme.accent};
        text-align: right;
    }}

    #status-model.loading:hover {{
        color: #ded2b8;
        text-style: underline;
    }}

    /* Toast overlay (e.g. 'Copied' 1.2s) */
    #toast-notification {{
        dock: top;
        height: 1;
        width: 100%;
        text-align: center;
        color: {theme.text};
        background: {theme.surface};
        display: none;
    }}

    /* Modal dialogs: Dim overlay with rounded card */
    .modal-scrim {{
        align: center middle;
        background: {theme.scrim};
    }}

    .modal-card {{
        width: 60;
        max-width: 90%;
        height: auto;
        max-height: 80%;
        background: {theme.surface};
        border: round {theme.raised};
        padding: 1 2;
    }}

    #terminal-too-small-warning {{
        width: 1fr;
        height: 1fr;
        content-align: center middle;
        text-align: center;
        color: {theme.text_dim};
        background: {theme.bg};
        display: none;
    }}
    """
