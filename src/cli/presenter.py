"""
Terminal UI Presenter for Julius CLI (Julius-Style).

Handles:
- Rotating single-line in-place spinner ('/', '-', '\\', '|')
- Minimal inline diffs with [a]ccept / [d]ecline prompts
- Rich markdown rendering for final answers
- Clean concise error presentation
"""

from __future__ import annotations

import asyncio
import difflib
import sys
import threading
import time
from typing import Dict, Any, Optional

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.text import Text
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None


class Spinner:
    """Single-line in-place rotating spinner updated via \\r."""

    FRAMES = ['/', '-', '\\', '|']

    def __init__(self, message: str = "Working...") -> None:
        self.message = message
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _spin(self) -> None:
        idx = 0
        while self.running:
            char = self.FRAMES[idx % len(self.FRAMES)]
            # Print subdued single line spinner without extra text scrolling
            if HAS_RICH:
                sys.stdout.write(f"\r\033[90m{char}\033[0m {self.message}")
            else:
                sys.stdout.write(f"\r{char} {self.message}")
            sys.stdout.flush()
            idx += 1
            time.sleep(0.12)

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        if self._thread:
            self._thread.join(timeout=0.5)
        # Clear spinner line completely
        sys.stdout.write("\r" + " " * 70 + "\r")
        sys.stdout.flush()


def render_inline_diff(path: str, old_text: str, new_text: str) -> None:
    """Render a restrained, compact inline diff using Rich."""
    sys.stdout.write(f"\n📄 Proposed edits to [bold cyan]{path}[/bold cyan]:\n" if HAS_RICH else f"\n📄 Proposed edits to {path}:\n")
    
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}", n=2))
    
    if not diff:
        print("  (No visible text changes)")
        return

    if HAS_RICH and console:
        diff_text = Text()
        for line in diff:
            line_str = line.rstrip('\n')
            if line.startswith('+++') or line.startswith('---'):
                diff_text.append(f"{line_str}\n", style="bold dim")
            elif line.startswith('@@'):
                diff_text.append(f"{line_str}\n", style="cyan dim")
            elif line.startswith('+'):
                diff_text.append(f"{line_str}\n", style="green")
            elif line.startswith('-'):
                diff_text.append(f"{line_str}\n", style="red")
            else:
                diff_text.append(f"{line_str}\n", style="dim")
        console.print(diff_text)
    else:
        for line in diff:
            sys.stdout.write(line)
        sys.stdout.flush()


def render_confirmation_prompt(action_name: str, args: Dict[str, Any]) -> str:
    """
    Render a minimal Julius-style confirmation request with diff/preview
    and return prompt label.
    """
    if action_name == 'edit_file':
        path = args.get('path', '')
        old_text = args.get('old_text', '')
        new_text = args.get('new_text', '')
        render_inline_diff(path, old_text, new_text)

    elif action_name == 'write_file':
        path = args.get('path', '')
        content = args.get('content', '')
        render_inline_diff(path, "", content[:500])

    elif action_name == 'run_bash':
        cmd = args.get('command', '')
        if HAS_RICH and console:
            console.print(f"\n⚡ [bold yellow]Command Execution:[/bold yellow] [bold white]{cmd}[/bold white]")
        else:
            print(f"\n⚡ Command Execution: {cmd}")

    elif action_name == 'git':
        subcmd = args.get('subcommand', '')
        if HAS_RICH and console:
            console.print(f"\n🔀 [bold magenta]Git Command:[/bold magenta] [bold white]git {subcmd}[/bold white]")
        else:
            print(f"\n🔀 Git Command: git {subcmd}")

    else:
        if HAS_RICH and console:
            console.print(f"\n⚠️ Action [bold]{action_name}[/bold] requires confirmation.")
        else:
            print(f"\n⚠️ Action {action_name} requires confirmation.")

    return "[a]ccept / [d]ecline: "


def render_final_answer(answer_text: str) -> None:
    """Render final response prose cleanly with Rich Markdown."""
    if not answer_text or not answer_text.strip():
        return
    print()
    if HAS_RICH and console:
        console.print(Markdown(answer_text.strip()))
    else:
        print(answer_text.strip())
    print()


def render_error(error_message: str) -> None:
    """Render concise error message without raw stack traces by default."""
    print()
    if HAS_RICH and console:
        console.print(f"[bold red]Error:[/bold red] {error_message}")
    else:
        print(f"Error: {error_message}")
    print()
