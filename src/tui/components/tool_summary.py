"""
Collapsible ToolSummary widget for Julius.

Design requirements:
- Collapsed by default into one quiet dim line:
  e.g. '› Ran 9 steps · 0.2s (press enter or ctrl+o to view)'
- Enter, ctrl+o, or click expands it inline.
- When expanded:
  Shows '⌄ Ran 9 steps · 0.2s'
  Underneath, lists each executed tool step with an opening arrow:
  e.g. '   › Executed search_files (0.1s)'
- Clicking any step line (or its arrow) opens that specific step to '   ⌄ ...'
  revealing the exact command / arguments and output underneath.
- Clicking the header line collapses the entire ToolSummary back.
"""

from __future__ import annotations

import time
import textwrap
from typing import List, Tuple, Set
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from ..motion import animate_enter
from ..state import ToolExecutionRecord


def format_step_duration(seconds: float) -> str:
    """Format step duration: in seconds if < 60s, in minutes (and seconds) if >= 60s."""
    if seconds <= 0:
        return "0.1s"
    if seconds < 60.0:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    secs = int(round(seconds % 60))
    if secs >= 60:
        mins += 1
        secs = 0
    if secs > 0:
        return f"{mins}m {secs}s"
    return f"{mins}m"


class ToolSummary(Widget, can_focus=True):
    """Quiet collapsible tool activity summary with nested per-step command inspectors."""

    DEFAULT_CSS = """
    ToolSummary {
        width: 1fr;
        height: auto;
        margin-top: 0;
        margin-bottom: 1;
        margin-left: 8;
        margin-right: 8;
        padding: 0 1;
        background: transparent;
    }
    ToolSummary:focus {
        background: transparent;
    }
    """

    expanded: reactive[bool] = reactive(False)

    def __init__(self, tools: List[ToolExecutionRecord], total_duration_s: float = 0.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self.tools = list(tools)
        if total_duration_s > 0:
            self.total_duration_s = total_duration_s
        elif self.tools:
            sum_dur = sum(t.duration_s for t in self.tools)
            self.total_duration_s = max(0.1, sum_dur)
        else:
            self.total_duration_s = 0.1

        self.expanded_steps: Set[int] = set()
        self._step_line_ranges: List[Tuple[int, int]] = []
        self._content_widget = Static("", id="tool-summary-content")

    def compose(self) -> ComposeResult:
        yield self._content_widget

    def on_mount(self) -> None:
        self.styles.opacity = 1.0
        self._refresh_content()
        animate_enter(self)

    def watch_expanded(self, new_val: bool) -> None:
        self._refresh_content()

    def toggle(self) -> None:
        """Toggle main expanded state."""
        self.expanded = not self.expanded

    def on_click(self, event: events.Click) -> None:
        event.stop()
        if not self.expanded:
            self.expanded = True
            return

        click_y = event.y
        # Line 0 is the main header: "⌄ Ran X steps · Y.Zs"
        if click_y == 0:
            self.expanded = False
            return

        # Check which step line was clicked
        for idx, (start, end) in enumerate(self._step_line_ranges):
            if start <= click_y <= end:
                if idx in self.expanded_steps:
                    self.expanded_steps.remove(idx)
                else:
                    self.expanded_steps.add(idx)
                self._refresh_content()
                return

        # If clicked anywhere else, collapse
        self.expanded = False

    def on_key(self, event: events.Key) -> None:
        if event.key in ("enter", "space", "ctrl+o"):
            event.stop()
            event.prevent_default()
            self.toggle()
        elif event.key == "e":
            event.stop()
            # Toggle expand all steps
            if len(self.expanded_steps) == len(self.tools):
                self.expanded_steps.clear()
            else:
                self.expanded_steps = set(range(len(self.tools)))
            self._refresh_content()
        elif event.key.isdigit():
            idx = int(event.key) - 1
            if 0 <= idx < len(self.tools):
                event.stop()
                if idx in self.expanded_steps:
                    self.expanded_steps.remove(idx)
                else:
                    self.expanded_steps.add(idx)
                self._refresh_content()

    def _refresh_content(self) -> None:
        if not hasattr(self, "_content_widget"):
            return
        try:
            _ = self.app
        except Exception:
            return

        step_count = len(self.tools)
        time_str = format_step_duration(self.total_duration_s) if self.total_duration_s > 0 else "0.1s"

        self._step_line_ranges = []

        if not self.expanded:
            # Collapsed view: one quiet dim line
            header = Text.assemble(
                ("› ", "dim"),
                (f"Ran {step_count} step{'s' if step_count != 1 else ''} · {time_str}", "dim"),
                ("  (press enter or ctrl+o to view)", "dim"),
            )
            self._content_widget.update(header)
        else:
            # Expanded view: header + expandable tool steps
            res = Text()
            res.append(f"⌄ Ran {step_count} step{'s' if step_count != 1 else ''} · {time_str}\n", style="dim")

            current_line = 1  # Header line is line 0

            for idx, t in enumerate(self.tools):
                step_start_line = current_line
                dur_tag = f" ({format_step_duration(t.duration_s)})" if t.duration_s > 0 else " (0.1s)"
                is_open = idx in self.expanded_steps
                arrow = "⌄" if is_open else "›"
                arrow_style = "bold #c8b896" if is_open else "dim"

                # Step summary line with opening arrow
                res.append(f"   {arrow} ", style=arrow_style)
                res.append(f"{t.summary}", style="bold #f5f5f7" if is_open else "dim")
                res.append(f"{dur_tag}\n", style="dim")
                current_line += 1

                # If this specific step is open, render command & output inside a dynamic grey box
                if is_open:
                    cmd_str = (t.command or (f"{t.tool_name}({t.args})" if t.args else t.summary)).strip()

                    # 1. Break / wrap command lines cleanly so no part is truncated
                    cmd_wrap_w = 76
                    wrapped_cmd_lines: List[str] = []
                    for raw_cmd_line in cmd_str.splitlines():
                        sub_wrapped = textwrap.wrap(raw_cmd_line, width=cmd_wrap_w, break_long_words=True, break_on_hyphens=False)
                        wrapped_cmd_lines.extend(sub_wrapped or [raw_cmd_line])
                    if not wrapped_cmd_lines:
                        wrapped_cmd_lines = [cmd_str]

                    # 2. Prepare output preview lines
                    out_lines: List[str] = []
                    if t.output:
                        raw_out_lines = t.output.strip().splitlines()
                        max_preview = 8
                        for l in raw_out_lines[:max_preview]:
                            sub_w = textwrap.wrap(l, width=cmd_wrap_w, break_long_words=True)
                            out_lines.extend(sub_w or [l])
                        if len(raw_out_lines) > max_preview:
                            out_lines.append(f"… ({len(raw_out_lines) - max_preview} more lines)")

                    # 3. Compute dynamic width according to text size
                    max_content_len = 0
                    for i, cl in enumerate(wrapped_cmd_lines):
                        p = "$ " if i == 0 else "  "
                        max_content_len = max(max_content_len, len(p + cl))
                    for ol in out_lines:
                        max_content_len = max(max_content_len, len(ol))

                    # Dynamic box width according to text size (between 28 and 80 chars)
                    box_w = max(min(max_content_len + 4, 80), 28)
                    inner_w = box_w - 4

                    # Top border
                    res.append("       ╭" + "─" * (box_w - 2) + "╮\n", style="#3e3e42")
                    current_line += 1

                    # Command lines inside transparent grey box
                    for i, cl in enumerate(wrapped_cmd_lines):
                        p = "$ " if i == 0 else "  "
                        line_str = (p + cl)[:inner_w]
                        res.append("       │ ", style="#3e3e42")
                        res.append(f"{line_str:<{inner_w}}", style="bold #c8b896")
                        res.append(" │\n", style="#3e3e42")
                        current_line += 1

                    # Divider if output lines exist
                    if out_lines:
                        res.append("       ├" + "─" * (box_w - 2) + "┤\n", style="#2c2c2e")
                        current_line += 1
                        for ol in out_lines:
                            line_str = ol[:inner_w]
                            res.append("       │ ", style="#3e3e42")
                            res.append(f"{line_str:<{inner_w}}", style="#a1a1a6")
                            res.append(" │\n", style="#3e3e42")
                            current_line += 1

                    # Bottom border
                    res.append("       ╰" + "─" * (box_w - 2) + "╯\n", style="#3e3e42")
                    current_line += 1

                step_end_line = current_line - 1
                self._step_line_ranges.append((step_start_line, step_end_line))

            self._content_widget.update(res)
