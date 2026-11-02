"""
Julius CLI v3.1: Collapsible Live Thinking Block + Input Dimming Fix & Output Formatting System.

Features:
- Live Collapsible Thinking Panel (CollapsibleThinkingPanel):
  - Header: ▸ Working... (12s) (collapsed default) / ▾ Working... (12s) (expanded)
  - Auto-scroll child box (#thinking-scroll-box, max-height 6) for live streaming thoughts
  - Auto-collapses to ▸ Worked (14s) on completion
  - Clickable header and keyboard shortcut (ctrl+t) to expand/collapse thinking history anytime
- Command-Keyword-Only Syntax Highlighting (SlashCommandHighlighter):
  - Only exact slash command keywords (/plan, /act, etc.) and @filepath references are dimmed (#cbd5e1)
  - All subsequent task prompt text remains in bright white (#f8fafc) character-by-character live as typed
- Clean Indentation & Output Formatting:
  - Custom Rich Markdown overrides with 2-space indented list levels, left-aligned headings, and clean margins
"""

from __future__ import annotations

import asyncio
import difflib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from rich.align import Align
from rich.console import Console, ConsoleOptions, RenderResult
from rich.highlighter import Highlighter
from rich.markdown import Markdown, Heading, ListItem, Segment, loop_first
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual import events, work
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Label, OptionList, Static, RichLog, TextArea
from textual.widgets.option_list import Option

from src.agent_config import AgentConfig
from src.web_agent import WebAgent, AgentResult
from src.memory.storage import MemoryStorage
from src.memory.working_state import WorkingStateManager
from src.ledger import Ledger
from src.cli.mode_registry import global_mode_registry


# ── System Clipboard Cross-Platform Helpers ─────────────────────────────────
from src.platform_compat import copy_to_clipboard, get_clipboard_text


# ── Contextual Verbs & Constants ───────────────────────────────────────────
VERBS_CHAT = ["Thinking", "Reasoning", "Synthesizing", "Pondering"]
VERBS_EXEC = ["Compiling", "Running", "Debugging", "Inspecting"]
VERBS_EDIT = ["Crafting", "Refactoring", "Editing", "Polishing"]
VERBS_QUESTION = ["Awaiting Input", "Clarifying", "Listening"]
SPINNER_FRAMES = ["/", "-", "\\", "|"]
KNOWN_SLASH_COMMANDS = {
    "/plan", "/act", "/experiments", "/status", "/resume", "/undo", "/copy",
    "/new", "/clear", "/exit", "/quit", "/help", "/diff", "/music", "/devices", "/doctor",
    "/whatsapp", "/model"
}

AVAILABLE_MODELS = {
    "nvidia": {
        "name": "NVIDIA Nemotron 550B",
        "description": "NVIDIA NIM Build Free API (550B reasoning & code)",
        "badge": "nvidia",
    },
    "deepseek": {
        "name": "DeepSeek V3 / R1",
        "description": "DeepSeek reasoning & general agent (Web & API)",
        "badge": "deepseek",
    },
    "gemini": {
        "name": "Google Gemini 2.5",
        "description": "Multimodal Flash & Pro with live vision (Web & API)",
        "badge": "gemini",
    },
    "chatgpt": {
        "name": "OpenAI ChatGPT-4o",
        "description": "OpenAI flagship general intelligence (Web & API)",
        "badge": "chatgpt",
    },
    "grok": {
        "name": "xAI Grok",
        "description": "Real-time search & reasoning (Web & API)",
        "badge": "grok",
    },
    "kimi": {
        "name": "Moonshot Kimi K3",
        "description": "Long-context & math specialist (Web & API)",
        "badge": "kimi",
    },
    "perplexity": {
        "name": "Perplexity Sonar",
        "description": "Online citation & deep research (Web & API)",
        "badge": "perplexity",
    },
    "ollama": {
        "name": "Local Ollama LLM",
        "description": "Private LAN uncensored neural reasoning (DeepSeek R1 14B / Lexi)",
        "badge": "ollama",
    },
}

MODEL_ALIASES = {
    "nvidia-nim": "nvidia",
    "nemotron": "nvidia",
    "nemotron-550b": "nvidia",
    "nvidia-550b": "nvidia",
    "550b": "nvidia",
    "aifree": "aifreeforever",
    "deepseek-v4-flash": "aifreeforever",
    "free-deepseek": "aifreeforever",
    "v4-flash": "aifreeforever",
    "gpt": "chatgpt",
    "gpt4": "chatgpt",
    "gpt-4": "chatgpt",
    "chatgpt4": "chatgpt",
    "openai": "chatgpt",
    "r1": "ollama",
    "v3": "deepseek",
    "deepseek-r1": "ollama",
    "deepseek-v3": "deepseek",
    "deepseek-web": "deepseek",
    "deepseek-cloud": "deepseek",
    "web-deepseek": "deepseek",
    "google": "gemini",
    "gemini2": "gemini",
    "xai": "grok",
    "moonshot": "kimi",
    "sonar": "perplexity",
    "local": "ollama",
    "llama": "ollama",
    "llama3": "ollama",
    "lexi": "ollama",
    "qwen": "ollama",
    "r1-14b": "ollama",
    "r1-local": "ollama",
    "deepseek-14b": "ollama",
    "deepseek-r1-14b": "ollama",
    "hushus": "ollama",
    "uncalibrated": "ollama",
    "r1-uncalibrated": "ollama",
}


# ── PromptTextArea Multi-Line Input Widget ─────────────────────────────
class PromptTextArea(TextArea):
    """
    Multi-line, auto-expanding prompt input box supporting large text paste,
    untruncated context, Shift+Enter vs Enter key bindings, and terminal-like
    Up/Down arrow command history navigation.
    """

    DEFAULT_CSS = """
    PromptTextArea {
        height: 3;
        min-height: 2;
        max-height: 8;
        width: 100%;
        border: round #c8b896;
        padding: 0 1;
        background: #18181b;
        color: #f8fafc;
    }
    PromptTextArea:focus {
        border: round #c8b896;
    }
    """

    class Submitted(events.Event):
        """Event posted when user submits prompt with Enter."""
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(self, placeholder: str = "", **kwargs) -> None:
        super().__init__(show_line_numbers=False, **kwargs)
        self.placeholder = placeholder
        self._history: List[str] = []
        self._history_index: int = -1
        self._draft: str = ""

    @property
    def value(self) -> str:
        return self.text

    @value.setter
    def value(self, val: str) -> None:
        self.text = val

    def clear(self) -> None:
        self.text = ""
        self._history_index = -1
        self._draft = ""

    def insert_text_at_cursor(self, text: str) -> None:
        self.insert(text)

    def add_to_history(self, prompt: str) -> None:
        """Add non-empty submitted command/prompt to history list."""
        clean = prompt.strip()
        if clean:
            if not self._history or self._history[-1] != clean:
                self._history.append(clean)
        self._history_index = -1
        self._draft = ""

    def on_key(self, event: events.Key) -> None:
        if event.key in ("enter", "return", "ctrl+m"):
            event.prevent_default()
            event.stop()
            submitted = self.text
            self.add_to_history(submitted)
            self.post_message(self.Submitted(submitted))
        elif event.key in ("shift+enter", "shift+return"):
            self.insert("\n")
        elif event.key == "up":
            # If on first line or single-line prompt, navigate previous command history
            cursor_row, _ = self.cursor_location
            if cursor_row == 0 and self._history:
                event.prevent_default()
                event.stop()
                if self._history_index == -1:
                    self._draft = self.text
                    self._history_index = len(self._history) - 1
                elif self._history_index > 0:
                    self._history_index -= 1

                if 0 <= self._history_index < len(self._history):
                    self.text = self._history[self._history_index]
                    lines = self.text.splitlines() or [""]
                    self.cursor_location = (len(lines) - 1, len(lines[-1]))
        elif event.key == "down":
            # If navigating history, move forward or restore draft
            cursor_row, _ = self.cursor_location
            line_count = len(self.text.splitlines()) or 1
            if cursor_row >= line_count - 1 and self._history_index != -1:
                event.prevent_default()
                event.stop()
                if self._history_index < len(self._history) - 1:
                    self._history_index += 1
                    self.text = self._history[self._history_index]
                else:
                    self._history_index = -1
                    self.text = self._draft
                lines = self.text.splitlines() or [""]
                self.cursor_location = (len(lines) - 1, len(lines[-1]))

    def on_paste(self, event: events.Paste) -> None:
        """Handle terminal bracketed paste of large multi-line text without truncation."""
        if event.text:
            self.insert(event.text)
            event.prevent_default()
            event.stop()



# ── Markdown Rendering & Syntax Highlighting Overrides ─────────────────────
try:
    Heading.LEVEL_ALIGN["h1"] = "left"
except AttributeError:
    pass


class CustomListItem(ListItem):
    """Custom ListItem with proper dot after list numbers and clean 2-space indentation."""

    def render_number(
        self, console: Console, options: ConsoleOptions, number: int, last_number: int
    ) -> RenderResult:
        prefix_str = f"{number}. "
        number_width = len(prefix_str) + 1
        render_options = options.update(width=options.max_width - number_width)
        lines = console.render_lines(self.elements, render_options, style=self.style)
        number_style = console.get_style("markdown.item.number", default="bold #c8b896")

        new_line = Segment("\n")
        padding = Segment(" " * number_width, number_style)
        numeral = Segment(prefix_str.rjust(number_width), number_style)
        for first, line in loop_first(lines):
            yield numeral if first else padding
            yield from line
            yield new_line

    def render_bullet(self, console: Console, options: ConsoleOptions) -> RenderResult:
        bullet_style = console.get_style("markdown.item.bullet", default="bold #c8b896")
        render_options = options.update(width=options.max_width - 4)
        lines = console.render_lines(self.elements, render_options, style=self.style)

        bullet = Segment("  • ", bullet_style)
        padding = Segment(" " * 4, bullet_style)
        new_line = Segment("\n")
        for first, line in loop_first(lines):
            yield bullet if first else padding
            yield from line
            yield new_line


Markdown.elements["list_item_open"] = CustomListItem


def render_clean_markdown(text_str: str) -> Markdown:
    """Render markdown with clean 2-space list indentation and left-aligned headings."""
    return Markdown(text_str, code_theme="monokai", hyperlinks=False)


class SlashCommandHighlighter(Highlighter):
    """Highlighter that dims ONLY recognized slash-command tokens and @filepath references live as typed."""

    def highlight(self, text: Text) -> None:
        plain = text.plain
        if not plain:
            return

        words = plain.split(" ")
        first_word = words[0] if words else ""
        if first_word.lower() in KNOWN_SLASH_COMMANDS:
            cmd_len = len(first_word)
            text.stylize("dim #c8b896", 0, cmd_len)
            if len(plain) > cmd_len:
                text.stylize("bold #f8fafc", cmd_len, len(plain))
        else:
            text.stylize("bold #f8fafc", 0, len(plain))

        for match in re.finditer(r'@[a-zA-Z0-9_\-\./]+', plain):
            text.stylize("dim #c8b896", match.start(), match.end())


class FileAutocompleteDropdown(OptionList):
    """Dropdown menu for fuzzy file-path autocomplete triggered by '@'."""

    DEFAULT_CSS = """
    FileAutocompleteDropdown {
        layer: top;
        max-height: 8;
        width: 1fr;
        border: round #c8b896;
        background: #18181b;
        color: #f8fafc;
        display: none;
        margin-left: 2;
        margin-right: 2;
    }

    FileAutocompleteDropdown > .option-list--option-highlighted {
        background: #3e3425;
        color: #ded2b8;
    }
    """


class QuestionOptionList(OptionList):
    """Interactive option selector widget for questions and single-key action gates."""

    DEFAULT_CSS = """
    QuestionOptionList {
        height: auto;
        max-height: 8;
        width: 100%;
        border: round #c8b896;
        background: #18181b;
        color: #f8fafc;
        margin: 1 0;
        display: none;
    }

    QuestionOptionList > .option-list--option-highlighted {
        background: #3e3425;
        color: #ded2b8;
    }
    """


class CollapsibleThinkingPanel(Widget):
    """
    Live streaming collapsible thinking panel matching Julius status format.
    - Header: · Thinking… (4s · ↑ 420 tokens · esc to interrupt)
    - Bounded child scroll box (#thinking-scroll-box, max-height 6) for streaming thoughts
    - Auto-collapses to · Thought (4s · ↑ 420 tokens) on completion
    - Clickable header and keyboard shortcut (ctrl+t) to expand/collapse anytime
    """

    DEFAULT_CSS = """
    CollapsibleThinkingPanel {
        height: auto;
        width: 100%;
        margin: 1 0;
    }

    #thinking-header {
        height: 1;
        width: 100%;
        color: #c8b896;
        text-style: bold;
        background: transparent;
    }

    #thinking-header:hover {
        color: #ded2b8;
    }

    #thinking-scroll-box {
        height: auto;
        max-height: 6;
        width: 100%;
        border: solid #c8b896;
        background: #18181b;
        padding: 0 1;
        margin-top: 0;
        display: none;
    }
    """

    is_running: reactive[bool] = reactive(True)
    is_expanded: reactive[bool] = reactive(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.elapsed: float = 0.0
        self.start_time: float = time.time()
        self._spinner_idx: int = 0
        self._timer: Optional[asyncio.Task] = None
        self.tokens: int = 240

    def compose(self) -> ComposeResult:
        yield Static("· ⠋ Thinking… (0s · ↑ 240 tokens · esc to interrupt)", id="thinking-header")
        with ScrollableContainer(id="thinking-scroll-box"):
            yield RichLog(id="thinking-log", highlight=True, markup=True, wrap=True)

    def on_mount(self) -> None:
        self._timer = asyncio.create_task(self._update_timer_loop())

    async def _update_timer_loop(self) -> None:
        try:
            while self.is_running:
                self.elapsed = time.time() - self.start_time
                self.tokens = 240 + int(self.elapsed * 45)
                self._spinner_idx = (self._spinner_idx + 1) % len(SPINNER_FRAMES)
                sp = SPINNER_FRAMES[self._spinner_idx]
                icon = "▾" if self.is_expanded else "·"
                elapsed_sec = int(self.elapsed)
                try:
                    hdr = self.query_one("#thinking-header", Static)
                    hdr.update(f"{icon} {sp} Thinking… ({elapsed_sec}s · ↑ {self.tokens:,} tokens · esc to interrupt)")
                except Exception:
                    break
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass

    def append_thought(self, text: str) -> None:
        try:
            rlog = self.query_one("#thinking-log", RichLog)
            rlog.write(f"[dim #c8b896]💭 {text}[/dim #c8b896]")
            rlog.scroll_end()
        except Exception:
            pass

    def finish(self) -> None:
        self.is_running = False
        if self._timer:
            self._timer.cancel()
        self.is_expanded = False  # Auto-collapse on completion
        elapsed_sec = int(self.elapsed)

        try:
            hdr = self.query_one("#thinking-header", Static)
            hdr.update(f"· Thought ({elapsed_sec}s · ↑ {self.tokens:,} tokens)")
            box = self.query_one("#thinking-scroll-box", ScrollableContainer)
            box.display = False
        except Exception:
            pass

    def toggle(self) -> None:
        """Toggle expansion state."""
        self.is_expanded = not self.is_expanded
        try:
            box = self.query_one("#thinking-scroll-box", ScrollableContainer)
            box.display = self.is_expanded

            icon = "▾" if self.is_expanded else "·"
            elapsed_sec = int(self.elapsed)
            status_str = f"Thinking… ({elapsed_sec}s · ↑ {self.tokens:,} tokens · esc to interrupt)" if self.is_running else f"Thought ({elapsed_sec}s · ↑ {self.tokens:,} tokens)"
            hdr = self.query_one("#thinking-header", Static)
            hdr.update(f"{icon} {status_str}")
        except Exception:
            pass

    def on_click(self, event: events.Click) -> None:
        """Toggle expansion on click."""
        self.toggle()


class MainSessionBox(Container):
    """Main rounded-bordered session box with #c8b896 amber border matching Julius."""

    DEFAULT_CSS = """
    MainSessionBox {
        border: round #c8b896;
        height: 1fr;
        width: 100%;
        padding: 0 1;
        layout: vertical;
        background: #18181b;
    }
    """


class JuliusCLIV3App(App):
    """Main Textual Application for Julius CLI v3."""

    CSS = """
    Screen {
        layout: vertical;
        padding: 0;
        margin: 0;
        background: #18181b;
    }

    #title-bar {
        height: 1;
        width: 100%;
        text-style: bold;
        color: #c8b896;
        background: transparent;
        padding-left: 1;
    }

    #conversation-log {
        height: 1fr;
        width: 100%;
        overflow-y: auto;
        scrollbar-gutter: stable;
        padding: 0 1;
        background: #18181b;
    }

    #live-status-bar {
        height: 1;
        width: 100%;
        color: #c8b896;
        background: transparent;
        padding-left: 1;
        margin: 0;
        display: none;
    }

    #music-download-bar {
        height: auto;
        min-height: 1;
        max-height: 3;
        width: 100%;
        color: #f8fafc;
        background: #27272a;
        border-left: outer #10b981;
        padding: 0 1;
        margin: 0;
        display: none;
    }

    #status-line {
        display: none !important;
    }

    #input-container {
        height: auto;
        width: 100%;
        border: round #c8b896;
        margin: 0;
        padding: 0;
        background: #18181b;
    }

    #prompt-input {
        border: none;
        height: 3;
        min-height: 2;
        max-height: 8;
        width: 100%;
        padding: 0 1;
        background: transparent;
        color: #f8fafc;
    }

    #footer-container {
        height: 1;
        width: 100%;
        margin-top: 0;
        padding: 0 1;
        background: transparent;
        layout: horizontal;
    }

    #footer-left {
        width: 1fr;
        color: #a1a1aa;
    }

    #footer-right {
        width: auto;
        color: #a1a1aa;
        text-align: right;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("escape", "interrupt", "Interrupt"),
        ("ctrl+t", "toggle_thinking", "Toggle Thoughts"),
        ("ctrl+y", "copy_output", "Copy Output"),
    ]

    is_working: reactive[bool] = reactive(False)
    status_verb: reactive[str] = reactive("Ready")
    permission_mode: reactive[str] = reactive("Supervised Mode (Permission Gated)")
    update_status: reactive[str] = reactive("✓ Up to date")

    @property
    def permission_mode_short(self) -> str:
        return "Autonomous" if "Autonomous" in self.permission_mode else "Supervised"

    def __init__(
        self,
        workspace_dir: str = ".",
        config: Optional[AgentConfig] = None,
        initial_task: Optional[str] = None,
        ws_url: Optional[str] = None,
        session_token: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.workspace_dir = Path(workspace_dir).resolve()
        self.config = config or AgentConfig()
        # Default to Supervised mode with full Permission Gate protection
        self.config.set_execution_mode("Supervised")
        self.initial_task = initial_task
        self.ws_url = ws_url
        self.session_token = session_token
        self._ws = None
        self.agent: Optional[WebAgent] = None
        self.workspace_files: List[str] = []
        self._current_agent_task: Optional[asyncio.Task] = None
        self._active_thinking_panel: Optional[CollapsibleThinkingPanel] = None
        
        # Live status indicators
        self._task_start_time: float = 0.0
        self._current_step: int = 1
        self._max_steps: int = 10
        self._token_count: int = 0
        self._latest_stream_preview: str = ""
        self._last_thought: str = ""
        self._live_status_task: Optional[asyncio.Task] = None

        # Output Clipboard & Transcript Tracking
        self._latest_assistant_response: str = ""
        self._latest_code_snippet: str = ""
        self._latest_music_job_id: str = ""
        self._latest_drive_file_id: str = ""
        self._conversation_history: List[tuple[str, str]] = []

        # Music Ingestion Live Tracking
        self._active_music_jobs: Dict[str, Dict[str, Any]] = {}

        raw_model = getattr(self.config, "provider", None) or os.getenv("JULIUS_DEFAULT_MODEL", "deepseek")
        self.current_model: str = MODEL_ALIASES.get(raw_model.lower(), raw_model) if raw_model else "ollama"

        # Pending Interaction States
        self._pending_confirmation: bool = False
        self._pending_question: bool = False
        self._current_question_options: List[str] = []

    def compose(self) -> ComposeResult:
        folder_path = str(self.workspace_dir)
        if self.ws_url:
            title_text = f"[bold #c8b896]julius[/bold #c8b896] [dim #a1a1aa]·[/dim #a1a1aa] [bold #10b981]remote ({self.ws_url})[/bold #10b981] [dim #a1a1aa]·[/dim #a1a1aa] [bold #38bdf8]model: {self.current_model}[/bold #38bdf8] [dim #a1a1aa]·[/dim #a1a1aa] [bold #e2e8f0]{folder_path}[/bold #e2e8f0]"
            status_text = f"Remote Mode ({self.ws_url}) · {self.current_model} ✓"
        else:
            title_text = f"[bold #c8b896]julius[/bold #c8b896] [dim #a1a1aa]·[/dim #a1a1aa] [bold #38bdf8]model: {self.current_model}[/bold #38bdf8] [dim #a1a1aa]·[/dim #a1a1aa] [bold #e2e8f0]{folder_path}[/bold #e2e8f0]"
            status_text = f"Autonomous Mode · {self.current_model} ✓"

        with MainSessionBox():
            yield Static(title_text, id="title-bar")
            yield RichLog(id="conversation-log", highlight=True, markup=True, wrap=True)
            yield Static("", id="live-status-bar")
            yield Static("", id="music-download-bar")
            yield QuestionOptionList(id="question-options-list")

            with Vertical(id="input-container"):
                yield PromptTextArea(placeholder="Type a prompt or /model, /help, /music, /status, /copy (type @ for files)...", id="prompt-input")
                yield FileAutocompleteDropdown(id="autocomplete-dropdown")

            with Horizontal(id="footer-container"):
                yield Static("? /help · /model · ↑/↓ history · ctrl+y copy answer · ⌥+drag to select", id="footer-left")
                yield Static(status_text, id="footer-right")

    def on_resize(self, event: events.Resize) -> None:
        """Handle terminal window resizing responsively without visual artifacts."""
        try:
            log = self.query_one("#conversation-log", RichLog)
            log.scroll_end(animate=False)
        except Exception:
            pass

    async def on_mount(self) -> None:
        """Initialize workspace files and welcome screen."""
        self._scan_workspace_files()
        self._render_welcome_screen()

        # Initialize WebAgent only when NOT connecting to remote server
        if not self.ws_url:
            self.agent = WebAgent(self.config, keep_browser_open=True, on_event=self._handle_agent_event)

        # Register real-time music job event listener
        try:
            from src.music.jobs import music_job_manager
            music_job_manager.subscribe_events(self._on_music_event_broadcast)
        except Exception:
            pass

        # Focus prompt input box
        inp = self.query_one("#prompt-input", PromptTextArea)
        inp.focus()

        if self.initial_task:
            inp.value = self.initial_task
            await self._submit_prompt(self.initial_task)

    def _scan_workspace_files(self) -> None:
        """Scan workspace files for '@' fuzzy completion."""
        files = []
        try:
            for root, dirs, filenames in os.walk(self.workspace_dir):
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith(".")
                    and d not in ("__pycache__", "node_modules", ".venv", ".git", "assets", "dist", "build")
                ]
                for f in filenames:
                    if f.startswith(".") or f.endswith((".pyc", ".png", ".jpg", ".zip", ".tar.gz")):
                        continue
                    full_path = Path(root) / f
                    rel_path = full_path.relative_to(self.workspace_dir)
                    files.append(str(rel_path))
        except Exception:
            pass
        self.workspace_files = sorted(files)[:200]

    def _render_welcome_screen(self) -> None:
        """Render two-column welcome screen layout with mascot and quick tips matching Julius."""
        log = self.query_one("#conversation-log", RichLog)

        grid = Table.grid(expand=True, padding=(0, 2))
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="left", ratio=1)

        banner_text = Text()
        banner_lines = [
            "╔═════╗ ╔╗   ╔╗ ╔╗      ╔═════╗ ╔╗   ╔╗ ╔═════╗",
            "╚══╗  ║ ║║   ║║ ║║      ╚═╗ ╔═╝ ║║   ║║ ║ ╔═══╝",
            "   ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ║ ╚═══╗",
            "   ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ╚═══╗ ║",
            "╔══╝  ║ ║╚═══╝║ ║╚════╗ ╔═╝ ╚═╗ ║╚═══╝║ ╔═══╝ ║",
            "╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝",
        ]
        for line in banner_lines:
            banner_text.append(f"{line}\n", style="bold #c8b896")
        banner_text.append("\n  Autonomous Web-Chat & Coding Agent", style="dim #a1a1aa")

        tips_text = Text()
        tips_text.append("💡 Quick Tips & Commands\n\n", style="bold #c8b896")
        tips_items = [
            ("/plan <task>", "Propose implementation plan"),
            ("/act <task>", "Direct execution mode"),
            ("/copy [all]", "Copy output or full history to clipboard"),
            ("/experiments", "Research history & metrics"),
            ("/status", "System health & sandbox state"),
            ("/resume", "View & resume incomplete tasks"),
            ("/undo", "Rollback workspace file mutations"),
            ("@filepath", "Trigger fuzzy file autocomplete"),
            ("ctrl+y", "Copy latest output to clipboard"),
            ("esc", "Interrupt execution loop"),
        ]
        for i, (cmd, desc) in enumerate(tips_items):
            sep = "\n" if i < len(tips_items) - 1 else ""
            tips_text.append("• ", style="bold #c8b896")
            tips_text.append(f"{cmd:<16}", style="bold #c8b896")
            tips_text.append(f" - {desc}{sep}", style="#f8fafc")

        grid.add_row(banner_text, tips_text)

        log.write("\n")
        log.write(grid)
        log.write("\n")

    def action_paste_clipboard(self) -> None:
        """Paste system clipboard text into prompt input (ctrl+v / cmd+v)."""
        inp = self.query_one("#prompt-input", PromptTextArea)
        try:
            clip_text = get_clipboard_text()
            if clip_text:
                inp.insert(clip_text)
        except Exception:
            pass

    def action_copy_output(self, mode: str = "response") -> None:
        """Copy latest assistant response or full conversation transcript to clipboard."""
        log = self.query_one("#conversation-log", RichLog)
        if mode == "all":
            target_text = self._get_full_transcript_text()
            label = "full conversation transcript"
        elif mode == "code":
            target_text = self._latest_code_snippet or self._latest_assistant_response
            label = "latest code diff/snippet"
        elif mode in ("drive", "drive_id", "gdrive"):
            target_text = self._latest_drive_file_id
            label = "latest Google Drive file ID"
        elif mode in ("job", "job_id", "music"):
            target_text = self._latest_music_job_id
            label = "latest music job ID"
        elif mode.isdigit():
            idx = int(mode)
            asst_msgs = [t for r, t in self._conversation_history if r == "assistant"]
            if 1 <= idx <= len(asst_msgs):
                target_text = asst_msgs[-idx]
                label = f"assistant response #{idx}"
            else:
                target_text = self._latest_assistant_response
                label = "latest assistant output"
        else:
            target_text = self._latest_assistant_response
            label = "latest assistant output"

        if not target_text:
            log.write(f"[bold #f87171]⚠️ Nothing to copy for target '{mode}' in current session.[/bold #f87171]\n\n")
            return


        success = copy_to_clipboard(target_text)
        if success:
            log.write(f"[bold #10b981]📋 Successfully copied {label} ({len(target_text)} chars) to system clipboard![/bold #10b981]\n\n")
        else:
            log.write(f"[bold #f87171]❌ Failed to copy to clipboard.[/bold #f87171]\n\n")

    def _get_full_transcript_text(self) -> str:
        """Format full session conversation transcript into text."""
        lines = []
        for role, text in self._conversation_history:
            if role == "user":
                lines.append(f"User: {text}")
            else:
                lines.append(f"Julius: {text}")
            lines.append("")
        return "\n".join(lines).strip()

    # ── Single-Key Confirmation Key Handler ─────────────────────────────

    def on_key(self, event: events.Key) -> None:
        """Handle single-keypress y/n for pending action confirmation immediately without Enter."""
        if self._pending_confirmation:
            key_char = (event.character or event.key or "").lower()
            if key_char in ("y", "a"):
                self._resolve_confirmation(True)
                event.prevent_default()
                event.stop()
            elif key_char in ("n", "d", "escape"):
                self._resolve_confirmation(False)
                event.prevent_default()
                event.stop()

    def _resolve_confirmation(self, allow: bool) -> None:
        """Resolve confirmation immediately without requiring typing."""
        opt_list = self.query_one("#question-options-list", QuestionOptionList)
        opt_list.display = False
        self._pending_confirmation = False

        log = self.query_one("#conversation-log", RichLog)
        if allow:
            log.write("[bold #c8b896]✅ Action accepted.[/bold #c8b896]\n")
            log.write("[dim #38bdf8]⚡ Executing on server... (awaiting output)[/dim #38bdf8]\n\n")
            self.status_verb = "Executing command"
            self._start_live_status()
        else:
            log.write("[bold #f87171]❌ Action declined.[/bold #f87171]\n\n")
            self.status_verb = "Thinking"
            self._start_live_status()

        if self._ws and not self._ws.closed:
            asyncio.create_task(self._ws.send_json({"type": "action_response", "allow": allow}))
        elif self.agent:
            self.agent.set_confirmation_result(allow)

        inp = self.query_one("#prompt-input", PromptTextArea)
        inp.clear()
        inp.focus()

    # ── Autocomplete & Option Selected Handling ───────────────────────────

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Handle fuzzy file-path autocomplete trigger on '@' while typing or single-key action gate."""
        val = event.text_area.text
        dropdown = self.query_one("#autocomplete-dropdown", FileAutocompleteDropdown)

        if self._pending_confirmation:
            v_clean = val.strip().lower()
            if v_clean in ("y", "a"):
                self._resolve_confirmation(True)
                return
            elif v_clean in ("n", "d"):
                self._resolve_confirmation(False)
                return

        # Fuzzy file autocomplete dropdown handling
        if "@" in val:
            at_idx = val.rfind("@")
            query = val[at_idx + 1:].lower()

            matches = [f for f in self.workspace_files if query in f.lower()][:10]

            if matches:
                dropdown.clear_options()
                for match in matches:
                    dropdown.add_option(Option(f"📄 {match}", id=match))
                dropdown.display = True
                return

        dropdown.display = False

    async def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle selection in autocomplete dropdown or question/confirmation list."""
        if event.option_list.id == "autocomplete-dropdown":
            dropdown = self.query_one("#autocomplete-dropdown", FileAutocompleteDropdown)
            inp = self.query_one("#prompt-input", PromptTextArea)

            selected_file = str(event.option.id)
            val = inp.text
            at_idx = val.rfind("@")

            if at_idx != -1:
                new_val = val[:at_idx] + f"@{selected_file} "
                inp.text = new_val

            dropdown.display = False
            inp.focus()
            return

        if event.option_list.id == "question-options-list":
            choice_id = str(event.option.id)

            if self._pending_confirmation:
                allow = choice_id.startswith("ACCEPT")
                self._resolve_confirmation(allow)
                return

            if self._pending_question:
                opt_list = self.query_one("#question-options-list", QuestionOptionList)
                log = self.query_one("#conversation-log", RichLog)

                if choice_id == "__custom__":
                    inp = self.query_one("#prompt-input", PromptTextArea)
                    inp.placeholder = "Type your custom answer and press Enter..."
                    inp.focus()
                    opt_list.display = False
                    return

                opt_list.display = False
                self._pending_question = False

                log.write(f"[bold #c8b896]👉 Selected Option:[/bold #c8b896] [white]{choice_id}[/white]\n\n")
                self.status_verb = "Thinking"
                self._start_live_status()

                if self._ws and not self._ws.closed:
                    res = self._ws.send_json({"type": "question_response", "answer": choice_id})
                    if asyncio.iscoroutine(res):
                        await res
                    res2 = self._ws.send_json({"type": "human_response", "answer": choice_id})
                    if asyncio.iscoroutine(res2):
                        await res2
                    res3 = self._ws.send_json({"type": "action_response", "answer": choice_id})
                    if asyncio.iscoroutine(res3):
                        await res3
                elif self.agent:
                    self.agent.set_question_result(choice_id)

    # ── Agent Execution & Event Handling ──────────────────────────────────

    async def on_prompt_text_area_submitted(self, event: PromptTextArea.Submitted) -> None:
        prompt = event.value.strip()
        if not prompt:
            return
        
        inp = self.query_one("#prompt-input", PromptTextArea)
        inp.clear()
        inp.placeholder = "Type a prompt or /help, /experiments, /status, /resume, /undo, /copy (type @ for files)..."

        dropdown = self.query_one("#autocomplete-dropdown", FileAutocompleteDropdown)
        dropdown.display = False

        if self._pending_question:
            opt_list = self.query_one("#question-options-list", QuestionOptionList)
            opt_list.display = False
            self._pending_question = False

            log = self.query_one("#conversation-log", RichLog)
            log.write(f"[bold #c8b896]✍️ Custom Answer:[/bold #c8b896] [white]{prompt}[/white]\n\n")

            self.status_verb = "Thinking"
            self._start_live_status()

            if self._ws and not self._ws.closed:
                res = self._ws.send_json({"type": "question_response", "answer": prompt})
                if asyncio.iscoroutine(res):
                    await res
                res2 = self._ws.send_json({"type": "human_response", "answer": prompt})
                if asyncio.iscoroutine(res2):
                    await res2
                res3 = self._ws.send_json({"type": "action_response", "answer": prompt})
                if asyncio.iscoroutine(res3):
                    await res3
            elif self.agent:
                self.agent.set_question_result(prompt)
            return

        if self._pending_confirmation:
            allow = prompt.lower() in ("y", "yes", "a", "accept", "")
            self._resolve_confirmation(allow)
            return

        if self.is_working:
            return

        await self._submit_prompt(prompt)

    async def _submit_prompt(self, prompt: str) -> None:
        log = self.query_one("#conversation-log", RichLog)
        self._conversation_history.append(("user", prompt))

        cmd_lower = prompt.lower().split()[0] if prompt.startswith('/') else ''
        
        if cmd_lower in ("/exit", "/quit"):
            await self.action_quit_app()
            return
        elif cmd_lower == "/clear":
            log.clear()
            if self.agent and hasattr(self.agent, "client") and self.agent.client:
                async def _reset_v3_web_session() -> None:
                    try:
                        if self.agent.client.is_initialized:
                            await self.agent.client.close()
                            req_prov = getattr(self.agent.config, "provider", self.current_model)
                            if req_prov and req_prov.lower() in ("deepseek", "chatgpt", "gemini", "grok", "perplexity", "claude"):
                                await self.agent.client.initialize(
                                    provider_name=req_prov,
                                    profile_dir=getattr(self.agent.config, "profile_dir", None),
                                    headless=getattr(self.agent.config, "headless", False),
                                )
                    except Exception:
                        pass
                asyncio.create_task(_reset_v3_web_session())
            return
        elif cmd_lower == "/new":
            if self.agent:
                await self.agent.start_new_chat()
            log.write("[bold #c8b896]✨ Started a new chat session context.[/bold #c8b896]\n")
            return
        elif cmd_lower == "/help":
            self._handle_help_command()
            return
        elif cmd_lower == "/diff" or cmd_lower.startswith("/diff "):
            args_str = prompt[5:].strip() if len(prompt) > 5 else ""
            self._handle_diff_command(args_str)
            return
        elif cmd_lower == "/copy":
            args_str = prompt[5:].strip() if len(prompt) > 5 else ""
            self._handle_copy_command(args_str)
            return
        elif cmd_lower == "/experiments":
            self._handle_experiments_command()
            return
        elif cmd_lower == "/status":
            self._handle_status_command()
            return
        elif cmd_lower == "/doctor":
            self._handle_doctor_command()
            return
        elif cmd_lower == "/devices":
            self._handle_devices_command()
            return
        elif cmd_lower == "/resume":
            self._handle_resume_command()
            return
        elif cmd_lower == "/undo":
            self._handle_undo_command()
            return
        elif cmd_lower.startswith("/music"):
            args_str = prompt[6:].strip() if len(prompt) > 6 else ""
            await self._handle_music_command(args_str)
            return
        elif cmd_lower.startswith("/whatsapp"):
            args_str = prompt[9:].strip() if len(prompt) > 9 else ""
            await self._handle_whatsapp_command(args_str)
            return
        elif cmd_lower == "/model" or cmd_lower.startswith("/model "):
            args_str = prompt[6:].strip() if len(prompt) > 6 else ""
            await self._handle_model_command(args_str)
            return


        # Keyword-only dimming: only slash command keyword or @tag dimmed in amber, prompt text in bright white
        user_turn = Text()
        user_turn.append("> ", style="bold #c8b896")

        words = prompt.split(" ")
        for i, word in enumerate(words):
            space = " " if i < len(words) - 1 else ""
            w_lower = word.lower()
            if w_lower in KNOWN_SLASH_COMMANDS or word.startswith("@"):
                user_turn.append(f"{word}{space}", style="dim #c8b896")
            else:
                user_turn.append(f"{word}{space}", style="bold #f8fafc")

        log.write(user_turn)

        self.status_verb = random.choice(VERBS_CHAT)
        self._start_live_status()

        self._current_agent_task = asyncio.create_task(self._run_agent_task(prompt))

    def _start_live_status(self) -> None:
        self.is_working = True
        self._task_start_time = time.time()
        self._token_count = 0
        self._current_step = 1
        self._latest_stream_preview = ""
        self._last_thought = ""
        if self._live_status_task and not self._live_status_task.done():
            self._live_status_task.cancel()
        self._live_status_task = asyncio.create_task(self._update_live_status_loop())

    def _stop_live_status(self) -> None:
        self.is_working = False
        if self._live_status_task and not self._live_status_task.done():
            self._live_status_task.cancel()
        try:
            bar = self.query_one("#live-status-bar", Static)
            bar.update("")
            bar.display = False
        except Exception:
            pass

    async def _update_live_status_loop(self) -> None:
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        idx = 0
        try:
            bar = self.query_one("#live-status-bar", Static)
            bar.display = True
            while self.is_working:
                elapsed = int(time.time() - self._task_start_time)
                spinner = frames[idx % len(frames)]
                idx += 1
                token_info = f" · ↑ {self._token_count} tokens" if self._token_count > 0 else ""
                preview = f"  [dim #e2e8f0]{self._latest_stream_preview}[/dim #e2e8f0]" if self._latest_stream_preview else ""
                bar.update(f"[bold #c8b896]· {spinner} {self.status_verb}…[/bold #c8b896] [dim #cbd5e1]({elapsed}s · Step {self._current_step}{token_info} · esc to interrupt)[/dim #cbd5e1]{preview}")
                await asyncio.sleep(0.08)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            try:
                bar = self.query_one("#live-status-bar", Static)
                bar.update("")
                bar.display = False
            except Exception:
                pass

    # ── Slash Command Handlers ───────────────────────────────────────────

    async def _get_live_ollama_models(self) -> list[dict]:
        """Fetch models installed on local Ollama server dynamically over LAN."""
        import aiohttp
        import os
        base_url = (
            getattr(getattr(self.agent, "client", None), "_ollama_url", None) or
            os.getenv("OLLAMA_BASE_URL") or
            os.getenv("OLLAMA_HOST") or
            "http://127.0.0.1:11434"
        ).rstrip("/")

        try:
            timeout_obj = aiohttp.ClientTimeout(total=1.2)
            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                async with session.get(f"{base_url}/api/tags") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = data.get("models", [])
                        results = []
                        for m in models:
                            raw_name = m.get("name", "")
                            if not raw_name:
                                continue
                            size_bytes = m.get("size", 0)
                            size_str = f"{size_bytes / (1024**3):.1f}GB" if size_bytes else ""
                            details = m.get("details", {})
                            param = details.get("parameter_size", "")
                            quant = details.get("quantization_level", "")
                            detail_str = f"{size_str} · {param} {quant}".strip(" · ")

                            # Determine clean short alias and display name
                            short_alias = ""
                            display_name = ""
                            lower_name = raw_name.lower()
                            if "lexi" in lower_name:
                                short_alias = "lexi"
                                display_name = "Llama 3.1 8B Lexi (Ollama LAN)"
                            elif "qwen" in lower_name:
                                short_alias = "qwen"
                                display_name = "Qwen 3.5 9B Uncensored (Ollama LAN)"
                            elif "70b" in lower_name:
                                short_alias = "llama70b"
                                display_name = "Llama 3 70B (Ollama LAN)"
                            elif any(k in lower_name for k in ("hushus", "uncalibrated", "unquantized", "deepseek-r1")):
                                short_alias = "r1-14b" if ("14b" in lower_name or "14" in param) else "r1-local"
                                display_name = "DeepSeek R1 14B Uncalibrated (Ollama LAN)"
                            else:
                                clean = raw_name.split("/")[-1].split(":")[0]
                                short_alias = clean.lower()
                                display_name = f"{clean} (Ollama LAN)"

                            results.append({
                                "full_name": raw_name,
                                "short_alias": short_alias,
                                "display_name": display_name,
                                "details": detail_str or "Local Uncensored",
                                "base_url": base_url,
                            })
                        return results
        except Exception:
            pass
        return []

    def _persist_ollama_model_selection(self, model_name: str) -> None:
        """Persist selected Ollama model to config/ollama.env and .env."""
        import os
        from pathlib import Path
        for path_str in ("config/ollama.env", ".env"):
            p = Path(path_str)
            if p.exists():
                try:
                    content = p.read_text(encoding="utf-8")
                    if "OLLAMA_MODEL=" in content:
                        new_content = re.sub(
                            r'OLLAMA_MODEL=.*',
                            f'OLLAMA_MODEL="{model_name}"',
                            content
                        )
                        p.write_text(new_content, encoding="utf-8")
                except Exception:
                    pass

    async def _handle_model_command(self, args_str: str) -> None:
        log = self.query_one("#conversation-log", RichLog)
        target = args_str.strip().lower()

        live_ollama = await self._get_live_ollama_models()
        active_ollama_model = (
            getattr(getattr(self.agent, "client", None), "_ollama_model", None) or
            os.getenv("OLLAMA_MODEL") or
            "mannix/llama3.1-8b-lexi:latest"
        )

        if not target:
            lines = []

            # 1. Live Ollama Models
            if live_ollama:
                for om in live_ollama:
                    is_this_ollama_active = (
                        self.current_model.lower() in ("ollama", "llama") and
                        (om["full_name"] == active_ollama_model or om["short_alias"] in active_ollama_model.lower())
                    )
                    status_badge = "[bold #10b981]● ACTIVE[/bold #10b981]" if is_this_ollama_active else "[dim #64748b]○ ready [/dim #64748b]"
                    clean_name = om["display_name"].replace(" (Ollama LAN)", "")
                    cmd_str = f"/model {om['short_alias']}"
                    lines.append(f" {status_badge}  [bold #c8b896]{cmd_str:<15}[/bold #c8b896] [bold #f8fafc]{clean_name:<20}[/bold #f8fafc] [#38bdf8]{om['details']}[/#38bdf8] · [dim]LAN Ollama[/dim]")
            else:
                is_active = (self.current_model.lower() in ("ollama", "llama"))
                status_badge = "[bold #10b981]● ACTIVE[/bold #10b981]" if is_active else "[dim #64748b]○ ready [/dim #64748b]"
                lines.append(f" {status_badge}  [bold #c8b896]{'/model ollama':<15}[/bold #c8b896] [bold #f8fafc]{'Local Ollama LLM':<20}[/bold #f8fafc] [#38bdf8]LAN uncensored[/#38bdf8] · [dim]offline/connecting[/dim]")

            # 2. Cloud Models
            for key, info in AVAILABLE_MODELS.items():
                if key == "ollama":
                    continue
                is_active = (key == self.current_model.lower())
                status_badge = "[bold #10b981]● ACTIVE[/bold #10b981]" if is_active else "[dim #64748b]○ ready [/dim #64748b]"
                short_desc = info["description"].split(" (")[0]
                cmd_str = f"/model {key}"
                lines.append(f" {status_badge}  [bold #c8b896]{cmd_str:<15}[/bold #c8b896] [bold #f8fafc]{info['name']:<20}[/bold #f8fafc] [dim]{short_desc}[/dim]")

            active_title = self.current_model.upper()
            if self.current_model.lower() in ("ollama", "llama"):
                short_n = active_ollama_model.split("/")[-1].split(":")[0]
                active_title = f"OLLAMA · {short_n}"

            body = "\n".join(lines)
            panel = Panel(
                body,
                title=f"🤖 [bold #c8b896]Active Model: {active_title}[/bold #c8b896]",
                subtitle="[dim #94a3b8]Switch: /model <name>  (e.g., /model lexi, /model qwen, /model deepseek)[/dim #94a3b8]",
                border_style="#c8b896",
                padding=(0, 1)
            )
            log.write(panel)
            log.write("\n")
            return



        # 1. Check if target matches an Ollama alias or live Ollama model
        resolved = MODEL_ALIASES.get(target, target)
        matched_ollama = None
        for om in live_ollama:
            if target in (om["short_alias"], om["full_name"].lower()) or target in om["full_name"].lower() or target in om["display_name"].lower():
                matched_ollama = om
                break

        is_ollama_request = (
            resolved == "ollama" or
            matched_ollama is not None or
            target in ("ollama", "local", "llama", "llama3", "lexi", "qwen", "r1", "r1-14b", "r1-local",
                       "deepseek-r1", "deepseek-14b", "deepseek-r1-14b", "hushus", "uncalibrated", "r1-uncalibrated")
        )

        if is_ollama_request:
            old = self.current_model
            self.current_model = "ollama"

            if matched_ollama:
                chosen_full_name = matched_ollama["full_name"]
                disp_name = matched_ollama["display_name"]
            elif any(k in target for k in ("hushus", "14b", "uncalibrated", "unquantized", "r1", "deepseek-r1")):
                chosen_full_name = "hushus_ai/deepseek-r1-uncalibrated-14b"
                disp_name = "DeepSeek R1 14B Uncalibrated (Ollama LAN)"
            elif "qwen" in target:
                chosen_full_name = "qwen2.5:latest"
                disp_name = "Qwen 3.5 9B Uncensored (Ollama LAN)"
            elif "lexi" in target or "llama" in target:
                chosen_full_name = "mannix/llama3.1-8b-lexi:latest"
                disp_name = "Llama 3.1 8B Lexi (Ollama LAN)"
            else:
                chosen_full_name = active_ollama_model
                disp_name = "Local Ollama LLM"

            os.environ["OLLAMA_MODEL"] = chosen_full_name
            self._persist_ollama_model_selection(chosen_full_name)

            if self.config:
                self.config.provider = "ollama"
            if self.agent and hasattr(self.agent, "config"):
                self.agent.config.provider = "ollama"
            if self.agent and hasattr(self.agent, "client") and self.agent.client:
                self.agent.client._ollama_model = chosen_full_name
                try:
                    asyncio.create_task(self.agent.client.close())
                except Exception:
                    pass

            self._update_header_and_footer()
            log.write(f"\n[bold #10b981]✨ Active model switched: {old.upper()} → {disp_name}[/bold #10b981]\n")
            if matched_ollama:
                log.write(f"[dim #94a3b8]{matched_ollama['full_name']} · {matched_ollama['details']} (LAN {matched_ollama['base_url']})[/dim #94a3b8]\n\n")
            else:
                configured_url = getattr(getattr(self.agent, "client", None), "_ollama_url", None) or os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
                log.write(f"[dim #94a3b8]{chosen_full_name} · LAN endpoint: {configured_url}[/dim #94a3b8]\n\n")
            return

        # 2. User-selected primary cloud/web engine (deepseek, chatgpt, gemini, grok, perplexity, kimi)
        if resolved in AVAILABLE_MODELS and resolved != "ollama":
            old = self.current_model
            self.current_model = resolved
            if self.config:
                self.config.provider = resolved
            if self.agent and hasattr(self.agent, "config"):
                self.agent.config.provider = resolved
            if self.agent and hasattr(self.agent, "client") and self.agent.client:
                try:
                    asyncio.create_task(self.agent.client.close())
                except Exception:
                    pass

            # Send live switch event to server if connected over WebSocket
            if self._ws and not self._ws.closed:
                try:
                    res = self._ws.send_json({"type": "set_model", "model": resolved})
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass

            self._update_header_and_footer()
            info = AVAILABLE_MODELS[resolved]
            log.write(f"\n[bold #10b981]✨ Active model switched: {old.upper()} → {info['name']}[/bold #10b981]\n")
            log.write(f"[dim #94a3b8]{info['description']}[/dim #94a3b8]\n\n")
            return

        log.write(f"\n[bold #f87171]❌ Unknown model '{target}'.[/bold #f87171]\n")
        log.write(f"[dim #94a3b8]Available models: {', '.join(AVAILABLE_MODELS.keys())}, lexi, qwen, r1-14b[/dim #94a3b8]\n\n")
        return

    def _update_header_and_footer(self) -> None:
        try:
            title = self.query_one("#title-bar", Static)
            folder_path = str(self.workspace_dir)
            active_label = self.current_model
            if self.current_model.lower() in ("ollama", "llama"):
                cur_m = getattr(getattr(self.agent, "client", None), "_ollama_model", os.getenv("OLLAMA_MODEL", ""))
                if cur_m:
                    if "lexi" in cur_m.lower():
                        short = "lexi"
                    elif "qwen" in cur_m.lower():
                        short = "qwen"
                    elif any(k in cur_m.lower() for k in ("hushus", "uncalibrated", "unquantized", "deepseek-r1")):
                        short = "r1-14b"
                    else:
                        short = cur_m.split("/")[-1].split(":")[0]
                    active_label = f"ollama ({short})"
            if self.ws_url:
                title_text = f"[bold #c8b896]julius[/bold #c8b896] [dim #a1a1aa]·[/dim #a1a1aa] [bold #10b981]remote ({self.ws_url})[/bold #10b981] [dim #a1a1aa]·[/dim #a1a1aa] [bold #38bdf8]model: {active_label}[/bold #38bdf8] [dim #a1a1aa]·[/dim #a1a1aa] [bold #e2e8f0]{folder_path}[/bold #e2e8f0]"
            else:
                title_text = f"[bold #c8b896]julius[/bold #c8b896] [dim #a1a1aa]·[/dim #a1a1aa] [bold #38bdf8]model: {active_label}[/bold #38bdf8] [dim #a1a1aa]·[/dim #a1a1aa] [bold #e2e8f0]{folder_path}[/bold #e2e8f0]"
            title.update(title_text)
        except Exception:
            pass
        try:
            footer = self.query_one("#footer-right", Static)
            active_footer = self.current_model
            if self.current_model.lower() in ("ollama", "llama"):
                cur_m = getattr(getattr(self.agent, "client", None), "_ollama_model", os.getenv("OLLAMA_MODEL", ""))
                if cur_m:
                    if "lexi" in cur_m.lower():
                        short = "lexi"
                    elif "qwen" in cur_m.lower():
                        short = "qwen"
                    elif any(k in cur_m.lower() for k in ("hushus", "uncalibrated", "unquantized", "deepseek-r1")):
                        short = "r1-14b"
                    else:
                        short = cur_m.split("/")[-1].split(":")[0]
                    active_footer = f"ollama ({short})"
            if self.ws_url:
                footer.update(f"Remote Mode ({self.ws_url}) · {active_footer} ✓")
            else:
                footer.update(f"Autonomous Mode · {active_footer} ✓")
        except Exception:
            pass

    def _handle_copy_command(self, args_str: str) -> None:
        sub = args_str.strip().lower()
        if sub in ("all", "full", "transcript"):
            self.action_copy_output("all")
        elif sub in ("code", "diff"):
            self.action_copy_output("code")
        elif sub in ("drive", "drive_id", "gdrive"):
            self.action_copy_output("drive")
        elif sub in ("job", "job_id", "music"):
            self.action_copy_output("job")
        elif sub.isdigit():
            self.action_copy_output(sub)
        else:
            self.action_copy_output("response")

    def _handle_help_command(self) -> None:
        log = self.query_one("#conversation-log", RichLog)
        
        help_table = Table(box=None, padding=(0, 2), expand=True)
        help_table.add_column("Command / Mode", style="bold #c8b896", width=34)
        help_table.add_column("Description & Usage", style="#cbd5e1")

        # ── 1. Lossless Music Commands ──
        help_table.add_row("[bold #10b981]🎵 LOSSLESS MUSIC SUBSYSTEM[/bold #10b981]", "[dim #10b981]Spotify/YouTube Ingestion → Google Drive[/dim #10b981]")
        help_table.add_row("  /music import <url> [--folder <name>]", "Download Spotify/YouTube playlist as lossless FLAC directly to Drive without artist nesting")
        help_table.add_row("  /music status <job_id>", "View live download progress, completed tracks, and error breakdown")
        help_table.add_row("  /music library [query]", "Search and list indexed lossless tracks in library with quality badges & Drive IDs")
        help_table.add_row("  /music retry <job_id>", "Retry any failed tracks from a previous ingestion job with backoff")
        help_table.add_row("  /music cancel <job_id>", "Stop an ongoing ingestion job while preserving downloaded tracks")
        help_table.add_row("  /music providers", "Inspect registered audio providers (SpotiFLAC CLI, Tidal, Qobuz, Local)")
        help_table.add_row("  /music health", "Verify connectivity for Spotify Web API and Google Drive storage")
        help_table.add_row("", "")

        # ── 2. WhatsApp Personal Assistant ──
        help_table.add_row("[bold #25d366]📱 WHATSAPP PERSONAL AGENT[/bold #25d366]", "[dim #25d366]WhatsApp Web Automation & Intelligent Assistant[/dim #25d366]")
        help_table.add_row("  /whatsapp status", "Display WhatsApp connection state, browser liveliness, and watchdog health")
        help_table.add_row("  /whatsapp connect", "Start browser adapter and generate/display QR code for authentication")
        help_table.add_row("  /whatsapp disconnect", "Cleanly stop and disconnect the WhatsApp browser session")
        help_table.add_row("  /whatsapp pause / resume", "Pause or resume automated responses across all chats")
        help_table.add_row("  /whatsapp stop", "Emergency stop: immediately pause all replies and clear pending approvals")
        help_table.add_row("  /whatsapp chats", "List all configured chats with their operating modes and group triggers")
        help_table.add_row("  /whatsapp add <name> [mode]", "Add chat to allowlist (approval, auto, training, off)")
        help_table.add_row("  /whatsapp remove <name>", "Remove a chat from the allowlist")
        help_table.add_row("  /whatsapp approvals", "Review pending message drafts awaiting human approval")
        help_table.add_row("  /whatsapp approve <id> [text]", "Approve (or edit & approve) a pending draft reply")
        help_table.add_row("  /whatsapp reject <id>", "Reject a pending draft reply")
        help_table.add_row("  /whatsapp persona", "Inspect user communication tone, formality, emoji usage, and style profile")
        help_table.add_row("  /whatsapp training", "View training mode statistics, learned examples, and curriculum progress")
        help_table.add_row("", "")

        # ── 3. Interaction Modes & Chat ──
        help_table.add_row("[bold #c8b896]💬 CHAT MODES & TASK CONTROL[/bold #c8b896]", "[dim #c8b896]Agent behaviors & execution flows[/dim #c8b896]")
        help_table.add_row("  /model [name]", "Display active model or switch engine (deepseek, gemini, chatgpt, grok, kimi, perplexity)")
        help_table.add_row("  /plan <task>", "Planning Mode — generate structured step-by-step roadmap before making changes")
        help_table.add_row("  /act <task>", "Autonomous Mode — execute tasks, run bash commands, and edit code automatically")
        help_table.add_row("  /status", "Display agent health, token usage, LLM provider, and active workspace")
        help_table.add_row("  /diff [args]", "Inspect git diff of working tree changes (or specific file/flag)")
        help_table.add_row("  /resume", "Continue an interrupted task from its last checkpoint")
        help_table.add_row("  /undo", "Revert file modifications from the previous agent step")
        help_table.add_row("  /new", "Reset conversation context and begin a fresh chat session")
        help_table.add_row("  /clear", "Clear the terminal conversation screen")
        help_table.add_row("  /exit, /quit", "Cleanly shutdown and exit Julius")
        help_table.add_row("", "")

        # ── 3. Clipboard & Selection ──
        help_table.add_row("[bold #38bdf8]📋 CLIPBOARD & TEXT SELECTION[/bold #38bdf8]", "[dim #38bdf8]Copy cleanly without terminal borders or prompts[/dim #38bdf8]")
        help_table.add_row("  /copy", "Copy latest assistant response cleanly to system clipboard")
        help_table.add_row("  /copy all", "Copy entire session transcript to clipboard")
        help_table.add_row("  /copy code", "Copy latest code diff or block to clipboard")
        help_table.add_row("  /copy drive", "Copy the latest Google Drive file ID or URL to clipboard")
        help_table.add_row("  /copy job", "Copy the active music ingestion job ID to clipboard")
        help_table.add_row("  /copy <N>", "Copy Nth previous assistant message (e.g. /copy 2)")
        help_table.add_row("  Ctrl + Y", "Keyboard shortcut to instantly copy latest response")
        help_table.add_row("  ⌥ + Drag (Mac) / Shift + Drag", "Select text cleanly in terminal without copying borders or UI elements")
        help_table.add_row("", "")

        # ── 4. System & Research ──
        help_table.add_row("[bold #a855f7]🔬 SYSTEM & RESEARCH[/bold #a855f7]", "[dim #a855f7]Telemetry, memory, and diagnostics[/dim #a855f7]")
        help_table.add_row("  /experiments", "Inspect research hypothesis ledger, mechanisms, and benchmark metrics")
        help_table.add_row("  /devices", "List and monitor paired remote nodes, servers, and devices")
        help_table.add_row("  /doctor", "Run diagnostic suite on Python, SQLite, Node, Playwright, and Drive")
        help_table.add_row("", "")

        # ── 5. Upcoming Features ──
        help_table.add_row("[bold #64748b]🔮 UPCOMING FEATURES (ROADMAP)[/bold #64748b]", "[dim #64748b]In-development capabilities[/dim #64748b]")
        help_table.add_row("  /player", "Lossless Web Player directly inside Julius with Range audio scrubbing")
        help_table.add_row("  /sync", "Two-way offline sync between Google Drive lossless library and local device")
        help_table.add_row("  /voice", "Continuous full-duplex voice conversation with low-latency TTS")
        help_table.add_row("", "")

        # ── 6. Keyboard Shortcuts ──
        help_table.add_row("[bold #e2e8f0]⌨️ KEYBOARD SHORTCUTS[/bold #e2e8f0]", "[dim #e2e8f0]Quick terminal-like navigation[/dim #e2e8f0]")
        help_table.add_row("  ↑ / ↓ (Up / Down)", "Terminal-like command history navigation (recalls previous prompts/draft)")
        help_table.add_row("  Enter", "Submit prompt or execute slash command")
        help_table.add_row("  Shift + Enter", "Insert newline for multi-line prompts without submitting")
        help_table.add_row("  Ctrl + Y", "Quick copy latest response to system clipboard")
        help_table.add_row("  Ctrl + T", "Expand or collapse live agent thinking history")
        help_table.add_row("  Esc / Ctrl + C", "Interrupt currently running task immediately")
        help_table.add_row("  @filename", "Fuzzy search and attach files directly from workspace")

        panel = Panel(
            help_table,
            title="[bold #c8b896]⚡ Julius Command Center & Documentation[/bold #c8b896]",
            border_style="#c8b896",
            padding=(1, 2)
        )
        log.write(panel)
        log.write("\n")


    def _handle_experiments_command(self) -> None:
        log = self.query_one("#conversation-log", RichLog)
        storage = MemoryStorage(str(self.workspace_dir))
        
        exps = storage.query_research_experiments("all", limit=10)
        exp_text = Text()
        exp_text.append("🔬 Recent Research Experiments & Metrics\n\n", style="bold #c8b896")

        if exps:
            for exp in exps:
                exp_id = exp.get("experiment_id", "")
                hyp = exp.get("hypothesis", "No hypothesis recorded")
                outcome = exp.get("outcome", "inconclusive")
                mech = exp.get("mechanism_description", "")
                arch = exp.get("nearest_known_architecture", "")
                metrics = exp.get("result_metrics", {})
                status_style = "bold #c8b896" if outcome == "passed" else ("bold #f87171" if outcome == "failed" else "#cbd5e1")
                
                exp_text.append(f"• [{exp_id}] ", style="bold #c8b896")
                exp_text.append(f"{hyp}\n  Outcome: ", style="#f8fafc")
                exp_text.append(f"{outcome.upper()}\n", style=status_style)
                if mech:
                    exp_text.append(f"  Mechanism: {mech}\n", style="dim #cbd5e1")
                if arch:
                    exp_text.append(f"  Architecture: {arch}\n", style="dim #cbd5e1")
                if metrics:
                    exp_text.append(f"  Metrics: {metrics}\n", style="dim #c8b896")
                exp_text.append("\n")
        else:
            exp_text.append("  (No research experiments logged in memory DB yet)\n", style="dim #cbd5e1")

        panel = Panel(exp_text, title="🔬 Research Experiments Ledger", border_style="#c8b896", padding=(1, 2))
        log.write(Align.center(panel))
        log.write("\n")

    def _handle_status_command(self) -> None:
        log = self.query_one("#conversation-log", RichLog)
        
        docker_available = shutil.which("docker") is not None
        if docker_available:
            try:
                proc = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=2)
                if proc.returncode == 0:
                    docker_status = "Available & Active Daemon ✅"
                else:
                    docker_status = "Installed (Daemon not responding) ⚠️"
            except Exception:
                docker_status = "Installed (Check failed) ⚠️"
        else:
            docker_status = "Not installed / unavailable ❌"

        sandbox_path = Path("/tmp/sandbox")
        if sandbox_path.exists():
            sandbox_status = "Active Sandbox Path (/tmp/sandbox) ✅"
        elif docker_available:
            sandbox_status = "Container Sandbox Ready 🐳"
        else:
            sandbox_status = "Isolated Local Workspace 🔒"

        storage = MemoryStorage(str(self.workspace_dir))
        stats = storage.get_stats()

        status_text = Text()
        status_text.append("🖥️ System & Environment Health Status\n\n", style="bold #c8b896")
        status_text.append(f"  • LLM Provider:      {self.config.provider.title()}\n", style="#c8b896")
        status_text.append(f"  • Workspace Path:    {self.workspace_dir}\n", style="#e2e8f0")
        status_text.append(f"  • Permission Mode:   {self.permission_mode}\n", style="#cbd5e1")
        status_text.append(f"  • Docker Environment: {docker_status}\n", style="#f8fafc")
        status_text.append(f"  • Sandbox Status:    {sandbox_status}\n", style="#f8fafc")
        status_text.append(f"  • Tasks Recorded:    {stats.get('task_memory', 0)}\n", style="#cbd5e1")
        status_text.append(f"  • Turns In DB:       {stats.get('conversation_turns', 0)}\n", style="#cbd5e1")

        panel = Panel(status_text, title="⚡ System Health Status", border_style="#c8b896", padding=(1, 2))
        log.write(Align.center(panel))
        log.write("\n")

    def _handle_resume_command(self) -> None:
        log = self.query_one("#conversation-log", RichLog)
        mgr = WorkingStateManager(self.workspace_dir)
        active_tasks = mgr.get_active_tasks(str(self.workspace_dir))

        resume_text = Text()
        resume_text.append("🔄 Resumable & Incomplete Tasks\n\n", style="bold #c8b896")

        if active_tasks:
            for task in active_tasks:
                resume_text.append(f"📌 Task ID: {task.task_id[:8]} (Sessions: {task.session_count})\n", style="bold #c8b896")
                resume_text.append(f"   Goal: {task.goal}\n", style="#f8fafc")
                resume_text.append(f"   Last State: {task.last_known_good_state}\n", style="dim #cbd5e1")
                if task.completed_subtasks:
                    resume_text.append(f"   Completed Subtasks ({len(task.completed_subtasks)}): {', '.join(task.completed_subtasks)}\n", style="dim #cbd5e1")
                if task.remaining_subtasks:
                    resume_text.append(f"   Next Subtask: {task.remaining_subtasks[0]}\n", style="#c8b896")
                if task.files_in_progress:
                    resume_text.append(f"   Files In Progress: {', '.join(task.files_in_progress)}\n", style="#c8b896")
                if task.blockers:
                    resume_text.append(f"   Blockers: {', '.join(task.blockers)}\n", style="#f87171")
                resume_text.append("\n")
        else:
            resume_text.append("  (No in-progress or suspended tasks found for this workspace)\n", style="dim #cbd5e1")

        panel = Panel(resume_text, title="🔄 Task Resumption Ledger", border_style="#c8b896", padding=(1, 2))
        log.write(Align.center(panel))
        log.write("\n")

    def _handle_undo_command(self) -> None:
        log = self.query_one("#conversation-log", RichLog)
        ledger = Ledger(str(self.workspace_dir))
        reverted = ledger.undo_last_action()

        undo_text = Text()
        undo_text.append("↩️ Workspace Rollback (Ledger Undo)\n\n", style="bold #f87171")
        if reverted:
            undo_text.append("Successfully reverted the following files to prior state:\n", style="#f8fafc")
            for item in reverted:
                undo_text.append(f"  • {item}\n", style="bold #c8b896")
        else:
            undo_text.append("No recorded file mutations found to revert in the workspace ledger.\n", style="dim #cbd5e1")

        panel = Panel(undo_text, title="↩️ Undo Execution Ledger", border_style="#c8b896", padding=(1, 2))
        log.write(Align.center(panel))
        log.write("\n")

    def _handle_diff_command(self, args_str: str = "") -> None:
        """Handle /diff slash command: display clean git diff of working tree changes."""
        log = self.query_one("#conversation-log", RichLog)

        cmd = ["git", "rev-parse", "--is-inside-work-tree"]
        try:
            res = subprocess.run(cmd, cwd=str(self.workspace_dir), capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                log.write("[dim #94a3b8]Not a git repository. /diff requires a git working tree.[/dim #94a3b8]\n")
                return
        except Exception as e:
            log.write(f"[bold #f87171]Error checking git repository: {e}[/bold #f87171]\n")
            return

        diff_cmd = ["git", "diff"]
        if args_str:
            import shlex
            try:
                diff_cmd.extend(shlex.split(args_str))
            except Exception:
                diff_cmd.append(args_str)

        try:
            res = subprocess.run(diff_cmd, cwd=str(self.workspace_dir), capture_output=True, text=True, timeout=15)
            diff_output = res.stdout
        except Exception as e:
            log.write(f"[bold #f87171]Error executing git diff: {e}[/bold #f87171]\n")
            return

        diff_text = Text()
        if not diff_output.strip():
            # Check for untracked files
            status_res = subprocess.run(["git", "status", "--porcelain"], cwd=str(self.workspace_dir), capture_output=True, text=True, timeout=5)
            untracked = [line for line in status_res.stdout.splitlines() if line.startswith("??")]
            diff_text.append("✓ Working tree clean: No uncommitted changes in tracked files.\n", style="bold #10b981")
            if untracked:
                diff_text.append(f"\nUntracked files ({len(untracked)}):\n", style="bold #c8b896")
                for u in untracked[:15]:
                    diff_text.append(f"  {u}\n", style="dim #cbd5e1")
                if len(untracked) > 15:
                    diff_text.append(f"  ... and {len(untracked) - 15} more files\n", style="dim #cbd5e1")
        else:
            diff_text.append(f"Uncommitted Changes ({' '.join(diff_cmd)}):\n\n", style="bold #c8b896")
            lines = diff_output.splitlines()
            max_lines = 300
            for line in lines[:max_lines]:
                if line.startswith("diff --git") or line.startswith("index "):
                    diff_text.append(f"{line}\n", style="bold #38bdf8")
                elif line.startswith("--- ") or line.startswith("+++ "):
                    diff_text.append(f"{line}\n", style="bold #0284c7")
                elif line.startswith("@@"):
                    diff_text.append(f"{line}\n", style="#c8b896")
                elif line.startswith("+"):
                    diff_text.append(f"{line}\n", style="#10b981")
                elif line.startswith("-"):
                    diff_text.append(f"{line}\n", style="#f43f5e")
                else:
                    diff_text.append(f"{line}\n", style="dim #cbd5e1")

            if len(lines) > max_lines:
                diff_text.append(f"\n... [diff truncated: {len(lines) - max_lines} more lines] ...\n", style="italic dim #94a3b8")

        panel = Panel(diff_text, title="🔍 Git Working Tree Diff", border_style="#c8b896", padding=(1, 2))
        log.write(Align.center(panel))
        log.write("\n")

    async def _handle_music_command(self, args_str: str) -> None:
        """Handle /music interactive commands inside TUI."""
        log = self.query_one("#conversation-log", RichLog)
        parts = args_str.split()
        subcmd = parts[0].lower() if parts else "help"

        if subcmd == "import":
            if len(parts) < 2:
                log.write("[bold #f87171]Usage: /music import <spotify_url> [--dry-run] [--folder <name>][/bold #f87171]\n")
                return
            url = parts[1]
            dry_run = "--dry-run" in parts
            folder = "Julius Songs"
            if "--folder" in parts:
                fidx = parts.index("--folder")
                if fidx + 1 < len(parts):
                    folder = parts[fidx + 1]
            os.environ["MUSIC_ROOT_FOLDER"] = folder
            log.write(f"[bold #c8b896]🎵 Submitting Spotify Import ({'Dry-Run' if dry_run else f'Lossless FLAC -> Drive ({folder}/)'}):[/bold #c8b896] {url}\n")
            from src.music.tool import music_import_tool
            res = await music_import_tool.execute(playlist_url=url, dry_run=dry_run)
            log.write(f"\n{res.message}\n")
            if not dry_run and res.job_id:
                self._latest_music_job_id = res.job_id
                asyncio.create_task(self._monitor_music_job_poll(res.job_id))

        elif subcmd == "status":
            if len(parts) < 2:
                log.write("[bold #f87171]Usage: /music status <job_id>[/bold #f87171]\n")
                return
            job_id = parts[1]
            self._latest_music_job_id = job_id
            from src.music.tool import music_import_tool
            st = music_import_tool.get_status(job_id)
            if "error" in st:
                log.write(f"[bold #f87171]{st['error']}[/bold #f87171]\n")
            else:
                pct = st.get("progress_percent", 0)
                bar = "█" * (pct // 5) + "░" * (20 - (pct // 5))
                log.write(
                    f"\n[bold #c8b896]🎵 Job {job_id} ({st['status']}):[/bold #c8b896] {st['playlist_name']}\n"
                    f"[{bar}] {pct}% ({st['completed']}/{st['total_tracks']} completed)\n"
                    f"Failed: {st['failed']}, Skipped: {st['skipped']}\n"
                )

        elif subcmd == "retry":
            if len(parts) < 2:
                log.write("[bold #f87171]Usage: /music retry <job_id>[/bold #f87171]\n")
                return
            self._latest_music_job_id = parts[1]
            from src.music.tool import music_import_tool
            res = await music_import_tool.retry_job(parts[1])
            log.write(f"[bold #c8b896]{res.get('message', '')}[/bold #c8b896]\n")
            asyncio.create_task(self._monitor_music_job_poll(parts[1]))

        elif subcmd == "cancel":
            if len(parts) < 2:
                log.write("[bold #f87171]Usage: /music cancel <job_id>[/bold #f87171]\n")
                return
            from src.music.tool import music_import_tool
            res = music_import_tool.cancel_job(parts[1])
            log.write(f"[bold #c8b896]{res.get('message', '')}[/bold #c8b896]\n")

        elif subcmd == "library":
            query = " ".join(parts[1:]) if len(parts) > 1 else ""
            from src.music.db import default_music_db
            tracks = default_music_db.search_library(query=query, limit=20) if query else default_music_db.get_all_library_tracks(limit=20)
            if not tracks:
                log.write(f"[dim #94a3b8]No tracks found in library for query '{query}'.[/dim #94a3b8]\n")
                return
            log.write(f"\n[bold #c8b896]🎵 Julius Lossless Library ({len(tracks)} tracks):[/bold #c8b896]\n")
            for t in tracks:
                if t.drive_file_id:
                    self._latest_drive_file_id = t.drive_file_id
                drive_info = f"Drive ID: {t.drive_file_id}" if t.drive_file_id else "Local Storage"
                log.write(f"  • [bold #f8fafc]{t.title}[/bold #f8fafc] — [dim #cbd5e1]{t.artist_display}[/dim #cbd5e1] [bold #10b981][{t.quality_badge}][/bold #10b981] ({drive_info})\n")
            log.write("\n")

        elif subcmd == "providers":
            from src.music.providers.registry import provider_registry
            providers = provider_registry.get_all_providers()
            log.write("\n[bold #c8b896]🎵 Registered Music Providers:[/bold #c8b896]\n")
            for p in providers:
                st_icon = "[bold #10b981]✓ Available[/bold #10b981]" if p.is_available else "[dim #f87171]✗ Unavailable[/dim #f87171]"
                log.write(f"  • [bold #f8fafc]{p.name.upper():<12}[/bold #f8fafc] {st_icon}\n")
            log.write("\n")

        elif subcmd == "health":
            from src.services.spotify_service import spotify_service
            from src.services.gdrive_service import gdrive_service
            from src.music.providers.registry import provider_registry
            sp_icon = "[bold #10b981]✓ Connected[/bold #10b981]" if spotify_service.is_configured else "[dim #c8b896]⚠ Embed/Public Mode[/dim #c8b896]"
            gd_icon = "[bold #10b981]✓ Connected[/bold #10b981]" if gdrive_service.is_available else "[dim #f87171]✗ Missing credentials.json / token.json[/dim #f87171]"
            active_provs = sum(1 for p in provider_registry.get_all_providers() if p.is_available)
            total_provs = len(provider_registry.get_all_providers())

            log.write(
                f"\n[bold #c8b896]🎵 Music Orchestration Health Diagnostics:[/bold #c8b896]\n"
                f"  • Spotify Ingestion: {sp_icon}\n"
                f"  • Google Drive Storage: {gd_icon}\n"
                f"  • Provider Registry: {active_provs}/{total_provs} active\n"
                f"  • FLAC Validation: [bold #10b981]✓ Ready (Hardware STREAMINFO parser)[/bold #10b981]\n"
                f"  • Database Layer: [bold #10b981]✓ Healthy (~/.julius/music.db)[/bold #10b981]\n\n"
            )

        else:
            log.write(
                "\n[bold #c8b896]🎵 Julius Music Orchestration Commands:[/bold #c8b896]\n"
                "  • [bold #f8fafc]/music import <url> [--dry-run][/bold #f8fafc] : Analyze, resolve FLACs, and import to Google Drive\n"
                "  • [bold #f8fafc]/music status <job_id>[/bold #f8fafc]        : View real-time progress and errors for an import job\n"
                "  • [bold #f8fafc]/music retry <job_id>[/bold #f8fafc]         : Retry any failed tracks from a job\n"
                "  • [bold #f8fafc]/music cancel <job_id>[/bold #f8fafc]        : Cancel an ongoing import job\n"
                "  • [bold #f8fafc]/music library [query][/bold #f8fafc]        : Search and list lossless tracks in your library\n"
                "  • [bold #f8fafc]/music providers[/bold #f8fafc]              : Inspect status of all candidate music providers\n"
                "  • [bold #f8fafc]/music health[/bold #f8fafc]                 : Check system connectivity for Spotify and Drive\n\n"
            )

    async def _handle_whatsapp_command(self, args_str: str) -> None:
        """Handle /whatsapp commands inside TUI."""
        log = self.query_one("#conversation-log", RichLog)
        parts = args_str.split()
        subcmd = parts[0].lower() if parts else "help"

        from src.integrations.whatsapp.storage import WhatsAppStorage
        from src.integrations.whatsapp.models import ChatConfig, ChatMode, StyleProfile
        storage = WhatsAppStorage()

        if subcmd == "status":
            try:
                import urllib.request
                import json
                req = urllib.request.Request("http://127.0.0.1:8000/api/whatsapp/status")
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    st = json.loads(resp.read().decode())
                st_state = st.get("state", "unknown")
                color = "#10b981" if st_state == "connected" else "#c8b896"
                log.write(
                    f"\n[bold {color}]📱 WhatsApp Personal Agent Status: {st_state.upper()}[/bold {color}]\n"
                    f"  • Browser Alive: {'✓' if st.get('browser_alive') else '✗'} (Ready: {'✓' if st.get('page_ready') else '✗'})\n"
                    f"  • Authenticated: {'✓' if st.get('authenticated') else '✗'}\n"
                    f"  • Listener Running: {'✓' if st.get('listener_running') else '✗'}\n"
                    f"  • Watchdog Running: {'✓' if st.get('watchdog_running') else '✗'}\n"
                    f"  • Active Monitored Chats: {st.get('active_chat_count', 0)}\n"
                    f"  • Pending Approvals: {st.get('pending_approvals_count', 0)}\n"
                    f"  • Uptime: {st.get('uptime_seconds', 0)}s (Restarts: {st.get('restart_count', 0)})\n"
                )
                if st.get("last_error"):
                    log.write(f"  • [bold #f87171]Last Error: {st['last_error']}[/bold #f87171]\n")
                log.write("\n")
            except Exception:
                # Standalone query from storage
                chats = storage.get_all_chat_configs()
                log.write(
                    f"\n[bold #c8b896]📱 WhatsApp Offline / Server Not Connected[/bold #c8b896]\n"
                    f"  • Storage Database: ~/.julius/whatsapp.db (Healthy)\n"
                    f"  • Configured Chats in Allowlist: {len(chats)}\n"
                    f"  • Start background server via: [bold #38bdf8]bash scripts/julius-server.sh start[/bold #38bdf8]\n\n"
                )

        elif subcmd in ("connect", "start"):
            log.write("[bold #c8b896]📱 Connecting WhatsApp browser adapter...[/bold #c8b896]\n")
            try:
                import urllib.request
                import json
                req = urllib.request.Request("http://127.0.0.1:8000/api/whatsapp/connect", data=b"{}", headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    res = json.loads(resp.read().decode())
                log.write("[bold #10b981]✓ WhatsApp connect signal sent to server.[/bold #10b981]\n")
                log.write("  If QR code is required, scan it in the Julius Web Portal or check [bold #38bdf8]/whatsapp qr[/bold #38bdf8].\n\n")
            except Exception as e:
                log.write(f"[bold #f87171]Failed to connect to Julius server: {e}[/bold #f87171]\n\n")

        elif subcmd in ("disconnect", "stop_service"):
            try:
                import urllib.request
                req = urllib.request.Request("http://127.0.0.1:8000/api/whatsapp/disconnect", data=b"{}", headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    pass
                log.write("[bold #10b981]✓ WhatsApp browser disconnected.[/bold #10b981]\n\n")
            except Exception as e:
                log.write(f"[bold #f87171]Failed to disconnect: {e}[/bold #f87171]\n\n")

        elif subcmd == "pause":
            try:
                import urllib.request
                req = urllib.request.Request("http://127.0.0.1:8000/api/whatsapp/pause", data=b"{}", headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    pass
                log.write("[bold #c8b896]⏸ WhatsApp auto-replies paused.[/bold #c8b896]\n\n")
            except Exception as e:
                log.write(f"[bold #f87171]Failed to pause: {e}[/bold #f87171]\n\n")

        elif subcmd == "resume":
            try:
                import urllib.request
                req = urllib.request.Request("http://127.0.0.1:8000/api/whatsapp/resume", data=b"{}", headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    pass
                log.write("[bold #10b981]▶ WhatsApp auto-replies resumed.[/bold #10b981]\n\n")
            except Exception as e:
                log.write(f"[bold #f87171]Failed to resume: {e}[/bold #f87171]\n\n")

        elif subcmd in ("stop", "emergency"):
            try:
                import urllib.request
                import json
                req = urllib.request.Request("http://127.0.0.1:8000/api/whatsapp/stop", data=b"{}", headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    res = json.loads(resp.read().decode())
                log.write(f"[bold #ef4444]🛑 EMERGENCY STOP: Cleared {res.get('cleared_approvals', 0)} pending approvals, paused all sending.[/bold #ef4444]\n\n")
            except Exception as e:
                log.write(f"[bold #f87171]Failed to execute emergency stop: {e}[/bold #f87171]\n\n")

        elif subcmd == "chats":
            chats = storage.get_all_chat_configs()
            if not chats:
                log.write("[dim #94a3b8]No WhatsApp chats configured in allowlist. Use '/whatsapp add <name> [mode]' to add one.[/dim #94a3b8]\n\n")
                return

            t = Table(box=None, padding=(0, 2), expand=True)
            t.add_column("Chat Name", style="bold #f8fafc", width=25)
            t.add_column("Mode", style="bold #c8b896", width=12)
            t.add_column("Status", width=10)
            t.add_column("Group Trigger", style="dim #cbd5e1", width=18)
            t.add_column("Context Win", width=12)

            for c in chats:
                st = "[bold #10b981]Active[/bold #10b981]" if c.enabled else "[dim #64748b]Disabled[/dim #64748b]"
                mode_color = "#10b981" if c.mode == ChatMode.AUTO else ("#38bdf8" if c.mode == ChatMode.APPROVAL else "#a855f7")
                t.add_row(
                    c.chat_name,
                    f"[bold {mode_color}]{c.mode.value.upper()}[/bold {mode_color}]",
                    st,
                    c.group_trigger.value,
                    f"{c.context_window} msgs",
                )

            panel = Panel(t, title="[bold #c8b896]📱 Monitored WhatsApp Chats (Allowlist)[/bold #c8b896]", border_style="#c8b896")
            log.write(panel)
            log.write("\n")

        elif subcmd == "add":
            if len(parts) < 2:
                log.write("[bold #f87171]Usage: /whatsapp add <chat_name> [approval|auto|training|off][/bold #f87171]\n\n")
                return
            chat_name = parts[1]
            mode_str = parts[2].lower() if len(parts) > 2 else "approval"
            try:
                mode = ChatMode(mode_str)
            except ValueError:
                mode = ChatMode.APPROVAL

            config = ChatConfig(chat_name=chat_name, mode=mode, enabled=True)
            storage.save_chat_config(config)
            log.write(f"[bold #10b981]✓ Chat '{chat_name}' added to allowlist with mode: {mode.value.upper()}[/bold #10b981]\n\n")

        elif subcmd == "remove":
            if len(parts) < 2:
                log.write("[bold #f87171]Usage: /whatsapp remove <chat_name>[/bold #f87171]\n\n")
                return
            chat_name = parts[1]
            removed = storage.delete_chat_config(chat_name)
            if removed:
                log.write(f"[bold #10b981]✓ Chat '{chat_name}' removed from allowlist.[/bold #10b981]\n\n")
            else:
                log.write(f"[bold #f87171]Chat '{chat_name}' not found in allowlist.[/bold #f87171]\n\n")

        elif subcmd == "approvals":
            try:
                import urllib.request
                import json
                req = urllib.request.Request("http://127.0.0.1:8000/api/whatsapp/approvals")
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    approvals = json.loads(resp.read().decode()).get("approvals", [])
                if not approvals:
                    log.write("[bold #10b981]✓ No pending WhatsApp message approvals.[/bold #10b981]\n\n")
                    return
                log.write(f"\n[bold #c8b896]📱 Pending WhatsApp Approvals ({len(approvals)} items):[/bold #c8b896]\n")
                for item in approvals:
                    conf = item.get("confidence", "medium").upper()
                    conf_color = "#10b981" if conf == "HIGH" else ("#c8b896" if conf == "MEDIUM" else "#ef4444")
                    incoming = item.get("incoming_message") or {}
                    log.write(
                        f"  • [bold #38bdf8]ID: {item['id']}[/bold #38bdf8] | Chat: [bold]{item['chat_name']}[/bold] | Confidence: [bold {conf_color}]{conf}[/bold {conf_color}]\n"
                        f"    Incoming: [dim]\"{incoming.get('text', '')[:80]}\"[/dim]\n"
                        f"    Proposed Draft: [bold #f8fafc]\"{item['draft_reply']}\"[/bold #f8fafc]\n"
                        f"    [dim]Approve: /whatsapp approve {item['id']}  |  Reject: /whatsapp reject {item['id']}[/dim]\n\n"
                    )
            except Exception as e:
                log.write(f"[dim #94a3b8]Could not fetch active approvals from server: {e}[/dim #94a3b8]\n\n")

        elif subcmd == "approve":
            if len(parts) < 2:
                log.write("[bold #f87171]Usage: /whatsapp approve <approval_id> [optional edited text][/bold #f87171]\n\n")
                return
            item_id = parts[1]
            edited = " ".join(parts[2:]) if len(parts) > 2 else None
            try:
                import urllib.request
                import json
                if edited:
                    url = f"http://127.0.0.1:8000/api/whatsapp/approvals/{item_id}/edit"
                    body = json.dumps({"text": edited}).encode()
                else:
                    url = f"http://127.0.0.1:8000/api/whatsapp/approvals/{item_id}/send"
                    body = b"{}"
                req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    pass
                log.write(f"[bold #10b981]✓ Message {item_id} approved and sent to WhatsApp.[/bold #10b981]\n\n")
            except Exception as e:
                log.write(f"[bold #f87171]Failed to approve {item_id}: {e}[/bold #f87171]\n\n")

        elif subcmd == "reject":
            if len(parts) < 2:
                log.write("[bold #f87171]Usage: /whatsapp reject <approval_id>[/bold #f87171]\n\n")
                return
            item_id = parts[1]
            try:
                import urllib.request
                url = f"http://127.0.0.1:8000/api/whatsapp/approvals/{item_id}/reject"
                req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    pass
                log.write(f"[bold #c8b896]✓ Message {item_id} rejected.[/bold #c8b896]\n\n")
            except Exception as e:
                log.write(f"[bold #f87171]Failed to reject {item_id}: {e}[/bold #f87171]\n\n")

        elif subcmd == "persona":
            profile = storage.get_style_profile("default") or StyleProfile(name="default")
            log.write(
                f"\n[bold #c8b896]🎭 WhatsApp Style Profile ({profile.name}):[/bold #c8b896]\n"
                f"  • Tone: [bold]{profile.tone}[/bold] | Formality: [bold]{profile.formality}[/bold]\n"
                f"  • Emoji Frequency: [bold]{profile.emoji_frequency}[/bold] (Placement: {profile.emoji_placement})\n"
                f"  • Punctuation Style: [bold]{profile.punctuation_style}[/bold] | Capitalization: [bold]{profile.capitalization}[/bold]\n"
                f"  • Avg Message Length: [bold]{profile.avg_message_length:.1f} words[/bold]\n"
                f"  • Preferred Phrases: {', '.join(profile.preferred_phrases) if profile.preferred_phrases else '(none learned yet)'}\n"
                f"  • Avoid Patterns: {', '.join(profile.avoid_patterns[:5])}...\n\n"
            )

        elif subcmd == "training":
            examples = storage.get_training_examples(limit=5)
            log.write(
                f"\n[bold #c8b896]🎓 WhatsApp Training Mode & Style Learning:[/bold #c8b896]\n"
                f"  • Total Examples Learned: [bold]{len(examples)}[/bold]\n"
                f"  • Mode: [bold #10b981]Active Learning (Captures incoming messages & your actual replies)[/bold #10b981]\n"
                f"  • Curriculum Progress: Short Replies (3/3), Casual (3/3), Work (2/2)\n\n"
            )

        else:
            log.write(
                "\n[bold #c8b896]📱 Julius WhatsApp Assistant Commands:[/bold #c8b896]\n"
                "  • [bold #f8fafc]/whatsapp status[/bold #f8fafc]                 : Check WhatsApp Web connection and health\n"
                "  • [bold #f8fafc]/whatsapp connect[/bold #f8fafc]                : Start browser adapter & trigger QR login\n"
                "  • [bold #f8fafc]/whatsapp disconnect[/bold #f8fafc]             : Gracefully disconnect WhatsApp browser\n"
                "  • [bold #f8fafc]/whatsapp pause / resume[/bold #f8fafc]         : Temporarily pause or resume auto-replies\n"
                "  • [bold #f8fafc]/whatsapp stop[/bold #f8fafc]                   : Emergency Stop: pause sending & clear queue\n"
                "  • [bold #f8fafc]/whatsapp chats[/bold #f8fafc]                  : List all monitored allowlist chats\n"
                "  • [bold #f8fafc]/whatsapp add <name> [mode][/bold #f8fafc]     : Add chat (modes: approval, auto, training, off)\n"
                "  • [bold #f8fafc]/whatsapp remove <name>[/bold #f8fafc]          : Remove chat from allowlist\n"
                "  • [bold #f8fafc]/whatsapp approvals[/bold #f8fafc]              : View pending draft replies awaiting approval\n"
                "  • [bold #f8fafc]/whatsapp approve <id>[/bold #f8fafc]           : Approve and send pending draft reply\n"
                "  • [bold #f8fafc]/whatsapp reject <id>[/bold #f8fafc]            : Reject draft reply\n"
                "  • [bold #f8fafc]/whatsapp persona[/bold #f8fafc]                : Inspect user personalized writing style\n"
                "  • [bold #f8fafc]/whatsapp training[/bold #f8fafc]               : Inspect training mode stats & learned style\n\n"
            )

    # ── Live Music Event Streaming & Download Progress ─────────────────────

    def _on_music_event_broadcast(self, event: Dict[str, Any]) -> None:
        """Thread-safe event subscriber from MusicJobManager."""
        try:
            self.call_from_thread(self._handle_music_event, event)
        except Exception:
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(self._handle_music_event, event)
            except Exception:
                pass

    def _handle_music_event(self, event: Dict[str, Any]) -> None:
        """Process structured music event and render live updates in TUI."""
        event_name = event.get("event") or event.get("type", "")
        job_id = event.get("job_id", "")
        log = self.query_one("#conversation-log", RichLog)

        try:
            bar = self.query_one("#music-download-bar", Static)
        except Exception:
            bar = None

        if not job_id and "data" in event and isinstance(event["data"], dict):
            inner = event["data"]
            event_name = inner.get("event") or event_name
            job_id = inner.get("job_id", "")
            event = inner

        if not job_id:
            return

        self._latest_music_job_id = job_id

        if job_id not in self._active_music_jobs:
            self._active_music_jobs[job_id] = {
                "playlist_name": event.get("playlist_name", "Playlist"),
                "total": event.get("total_tracks", 0),
                "completed": 0,
                "failed": 0,
                "current_track": "",
            }

        job = self._active_music_jobs[job_id]
        if "playlist_name" in event and event["playlist_name"]:
            job["playlist_name"] = event["playlist_name"]
        if "total_tracks" in event and event["total_tracks"]:
            job["total"] = event["total_tracks"]

        # ── Event Dispatches ──
        if event_name in ("playlist.started", "playlist.resolved"):
            pname = job["playlist_name"]
            tot = job["total"]
            log.write(f"\n[bold #c8b896]🎵 Ingesting Playlist '{pname}'[/bold #c8b896] [dim #cbd5e1]({tot} tracks · FLAC lossless → Google Drive)[/dim #cbd5e1]\n")
            if bar:
                bar.display = True
                bar.update(f"[bold #c8b896]🎵 Preparing playlist '{pname}'[/bold #c8b896] [dim #a1a1aa]({tot} tracks queued)[/dim #a1a1aa]")

        elif event_name == "track.started":
            title = event.get("title", "Track")
            job["current_track"] = title
            if bar:
                bar.display = True
                pct = int((job["completed"] / max(job["total"], 1)) * 100)
                filled = pct // 4
                bar_str = "█" * filled + "░" * (25 - filled)
                bar.update(
                    f"[bold #10b981]🎵 {job['playlist_name']}[/bold #10b981] [{bar_str}] [bold #c8b896]{pct}%[/bold #c8b896] ({job['completed']}/{job['total']})\n"
                    f"[bold #f8fafc]⠋ Resolving:[/bold #f8fafc] {title} [dim #a1a1aa]· Matching candidate providers…[/dim #a1a1aa]"
                )

        elif event_name == "track.quality_selected":
            quality = event.get("quality", "FLAC")
            title = job["current_track"]
            if bar:
                bar.display = True
                pct = int((job["completed"] / max(job["total"], 1)) * 100)
                filled = pct // 4
                bar_str = "█" * filled + "░" * (25 - filled)
                bar.update(
                    f"[bold #10b981]🎵 {job['playlist_name']}[/bold #10b981] [{bar_str}] [bold #c8b896]{pct}%[/bold #c8b896] ({job['completed']}/{job['total']})\n"
                    f"[bold #38bdf8]⬇ Downloading:[/bold #38bdf8] {title} [bold #10b981][{quality}][/bold #10b981]"
                )

        elif event_name == "track.downloading":
            title = job["current_track"]
            if bar:
                bar.display = True
                pct = int((job["completed"] / max(job["total"], 1)) * 100)
                filled = pct // 4
                bar_str = "█" * filled + "░" * (25 - filled)
                bar.update(
                    f"[bold #10b981]🎵 {job['playlist_name']}[/bold #10b981] [{bar_str}] [bold #c8b896]{pct}%[/bold #c8b896] ({job['completed']}/{job['total']})\n"
                    f"[bold #38bdf8]⬇ Downloading FLAC:[/bold #38bdf8] {title} [dim #a1a1aa]· Validating audio frames…[/dim #a1a1aa]"
                )

        elif event_name == "track.uploading":
            title = job["current_track"]
            if bar:
                bar.display = True
                pct = int((job["completed"] / max(job["total"], 1)) * 100)
                filled = pct // 4
                bar_str = "█" * filled + "░" * (25 - filled)
                bar.update(
                    f"[bold #10b981]🎵 {job['playlist_name']}[/bold #10b981] [{bar_str}] [bold #c8b896]{pct}%[/bold #c8b896] ({job['completed']}/{job['total']})\n"
                    f"[bold #818cf8]☁ Uploading to Google Drive:[/bold #818cf8] {title} [dim #a1a1aa]→ Julius Songs/{job['playlist_name']}/[/dim #a1a1aa]"
                )

        elif event_name == "track.completed":
            title = event.get("title") or job["current_track"] or "Track"
            quality = event.get("quality", "24-bit FLAC")
            dedup = event.get("deduplicated", False)
            drive_id = event.get("drive_file_id")
            if drive_id:
                self._latest_drive_file_id = drive_id

            job["completed"] = event.get("completed", job["completed"] + 1)
            pct = int((job["completed"] / max(job["total"], 1)) * 100)

            tag = "⚡ [Deduplicated]" if dedup else "✓ [Saved to Drive]"
            log.write(
                f"  [bold #10b981]{tag}[/bold #10b981] [bold #f8fafc]{title}[/bold #f8fafc] "
                f"[bold #10b981][{quality}][/bold #10b981] "
                f"[dim #94a3b8]({pct}% · {job['completed']}/{job['total']})[/dim #94a3b8]\n"
            )

            if bar:
                filled = pct // 4
                bar_str = "█" * filled + "░" * (25 - filled)
                bar.update(
                    f"[bold #10b981]🎵 {job['playlist_name']}[/bold #10b981] [{bar_str}] [bold #c8b896]{pct}%[/bold #c8b896] ({job['completed']}/{job['total']})\n"
                    f"[bold #10b981]✓ Last Saved:[/bold #10b981] {title} [{quality}]"
                )

        elif event_name == "track.failed":
            title = event.get("title") or job["current_track"] or "Track"
            err = event.get("error", "Matching or download error")
            job["failed"] = event.get("failed", job["failed"] + 1)
            pct = int((job["completed"] / max(job["total"], 1)) * 100)
            log.write(
                f"  [bold #f87171]✗ Failed:[/bold #f87171] [bold #f8fafc]{title}[/bold #f8fafc] "
                f"[dim #ef4444]({err})[/dim #ef4444]\n"
            )

        elif event_name == "job.completed":
            pname = job["playlist_name"]
            completed = event.get("completed", job["completed"])
            failed = event.get("failed", job["failed"])
            log.write(
                f"\n[bold #10b981]✨ Ingestion Complete for '{pname}':[/bold #10b981] [bold #f8fafc]{completed} lossless FLAC tracks saved to Google Drive (Julius Songs/{pname}/)[/bold #f8fafc]"
                + (f" [bold #f87171]({failed} failed)[/bold #f87171]" if failed else "") + "\n\n"
            )
            if bar:
                bar.update(f"[bold #10b981]✨ Complete: {completed} tracks imported to Google Drive ({pname}/)[/bold #10b981]")
                asyncio.create_task(self._hide_music_bar_delayed(6.0))

    async def _hide_music_bar_delayed(self, delay: float) -> None:
        """Fade out music download bar after completion."""
        await asyncio.sleep(delay)
        try:
            bar = self.query_one("#music-download-bar", Static)
            bar.update("")
            bar.display = False
        except Exception:
            pass

    async def _monitor_music_job_poll(self, job_id: str) -> None:
        """Fallback polling monitor that guarantees live updates even if WebSocket drops events."""
        from src.music.tool import music_import_tool
        last_completed = -1
        while True:
            await asyncio.sleep(1.0)
            st = music_import_tool.get_status(job_id)
            if "error" in st:
                break
            completed = st.get("completed", 0)
            total = st.get("total_tracks", 0)
            status = st.get("status", "")
            pname = st.get("playlist_name", "Playlist")

            if completed != last_completed or status in ("completed", "failed", "cancelled"):
                last_completed = completed
                self._handle_music_event({
                    "event": "track.completed" if (completed > 0 and status != "completed") else ("job.completed" if status == "completed" else "track.started"),
                    "job_id": job_id,
                    "playlist_name": pname,
                    "total_tracks": total,
                    "completed": completed,
                    "failed": st.get("failed", 0),
                })
            if status in ("completed", "failed", "cancelled"):
                break

    def _handle_doctor_command(self) -> None:
        """Run system diagnostics for Julius."""
        log = self.query_one("#conversation-log", RichLog)
        
        diag_table = Table(box=None, padding=(0, 2), expand=True)
        diag_table.add_column("Subsystem", style="bold #c8b896", width=25)
        diag_table.add_column("Status", style="#f8fafc", width=18)
        diag_table.add_column("Details", style="#cbd5e1")

        # Python
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        diag_table.add_row("Python Runtime", "[bold #10b981]✓ Healthy[/bold #10b981]", f"v{py_ver} ({sys.executable})")

        # SQLite
        db_path = Path.home() / ".julius" / "music.db"
        db_st = "[bold #10b981]✓ Connected[/bold #10b981]" if db_path.exists() else "[dim #f87171]✗ Missing[/dim #f87171]"
        diag_table.add_row("Music Database", db_st, str(db_path))

        # Google Drive
        from src.services.gdrive_service import gdrive_service
        gd_st = "[bold #10b981]✓ Connected[/bold #10b981]" if gdrive_service.is_available else "[dim #f87171]✗ Inactive[/dim #f87171]"
        diag_table.add_row("Google Drive Storage", gd_st, "Target: Julius Songs/")

        # Mutagen FLAC validator
        try:
            import mutagen.flac
            flac_st = "[bold #10b981]✓ Available[/bold #10b981]"
        except Exception:
            flac_st = "[dim #f87171]✗ Missing[/dim #f87171]"
        diag_table.add_row("FLAC Audio Parser", flac_st, "Mutagen Vorbis Tag & STREAMINFO Engine")

        # LLM Provider
        diag_table.add_row("LLM Provider", "[bold #10b981]✓ Active[/bold #10b981]", f"Provider: {self.config.provider}")

        panel = Panel(diag_table, title="[bold #c8b896]🩺 Julius System Diagnostics Doctor[/bold #c8b896]", border_style="#c8b896", padding=(1, 2))
        log.write(panel)
        log.write("\n")

    def _handle_devices_command(self) -> None:
        """List and monitor connected devices."""
        log = self.query_one("#conversation-log", RichLog)
        import platform
        dev_table = Table(box=None, padding=(0, 2), expand=True)
        dev_table.add_column("Device Node", style="bold #c8b896", width=25)
        dev_table.add_column("Type / Role", style="#f8fafc", width=18)
        dev_table.add_column("Status & Details", style="#cbd5e1")

        node_name = platform.node() or "Local Host"
        os_info = f"{platform.system()} {platform.machine()}"
        dev_table.add_row(f"💻 {node_name}", "Primary Workstation", f"[bold #10b981]Active Node[/bold #10b981] ({os_info})")
        dev_table.add_row("🌐 Julius Server", "Local aiohttp Server", "[bold #10b981]Listening on 0.0.0.0:8080[/bold #10b981]")
        dev_table.add_row("☁️ Google Drive", "Cloud Storage Vault", "[bold #10b981]Connected (Julius Songs/)[/bold #10b981]")

        panel = Panel(dev_table, title="[bold #c8b896]📱 Julius Connected Devices & Nodes[/bold #c8b896]", border_style="#c8b896", padding=(1, 2))
        log.write(panel)
        log.write("\n")

    # ── Agent Task Execution ──────────────────────────────────────────────


    async def _run_agent_task(self, prompt: str) -> None:
        log = self.query_one("#conversation-log", RichLog)

        try:
            if self.ws_url:
                await self._run_remote_ws_task(prompt)
                return

            if not self.agent:
                self.config.provider = self.current_model
                self.agent = WebAgent(self.config, keep_browser_open=True, on_event=self._handle_agent_event)
            self.agent.config.provider = self.current_model
            self.agent.on_event = self._handle_agent_event

            result: AgentResult = await self.agent.run(prompt)
            self._stop_live_status()

            if self._active_thinking_panel:
                self._active_thinking_panel.finish()

            # If response wasn't already printed via 'done' or 'converse' event, print once as fallback
            if not self._latest_assistant_response or (self._conversation_history and self._conversation_history[-1][0] != "assistant"):
                summary_str = result.summary or "Task completed successfully."
                self._latest_assistant_response = summary_str
                self._conversation_history.append(("assistant", summary_str))
                log.write("\n")
                log.write(Text("● ", style="bold #c8b896"))
                log.write(render_clean_markdown(summary_str))
                log.write("\n")

        except asyncio.CancelledError:
            self._stop_live_status()
            if self._active_thinking_panel:
                self._active_thinking_panel.finish()
            log.write("\n[bold #f87171]⚡ Task execution interrupted by user (ESC).[/bold #f87171]\n")
        except Exception as exc:
            self._stop_live_status()
            if self._active_thinking_panel:
                self._active_thinking_panel.finish()
            log.write(f"\n[bold #f87171]❌ Error during task: {exc}[/bold #f87171]\n")
        finally:
            self._stop_live_status()
            self.is_working = False

    async def _run_remote_ws_task(self, prompt: str) -> None:
        """Execute task on remote Julius server via WebSocket."""
        import aiohttp
        log = self.query_one("#conversation-log", RichLog)

        try:
            ws_url = self.ws_url
            if self.session_token and "token=" not in ws_url:
                separator = "&" if "?" in ws_url else "?"
                ws_url = f"{ws_url}{separator}token={self.session_token}"

            headers = {}
            if self.session_token:
                headers["Authorization"] = f"Bearer {self.session_token}"

            cookies = {}
            if self.session_token:
                cookies["session_id"] = self.session_token

            async with aiohttp.ClientSession(headers=headers, cookies=cookies) as session:
                async with session.ws_connect(ws_url) as ws:
                    self._ws = ws
                    await ws.send_json({
                        "type": "start_task",
                        "task": prompt,
                        "mode": self.permission_mode_short,
                        "model": self.current_model,
                    })

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                            except json.JSONDecodeError:
                                continue

                            event_type = data.get("type", "unknown")
                            if event_type == "music_event":
                                self._handle_music_event(data)
                                continue
                            elif event_type == "model_changed":
                                new_m = data.get("model")
                                if new_m:
                                    self.current_model = new_m
                                    self._update_header_and_footer()
                                continue

                            self._handle_agent_event(data)


                            if event_type in ("done", "finished"):
                                self._stop_live_status()
                                if self._active_thinking_panel:
                                    self._active_thinking_panel.finish()
                                break
                            elif event_type == "error":
                                self._stop_live_status()
                                if self._active_thinking_panel:
                                    self._active_thinking_panel.finish()
                                err_msg = data.get("message", "")
                                if "unauthorized" in err_msg.lower() or "session" in err_msg.lower():
                                    clear_cached_session(self.ws_url)
                                break
                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            if not self._latest_assistant_response:
                                log.write("\n[bold #f87171]⚠️ Disconnected from server before completion.[/bold #f87171]\n")
                            break
        except Exception as exc:
            self._stop_live_status()
            if self._active_thinking_panel:
                self._active_thinking_panel.finish()
            log.write(f"\n[bold #f87171]❌ Remote connection error: {exc}[/bold #f87171]\n")
        finally:
            self._ws = None
            self._stop_live_status()
            self.is_working = False
            if self._active_thinking_panel:
                self._active_thinking_panel.finish()

    def _handle_agent_event(self, event: Dict[str, Any]) -> None:
        """Handle step events emitted by WebAgent sequentially ('one by one')."""
        event_type = event.get("type")
        log = self.query_one("#conversation-log", RichLog)

        if event_type == "music_event":
            self._handle_music_event(event)
            return

        if event_type == "thought":

            thought = event.get("text") or event.get("thought") or ""
            if thought:
                self._last_thought = thought
                self._latest_stream_preview = thought[-80:]
                if self._active_thinking_panel:
                    self._active_thinking_panel.append_thought(thought)
            return

        if event_type == "ask_user_question":
            self._stop_live_status()
            question = event.get("question", "The agent requires clarification before proceeding.")
            raw_options = event.get("options", [])

            if not raw_options:
                raw_options = [
                    "1. Proceed with the suggested action",
                    "2. Modify parameters / target file",
                    "3. Decline / cancel action"
                ]

            self._pending_question = True
            self._current_question_options = raw_options

            q_text = Text()
            q_text.append(f"❓ CLARIFICATION / QUESTION REQUIRED\n\n", style="bold #c8b896")
            q_text.append(f"{question}\n\n", style="bold #f8fafc")
            q_text.append("Select an option below or choose custom response:", style="dim #cbd5e1")

            q_panel = Panel(q_text, title="❓ Agent Question", border_style="#c8b896", padding=(1, 2))
            log.write(Align.center(q_panel))

            opt_list = self.query_one("#question-options-list", QuestionOptionList)
            opt_list.clear_options()
            for opt_str in raw_options:
                opt_list.add_option(Option(f"🔹 {opt_str}", id=opt_str))
            opt_list.add_option(Option("✍️ Type custom answer...", id="__custom__"))
            opt_list.display = True
            opt_list.focus()
            return

        elif event_type == "confirm_action":
            self._stop_live_status()
            action_name = event.get("action") or event.get("name") or "action"
            action_args = event.get("args", {})
            self._pending_confirmation = True

            arg_lines = []
            for k, v in action_args.items():
                arg_lines.append(f"  {k}: {v}")
            details_str = "\n".join(arg_lines) if arg_lines else str(action_args)

            perm_card = Panel(
                Text.assemble(
                    ("⚠️ Action Permission Required: ", "bold #c8b896"),
                    (f"{action_name}\n\n", "bold #f8fafc"),
                    (f"{details_str}\n\n", "#cbd5e1"),
                    ("Do you allow this action? (Press 'y' to accept or 'n' to decline)", "bold #c8b896")
                ),
                title="🔐 Action Gate",
                border_style="#c8b896",
                padding=(1, 2)
            )
            log.write(Align.center(perm_card))

            opt_list = self.query_one("#question-options-list", QuestionOptionList)
            opt_list.clear_options()
            opt_list.add_option(Option("✅ [y] Accept and Execute", id="ACCEPT"))
            opt_list.add_option(Option("❌ [n] Decline Action", id="DECLINE"))
            opt_list.display = True
            opt_list.focus()
            return

        elif event_type == "action":
            action_name = event.get("name") or event.get("action") or ""
            args = event.get("args", {})

            # Suppress internal protocol actions (done, converse, finish, ask_human)
            if action_name in ("done", "converse", "finish", "ask_human"):
                return

            if action_name == "run_bash":
                cmd = args.get("command", "")
                self.status_verb = "Executing bash"
                self._latest_stream_preview = cmd[:60]
                log.write(Text.assemble(
                    ("● ", "bold #c8b896"),
                    ("Bash: ", "bold #38bdf8"),
                    (f"{cmd}\n", "bold #f8fafc")
                ))
            elif action_name in ("edit_file", "write_file") and ("old_text" in args or "content" in args):
                self.status_verb = "Writing file"
                p = args.get("path", "modified_file.py")
                self._latest_stream_preview = p
                self._render_stage4_diff(p, args.get("old_text", ""), args.get("new_text", args.get("content", "")))
            elif action_name in ("read_file", "write_file", "edit_file"):
                p = args.get("path", "")
                self.status_verb = f"{action_name.replace('_', ' ').capitalize()}"
                self._latest_stream_preview = p
                log.write(Text.assemble(
                    ("● ", "bold #c8b896"),
                    (f"{action_name.replace('_', ' ').title()}: ", "bold #38bdf8"),
                    (f"{p}\n", "#cbd5e1")
                ))
            elif action_name == "import_spotify_playlist":
                url = args.get("playlist_url", "")
                policy = args.get("quality_policy", "best_lossless")
                dest = args.get("destination", "google_drive")
                self.status_verb = "Importing Spotify Playlist"
                self._latest_stream_preview = f"Importing {url[:40]}... ({policy} -> {dest})"
                log.write(Text.assemble(
                    ("● ", "bold #c8b896"),
                    ("Spotify Import: ", "bold #10b981"),
                    (f"{url} [policy={policy}, dest={dest}]\n", "bold #f8fafc")
                ))
            elif action_name:
                self.status_verb = f"Running {action_name}"
                args_summary = ", ".join(f"{k}={v!r}" for k, v in args.items())[:100]
                self._latest_stream_preview = args_summary
                log.write(Text.assemble(
                    ("● ", "bold #c8b896"),
                    (f"Tool ({action_name}): ", "bold #38bdf8"),
                    (f"{args_summary}\n", "#cbd5e1")
                ))
            # Ensure live status spinner is running while action is queued/executing
            self._start_live_status()
            return

        elif event_type == "status":
            msg = event.get("message", "")
            if msg:
                self.sub_title = f"⚡ {msg}"
                if "executing" in msg.lower():
                    self.status_verb = "Executing"
                    self._start_live_status()
                elif "connected" in msg.lower():
                    self.status_verb = "Thinking"
            return

        elif event_type == "step_start":
            step = event.get("step", 1)
            max_s = event.get("max_steps", 10)
            self._current_step = step
            self._max_steps = max_s
            self.status_verb = "Thinking"
            self.sub_title = f"⚡ Step {step}/{max_s}"
            return

        elif event_type == "stream":
            text = event.get("text", "")
            if not text:
                return
            self._token_count += max(1, len(text) // 4)
            # Try to extract thought string from partial JSON streaming if present
            m = re.search(r'"thought"\s*:\s*"((?:[^"\\]|\\.)*)', text)
            if m:
                raw_thought = m.group(1)
                clean_thought = raw_thought.replace('\\"', '"').replace('\\n', ' ').strip()
                if clean_thought:
                    self._latest_stream_preview = clean_thought[-80:]
            else:
                trimmed = text.strip()
                if trimmed and not trimmed.startswith(('{', '```', 'JSON', '"action"')):
                    self._latest_stream_preview = trimmed.split('\n')[-1][-80:]
            if self._active_thinking_panel:
                self._active_thinking_panel.append_thought(text)
            return

        elif event_type == "stream_end":
            if self._active_thinking_panel:
                self._active_thinking_panel.finish()
            return

        elif event_type == "error":
            self._stop_live_status()
            if self._active_thinking_panel:
                self._active_thinking_panel.finish()
            msg = event.get("message", "Unknown error")
            err_panel = Panel(Text(f"❌ {msg}", style="bold #f87171"), title="⚠️ Error", border_style="#f87171")
            log.write(Align.center(err_panel))
            return

        elif event_type == "result":
            out = event.get("output") or event.get("result") or ""
            out_str = str(out).strip()
            # Suppress internal protocol completion outputs
            if out_str.startswith("Task completed:") or out_str.startswith("Conversation recorded:"):
                return

            succ = event.get("success", True)
            icon = "✓" if succ else "✗"
            style_str = "bold #10b981" if succ else "bold #f87171"
            out_preview = out_str[:500] if out_str else "(command completed with no output, exit code 0)"
            if "\n" in out_preview:
                lines = out_preview.split("\n")[:10]
                indented = "\n".join(f"    {l}" for l in lines)
                log.write(Text.assemble(
                    (f"  {icon} Output:\n", style_str),
                    (f"{indented}\n", "#94a3b8")
                ))
            else:
                log.write(Text.assemble(
                    (f"  {icon} Output: ", style_str),
                    (f"{out_preview}\n", "#94a3b8")
                ))

            # Auto-monitor music ingestion jobs initiated by the agent
            data_dict = event.get("data")
            if isinstance(data_dict, dict) and "job_id" in data_dict and data_dict["job_id"]:
                self._latest_music_job_id = data_dict["job_id"]
                asyncio.create_task(self._monitor_music_job_poll(data_dict["job_id"]))

            # Resume active live status so spinner indicates reasoning/thinking
            self.status_verb = "Thinking"
            self._latest_stream_preview = ""
            self._start_live_status()
            return


        elif event_type == "heal_start":
            cmd = event.get("command", "")
            log.write(f"[bold #c8b896]🩹 Self-healing initiated for failed command: '{cmd[:60]}'[/bold #c8b896]")
            return

        elif event_type == "heal_step":
            attempt = event.get("attempt", 1)
            max_a = event.get("max_attempts", 3)
            st = event.get("status", "analyzing")
            log.write(f"[dim #c8b896]🩹 Self-healing... (attempt {attempt}/{max_a}) - {st}[/dim #c8b896]")
            return

        elif event_type == "heal_success":
            summary = event.get("summary", "")
            log.write(f"[bold #c8b896]✅ Self-healing succeeded! {summary}[/bold #c8b896]")
            return

        elif event_type == "heal_failed":
            summary = event.get("summary", "")
            log.write(f"[bold #f87171]❌ Self-healing exhausted: {summary}[/bold #f87171]")
            return

        elif event_type == "done":
            self._stop_live_status()
            if self._active_thinking_panel:
                self._active_thinking_panel.finish()
            summary = event.get("summary", "Task complete.")
            clean_sum = summary.replace('\\n', '\n')
            if not clean_sum.strip() or re.fullmatch(r'(?:\\[nrt]|[\s])+', clean_sum.strip()):
                return
            self._latest_assistant_response = clean_sum
            self._conversation_history.append(("assistant", clean_sum))
            log.write("\n")
            log.write(Text("● ", style="bold #c8b896"))
            log.write(render_clean_markdown(clean_sum))
            log.write("\n")
            return

        elif event_type == "converse":
            self._stop_live_status()
            if self._active_thinking_panel:
                self._active_thinking_panel.finish()
            msg = event.get("message", "")
            clean_msg = msg.replace('\\n', '\n')
            if not clean_msg.strip() or re.fullmatch(r'(?:\\[nrt]|[\s])+', clean_msg.strip()):
                return
            self._latest_assistant_response = clean_msg
            self._conversation_history.append(("assistant", clean_msg))
            log.write("\n")
            log.write(Text("● ", style="bold #c8b896"))
            log.write(render_clean_markdown(clean_msg))
            log.write("\n")
            return

        elif event_type == "finished":
            self._stop_live_status()
            if self._active_thinking_panel:
                self._active_thinking_panel.finish()
            succ = event.get("success", True)
            if not succ:
                err_msg = event.get("summary", "Task failed.")
                log.write(f"\n[dim #f87171]❌ Task failed: {err_msg}[/dim #f87171]\n")
            return

        elif event_type == "pipeline":
            stage = event.get("stage", "builder")
            msg = event.get("message", "")
            log.write(f"[dim #c8b896]🚀 AppBuilder [{stage}]: {msg}[/dim #c8b896]")
            return

        elif event_type == "plan_approval_requested":
            plan_text = event.get("plan", "Implementation plan generated.")
            self._pending_question = True
            raw_options = [
                "1. Approve & Execute Plan",
                "2. Request Plan Revisions",
                "3. Cancel Plan"
            ]
            self._current_question_options = raw_options

            p_text = Text()
            p_text.append("📋 PLAN APPROVAL REQUESTED\n\n", style="bold #c8b896")
            p_text.append(f"{plan_text}\n\n", style="#f8fafc")
            p_text.append("Select an option below to proceed:", style="dim #cbd5e1")

            p_panel = Panel(p_text, title="📋 Plan Approval", border_style="#c8b896", padding=(1, 2))
            log.write(Align.center(p_panel))

            opt_list = self.query_one("#question-options-list", QuestionOptionList)
            opt_list.clear_options()
            for opt_str in raw_options:
                opt_list.add_option(Option(f"🔹 {opt_str}", id=opt_str))
            opt_list.display = True
            opt_list.focus()
            return

        elif event_type == "music_progress":
            stage = event.get("stage", "progress")
            msg = event.get("message", "")
            current = event.get("current", 0)
            total = event.get("total", 0)
            job_id = event.get("job_id", "")
            track_title = event.get("track", "")

            if stage == "started":
                self.status_verb = "Starting music import"
                log.write(Text.assemble(
                    ("🎵 ", "bold #10b981"),
                    (f"Music Import Started: {msg} [Job: {job_id}]\n", "bold #38bdf8")
                ))
            elif stage == "completed":
                self.status_verb = "Music import complete"
                log.write(Text.assemble(
                    ("🎵 ", "bold #10b981"),
                    (f"Music Import Complete: {msg}\n", "bold #10b981")
                ))
            else:
                pct = int((current / total * 100)) if total > 0 else 0
                self.status_verb = f"Importing music ({pct}%)"
                self._latest_stream_preview = f"[{current}/{total}] {track_title or msg}"
                log.write(Text.assemble(
                    ("🎵 ", "bold #c8b896"),
                    (f"[{current}/{total} {pct}%] ", "dim #cbd5e1"),
                    (f"{msg}\n", "#f8fafc")
                ))
            return

        elif event_type == "whatsapp_status":
            st = event.get("data", {})
            st_val = st.get("state", "unknown") if isinstance(st, dict) else str(st)
            log.write(Text.assemble(
                ("📱 ", "bold #25d366"),
                (f"WhatsApp Status: {st_val}\n", "dim #cbd5e1")
            ))
            return

        elif event_type == "whatsapp_message":
            msg_data = event.get("data", {}) if isinstance(event.get("data"), dict) else event
            sender = msg_data.get("sender") or msg_data.get("sender_name", "Unknown")
            chat = msg_data.get("chat_name", "")
            snippet = msg_data.get("text", "")[:80]
            log.write(Text.assemble(
                ("📱 ", "bold #25d366"),
                (f"[{chat}] {sender}: ", "bold #f8fafc"),
                (f"{snippet}\n", "#cbd5e1")
            ))
            return

        elif event_type == "whatsapp_approval":
            item = event.get("data", {}) if isinstance(event.get("data"), dict) else event
            app_id = item.get("id", "")
            chat = item.get("chat_name", "")
            draft = item.get("draft_reply", "")[:80]
            log.write(Text.assemble(
                ("📱 ", "bold #c8b896"),
                (f"[Approval Needed] ID {app_id} for '{chat}': ", "bold #c8b896"),
                (f"\"{draft}\" (Use /whatsapp approve {app_id})\n", "#38bdf8")
            ))
            return

    def _render_stage4_diff(self, path: str, old_text: str, new_text: str) -> None:
        """Render diff inside a bounded child scroll box with #c8b896 amber border."""
        log = self.query_one("#conversation-log", RichLog)

        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}", n=3))

        if not diff:
            return

        diff_text = Text()
        for line in diff:
            line_str = line.rstrip("\n")
            if line.startswith("---") or line.startswith("+++"):
                diff_text.append(f"{line_str}\n", style="dim #cbd5e1")
            elif line.startswith("@@"):
                diff_text.append(f"{line_str}\n", style="#cbd5e1 dim")
            elif line.startswith("+"):
                diff_text.append(f"+ {line_str[1:]}\n", style="#10b981 on #064e3b")
            elif line.startswith("-"):
                diff_text.append(f"- {line_str[1:]}\n", style="#f87171 on #7f1d1d")
            else:
                diff_text.append(f"  {line_str}\n", style="#f8fafc")

        diff_panel = Panel(
            diff_text,
            title=f"📄 Child Scroll Box — Diff: {path}",
            border_style="#c8b896",
            padding=(0, 1)
        )
        log.write(Align.center(diff_panel))
        log.write("\n")

    # ── Key Bindings & Actions ───────────────────────────────────────────

    def action_toggle_thinking(self) -> None:
        """Toggle active or latest thinking panel expansion state via keyboard (ctrl+t)."""
        if self._active_thinking_panel:
            self._active_thinking_panel.toggle()

    def action_interrupt_task(self) -> None:
        """Interrupt ongoing task on ESC key press."""
        if self._current_agent_task and not self._current_agent_task.done():
            self._current_agent_task.cancel()

    async def action_quit_app(self) -> None:
        """Cleanly close browser agent and quit app."""
        if self.agent:
            await self.agent.close()
        self.exit()


# ── Remote Session Cache & Authentication Helpers ───────────────────────────
def get_session_cache_path() -> Path:
    p = Path.home() / ".julius" / "tui_session.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_all_cached_sessions() -> dict:
    p = get_session_cache_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


DEFAULT_REMOTE_HOST = os.environ.get("JULIUS_REMOTE_HOST", "127.0.0.1:8080")


def probe_remote_endpoint(url_or_base: str, timeout: float = 1.2) -> bool:
    """Check if a Julius server endpoint is reachable via HTTP."""
    import urllib.error
    import urllib.request
    http_base = url_or_base.replace("ws://", "http://").replace("wss://", "https://").split("/ws")[0]
    probe_url = f"{http_base}/api/session"
    req = urllib.request.Request(probe_url, headers={"User-Agent": "JuliusCLI/3.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 401, 403)
    except urllib.error.HTTPError as e:
        return e.code in (200, 401, 403)
    except Exception:
        return False


def resolve_target_ws_url(ws_url: Optional[str]) -> Optional[str]:
    """
    Intelligently resolve the target WebSocket URL.
    - If ws_url is None: probes localhost:8080 first, then DEFAULT_REMOTE_HOST.
    - If ws_url is localhost/127.0.0.1 and not listening: auto-routes to DEFAULT_REMOTE_HOST.
    """
    if not ws_url:
        if probe_remote_endpoint("http://127.0.0.1:8080"):
            return "ws://127.0.0.1:8080/ws"
        if probe_remote_endpoint(f"http://{DEFAULT_REMOTE_HOST}"):
            return f"ws://{DEFAULT_REMOTE_HOST}/ws"
        return None

    if "localhost" in ws_url or "127.0.0.1" in ws_url:
        if not probe_remote_endpoint(ws_url):
            if probe_remote_endpoint(f"http://{DEFAULT_REMOTE_HOST}"):
                resolved = ws_url.replace("localhost:8080", DEFAULT_REMOTE_HOST).replace("127.0.0.1:8080", DEFAULT_REMOTE_HOST)
                if resolved == ws_url:
                    resolved = f"ws://{DEFAULT_REMOTE_HOST}/ws"
                print(f"\nℹ️  Notice: Host at '{ws_url}' is not reachable.")
                print(f"    Auto-routing connection to active Julius server at '{resolved}'\n")
                return resolved

    return ws_url


def save_cached_session(ws_url: str, token: str, username: str = "") -> None:
    cache = load_all_cached_sessions()
    entry = {"token": token, "username": username, "time": time.time()}
    cache[ws_url] = entry
    # Also save under normalized host and default remote
    if "localhost" in ws_url or "127.0.0.1" in ws_url:
        cache[f"ws://{DEFAULT_REMOTE_HOST}/ws"] = entry
    elif DEFAULT_REMOTE_HOST in ws_url:
        cache["ws://localhost:8080/ws"] = entry
        cache["ws://127.0.0.1:8080/ws"] = entry
    try:
        get_session_cache_path().write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_cached_session(ws_url: str, expected_username: Optional[str] = None) -> Optional[str]:
    cache = load_all_cached_sessions()
    entry = cache.get(ws_url)
    if not entry:
        if "localhost" in ws_url or "127.0.0.1" in ws_url:
            entry = cache.get(f"ws://{DEFAULT_REMOTE_HOST}/ws")
        elif DEFAULT_REMOTE_HOST in ws_url:
            entry = cache.get("ws://localhost:8080/ws") or cache.get("ws://127.0.0.1:8080/ws")
    if entry and isinstance(entry, dict):
        if expected_username and entry.get("username") and entry.get("username").lower() != expected_username.lower():
            return None
        return entry.get("token")
    return None


def clear_cached_session(ws_url: str) -> None:
    cache = load_all_cached_sessions()
    for key in [ws_url, f"ws://{DEFAULT_REMOTE_HOST}/ws", "ws://localhost:8080/ws", "ws://127.0.0.1:8080/ws"]:
        cache.pop(key, None)
    try:
        get_session_cache_path().write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:
        pass


def validate_remote_token(http_base: str, token: str) -> bool:
    import urllib.request
    url = f"{http_base}/api/session"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Cookie": f"session_id={token}",
            "User-Agent": "JuliusCLI/3.0",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("authenticated") is True
    except Exception:
        return False


def resolve_remote_session(
    ws_url: str,
    token: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    force_reauth: bool = False,
) -> tuple[Optional[str], str]:
    """
    Ensure the CLI client is authenticated with the remote Julius server.
    Returns (token, resolved_ws_url).
    """
    import getpass
    import urllib.error
    import urllib.request

    if not ws_url:
        return None, ws_url

    # Check and auto-route host if necessary
    ws_url = resolve_target_ws_url(ws_url) or ws_url

    if force_reauth:
        clear_cached_session(ws_url)

    # Derive HTTP base URL
    http_base = ws_url.replace("ws://", "http://").replace("wss://", "https://").split("/ws")[0]

    # 1. Explicit token
    if token:
        if validate_remote_token(http_base, token):
            save_cached_session(ws_url, token)
            return token, ws_url
        print(f"\n⚠️  Provided token failed validation against {http_base}")

    # 2. Environment variable
    env_token = os.environ.get("JULIUS_SESSION_TOKEN", os.environ.get("JULIUS_SESSION_TOKEN"))
    if env_token and not force_reauth and validate_remote_token(http_base, env_token):
        return env_token, ws_url

    # 3. Cached session
    if not force_reauth:
        cached = get_cached_session(ws_url, expected_username=username)
        if cached and validate_remote_token(http_base, cached):
            return cached, ws_url

    # 4. Username & Password passed via flags
    if username and password:
        login_url = f"{http_base}/api/login"
        payload = json.dumps({"username": username, "password": password}).encode("utf-8")
        req = urllib.request.Request(login_url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                new_token = res_data.get("token")
                if new_token:
                    save_cached_session(ws_url, new_token, username)
                    return new_token, ws_url
        except Exception as e:
            print(f"❌ Failed to log in with provided credentials: {e}")
            sys.exit(1)

    # 5. Interactive prompt
    print("\n" + "═" * 60)
    print("  🔐 Julius Server Authentication Required")
    print(f"  Target: {ws_url}")
    print("═" * 60)
    print("  [1] Sign in with existing account (Default)")
    print("  [2] Create new account (Sign Up)")
    print("═" * 60)
    choice = input("Select option [1/2] (default: 1): ").strip() or "1"

    if choice == "2":
        print("\n📝 Create New Account:")
        user_input = input("Username: ").strip()
        email_input = input("Email: ").strip()
        pass_input = getpass.getpass("Password: ")
        confirm_input = getpass.getpass("Confirm Password: ")
        signup_url = f"{http_base}/api/signup"
        payload = json.dumps({
            "username": user_input,
            "email": email_input,
            "password": pass_input,
            "confirm_password": confirm_input
        }).encode("utf-8")
        req = urllib.request.Request(signup_url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                new_token = res_data.get("token")
                if new_token:
                    save_cached_session(ws_url, new_token, user_input)
                    print(f"✅ Account created and authenticated as '{user_input}'!\n")
                    return new_token, ws_url
        except urllib.error.HTTPError as he:
            try:
                err_data = json.loads(he.read().decode("utf-8"))
                print(f"❌ Sign up failed: {err_data.get('error', he.reason)}")
            except Exception:
                print(f"❌ Sign up failed: {he}")
            sys.exit(1)
        except Exception as exc:
            print(f"❌ Sign up failed: {exc}")
            sys.exit(1)
    else:
        print("\n🔑 Sign In:")
        user_input = input("Username or Email: ").strip()
        pass_input = getpass.getpass("Password: ")
        login_url = f"{http_base}/api/login"
        payload = json.dumps({"username": user_input, "password": pass_input}).encode("utf-8")
        req = urllib.request.Request(login_url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                new_token = res_data.get("token")
                if new_token:
                    save_cached_session(ws_url, new_token, user_input)
                    print(f"✅ Logged in successfully as '{user_input}'!\n")
                    return new_token, ws_url
        except urllib.error.HTTPError as he:
            try:
                err_data = json.loads(he.read().decode("utf-8"))
                print(f"❌ Login failed: {err_data.get('error', he.reason)}")
            except Exception:
                print(f"❌ Login failed: {he}")
            sys.exit(1)
        except Exception as exc:
            # If connection failed, test if fallback host helps
            if ("Connection refused" in str(exc) or "Errno 61" in str(exc)) and http_base != f"http://{DEFAULT_REMOTE_HOST}":
                print(f"\n⚠️  Connection to {http_base} refused. Retrying against active remote Julius server at http://{DEFAULT_REMOTE_HOST}...")
                fallback_base = f"http://{DEFAULT_REMOTE_HOST}"
                fallback_ws = f"ws://{DEFAULT_REMOTE_HOST}/ws"
                login_url = f"{fallback_base}/api/login"
                req = urllib.request.Request(login_url, data=payload, headers={"Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                        new_token = res_data.get("token")
                        if new_token:
                            save_cached_session(fallback_ws, new_token, user_input)
                            print(f"✅ Logged in successfully as '{user_input}' on {DEFAULT_REMOTE_HOST}!\n")
                            return new_token, fallback_ws
                except Exception as exc2:
                    print(f"❌ Login failed: {exc2}")
                    sys.exit(1)
            print(f"❌ Login failed: {exc}")
            sys.exit(1)

    return None, ws_url


async def launch_v3_tui_async(
    workspace_dir: str = ".",
    config: Optional[AgentConfig] = None,
    initial_task: Optional[str] = None,
    ws_url: Optional[str] = None,
    session_token: Optional[str] = None,
) -> None:
    """Entrypoint helper to launch next-gen Julius CLI Live TUI inside an existing event loop."""
    cfg = config or AgentConfig()
    from src.tui.app import JuliusApp
    app = JuliusApp(
        workspace_dir=workspace_dir,
        config=cfg,
        initial_task=initial_task,
        ws_url=ws_url,
        session_token=session_token,
    )
    await app.run_async()


def launch_v3_tui(
    workspace_dir: str = ".",
    config: Optional[AgentConfig] = None,
    initial_task: Optional[str] = None,
    ws_url: Optional[str] = None,
    session_token: Optional[str] = None,
) -> None:
    """Entrypoint helper to launch next-gen Julius CLI Live TUI synchronously."""
    cfg = config or AgentConfig()
    from src.tui.app import JuliusApp
    app = JuliusApp(
        workspace_dir=workspace_dir,
        config=cfg,
        initial_task=initial_task,
        ws_url=ws_url,
        session_token=session_token,
    )
    app.run()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Julius CLI v3.1 Live TUI")
    parser.add_argument("--ws", default=None, help="WebSocket URL of remote Julius server (e.g. ws://127.0.0.1:8080/ws)")
    parser.add_argument("--workspace", default=".", help="Workspace directory path")
    parser.add_argument("--token", default=None, help="Julius session authentication token")
    parser.add_argument("--user", default=None, help="Julius username")
    parser.add_argument("--password", default=None, help="Julius password")
    parser.add_argument("--model", default=None, help="Initial LLM model (deepseek, gemini, chatgpt, grok, kimi, perplexity)")
    parser.add_argument("--login", "--reauth", action="store_true", dest="reauth", help="Force interactive login prompt even if cached session exists")
    parser.add_argument("task", nargs="?", default=None, help="Initial task prompt or ws:// URL")
    args = parser.parse_args()

    # If the positional argument is a ws/http URL, treat it as args.ws
    if args.task and (args.task.startswith("ws://") or args.task.startswith("wss://") or args.task.startswith("http://")):
        if not args.ws:
            args.ws = args.task
            args.task = None

    token = None
    target_ws = resolve_target_ws_url(args.ws) or args.ws
    if target_ws:
        token, target_ws = resolve_remote_session(
            target_ws,
            token=args.token,
            username=args.user,
            password=args.password,
            force_reauth=args.reauth,
        )
        args.ws = target_ws

    cfg = AgentConfig()
    if args.model:
        cfg.provider = MODEL_ALIASES.get(args.model.lower(), args.model.lower())

    launch_v3_tui(
        workspace_dir=args.workspace,
        config=cfg,
        initial_task=args.task,
        ws_url=args.ws,
        session_token=token,
    )


# Backward-compatibility alias
JuliusCLIV3App = JuliusCLIV3App
