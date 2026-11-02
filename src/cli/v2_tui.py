"""
Julius CLI v2: Julius-Style Bordered Live TUI.

Provides a live, persistent, redrawable terminal interface featuring:
- Bordered main session box with dynamic context title bar
- Scrollable conversation history (> for user, ● for assistant)
- Live status line with contextual present-participle verbs (Smiling..., Honking...), elapsed time, token count
- Pinned bottom input box with blinking cursor & permission gate handler
- External footer outside main box for shortcuts and permission mode state
- Syntax-highlighted diffs inside the box with line numbers
- Centered welcome screen with real task_memory recent activity history
- '@'-triggered fuzzy workspace file-path autocomplete overlay
"""

from __future__ import annotations

import asyncio
import difflib
import os
import random
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual import events, work
from textual.reactive import reactive
from textual.widgets import Input, Label, OptionList, Static, RichLog
from textual.widgets.option_list import Option

from src.agent_config import AgentConfig
from src.web_agent import WebAgent, AgentResult
from src.memory.storage import MemoryStorage


# ── Contextual Present-Participle Status Verbs ─────────────────────────────
VERBS_CHAT = ["Smiling", "Pondering", "Brainstorming", "Thinking", "Synthesizing", "Reasoning"]
VERBS_EXEC = ["Honking", "Compiling", "Inspecting", "Wrangling", "Debugging", "Running"]
VERBS_EDIT = ["Crafting", "Refactoring", "Polishing", "Editing", "Stitching", "Sculpting"]
VERBS_IDLE = ["Ready", "Napping", "Waiting", "Standing by"]


class FileAutocompleteDropdown(OptionList):
    """Dropdown menu for fuzzy file-path autocomplete triggered by '@'."""

    DEFAULT_CSS = """
    FileAutocompleteDropdown {
        layer: top;
        max-height: 8;
        width: 1fr;
        border: solid $accent;
        background: $surface;
        display: none;
        margin-left: 2;
        margin-right: 2;
    }
    """


class MainSessionBox(Container):
    """Main rounded-corner bordered session box."""

    DEFAULT_CSS = """
    MainSessionBox {
        border: round $accent;
        height: 1fr;
        width: 100%;
        padding: 0 1;
        layout: vertical;
    }
    """


class ExternalFooter(Static):
    """Footer bar rendered outside the main bordered box."""

    DEFAULT_CSS = """
    ExternalFooter {
        height: 1;
        width: 100%;
        background: $surface-darken-1;
        color: $text-muted;
        padding: 0 1;
    }
    """


class JuliusCLIV2App(App):
    """
    Main Textual Application for Julius CLI v2 Live TUI.
    """

    CSS = """
    Screen {
        layout: vertical;
        padding: 0;
        margin: 0;
        background: $background;
    }

    #title-bar {
        height: 1;
        width: 100%;
        text-style: bold;
        color: $accent;
        padding-left: 1;
    }

    .welcome-col {
        width: 1fr;
        height: auto;
        border: round $primary-muted;
        padding: 0 1;
        margin: 0 1;
    }

    #recent-activity {
        height: auto;
        border: round $primary-muted;
        margin: 1 1;
        padding: 0 1;
    }

    #conversation-log {
        height: 1fr;
        width: 100%;
        overflow-y: auto;
        scrollbar-gutter: stable;
        padding: 0 1;
    }

    #status-line {
        height: 1;
        width: 100%;
        color: #c8b896;
        text-style: bold;
        padding-left: 2;
        display: none;
    }

    #input-container {
        height: auto;
        width: 100%;
        border: round $accent;
        margin: 0;
        padding: 0;
    }

    #prompt-input {
        border: none;
        height: 1;
        width: 100%;
        padding: 0 1;
        background: transparent;
    }

    #prompt-input:focus {
        border: none;
    }

    #autocomplete-popup {
        height: auto;
        max-height: 8;
    }
    """

    BINDINGS = [
        ("escape", "interrupt_task", "Interrupt execution"),
        ("ctrl+c", "quit_app", "Quit"),
    ]

    is_working: reactive[bool] = reactive(False)
    status_verb: reactive[str] = reactive("Ready")
    elapsed_seconds: reactive[int] = reactive(0)
    token_count: reactive[int] = reactive(0)
    permission_mode: reactive[str] = reactive("Bypassing Permissions")
    update_status: reactive[str] = reactive("✓ Up to date")
    title_context: reactive[str] = reactive("")

    def __init__(
        self,
        workspace_dir: str,
        config: AgentConfig,
        initial_task: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.workspace_dir = Path(workspace_dir).resolve()
        self.config = config
        self.initial_task = initial_task
        self.agent: Optional[WebAgent] = None
        self.workspace_files: List[str] = []
        self._timer_task: Optional[asyncio.Task] = None
        self._start_time: float = 0.0
        self._current_agent_task: Optional[asyncio.Task] = None
        self._pending_confirmation: bool = False

    def compose(self) -> ComposeResult:
        folder_name = self.workspace_dir.name
        prod_name = "Julius (DeepSeek)" if self.config.provider == "deepseek" else f"Julius ({self.config.provider.title()})"

        with MainSessionBox():
            yield Static(f"📁 {folder_name} — {prod_name}", id="title-bar")
            
            yield RichLog(id="conversation-log", highlight=True, markup=True, wrap=True)
            
            yield Static("", id="status-line")
            
            with Vertical(id="input-container"):
                yield Input(placeholder="Type a prompt or /help, /plan, /act, /new (type @ for files)...", id="prompt-input")
                yield FileAutocompleteDropdown(id="autocomplete-dropdown")

        yield ExternalFooter(id="external-footer")

    async def on_mount(self) -> None:
        """Initialize workspace files, task memory, and welcome screen."""
        self._scan_workspace_files()
        self._update_permission_mode_text()
        self._render_welcome_screen()

        # Initialize WebAgent
        self.agent = WebAgent(self.config, keep_browser_open=True)
        self.agent.on_event = self._handle_agent_event

        self.query_one("#prompt-input", Input).focus()

        if self.initial_task:
            self.query_one("#prompt-input", Input).value = self.initial_task
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

    def _update_permission_mode_text(self) -> None:
        if not self.config.confirm_actions:
            self.permission_mode = "Bypassing Permissions"
        else:
            self.permission_mode = "Confirming Actions"
        self._refresh_footer()

    def _refresh_footer(self) -> None:
        try:
            footer = self.query_one("#external-footer", ExternalFooter)
        except Exception:
            return

        if self._pending_confirmation:
            left = "⚠️ CONFIRMATION REQUIRED: Type [y]es / [n]o or press y/n"
        elif self.is_working:
            left = "! for bash · / for commands · esc to undo"
        else:
            left = "? for shortcuts (/help, /plan, /act, /new)"
        
        right = f"{self.permission_mode}  │  {self.update_status}"
        
        total_width = self.size.width if self.size.width > 0 else 80
        spaces = max(2, total_width - len(left) - len(right) - 4)
        footer.update(f" {left}{' ' * spaces}{right} ")

    def _render_welcome_screen(self) -> None:
        """Render Stage 5 centered welcome layout + real task_memory recent activity."""
        log = self.query_one("#conversation-log", RichLog)

        # Header Title Banner
        header = Text()
        header.append("✨ JULIUS AI PAIR PROGRAMMER ✨\n", style="bold cyan")
        header.append(f"Autonomous Developer Agent • Workspace: {self.workspace_dir.name}\n\n", style="dim white")

        # Config & Shortcuts Details
        details = Text()
        details.append("⚙️ Environment & Config\n", style="bold yellow")
        details.append(f"  • Provider:   {self.config.provider.title()}\n", style="green")
        details.append(f"  • Directory:  {self.workspace_dir.name}\n", style="cyan")
        details.append(f"  • Permission: {self.permission_mode}\n\n", style="magenta")

        details.append("💡 Quick Tips & Commands\n", style="bold yellow")
        details.append("  • /plan <task>  - Analyze task & present step-by-step plan\n", style="dim")
        details.append("  • /act <task>   - Execute task directly without plan prompt\n", style="dim")
        details.append("  • /new          - Start fresh chat session context\n", style="dim")
        details.append("  • @filepath     - Trigger fuzzy file completion dropdown\n", style="dim")
        details.append("  • esc           - Interrupt ongoing live agent execution\n\n", style="dim")

        # Fetch Real Recent Activity from Task Memory SQLite
        storage = MemoryStorage(str(self.workspace_dir))
        recent_tasks = storage.list_tasks(limit=5)

        recent_text = Text()
        recent_text.append("📋 Recent Activity\n", style="bold white")
        if recent_tasks:
            for task in recent_tasks:
                summary = task.get("summary", "Untitled task")
                status = task.get("status", "completed")
                icon = "✓" if status == "completed" else "•"
                updated_ts = task.get("updated_at", 0)
                time_str = time.strftime("%H:%M", time.localtime(updated_ts)) if updated_ts else ""
                recent_text.append(f"  {icon} {summary} ", style="bold green" if status == "completed" else "yellow")
                if time_str:
                    recent_text.append(f"({time_str})", style="dim")
                recent_text.append("\n")
        else:
            recent_text.append("  (No recent activity)\n", style="dim italic")

        welcome_panel = Panel(
            Text.assemble(
                header,
                details,
                "─────────────────────────────────────────────────────────────\n",
                recent_text
            ),
            title="✨ Welcome to Julius CLI v2",
            border_style="cyan",
            padding=(1, 2)
        )
        log.write(welcome_panel)
        log.write("\n")

    # ── Autocomplete Handling ─────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle fuzzy file autocomplete on typing '@'."""
        val = event.value
        dropdown = self.query_one("#autocomplete-dropdown", FileAutocompleteDropdown)

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

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Insert selected autocomplete option into input bar."""
        dropdown = self.query_one("#autocomplete-dropdown", FileAutocompleteDropdown)
        inp = self.query_one("#prompt-input", Input)

        selected_file = str(event.option.id)
        val = inp.value
        at_idx = val.rfind("@")

        if at_idx != -1:
            new_val = val[:at_idx] + f"@{selected_file} "
            inp.value = new_val
            inp.cursor_position = len(new_val)

        dropdown.display = False
        inp.focus()

    # ── Agent Execution & Event Handling ──────────────────────────────────

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        if not prompt:
            return
        
        inp = self.query_one("#prompt-input", Input)
        inp.value = ""

        dropdown = self.query_one("#autocomplete-dropdown", FileAutocompleteDropdown)
        dropdown.display = False

        # Handle pending confirmation response
        if self._pending_confirmation:
            log = self.query_one("#conversation-log", RichLog)
            allow = prompt.lower() in ("y", "yes", "a", "accept", "")
            if self.agent:
                self.agent.set_confirmation_result(allow)
            self._pending_confirmation = False
            self._refresh_footer()
            if allow:
                log.write("[bold green]✅ Action accepted by user.[/bold green]\n")
            else:
                log.write("[bold red]❌ Action declined by user.[/bold red]\n")
            return

        if self.is_working:
            return

        await self._submit_prompt(prompt)

    async def _submit_prompt(self, prompt: str) -> None:
        log = self.query_one("#conversation-log", RichLog)

        if prompt.lower() == "/exit":
            await self.action_quit_app()
            return
        elif prompt.lower() == "/new":
            if self.agent:
                await self.agent.start_new_chat()
            log.write("[bold green]✨ Started a new chat session.[/bold green]\n")
            return
        elif prompt.lower() == "/help":
            log.write("[bold cyan]Commands:\n  /plan <task>  - Outline step-by-step plan\n  /act <task>   - Direct execution\n  /new          - Reset session\n  /exit         - Quit[/bold cyan]\n")
            return

        user_turn = Text()
        user_turn.append("> ", style="bold cyan")
        user_turn.append(prompt, style="bold white")
        log.write(user_turn)

        self.is_working = True
        self._start_time = time.time()
        self.status_verb = random.choice(VERBS_CHAT)
        self._start_timer()
        self._refresh_footer()

        try:
            title_bar = self.query_one("#title-bar", Static)
            folder_name = self.workspace_dir.name
            title_bar.update(f"📁 {folder_name} — Julius  │  · {self.status_verb}…")
        except Exception:
            pass

        self._current_agent_task = asyncio.create_task(self._run_agent_task(prompt))

    async def _run_agent_task(self, prompt: str) -> None:
        log = self.query_one("#conversation-log", RichLog)
        try:
            if not self.agent:
                self.agent = WebAgent(self.config, keep_browser_open=True)
                self.agent.on_event = self._handle_agent_event

            result: AgentResult = await self.agent.run(prompt)

            asst_turn = Text()
            asst_turn.append("\n● ", style="bold green")
            asst_turn.append(result.summary or "Task completed.", style="white")
            log.write(asst_turn)
            log.write("\n")

        except asyncio.CancelledError:
            log.write("\n[bold red]⚡ Task interrupted by user (esc).[/bold red]\n")
        except Exception as exc:
            log.write(f"\n[bold red]❌ Error during task: {exc}[/bold red]\n")
        finally:
            self._stop_timer()
            self.is_working = False
            self._refresh_footer()

            folder_name = self.workspace_dir.name
            prod_name = "Julius (DeepSeek)" if self.config.provider == "deepseek" else f"Julius ({self.config.provider.title()})"
            try:
                title_bar = self.query_one("#title-bar", Static)
                title_bar.update(f"📁 {folder_name} — {prod_name}")
            except Exception:
                pass

    def _handle_agent_event(self, event: Dict[str, Any]) -> None:
        """Handle step events emitted by WebAgent."""
        event_type = event.get("type")
        log = self.query_one("#conversation-log", RichLog)

        input_toks = event.get("input_tokens", 0)
        output_toks = event.get("output_tokens", 0)
        if input_toks or output_toks:
            self.token_count += (input_toks + output_toks)
        else:
            text_payload = str(event.get("text", "")) + str(event.get("thought", "")) + str(event.get("output", ""))
            if text_payload:
                self.token_count += max(1, len(text_payload.split()))

        if event_type == "confirm_action":
            action_name = event.get("action", "action")
            action_args = event.get("args", {})
            self._pending_confirmation = True
            self._refresh_footer()

            perm_card = Panel(
                Text.assemble(
                    (f"⚠️ Confirmation Required: {action_name}\n\n", "bold yellow"),
                    (f"Details: {action_args}\n\n", "white"),
                    ("Type 'y' (accept) or 'n' (decline) and press Enter.", "bold cyan")
                ),
                title="🔐 Action Gate",
                border_style="yellow"
            )
            log.write(perm_card)
            log.write("\n")

        elif event_type == "action":
            action_name = event.get("name", "")
            args = event.get("args", {})

            if action_name in ("run_bash", "git", "python"):
                self.status_verb = random.choice(VERBS_EXEC)
            elif action_name in ("edit_file", "write_file"):
                self.status_verb = random.choice(VERBS_EDIT)
            else:
                self.status_verb = random.choice(VERBS_CHAT)

            folder_name = self.workspace_dir.name
            subcmd = args.get("command", "") or args.get("path", action_name)
            try:
                title_bar = self.query_one("#title-bar", Static)
                title_bar.update(f"✳ {action_name} — {subcmd}  │  📁 {folder_name}")
            except Exception:
                pass

            if action_name in ("edit_file", "write_file") and ("old_text" in args or "content" in args):
                self._render_stage4_diff(args.get("path", "modified_file.py"), args.get("old_text", ""), args.get("new_text", args.get("content", "")))

        elif event_type == "thought":
            thought = event.get("text", "")
            if thought:
                # Display full thought without arbitrary '...' truncation
                log.write(f"[dim]💭 {thought}[/dim]")

    def _render_stage4_diff(self, path: str, old_text: str, new_text: str) -> None:
        """Render Stage 4 syntax-highlighted diff inside the bordered box log."""
        log = self.query_one("#conversation-log", RichLog)

        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}", n=3))

        if not diff:
            return

        diff_text = Text()
        diff_text.append(f"\n📄 Proposed Edits: {path}\n", style="bold cyan")

        for line in diff:
            line_str = line.rstrip("\n")
            if line.startswith("---") or line.startswith("+++"):
                diff_text.append(f"{line_str}\n", style="dim bold")
            elif line.startswith("@@"):
                diff_text.append(f"{line_str}\n", style="cyan dim")
            elif line.startswith("+"):
                diff_text.append(f"+ {line_str[1:]}\n", style="green on #1e3a1e")
            elif line.startswith("-"):
                diff_text.append(f"- {line_str[1:]}\n", style="red on #3a1e1e")
            else:
                diff_text.append(f"  {line_str}\n", style="dim")

        log.write(diff_text)

    # ── Live Status Timer ─────────────────────────────────────────────────

    def _start_timer(self) -> None:
        self._stop_timer()
        try:
            status_line = self.query_one("#status-line", Static)
            status_line.display = True
            self._timer_task = asyncio.create_task(self._update_status_loop())
        except Exception:
            pass

    def _stop_timer(self) -> None:
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None
        try:
            status_line = self.query_one("#status-line", Static)
            status_line.display = False
        except Exception:
            pass

    async def _update_status_loop(self) -> None:
        try:
            while self.is_working:
                elapsed = int(time.time() - self._start_time)
                self.elapsed_seconds = elapsed

                msg = f"· {self.status_verb}… ({elapsed}s · ↑ {self.token_count} tokens · esc to interrupt)"
                try:
                    status_line = self.query_one("#status-line", Static)
                    status_line.update(msg)
                except Exception:
                    break
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    # ── Key Bindings & Actions ───────────────────────────────────────────

    def action_interrupt_task(self) -> None:
        """Interrupt ongoing task on ESC key press."""
        if self._current_agent_task and not self._current_agent_task.done():
            self._current_agent_task.cancel()

    async def action_quit_app(self) -> None:
        """Cleanly close browser agent and quit app."""
        if self.agent:
            await self.agent.close()
        self.exit()


async def launch_v2_tui_async(workspace_dir: str, config: AgentConfig, initial_task: Optional[str] = None) -> None:
    """Entrypoint helper to launch Julius CLI v2 Live TUI inside an existing event loop."""
    app = JuliusCLIV2App(workspace_dir=workspace_dir, config=config, initial_task=initial_task)
    await app.run_async()


def launch_v2_tui(workspace_dir: str, config: AgentConfig, initial_task: Optional[str] = None) -> None:
    """Entrypoint helper to launch Julius CLI v2 Live TUI synchronously."""
    app = JuliusCLIV2App(workspace_dir=workspace_dir, config=config, initial_task=initial_task)
    app.run()
