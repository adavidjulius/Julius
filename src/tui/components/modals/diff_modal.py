"""
Interactive File Diff Reviewer modal (Ctrl+D or /diff).
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import List, Optional
from rich.syntax import Syntax
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Label, Static, OptionList
from textual.widgets.option_list import Option


class DiffReviewModal(ModalScreen[None]):
    """Calm diff inspection modal for workspace file modifications."""

    DEFAULT_CSS = """
    DiffReviewModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #diff-card {
        width: 90%;
        max-width: 120;
        height: 80%;
        background: #18181b;
        border: round #c8b896;
        padding: 1 2;
        layout: vertical;
    }

    #diff-title {
        color: #f5f5f7;
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }

    #diff-file-list {
        height: 4;
        max-height: 6;
        background: #0d0d0f;
        border: round #3e3e42;
        margin-bottom: 1;
    }

    #diff-content-scroll {
        height: 1fr;
        border: round #3e3e42;
        padding: 0 1;
        background: #0d0d0f;
    }

    #diff-footer {
        color: #86868b;
        text-align: center;
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(self, modified_files: List[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self.modified_files = modified_files

    def compose(self) -> ComposeResult:
        with Vertical(id="diff-card"):
            yield Label("Workspace Changes (Ledger)", id="diff-title")
            yield OptionList(id="diff-file-list")
            with ScrollableContainer(id="diff-content-scroll"):
                yield Static(id="diff-viewer")
            yield Label("Press Esc to close · Enter to select file", id="diff-footer")

    def on_mount(self) -> None:
        file_list = self.query_one("#diff-file-list", OptionList)
        file_list.clear_options()

        if not self.modified_files:
            file_list.add_option(Option("No modified files in this session", id="none"))
            self.query_one("#diff-viewer", Static).update(Text("Clean workspace. No file changes recorded yet.", style="dim"))
            return

        for p in self.modified_files:
            file_list.add_option(Option(p, id=p))

        file_list.focus()
        self._load_file_diff(self.modified_files[0])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id and event.option.id != "none":
            self._load_file_diff(str(event.option.id))

    def _load_file_diff(self, file_path: str) -> None:
        viewer = self.query_one("#diff-viewer", Static)
        p = Path(file_path)
        if not p.exists():
            viewer.update(Text(f"File {file_path} does not exist on disk.", style="dim"))
            return

        try:
            content = p.read_text(encoding="utf-8")
            # Render file content preview
            syntax = Syntax(content[:2000], "python" if p.suffix == ".py" else "text", line_numbers=True)
            viewer.update(syntax)
        except Exception as exc:
            viewer.update(Text(f"Could not read {file_path}: {exc}", style="dim"))

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss(None)
