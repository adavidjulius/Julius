"""
Julius Terminal User Interface (TUI).

Architecture:
- Centered 76-cell column with dynamic margins on wide terminals.
- Clean 3-tier hierarchy: Conversation Area, Rounded Composer, Single-line Status.
- Single-render Markdown pipeline with zero raw markdown leaks.
- 1-cell dim scrollbar thumb without thick colored bars.
- Backward compatibility exports for StreamPanel and JuliusTUI.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, ScrollableContainer
from textual.reactive import reactive
from textual.widgets import Label, Static, RichLog, Tree

from .config import JuliusConfig, load_config, save_config
from .theme import ThemeTokens, get_theme, generate_tcss
from .state import SessionState
from .event_bridge import EventBridge
from .markdown import render_julius_markdown, render_apple_markdown
from .components.welcome import WelcomeView
from .components.message import UserMessage, AssistantMessage, ThinkingDot
from .components.command_box import CommandBox
from .components.tool_summary import ToolSummary
from .components.composer import Composer
from .components.command_suggestions import CommandSuggestions
from .commands import COMMAND_LOOKUP
from .components.status_line import StatusLine
from .components.conversation_area import ConversationArea
from .components.modals.model_picker import ModelPickerModal
from .components.modals.help_modal import HelpModal
from .components.modals.diff_modal import DiffReviewModal
from .components.modals.active_action_modal import ActiveActionModal

# Cross-platform clipboard helper
from ..platform_compat import copy_to_clipboard
from ..agent_prompts import is_json_or_protocol


class JuliusApp(App):
    """Next-Gen minimalist Julius TUI."""

    BINDINGS = [
        Binding("ctrl+y", "copy_last_answer", "Copy Answer", show=False),
        Binding("ctrl+o", "toggle_tools", "Toggle Steps", show=False),
        Binding("f2", "open_model_picker", "Switch Model", show=False),
        Binding("ctrl+d", "open_diff_review", "Diff Review", show=False),
        Binding("ctrl+i", "open_active_action_modal", "Inspect Action", show=False),
        Binding("ctrl+t", "toggle_thinking", "Toggle Thinking", show=False),
        Binding("question_mark", "open_help", "Help", show=False),
        Binding("escape", "handle_escape", "Close / Cancel", show=False),
    ]

    terminal_too_small: reactive[bool] = reactive(False)

    def __init__(
        self,
        workspace_dir: str = ".",
        config: Optional[Any] = None,
        initial_task: Optional[str] = None,
        ws_url: Optional[str] = None,
        session_token: Optional[str] = None,
        app_config: Optional[JuliusConfig] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.workspace_dir = workspace_dir
        self.agent_config = config
        self.initial_task = initial_task
        self.ws_url = ws_url
        self.session_token = session_token

        # Load user configuration
        self.app_config: JuliusConfig = app_config or load_config()

        # Resolve theme
        self.active_theme: ThemeTokens = get_theme(self.app_config.theme)

        # Reactive session state
        self.session_state = SessionState(
            active_model=getattr(self.agent_config, "provider", self.app_config.model),
            theme_name=self.app_config.theme,
        )

        # Active turn widgets
        self.active_thinking_dot: Optional[ThinkingDot] = None
        self.active_assistant_msg: Optional[AssistantMessage] = None
        self._conversation_started = False
        self._current_tool_summary: Optional[ToolSummary] = None
        self._in_think_block: bool = False
        self._accumulated_thought: str = ""
        self._in_action_json_stream: bool = False
        self._accumulated_stream: str = ""

        # Backend event bridge
        self.event_bridge = EventBridge(
            session_state=self.session_state,
            post_message_callback=self._handle_bridge_message,
            update_status_callback=self._update_bridge_status,
        )

        # Agent instance (local WebAgent or remote WebSocket client)
        self.agent: Optional[Any] = None
        self._ws: Optional[Any] = None
        self._awaiting_confirmation: bool = False
        self._status_line_widget: Optional[Any] = None

    @property
    def is_awaiting_confirmation(self) -> bool:
        """Return True if agent is actively awaiting user confirmation."""
        if self.agent and getattr(self.agent, "_confirm_future", None) and not self.agent._confirm_future.done():
            return True
        return self._awaiting_confirmation

    def _smart_scroll_to_end(self, conv_area: ScrollableContainer, force: bool = False) -> None:
        """Scroll conversation area to bottom smoothly if user is near end or forced."""
        if force:
            conv_area.scroll_end(animate=False)
            return

        try:
            # If user is at or within 4 rows of the bottom, keep following
            is_at_end = (
                getattr(conv_area, "is_vertical_scroll_end", False)
                or (conv_area.max_scroll_y - conv_area.scroll_offset.y <= 4)
            )
            if is_at_end:
                conv_area.scroll_end(animate=False)
        except Exception:
            conv_area.scroll_end(animate=False)

    def handle_confirmation_choice(self, allow: bool) -> None:
        """Instantly process single-key or submitted confirmation choice (y/n) silently."""
        self._awaiting_confirmation = False
        conv_area = self.query_one("#conversation-area", ScrollableContainer)

        # Reset composer text and placeholder (silent entry, no text shown)
        try:
            composer = self.query_one("#composer-input", Composer)
            composer.text = ""
            composer.placeholder = "Ask Julius anything"
            composer._recalculate_height()
        except Exception:
            pass

        # Automatically remove asking confirmation prompt once answered (only needed while asking)
        if getattr(self, "_active_confirmation_msg", None):
            try:
                self._active_confirmation_msg.remove()
            except Exception:
                pass
            self._active_confirmation_msg = None

        for child in list(conv_area.children):
            if getattr(child, "_is_confirmation_prompt", False):
                try:
                    child.remove()
                except Exception:
                    pass

        # Reset status hint
        try:
            status_line = self.query_one("#status-line", StatusLine)
            status_line.update_hint("? for help")
        except Exception:
            pass

        if not self.active_thinking_dot:
            self.active_thinking_dot = ThinkingDot("Thinking")
            conv_area.mount(self.active_thinking_dot)
        else:
            self.active_thinking_dot.is_running = True
            self.active_thinking_dot.label = "Thinking"
            if not self.active_thinking_dot._spinner_timer:
                self.active_thinking_dot._spinner_timer = self.active_thinking_dot.set_interval(0.3, self.active_thinking_dot._spin)
            self.active_thinking_dot.refresh()

        self._smart_scroll_to_end(conv_area, force=True)

        if self.agent and getattr(self.agent, "_confirm_future", None) and not self.agent._confirm_future.done():
            self.agent.set_confirmation_result(allow)
        elif self._ws and not self._ws.closed:
            asyncio.create_task(self._ws.send_json({"type": "confirmation", "allow": allow}))

    def on_key(self, event: events.Key) -> None:
        """Global key listener: instantly confirm/deny with single key Y/N without typing or enter."""
        if self.is_awaiting_confirmation:
            key_char = (event.character or event.key or "").lower()
            if key_char in ("y", "n"):
                event.prevent_default()
                event.stop()
                self.handle_confirmation_choice(key_char == "y")
                return

    def get_default_screen(self):
        # Dynamically inject CSS built from theme tokens
        screen = super().get_default_screen()
        return screen

    def _set_pointer_shape(self, shape: str) -> None:
        """Force mouse pointer to remain normal arrow cursor, preventing stuck I-beam text shape."""
        if hasattr(self, "_driver") and self._driver is not None:
            try:
                self._driver.write("\x1b]22;default\x07")
            except Exception:
                pass

    def on_mount(self) -> None:
        """Initialize theme, terminal guard, and launch initial task if present."""
        self.screen.styles.background = self.active_theme.bg
        self.stylesheet.add_source(generate_tcss(self.active_theme))

        # Ensure terminal mouse pointer and text cursor are normal (arrow mouse pointer, block text cursor)
        if hasattr(self, "_driver") and self._driver is not None:
            try:
                self._driver.write("\x1b]22;default\x07\x1b[2 q")
            except Exception:
                pass

        # Check initial terminal size
        self._check_terminal_size()

        # Focus composer immediately (One primary action)
        composer = self.query_one("#composer-input", Composer)
        composer.focus()

        # Connect agent backend
        self._init_backend()

        # Hide toast notification initially
        try:
            toast = self.query_one("#toast-notification", Static)
            toast.styles.display = "none"
        except Exception:
            pass

        # If initial task was provided via CLI argument, dispatch it
        if self.initial_task:
            self.call_after_refresh(self._send_initial_task, self.initial_task)

    def on_unmount(self) -> None:
        """Reset terminal cursor and mouse pointer shapes upon clean exit."""
        if hasattr(self, "_driver") and self._driver is not None:
            try:
                self._driver.write("\x1b]22;default\x07\x1b[0 q")
            except Exception:
                pass

    def compose(self) -> ComposeResult:
        # Full-bleed container (spans 100% of terminal width and height, Rule L1)
        with Container(id="main-column"):
            # Floating toast notification (e.g. 'Copied' 1.2s)
            yield Static("Copied to clipboard", id="toast-notification")

            # 1. Conversation area (takes all free space, scrollable, auto-hiding scrollbar to maximize space)
            with ConversationArea(id="conversation-area"):
                yield WelcomeView(self.app_config)

            # Suggestions container (rendered directly above composer)
            yield CommandSuggestions(id="command-suggestions")

            # 2. Input composer (rounded, 3 to 8 rows, full width)
            yield Composer(id="composer-input")

            # 3. Status line (single dim line below input, full width)
            yield StatusLine(
                model_name=self.session_state.active_model,
                hint_text="? for help",
            )

        # Terminal size warning (overlay if < 60x16)
        yield Static(
            "Please enlarge your terminal window to continue with Julius.",
            id="terminal-too-small-warning",
        )

    def on_resize(self, event: events.Resize) -> None:
        self._check_terminal_size(event.size)

    def _check_terminal_size(self, current_size: Optional[Any] = None) -> None:
        size = current_size or self.size
        width = size.width
        height = size.height
        warning = self.query_one("#terminal-too-small-warning", Static)
        main_col = self.query_one("#main-column", Container)

        if width < 60 or height < 16:
            self.terminal_too_small = True
            warning.styles.display = "block"
            main_col.styles.display = "none"
        else:
            self.terminal_too_small = False
            warning.styles.display = "none"
            main_col.styles.display = "block"
            # Rule L2: Edge padding (2 cells, or 4 cells if terminal is 160+ columns wide)
            pad = 4 if width >= 160 else 2
            self.screen.styles.padding = (0, pad, 0, pad)

    def _init_backend(self) -> None:
        """Initialize WebAgent locally or prepare remote WebSocket."""
        if not self.ws_url:
            from ..web_agent import WebAgent
            from ..agent_config import AgentConfig
            cfg = self.agent_config or AgentConfig()
            self.agent = WebAgent(cfg, keep_browser_open=True, on_event=self.event_bridge.handle_event)
        else:
            # Connect to remote WebSocket in background worker
            self.run_worker(self._connect_websocket_worker, exclusive=True)

    async def _connect_websocket_worker(self) -> None:
        """Connect to remote Julius WebSocket server."""
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(self.ws_url) as ws:
                    self._ws = ws
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            import json
                            try:
                                data = json.loads(msg.data)
                                self.event_bridge.handle_event(data)
                            except Exception:
                                pass
        except Exception as exc:
            self.event_bridge.handle_event({"type": "error", "message": f"Connection error: {exc}"})

    # ── Composer Submissions & Actions ──────────────────────────────────────

    def on_composer_user_typing(self, event: Composer.UserTyping) -> None:
        """Fade out status line while user types."""
        if self._status_line_widget is None:
            try:
                self._status_line_widget = self.query_one("#status-line", StatusLine)
            except Exception:
                return
        self._status_line_widget.on_user_typing()

    def on_composer_submitted(self, event: Composer.Submitted) -> None:
        """Handle prompt submission from Composer."""
        prompt = event.text.strip()
        if not prompt:
            return

        # Check if agent is awaiting confirmation (e.g. y/n for outside workspace access)
        if self.is_awaiting_confirmation:
            if prompt.startswith("/"):
                cmd_lower = prompt.split()[0].lower()
                if cmd_lower in ("/cancel", "/abort"):
                    self.handle_confirmation_choice(False)
                    return
                elif cmd_lower in ("/help", "/?"):
                    self.action_open_help()
                    return
                elif cmd_lower in ("/exit", "/quit"):
                    self.handle_confirmation_choice(False)
                    self.exit()
                    return

            is_yes = prompt.lower() in ("y", "yes", "a", "allow", "ok", "true")
            self.handle_confirmation_choice(is_yes)
            return

        # Check if agent is awaiting question answer
        if self.agent and getattr(self.agent, "_question_future", None) and not self.agent._question_future.done():
            if prompt.startswith("/"):
                cmd_lower = prompt.split()[0].lower()
                if cmd_lower in ("/cancel", "/abort"):
                    self.agent.set_question_result("User cancelled.")
                    return
                elif cmd_lower in ("/help", "/?"):
                    self.action_open_help()
                    return
                elif cmd_lower in ("/exit", "/quit"):
                    self.agent.set_question_result("User cancelled.")
                    self.exit()
                    return

            conv_area = self.query_one("#conversation-area", ScrollableContainer)
            user_msg = UserMessage(prompt)
            conv_area.mount(user_msg)
            if not self.active_thinking_dot:
                self.active_thinking_dot = ThinkingDot("Thinking")
                conv_area.mount(self.active_thinking_dot)
            conv_area.scroll_end(animate=False)
            self.agent.set_question_result(prompt)
            return

        # Transition welcome view to scrolling top header on first conversation turn
        self._conversation_started = True
        try:
            welcome = self.query_one("#welcome-view", WelcomeView)
            welcome.add_class("scrolled-header")
            welcome.styles.height = "auto"
        except Exception:
            pass

        # Check for client slash commands
        if prompt.startswith("/"):
            self._handle_slash_command(prompt)
            return

        self._dispatch_user_prompt(prompt)

    def _dispatch_user_prompt(self, prompt: str) -> None:
        """Mount UserMessage, ThinkingDot, and trigger agent task."""
        conv_area = self.query_one("#conversation-area", ScrollableContainer)

        # Ensure welcome view is transitioned to scrolling top header
        self._conversation_started = True
        try:
            welcome = self.query_one("#welcome-view", WelcomeView)
            welcome.add_class("scrolled-header")
            welcome.styles.height = "auto"
        except Exception:
            pass

        # Stop and remove any prior active thinking indicator
        if self.active_thinking_dot:
            try:
                self.active_thinking_dot.stop()
                self.active_thinking_dot.remove()
            except Exception:
                pass
            self.active_thinking_dot = None

        self.active_assistant_msg = None
        self._current_tool_summary = None
        self._in_think_block = False
        # 0. Track turn start time for accurate duration display
        self._turn_start_time = time.time()
        self._accumulated_thought = ""
        self._in_action_json_stream = False
        self._accumulated_stream = ""

        # 1. Mount user message and record in history
        self.session_state.history.append(("user", prompt))
        user_msg = UserMessage(prompt)
        conv_area.mount(user_msg)

        # 2. Reset event bridge turn state
        self.event_bridge.start_turn()

        # 3. Mount thinking dot
        self.active_thinking_dot = ThinkingDot("Thinking")
        conv_area.mount(self.active_thinking_dot)

        # Scroll to bottom smoothly
        conv_area.scroll_end(animate=False)

        # Run task in background worker
        self.run_worker(self._run_agent_task_worker(prompt), exclusive=True)

    async def _run_agent_task_worker(self, prompt: str) -> None:
        """Execute task prompt on agent backend without blocking UI event loop."""
        if self._ws and not self._ws.closed:
            await self._ws.send_json({"type": "task", "prompt": prompt})
        elif self.agent:
            try:
                await self.agent.run(prompt)
            except asyncio.CancelledError:
                logger.info("Previous agent task worker was superseded or cancelled.")
            except Exception as exc:
                if not self.event_bridge._has_finalized_turn:
                    self.event_bridge.handle_event({"type": "error", "message": str(exc)})

    def _send_initial_task(self, task: str) -> None:
        """Execute initial task passed via CLI args."""
        self._dispatch_user_prompt(task)

    # ── Bridge Message Handler ──────────────────────────────────────────────

    def _handle_bridge_message(self, msg: Dict[str, Any]) -> None:
        """Process messages dispatched from EventBridge."""
        kind = msg.get("kind")
        conv_area = self.query_one("#conversation-area", ScrollableContainer)

        if kind == "thought":
            thought = msg.get("thought", "").strip()
            if thought and self.active_thinking_dot:
                clean_th = self.active_thinking_dot._sanitize_thought(thought)
                if clean_th:
                    summary = ThinkingDot.format_summary(clean_th)
                    self.active_thinking_dot.append_thought(clean_th)
                    self.active_thinking_dot.update_label(summary, full_thought=clean_th)

        elif kind == "action_scheduled":
            # If an intermediate streamed message exists, remove it immediately
            if self.active_assistant_msg:
                try:
                    self.active_assistant_msg.remove()
                except Exception:
                    pass
                self.active_assistant_msg = None
            self._smart_scroll_to_end(conv_area, force=False)

        elif kind == "stream_chunk":
            chunk = msg.get("chunk", "")
            trimmed = chunk.strip()
            self._accumulated_stream += chunk

            # Check if this chunk or ongoing stream indicates an internal JSON action
            if not self._in_action_json_stream:
                if (
                    is_json_or_protocol(trimmed)
                    or is_json_or_protocol(chunk)
                    or is_json_or_protocol(self._accumulated_stream)
                    or trimmed.startswith(('```', '{', 'json'))
                ):
                    self._in_action_json_stream = True

            # If inside an action JSON stream or chunk is JSON: extract thought for thinking dot and suppress from chat!
            if self._in_action_json_stream or is_json_or_protocol(chunk):
                self._in_action_json_stream = True
                if self.active_assistant_msg:
                    try:
                        self.active_assistant_msg.remove()
                    except Exception:
                        pass
                    self.active_assistant_msg = None

                m = re.search(r'"thought"\s*:\s*"((?:[^"\\]|\\.)*)', self._accumulated_stream)
                if m and self.active_thinking_dot:
                    raw_th = m.group(1).replace('\\"', '"').replace('\\n', '\n').strip()
                    clean_th = self.active_thinking_dot._sanitize_thought(raw_th)
                    if clean_th:
                        summary = ThinkingDot.format_summary(clean_th)
                        self.active_thinking_dot.append_thought(clean_th)
                        self.active_thinking_dot.update_label(summary, full_thought=clean_th)
                # Suppress JSON action from ever streaming into assistant chat!
                return

            # If not yet identified as JSON, buffer small leading tokens to prevent flashing fragments
            if len(self._accumulated_stream.strip()) < 20 and "\n" not in self._accumulated_stream:
                if self._accumulated_stream.strip().startswith(('`', '{', 'json')):
                    return

            # Handle DeepSeek / R1 <think> tags in streaming chunks
            non_think_text = ""
            current_chunk = chunk
            while current_chunk:
                if self._in_think_block:
                    if "</think>" in current_chunk:
                        th_part, _, after = current_chunk.partition("</think>")
                        self._accumulated_thought += th_part
                        if self.active_thinking_dot:
                            clean_th = self.active_thinking_dot._sanitize_thought(self._accumulated_thought)
                            if clean_th:
                                summary = ThinkingDot.format_summary(clean_th)
                                self.active_thinking_dot.append_thought(clean_th)
                                self.active_thinking_dot.update_label(summary, full_thought=clean_th)
                                self.active_thinking_dot.finish()
                        self._in_think_block = False
                        current_chunk = after
                    else:
                        self._accumulated_thought += current_chunk
                        if self.active_thinking_dot:
                            clean_th = self.active_thinking_dot._sanitize_thought(self._accumulated_thought)
                            if clean_th:
                                summary = ThinkingDot.format_summary(clean_th)
                                self.active_thinking_dot.append_thought(clean_th)
                                self.active_thinking_dot.update_label(summary, full_thought=clean_th)
                        current_chunk = ""
                else:
                    if "<think>" in current_chunk:
                        before, _, th_part = current_chunk.partition("<think>")
                        non_think_text += before
                        self._in_think_block = True
                        current_chunk = th_part
                    else:
                        non_think_text += current_chunk
                        current_chunk = ""

            if not non_think_text or is_json_or_protocol(non_think_text):
                return

            clean_text = non_think_text.replace('\\n', '\n')
            if not clean_text.strip() and not self.active_assistant_msg:
                return
            if re.fullmatch(r'(?:\\[nrt]|[\s])+', clean_text) and not self.active_assistant_msg:
                return

            if not self.active_assistant_msg:
                self.active_assistant_msg = AssistantMessage(
                    "",
                    theme=self.active_theme,
                    max_content_width=self.app_config.max_content_width,
                )
                conv_area.mount(self.active_assistant_msg)

            self.active_assistant_msg.append_chunk(clean_text)
            self._smart_scroll_to_end(conv_area, force=False)

        elif kind in ("done", "converse"):
            final_text = msg.get("summary") or msg.get("message") or ""
            tools = msg.get("tools", [])
            turn_dur = msg.get("duration_s") or max(0.1, time.time() - getattr(self, "_turn_start_time", time.time()))
            self._in_action_json_stream = False

            if not final_text and self.active_assistant_msg:
                candidate = self.active_assistant_msg.content
                if not is_json_or_protocol(candidate):
                    final_text = candidate

            # Extract any thinking blocks from final_text if present
            think_match = re.search(r'<think>(.*?)</think>', final_text, flags=re.DOTALL)
            if think_match:
                extracted_thought = think_match.group(1).strip()
                if self.active_thinking_dot and not self._accumulated_thought:
                    summary = ThinkingDot.format_summary(extracted_thought)
                    self.active_thinking_dot.append_thought(extracted_thought)
                    self.active_thinking_dot.update_label(summary, full_thought=extracted_thought)

            # Clean think tags and unwanted thinking process leakages from final_text
            final_text = re.sub(r'<think>.*?</think>', '', final_text, flags=re.DOTALL)
            final_text = re.sub(r'<thought>.*?</thought>', '', final_text, flags=re.DOTALL)
            final_text = re.sub(r'<reasoning>.*?</reasoning>', '', final_text, flags=re.DOTALL)
            final_text = re.sub(r'^(?:Thinking Process|Thought):\s*.*?(?=\n\n(?:```|{)|[A-Z]|\Z)', '', final_text, flags=re.DOTALL | re.IGNORECASE)
            final_text = final_text.strip()

            # Thinking indicator: stop and remove when turn completes
            if self.active_thinking_dot:
                self.active_thinking_dot.stop()
                try:
                    self.active_thinking_dot.remove()
                except Exception:
                    pass
                self.active_thinking_dot = None

            # Reset running status in bottom-left
            self._update_bridge_status("")

            # Mount quiet collapsible ToolSummary with real elapsed turn duration if tools were executed
            # Always ensure ToolSummary appears ABOVE the assistant response message
            if tools:
                tool_summary = ToolSummary(tools, total_duration_s=turn_dur)
                self._current_tool_summary = tool_summary
                if self.active_assistant_msg and self.active_assistant_msg in conv_area.children:
                    conv_area.mount(tool_summary, before=self.active_assistant_msg)
                else:
                    conv_area.mount(tool_summary)

            # Finalize or mount assistant message(s) and CommandBoxes
            self._sweep_leaked_json_messages(conv_area)

            if final_text and not is_json_or_protocol(final_text):
                if self.active_assistant_msg and not is_json_or_protocol(self.active_assistant_msg.content):
                    self.active_assistant_msg.finalize(final_text)
                    self.active_assistant_msg = None
                else:
                    self._mount_assistant_response(final_text, conv_area)
            self._smart_scroll_to_end(conv_area, force=True)

        elif kind == "error":
            err_text = msg.get("message", "Error")
            self._in_action_json_stream = False
            if self.active_thinking_dot:
                self.active_thinking_dot.expanded = False
                self.active_thinking_dot.stop()
                try:
                    self.active_thinking_dot.remove()
                except Exception:
                    pass
                self.active_thinking_dot = None

            self._sweep_leaked_json_messages(conv_area)
            self._update_bridge_status("")

            # Clean raw ASCII box-drawing characters and collapse multiple blank lines
            clean_err = re.sub(r"[┌─┐│└┘├┤┬┴┼]+", "", err_text).strip()
            clean_err = re.sub(r"\n\s*\n\s*\n", "\n\n", clean_err)

            err_msg = AssistantMessage(
                f"I ran into an issue:\n\n{clean_err}",
                theme=self.active_theme,
                max_content_width=self.app_config.max_content_width,
            )
            conv_area.mount(err_msg)
            self._smart_scroll_to_end(conv_area, force=True)

        elif kind == "ask_user_question":
            self._in_action_json_stream = False
            # Remove thinking dot while awaiting human clarification
            if self.active_thinking_dot:
                self.active_thinking_dot.expanded = False
                self.active_thinking_dot.stop()
                try:
                    self.active_thinking_dot.remove()
                except Exception:
                    pass
                self.active_thinking_dot = None

            self._sweep_leaked_json_messages(conv_area)
            self._update_bridge_status("")

            q_text = msg.get("question", "").strip()
            opts = msg.get("options", [])
            lines = [q_text]
            if opts:
                lines.append("")
                for opt in opts:
                    lines.append(f"- {opt}")
            formatted_text = "\n".join(lines)

            q_msg = AssistantMessage(
                formatted_text,
                theme=self.active_theme,
                max_content_width=self.app_config.max_content_width,
            )
            conv_area.mount(q_msg)
            self._smart_scroll_to_end(conv_area, force=True)

        elif kind == "confirm_action":
            self._awaiting_confirmation = True
            self._in_action_json_stream = False

            # Pause thinking dot while awaiting human confirmation (DO NOT destroy it)
            if self.active_thinking_dot:
                self.active_thinking_dot.update_label("Awaiting user confirmation…")

            # Clean up active assistant message and sweep conv_area so no leaked JSON/thought is visible
            if self.active_assistant_msg:
                try:
                    self.active_assistant_msg.remove()
                except Exception:
                    pass
                self.active_assistant_msg = None

            self._sweep_leaked_json_messages(conv_area)

            try:
                status_line = self.query_one("#status-line", StatusLine)
                status_line.update_running("")
            except Exception:
                pass

            act = msg.get("action", "")
            args = msg.get("args", {})
            if args.get("_outside_workspace"):
                raw_prompt = args.get(
                    "_permission_prompt",
                    f"Action `{act}` requested access outside the workspace folder.\n\nAllow un-sandboxed access across your Mac? (y/n)"
                )
            else:
                arg_lines = []
                for k, v in args.items():
                    if not str(k).startswith("_"):
                        arg_lines.append(f"{k}: {v}")
                details_str = f" ({', '.join(arg_lines)[:60]})" if arg_lines else ""
                raw_prompt = f"Allow action `{act}`{details_str}? (y/n)"

            # Clean raw prompt text (strip trailing y/n indicators so it is presented cleanly)
            clean_prompt_text = raw_prompt.replace("(y/n)", "").replace("(yes/no)", "").strip()

            # Compose confirmation renderable with centered (y) Yes / (n) No choices
            table = Table.grid(padding=0, expand=True)
            table.add_column(width=2, justify="left", vertical="top", overflow="fold", no_wrap=True)
            if self.app_config.max_content_width and self.app_config.max_content_width > 0:
                table.add_column(width=self.app_config.max_content_width, justify="left", overflow="fold", no_wrap=False)
            else:
                table.add_column(justify="left", overflow="fold", no_wrap=False)

            glyph = Text("◦ ", style="dim")

            body = Table.grid(padding=0, expand=True)
            body.add_column(justify="left", overflow="fold", no_wrap=False)
            body.add_row(render_julius_markdown(clean_prompt_text, self.active_theme))
            body.add_row(Text(""))
            body.add_row(
                Text.from_markup(
                    "[bold #22c55e](y) Yes[/bold #22c55e]       [dim]/[/dim]       [bold #ef4444](n) No[/bold #ef4444]",
                    justify="center",
                )
            )

            table.add_row(glyph, body)

            c_msg = AssistantMessage(
                clean_prompt_text,
                theme=self.active_theme,
                max_content_width=self.app_config.max_content_width,
                renderable=table,
            )
            c_msg._is_confirmation_prompt = True
            self._active_confirmation_msg = c_msg
            # Mount confirmation message UNDER the thinking panel
            conv_area.mount(c_msg)
            self._smart_scroll_to_end(conv_area, force=True)

            # Update status hint and composer placeholder to guide single-key Y/N
            try:
                status_line = self.query_one("#status-line", StatusLine)
                status_line.update_hint("[bold #22c55e]Y Allow[/bold #22c55e] • [bold #ef4444]N Decline[/bold #ef4444]")
            except Exception:
                pass
            try:
                composer = self.query_one("#composer-input", Composer)
                composer.placeholder = "Press Y to allow, N to decline"
            except Exception:
                pass

    def _update_bridge_status(self, status: str) -> None:
        """Update status line running indicator (bottom-left) and hint (bottom-right)."""
        try:
            status_line = self.query_one("#status-line", StatusLine)
            if status and status != "? for help" and "Y Allow" not in status and "Decline" not in status:
                status_line.update_running(status)
            else:
                status_line.update_running("")
                if status:
                    status_line.update_hint(status)
                else:
                    status_line.update_hint("? for help")
        except Exception:
            pass

    # ── Slash Commands & Modals ─────────────────────────────────────────────

    def _handle_slash_command(self, cmd_line: str) -> None:
        """Process local slash commands using canonical commands lookup."""
        parts = cmd_line.split(maxsplit=1)
        raw_cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        cmd_def = COMMAND_LOOKUP.get(raw_cmd)
        handler_id = cmd_def.handler_id if cmd_def else ""

        if handler_id == "help":
            self.action_open_help()
        elif handler_id == "model":
            if arg:
                self._switch_model(arg.strip())
            else:
                self.action_open_model_picker()
        elif handler_id == "theme":
            self._cycle_theme(arg.strip())
        elif handler_id == "diff":
            self.action_open_diff_review()
        elif handler_id == "action":
            self.action_open_active_action_modal()
        elif handler_id == "copy":
            self.action_copy_last_answer()
        elif handler_id == "clear":
            self._reset_conversation()
        elif handler_id == "quit":
            self.exit()
        elif handler_id == "doctor":
            self._handle_doctor_command()
        elif handler_id == "context":
            self._handle_context_command()
        elif handler_id == "cost":
            self._handle_cost_command()
        elif handler_id == "compact":
            self._handle_compact_command()
        elif handler_id == "undo":
            self._handle_undo_command()
        elif handler_id == "review":
            self._handle_review_command()
        elif handler_id == "heal":
            self._handle_heal_command()
        elif handler_id == "init":
            self._handle_init_command()
        elif handler_id in ("plan", "act"):
            self._dispatch_user_prompt(cmd_line)
        else:
            # Pass unhandled slash command to backend agent
            self._dispatch_user_prompt(cmd_line)

    def _handle_doctor_command(self) -> None:
        """Run health check diagnostics on python, git, workspace, and model."""
        import sys
        import shutil
        git_status = "Available" if shutil.which("git") else "Not found"
        node_status = "Available" if shutil.which("node") else "Not found"
        python_ver = sys.version.split()[0]
        report = f"""### 🩺 Julius Doctor Diagnostic Report
- **Python Runtime**: `{python_ver}` ({'virtualenv active' if sys.prefix != sys.base_prefix else 'system'})
- **Workspace Root**: `{self.workspace_dir}`
- **Active Model**: `{self.session_state.active_model}`
- **Git Binary**: `{git_status}`
- **Node.js**: `{node_status}`
- **Stateful Shell**: `PTY Terminal Engine Active`
- **Context Telemetry**: `{self.session_state.token_count} tokens tracked across {len(self.session_state.history)} turns`
- **System Health**: `All subsystems operational`"""
        conv = self.query_one("#conversation-area", ScrollableContainer)
        msg = AssistantMessage(report, theme=self.active_theme, max_content_width=self.app_config.max_content_width)
        conv.mount(msg)
        conv.scroll_end(animate=False)

    def _handle_context_command(self) -> None:
        """Display loaded workspace context, memory, and token telemetry."""
        mod_count = len(self.session_state.modified_files)
        mod_list = "\n".join(f"  - `{p}`" for p in self.session_state.modified_files[:5]) if mod_count else "  *(None)*"
        if mod_count > 5:
            mod_list += f"\n  - *...and {mod_count - 5} more*"
        elapsed = int(time.time() - self.session_state.start_time)
        uptime_str = f"{elapsed // 60}m {elapsed % 60}s" if elapsed >= 60 else f"{elapsed}s"
        report = f"""### 🧠 Workspace Context Telemetry
- **Active Reasoning Model**: `{self.session_state.active_model}`
- **Token Usage**: `{self.session_state.token_count:,} tokens`
- **Conversation Turns**: `{len(self.session_state.history)}`
- **Session Uptime**: `{uptime_str}`
- **Modified Workspace Files ({mod_count})**:
{mod_list}"""
        conv = self.query_one("#conversation-area", ScrollableContainer)
        msg = AssistantMessage(report, theme=self.active_theme, max_content_width=self.app_config.max_content_width)
        conv.mount(msg)
        conv.scroll_end(animate=False)

    def _handle_cost_command(self) -> None:
        """Show session token usage and estimated cost breakdown."""
        tokens = self.session_state.token_count
        elapsed = int(time.time() - self.session_state.start_time)
        uptime_str = f"{elapsed // 60}m {elapsed % 60}s" if elapsed >= 60 else f"{elapsed}s"
        report = f"""### 📊 Session Telemetry & Cost
- **Total Session Tokens**: `{tokens:,}`
- **Elapsed Time**: `{uptime_str}`
- **Active Engine**: `{self.session_state.active_model}`
- **Estimated API Cost**: `$0.00` *(Included in subscription / local provider)*"""
        conv = self.query_one("#conversation-area", ScrollableContainer)
        msg = AssistantMessage(report, theme=self.active_theme, max_content_width=self.app_config.max_content_width)
        conv.mount(msg)
        conv.scroll_end(animate=False)

    def _handle_compact_command(self) -> None:
        """Compress conversation history to reclaim context window headroom.
        
        Ensures the retained conversation slice begins cleanly on a user turn.
        """
        hist = self.session_state.history
        if len(hist) > 2:
            # Find indices of all user turns
            user_indices = [i for i, (role, _) in enumerate(hist) if role == "user"]
            if len(user_indices) >= 2:
                # Keep from the 2nd to last user turn to retain full recent context
                cutoff = user_indices[-2]
                self.session_state.history = hist[cutoff:]
            elif user_indices:
                cutoff = user_indices[-1]
                self.session_state.history = hist[cutoff:]
            else:
                self.session_state.history = []

        self._show_toast("Context window compacted")
        conv = self.query_one("#conversation-area", ScrollableContainer)
        msg = AssistantMessage("### 🗜️ Context Compacted\nConversation history compressed. Reclaimed context headroom for subsequent turns.", theme=self.active_theme, max_content_width=self.app_config.max_content_width)
        conv.mount(msg)
        conv.scroll_end(animate=False)

    def _handle_undo_command(self) -> None:
        """Rollback last file mutation from workspace ledger and restore filesystem state."""
        res = self.session_state.rollback_last_modification()
        if res:
            path, action_desc = res
            p_name = Path(path).name
            self._show_toast(f"Reverted {p_name}")
            conv = self.query_one("#conversation-area", ScrollableContainer)
            msg = AssistantMessage(
                f"### ↩️ Reverted Mutation\nRolled back `{path}` ({action_desc}).",
                theme=self.active_theme,
                max_content_width=self.app_config.max_content_width,
            )
            conv.mount(msg)
            conv.scroll_end(animate=False)
        else:
            self._show_toast("No file mutations to undo")

    def _handle_review_command(self) -> None:
        """Run git status and diff before dispatching review prompt."""
        import subprocess
        git_context = ""
        try:
            status_proc = subprocess.run(
                ["git", "status", "--short"],
                cwd=self.workspace_dir,
                capture_output=True,
                text=True,
                timeout=3,
            )
            diff_proc = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=self.workspace_dir,
                capture_output=True,
                text=True,
                timeout=3,
            )
            s_out = status_proc.stdout.strip()
            d_out = diff_proc.stdout.strip()
            if s_out or d_out:
                git_context = f"\n\nCurrent workspace changes:\n```\n{s_out}\n\n{d_out}\n```"
            else:
                git_context = "\n\n(Working tree clean: no unstaged changes detected. Review recent commits.)"
        except Exception:
            pass

        prompt = f"Please review recent code changes and unstaged git deltas. Highlight bugs, security issues, performance bottlenecks, and edge cases.{git_context}"
        self._dispatch_user_prompt(prompt)

    def _handle_heal_command(self) -> None:
        """Ground heal command with current unstaged changes, active job awareness, and diagnostics."""
        import subprocess
        git_context = ""
        try:
            status_proc = subprocess.run(
                ["git", "status", "--short"],
                cwd=self.workspace_dir,
                capture_output=True,
                text=True,
                timeout=3,
            )
            s_out = status_proc.stdout.strip()
            if s_out:
                git_context = f"\n\nModified workspace files:\n```\n{s_out}\n```"
        except Exception:
            pass

        running_note = ""
        try:
            active = self.executor.get_active_action_details()
            if active.get("is_running"):
                cmd = active.get("command", "active process")
                running_note = (
                    f"\n\nNote: A task is currently running (`{cmd}`). Do not kill or terminate it. "
                    f"Ask the user: 'I am running on `{cmd}`. May I go ahead and make a small clone, fix that, and merge it back?' "
                    "or fix without terminating the running job."
                )
        except Exception:
            pass

        prompt = f"Run diagnostic checks on the workspace, inspect recent errors or failing tests, and fix them automatically.{git_context}{running_note}"
        self._dispatch_user_prompt(prompt)

    def _handle_init_command(self) -> None:
        """Analyze codebase and initialize project architecture guide."""
        self._dispatch_user_prompt(
            "Analyze this codebase architecture, identify core tech stacks and entry points, and initialize project guidelines."
        )

    def action_copy_last_answer(self) -> None:
        """Copy last assistant answer to system clipboard with 1.2s toast."""
        text = self.session_state.last_assistant_answer
        if not text:
            self._show_toast("Nothing to copy yet")
            return

        success = copy_to_clipboard(text)
        if success:
            self._show_toast("Copied to clipboard")
        else:
            self._show_toast("Failed to access clipboard")

    def _sweep_leaked_json_messages(self, conv_area: ScrollableContainer) -> None:
        """Defense-in-depth: remove any AssistantMessage in conversation area containing leaked JSON action protocol, escaped newlines, or empty content."""
        def _is_empty_or_bogus(val: str) -> bool:
            if not val or not val.strip():
                return True
            if is_json_or_protocol(val):
                return True
            if re.fullmatch(r'(?:\\[nrt]|[\s])+', val.strip()):
                return True
            return False

        if self.active_assistant_msg:
            c = getattr(self.active_assistant_msg, "content", "")
            if _is_empty_or_bogus(c):
                try:
                    self.active_assistant_msg.remove()
                except Exception:
                    pass
                self.active_assistant_msg = None

        for child in list(conv_area.children):
            if isinstance(child, AssistantMessage):
                c = getattr(child, "content", "")
                if _is_empty_or_bogus(c):
                    try:
                        child.remove()
                    except Exception:
                        pass

    def _mount_assistant_response(self, text: str, conv_area: ScrollableContainer) -> None:
        """Mount assistant response with unified Julius markdown rendering."""
        clean = text.strip()
        # Clean any leaked think tags or reasoning headers before rendering
        clean = re.sub(r'<think>.*?</think>', '', clean, flags=re.DOTALL)
        clean = re.sub(r'<thought>.*?</thought>', '', clean, flags=re.DOTALL)
        clean = re.sub(r'<reasoning>.*?</reasoning>', '', clean, flags=re.DOTALL)
        clean = re.sub(r'^(?:Thinking Process|Thought):\s*.*?(?=\n\n(?:```|{)|[A-Z]|\Z)', '', clean, flags=re.DOTALL | re.IGNORECASE)
        clean = clean.strip()
        if not clean or is_json_or_protocol(clean):
            return

        msg = AssistantMessage(
            clean,
            theme=self.active_theme,
            max_content_width=self.app_config.max_content_width,
        )
        conv_area.mount(msg)

    def action_open_resource(self, target: str) -> None:
        """Action handler to open URL in browser or file in default OS application."""
        self.open_resource(target)

    def open_resource(self, target: str) -> bool:
        """Open a file, folder, or URL across macOS, Linux, and Windows."""
        import webbrowser
        from src.platform_compat import open_in_default_app

        t = target.strip()
        if not t:
            return False

        # 1. URL
        if t.startswith("http://") or t.startswith("https://"):
            try:
                webbrowser.open(t)
                self._show_toast(f"Opened link: {t[:35]}…")
                return True
            except Exception as e:
                self._show_toast(f"Failed to open link: {e}")
                return False

        # 2. File / Directory Path
        if t.startswith("file://"):
            t = t[7:]

        p = Path(os.path.expanduser(t))
        resolved_file = None

        if p.is_file():
            resolved_file = p
        elif (Path(self.workspace_dir) / p).is_file():
            resolved_file = Path(self.workspace_dir) / p
        elif (Path.home() / "Desktop" / p.name).is_file():
            resolved_file = Path.home() / "Desktop" / p.name
        elif (Path.home() / "Downloads" / p.name).is_file():
            resolved_file = Path.home() / "Downloads" / p.name

        if resolved_file:
            success = open_in_default_app(resolved_file)
            if success:
                self._show_toast(f"Opened: {resolved_file.name}")
                return True
            else:
                self._show_toast(f"Could not open: {resolved_file.name}")
                return False

        # If not a file, check directories
        if p.is_dir():
            open_in_default_app(p)
            self._show_toast(f"Opened folder: {p.name}")
            return True

        # Fallback to Desktop or containing folder
        desktop_dir = Path.home() / "Desktop"
        if desktop_dir.is_dir():
            open_in_default_app(desktop_dir)
            self._show_toast("Opened Desktop folder")
            return True
        elif p.parent.exists():
            open_in_default_app(p.parent)
            self._show_toast(f"Opened folder: {p.parent.name}")
            return True

        self._show_toast(f"File not found: {p.name}")
        return False

    def _show_toast(self, message: str) -> None:
        """Display brief inline toast notification that fades after 1.2s."""
        try:
            toast = self.query_one("#toast-notification", Static)
            toast.update(message)
            toast.styles.display = "block"
            self.set_timer(1.2, lambda: setattr(toast.styles, "display", "none"))
        except Exception:
            pass

    def action_toggle_tools(self) -> None:
        """Toggle collapsed/expanded state of latest tool execution summary."""
        if self._current_tool_summary:
            self._current_tool_summary.toggle()

    def action_open_model_picker(self) -> None:
        """Open model switcher modal."""
        def on_model_select(model_id: Optional[str]) -> None:
            if model_id:
                self._switch_model(model_id)

        self.push_screen(ModelPickerModal(current_model=self.session_state.active_model), on_model_select)

    def action_open_help(self) -> None:
        """Open keyboard shortcuts reference modal."""
        self.push_screen(HelpModal())

    def action_open_diff_review(self) -> None:
        """Open workspace file diff review modal."""
        self.push_screen(DiffReviewModal(modified_files=self.session_state.modified_files))

    def action_open_active_action_modal(self) -> None:
        """Open in-flight action inspector and control modal."""
        self.push_screen(ActiveActionModal())

    def action_toggle_thinking(self) -> None:
        """Toggle expansion of active thinking dot reasoning and checklist."""
        if self.active_thinking_dot:
            self.active_thinking_dot.expanded = not self.active_thinking_dot.expanded

    def get_active_action_info(self) -> Dict[str, Any]:
        """Fetch active command and telemetry for the inspector modal."""
        if self.agent and hasattr(self.agent, "get_active_action_details"):
            try:
                info = self.agent.get_active_action_details()
                if info.get("is_running") or info.get("command"):
                    return info
            except Exception:
                pass

        if hasattr(self, "event_bridge"):
            eb = self.event_bridge
            active_tool = getattr(eb, "_active_tool_name", "")
            if active_tool:
                args = getattr(eb, "_active_tool_args", {})
                start_time = getattr(eb, "_active_tool_start_time", 0.0)
                cmd = args.get("command", "") if active_tool == "run_bash" else str(args)
                elapsed = max(0.0, time.time() - start_time) if start_time > 0 else 0.0
                partial = ""
                if self.agent and hasattr(self.agent, "executor"):
                    shell = getattr(self.agent.executor, "_shell", None)
                    if shell and hasattr(shell, "partial_output"):
                        partial = shell.partial_output
                return {
                    "is_running": True,
                    "action": active_tool,
                    "command": cmd,
                    "elapsed": elapsed,
                    "output": partial,
                }
            if eb.state and eb.state.current_turn_tools:
                last_tool = eb.state.current_turn_tools[-1]
                return {
                    "is_running": False,
                    "action": last_tool.tool_name,
                    "command": last_tool.command or str(last_tool.args),
                    "elapsed": last_tool.duration_s,
                    "output": last_tool.output,
                }

        return {"is_running": False}

    def cancel_active_action(self) -> bool:
        """Cancel current in-flight action / bash command."""
        cancelled = False
        if self.agent and hasattr(self.agent, "cancel_active_action"):
            try:
                cancelled = self.agent.cancel_active_action()
            except Exception:
                pass

        if not cancelled and self._ws and not self._ws.closed:
            try:
                asyncio.create_task(self._ws.send_json({"type": "cancel_action"}))
                cancelled = True
            except Exception:
                pass

        if hasattr(self, "event_bridge"):
            self.event_bridge._active_tool_name = ""
            self.event_bridge.update_status("Action cancelled")

        return cancelled

    def action_handle_escape(self) -> None:
        """Handle Esc key: dismiss any modal or cancel active task."""
        if len(self.screen_stack) > 1:
            self.pop_screen()

    def _switch_model(self, model_id: str) -> None:
        """Update active model in session and config."""
        target = model_id.strip()
        self.session_state.active_model = target
        if self.agent and hasattr(self.agent, "config"):
            self.agent.config.provider = target
        self.app_config.model = target
        save_config(self.app_config)

        # Reset active LLM client session so the newly chosen engine connects cleanly
        if self.agent and hasattr(self.agent, "client") and self.agent.client:
            if target.lower() in ("lexi", "qwen", "llama70b") or any(k in target.lower() for k in ("lexi", "qwen")):
                self.agent.client._ollama_model = target
            if hasattr(self.agent.client, "close"):
                import asyncio
                try:
                    asyncio.create_task(self.agent.client.close())
                except Exception:
                    pass

        # Sync with WebSocket server if running connected to backend
        if self._ws and not self._ws.closed:
            import asyncio
            try:
                asyncio.create_task(self._ws.send_json({"type": "set_model", "model": target}))
            except Exception:
                pass

        status_line = self.query_one("#status-line", StatusLine)
        status_line.update_model(target)
        self._show_toast(f"Model switched to {target}")

    def _cycle_theme(self, target_theme: str = "") -> None:
        """Toggle or switch theme (auto -> dark -> light)."""
        if not target_theme:
            current = self.active_theme.name
            target = "light" if current == "dark" else "dark"
        else:
            target = target_theme

        self.active_theme = get_theme(target)
        self.app_config.theme = target
        save_config(self.app_config)

        # Apply new theme styles
        self.screen.styles.background = self.active_theme.bg
        self.stylesheet.add_source(generate_tcss(self.active_theme))
        self.refresh_css(animate=False)
        self._show_toast(f"Theme set to {target}")

    def _reset_conversation(self) -> None:
        """Reset conversation area to clean empty state and refresh browser session."""
        import asyncio
        conv_area = self.query_one("#conversation-area", ScrollableContainer)
        # Clear child message widgets
        for child in list(conv_area.children):
            if child.id != "welcome-view":
                child.remove()

        self._conversation_started = False
        self.session_state.history.clear()
        try:
            welcome = self.query_one("#welcome-view", WelcomeView)
            welcome.remove_class("scrolled-header")
            welcome.styles.height = "100%"
            welcome.styles.display = "block"
        except Exception:
            pass

        # Close existing DeepSeek / Web LLM webpage and open a fresh session
        if self.agent and hasattr(self.agent, "client") and self.agent.client:
            async def _reopen_fresh_web_session() -> None:
                try:
                    if self.agent.client.is_initialized:
                        logger.info("Closing DeepSeek / Web LLM browser session on /clear...")
                        await self.agent.client.close()
                        req_prov = getattr(self.agent.config, "provider", self.session_state.active_model)
                        if req_prov and req_prov.lower() in ("nvidia", "nvidia-nim", "nemotron", "nemotron-550b", "deepseek", "chatgpt", "gemini", "grok", "perplexity", "claude", "kimi", "aifreeforever", "aifree", "deepseek-v4-flash"):
                            await self.agent.client.initialize(
                                provider_name=req_prov,
                                profile_dir=getattr(self.agent.config, "profile_dir", None),
                                headless=getattr(self.agent.config, "headless", False),
                            )
                except Exception as exc:
                    logger.debug(f"Error resetting web session on /clear: {exc}")

            asyncio.create_task(_reopen_fresh_web_session())

        self._show_toast("Started fresh chat session")


# ── Backward-Compatibility Exports for test_tui_richlog_regression.py ─────────

class StreamPanel(RichLog):
    """Backward compatibility RichLog panel tested in test_tui_richlog_regression.py."""

    DEFAULT_CSS = """
    StreamPanel {
        height: 1fr;
        width: 1fr;
        overflow-y: auto;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._stream_buffer: str = ""
        self._last_stream_raw: str = ""

    def _flush_stream_buffer(self) -> None:
        """Flush any accumulated streaming text to the log."""
        if self._stream_buffer:
            text = self._stream_buffer
            self._stream_buffer = ""
            self._last_stream_raw = ""
            if text.strip() and not text.strip().startswith(('{', '```json', 'JSON')):
                self.write(text, scroll_end=True)

    def add_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Process an incoming event without passing unsupported kwargs like 'end' to RichLog.write."""
        if event_type not in ('stream', 'stream_end'):
            self._flush_stream_buffer()

        if event_type == 'step_start':
            step = data.get('step', '?')
            self.write(f'━━ Step {step} ━━', scroll_end=True)
        elif event_type == 'thought':
            t = data.get('thought') or data.get('text', '')
            if t:
                self.write(f'Thought: {t}', scroll_end=True)
        elif event_type == 'action':
            name = data.get('name') or data.get('action', '')
            args = data.get('args', {})
            if name == 'run_bash':
                cmd = args.get('command', '')
                self.write(f'Bash: {cmd}', scroll_end=True)
            elif name:
                self.write(f'Tool ({name}): {args}', scroll_end=True)
        elif event_type == 'stream':
            raw_text = data.get('text', '')
            if not raw_text:
                return
            trimmed = raw_text.strip()
            if trimmed in ('JSON', '```', '```json') or trimmed.startswith(('{', '```json', 'JSON\n', 'JSON\r', '"thought"', '"action"')):
                self._last_stream_raw = raw_text
                return

            if self._last_stream_raw and raw_text.startswith(self._last_stream_raw):
                delta = raw_text[len(self._last_stream_raw):]
            else:
                delta = raw_text
            self._last_stream_raw = raw_text

            if delta:
                if delta.strip().startswith(('{', '```', 'JSON', '"thought"')):
                    return
                self._stream_buffer += delta
                if '\n' in self._stream_buffer:
                    split_idx = self._stream_buffer.rfind('\n')
                    complete_lines = self._stream_buffer[:split_idx]
                    self._stream_buffer = self._stream_buffer[split_idx + 1:]
                    if complete_lines and not complete_lines.strip().startswith(('{', '```', 'JSON', '"thought"')):
                        self.write(complete_lines, scroll_end=True)
        elif event_type == 'stream_end':
            self._flush_stream_buffer()
        elif event_type == 'result':
            out = data.get('output') or data.get('result', '')
            self.write(f'Result: {out}', scroll_end=True)
        elif event_type in ('heal_start', 'heal_success', 'heal_failed'):
            summary = data.get('summary') or data.get('command') or ''
            self.write(f'Heal: {summary}', scroll_end=True)
        elif event_type == 'status':
            msg = data.get('message', '')
            self.write(f'Status: {msg}', scroll_end=True)
        elif event_type == 'error':
            msg = data.get('message', '')
            self.write(f'Error: {msg}', scroll_end=True)
        elif event_type == 'done':
            sum_txt = data.get('summary', '')
            self.write(f'Done: {sum_txt}', scroll_end=True)


class JuliusTUI(App):
    """Backward-compatibility alias."""
    def compose(self) -> ComposeResult:
        yield StreamPanel(id="stream-panel")
