"""
Message components: UserMessage, AssistantMessage, and ThinkingDot.

Design requirements:
- User message: Raised, rounded surface, left-aligned, subtle, not bold.
- Assistant message: No box. Plain text on base background with a small dim marker glyph '◦'
  in the left gutter (2 cells wide) on the first line only.
- Rendered markdown: Fully rendered markdown without raw markdown tokens.
- ThinkingDot: A breathing dot (slow opacity pulse 0.35 <-> 1.0, 1400 ms loop) instead of a spinner.
- Micro-interaction: Smooth enter animation (220 ms) and settle (160 ms).
"""

from __future__ import annotations

import re
from typing import Optional
from rich import box
from rich.console import RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from ..markdown import render_julius_markdown, render_apple_markdown
from ..motion import (
    MotionPresets,
    animate_enter,
    animate_settle,
    is_reduced_motion,
    stop_animations,
)
from ..theme import ThemeTokens, DARK_THEME
from ...agent_prompts import is_json_or_protocol


class UserMessage(Static):
    """User message rendered on a subtle raised rounded card, left-aligned, not bold."""

    DEFAULT_CSS = """
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
        border: round #3e3e42;
        text-style: none;
    }
    """

    def __init__(self, content: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.raw_content = content

    def on_mount(self) -> None:
        self.styles.opacity = 1.0
        self.update(Text(self.raw_content.strip()))
        animate_enter(self)


class AssistantMessage(Static):
    """
    Assistant message rendered directly on base background.
    Features a 2-cell gutter with dim '◦' marker on the first line only.
    Renders clean markdown with emoji stripped from headings.
    """

    DEFAULT_CSS = """
    AssistantMessage {
        width: 100%;
        height: auto;
        margin-top: 1;
        margin-bottom: 2;
        margin-left: 8;
        margin-right: 8;
        padding: 0 1;
        background: transparent;
    }
    """

    content: reactive[str] = reactive("")

    def __init__(
        self,
        content: str = "",
        theme: Optional[ThemeTokens] = None,
        max_content_width: int = 0,
        renderable: Optional[RenderableType] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.theme = theme or DARK_THEME
        self.max_content_width = max_content_width
        self.custom_renderable = renderable
        self.content = content
        self._settled = False

    def on_mount(self) -> None:
        self.styles.opacity = 1.0
        self._update_renderable()
        animate_enter(self)

    def watch_content(self, new_val: str) -> None:
        """Dynamically re-render as streaming content arrives."""
        self._update_renderable()

    def append_chunk(self, chunk: str) -> None:
        """Append streaming text chunk."""
        self.content += chunk

    def finalize(self, final_text: Optional[str] = None) -> None:
        """Finalize message content calmly with zero screen flicker."""
        if final_text is not None:
            self.content = final_text
        self._update_renderable()
        self.styles.opacity = 1.0
        if not self._settled:
            self._settled = True
            animate_settle(self)

    def _update_renderable(self) -> None:
        """Compose the 2-cell gutter table with rendered markdown or custom renderable."""
        if self.custom_renderable is not None:
            self.update(self.custom_renderable)
            return

        clean_text = self.content.replace('\\n', '\n')
        if not clean_text.strip() or is_json_or_protocol(clean_text) or re.fullmatch(r'(?:\\[nrt]|[\s])+', clean_text.strip()):
            self.update("")
            return

        md_renderable = render_julius_markdown(clean_text, self.theme)

        table = Table.grid(padding=0)
        # Gutter: exactly 2 cells wide
        table.add_column(width=2, justify="left", vertical="top", overflow="fold", no_wrap=True)
        if self.max_content_width and self.max_content_width > 0:
            table.add_column(width=self.max_content_width, justify="left", overflow="fold", no_wrap=False)
        else:
            table.add_column(justify="left", overflow="fold", no_wrap=False)
        # Glyph '◦ ' on first line only
        glyph = Text("◦ ", style="dim")
        table.add_row(glyph, md_renderable)

        self.grid_table = table
        self.update(table)

    def on_click(self, event: events.Click) -> None:
        """Handle click on embedded links, files, or resources."""
        if getattr(event, "style", None) and event.style.link:
            event.stop()
            target = event.style.link
            if hasattr(self.app, "open_resource"):
                self.app.open_resource(target)


from textual import events


class ThinkingPanel(Panel):
    """Panel wrapper providing .plain attribute and string conversion for tests."""
    @property
    def plain(self) -> str:
        if hasattr(self.renderable, "plain"):
            return self.renderable.plain
        return str(self.renderable)

    def __str__(self) -> str:
        from rich.console import Console
        import io
        buf = io.StringIO()
        c = Console(file=buf, width=100, record=True, force_terminal=False)
        c.print(self)
        return buf.getvalue()


class ThinkingDot(Static):
    """
    Quiet single-line reasoning progression indicator.
    Indented identically to UserMessage, ToolSummary, and AssistantMessage (8 cells / 1 inch).
    Non-intrusive status display without contextless internal chain-of-thought dumps.
    """

    can_focus = True

    DEFAULT_CSS = """
    ThinkingDot {
        width: 1fr;
        height: auto;
        min-height: 1;
        margin-top: 1;
        margin-bottom: 1;
        margin-left: 8;
        margin-right: 8;
        padding: 0 1;
        color: #86868b;
        background: transparent;
    }
    ThinkingDot:hover {
        background: #1c1c1e;
    }
    ThinkingDot:focus {
        background: transparent;
    }
    """

    SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
    expanded: reactive[bool] = reactive(False)
    is_running: reactive[bool] = reactive(True)

    @staticmethod
    def _sanitize_thought(t: str) -> str:
        """Strip thinking tags, markdown code fences, and raw JSON action wrapping from thoughts."""
        if not t or not isinstance(t, str):
            return ""
        clean = t.strip()
        # If wrapped in JSON action payload, extract inner thought first
        m_json_th = re.search(r'"thought"\s*:\s*"((?:[^"\\]|\\.)*)', clean)
        if m_json_th:
            clean = m_json_th.group(1).replace('\\"', '"').replace('\\n', ' ').strip()
        else:
            # Extract content from <think>...</think> if present
            m_think = re.search(r'<think>(.*?)(?:</think>|$)', clean, flags=re.DOTALL)
            if m_think and m_think.group(1).strip():
                clean = m_think.group(1).strip()
            else:
                clean = re.sub(r'</?(?:think|thought|reasoning)>', '', clean, flags=re.IGNORECASE)

            # Strip markdown code fences like ```json, ```, ```text
            clean = re.sub(r'^```[a-zA-Z0-9_-]*\s*', '', clean)
            clean = re.sub(r'\s*```$', '', clean)
            clean = re.sub(r'```[a-zA-Z0-9_-]*', '', clean)
            clean = clean.replace('```', '')

            # Strip leading prefixes like "Thought:", "Thinking Process:", "Reasoning:"
            clean = re.sub(r'^(?:Thinking Process|Thought|Reasoning):\s*', '', clean.strip(), flags=re.IGNORECASE)

        # Strip unparsed JSON fragments, trailing JSON blocks, braces
        clean = re.sub(r'json\{.*', '', clean, flags=re.DOTALL)
        clean = clean.strip().strip('`').strip()

        # Reject if the thought is just raw JSON syntax, braces, or protocol markers
        if not clean:
            return ""
        lower = clean.lower()
        if lower in ("json", "```", "```json", "{", "}", "{}", "[]", "none", "null"):
            return ""
        if lower.startswith(('{"action"', '{"actions"', '"action":', '"actions":', 'action:', 'actions:')):
            return ""
        if clean.startswith('{') and ('"action"' in clean or '"actions"' in clean):
            return ""
        if set(clean) <= set('{}[]()"\':;,` \n\r\t'):
            return ""

        return clean.strip()

    @staticmethod
    def format_summary(text: str, max_len: int = 65) -> str:
        """Format thought into a clean single-line summary with complete words and no cutoffs."""
        if not text:
            return "Thinking"
        # Sanitize thought first
        clean = ThinkingDot._sanitize_thought(text)
        if not clean:
            return "Thinking"
        clean = clean.strip().strip('`"\'—: .')
        if not clean:
            return "Thinking"

        # Iteratively strip thinking/thought/reasoning prefixes so only clean context remains
        while True:
            prev = clean
            clean = re.sub(
                r'^(?:thinking(?:\s+process)?|thought|reasoning)(?:\s*[:—\-])\s*',
                '',
                clean,
                flags=re.IGNORECASE,
            ).strip('`"\'—: .')
            clean = re.sub(
                r'^thinking(?:\.{2,3}|…)?\s+',
                '',
                clean,
                flags=re.IGNORECASE,
            ).strip('`"\'—: .')
            if clean.lower() in ("thinking", "thinking...", "thinking…", "thought", "reasoning", "thinking process", "json", "```", "```json"):
                clean = ""
                break
            if clean == prev:
                break

        if not clean:
            return "Thinking"

        # Reject fences, braces, and json keywords
        if clean.startswith(('`', '{', '}', '[', ']')) or clean.lower().startswith(('json', 'action:')):
            return "Thinking"

        # Capitalize first character of context
        clean = clean[0].upper() + clean[1:]

        first_line = clean.splitlines()[0].strip().strip('`"\'—: ')
        if not first_line or first_line.lower() in ("thinking", "thinking...", "thinking…", "thought", "reasoning", "json"):
            return "Thinking"

        if first_line.startswith(('`', '{', '}', '[', ']')):
            return "Thinking"

        # 1. If an early sentence boundary exists (. ! ?) within max_len:
        m = re.search(r'^(.*?[.!?])(?:\s|$)', first_line)
        if m and len(m.group(1)) <= max_len:
            sentence = m.group(1).rstrip('.!?').strip()
            if sentence and sentence.lower() not in ("thinking", "thinking...", "thinking…", "json"):
                return f"Thinking — {sentence}"

        # 2. If entire first line fits within max_len:
        if len(first_line) <= max_len:
            trimmed = first_line.rstrip('.!?').strip()
            if trimmed and trimmed.lower() not in ("thinking", "thinking...", "thinking…", "json"):
                return f"Thinking — {trimmed}"
            return "Thinking"

        # 3. Otherwise truncate strictly at word boundary without cutting words
        truncated = first_line[:max_len]
        if " " in truncated:
            truncated = truncated.rsplit(" ", 1)[0]
        clean_trunc = truncated.rstrip('.!?,— -').strip()
        clean_trunc = re.sub(r'[\s—-]+(?:and|or|because|but)?$', '', clean_trunc).strip()
        if clean_trunc and clean_trunc.lower() not in ("thinking", "thinking...", "thinking…", "json"):
            return f"Thinking — {clean_trunc}"
        return "Thinking"

    def __init__(self, label: str = "Thinking", full_thought: str = "", **kwargs) -> None:
        super().__init__(classes="thinking-indicator", **kwargs)
        clean_lbl = self._sanitize_thought(label)
        self.thoughts: list[str] = []
        clean_full = self._sanitize_thought(full_thought)
        if clean_full:
            self.thoughts.append(clean_full)
            self.full_thought = clean_full
        else:
            self.full_thought = clean_lbl or "Thinking"
        self.label = self.format_summary(clean_lbl or self.full_thought)
        self.scheduled_tasks: list[str] = []
        self._spinner_idx: int = 0
        self._spinner_timer = None

    def append_thought(self, text: str) -> None:
        """Append streamed or multi-step thought into panel history."""
        clean = self._sanitize_thought(text)
        if clean and clean not in self.thoughts:
            self.thoughts.append(clean)
            self.full_thought = "\n\n".join(self.thoughts)
            self._refresh_content()

    def update_label(self, new_label: str, full_thought: str = "") -> None:
        """Update label dynamically and store thought reasoning."""
        clean_full = self._sanitize_thought(full_thought) if full_thought else ""
        if clean_full and clean_full not in self.thoughts:
            self.thoughts.append(clean_full)
            self.full_thought = "\n\n".join(self.thoughts)

        if new_label:
            self.label = self.format_summary(new_label)
        elif self.thoughts:
            self.label = self.format_summary(self.thoughts[-1])
        else:
            self.label = "Thinking"
        self._refresh_content()

    def add_scheduled_task(self, task_name: str) -> None:
        """Record scheduled action in memory while keeping UI clean per user instruction."""
        if task_name not in self.scheduled_tasks:
            self.scheduled_tasks.append(task_name)

    def toggle(self) -> None:
        """Toggle thinking panel expansion state."""
        self.expanded = not self.expanded
        self.refresh(layout=True)

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.toggle()

    def on_key(self, event: events.Key) -> None:
        if event.key in ("enter", "space", "ctrl+t", "ctrl+o"):
            event.stop()
            self.toggle()

    def on_mount(self) -> None:
        if self.is_running and not self._spinner_timer:
            self._spinner_timer = self.set_interval(0.3, self._spin)

    def _spin(self) -> None:
        """Advance round loading spinner frame calmly."""
        if not self.is_running or not self.is_mounted:
            return
        self._spinner_idx = (self._spinner_idx + 1) % len(self.SPINNER_FRAMES)
        self.refresh()

    def finish(self, duration_s: Optional[float] = None) -> None:
        """Mark thinking as complete and stop spinner calmly."""
        self.is_running = False
        if self._spinner_timer:
            self._spinner_timer.stop()
            self._spinner_timer = None
        if duration_s is not None and duration_s > 0:
            if self.label and self.label != "Thinking" and not self.label.startswith("Thought for"):
                self.label = f"Thought for {duration_s:.1f}s · {self.label}"
            else:
                self.label = f"Thought for {duration_s:.1f}s"
        self._refresh_content()

    def stop(self) -> None:
        """Stop animations and timers cleanly."""
        self.is_running = False
        if self._spinner_timer:
            self._spinner_timer.stop()
            self._spinner_timer = None

    def _refresh_content(self) -> None:
        """Refresh widget display and request parent re-layout."""
        if self.is_mounted:
            self.refresh(layout=True)

    def render(self) -> RenderableType:
        """Render calm thinking indicator, expandable on click to reveal a clean rounded thinking panel."""
        frame = self.SPINNER_FRAMES[self._spinner_idx] if self.is_running else "●"
        status_color = "bold #c8b896" if self.is_running else "dim #c8b896"
        summary_text = self.label or "Thinking…"
        arrow = "⌄" if self.expanded else "›"

        if not self.expanded:
            return Text.assemble(
                (f"{arrow} ", "dim"),
                (f"{frame} ", status_color),
                (f"{summary_text}", "dim #f5f5f7"),
            )

        # Expanded card showing full thoughts inside a clean rounded panel
        raw_list = list(self.thoughts) if self.thoughts else ([self.full_thought] if self.full_thought else [])
        displayed = [
            th for th in raw_list
            if th and th.strip()
            and not th.strip().startswith(('```', '{', '}', 'json'))
            and th.strip().lower() not in ('```', '```json', 'json', '{}', 'none')
        ]
        if not displayed:
            displayed = ["(Analyzing request and preparing execution steps…)"]

        inner = Text()
        for idx_th, th in enumerate(displayed):
            if idx_th > 0:
                inner.append("\n\n")
            inner.append("● ", style="bold #c8b896")
            inner.append(th, style="#ded2b8")

        return ThinkingPanel(
            inner,
            title=f"[bold #f5f5f7]{arrow} {frame} {summary_text}[/bold #f5f5f7]",
            title_align="left",
            border_style="#3e3e42",
            box=box.ROUNDED,
            padding=(0, 1),
        )
