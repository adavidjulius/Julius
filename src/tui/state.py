"""
Reactive state and session tracking store for Julius TUI.
"""

from __future__ import annotations

import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple


@dataclass
class ToolExecutionRecord:
    """Record of a tool execution in the current turn."""
    tool_name: str
    summary: str
    duration_s: float = 0.0
    success: bool = True
    command: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    output: str = ""


@dataclass
class FileUndoRecord:
    """Snapshot of a file before it was modified in the session."""
    path: str
    pre_edit_content: Optional[str]  # None if file was newly created
    existed_before: bool


@dataclass
class SessionState:
    """Central store tracking session telemetry and UI states."""
    active_model: str = "deepseek"
    theme_name: str = "auto"
    token_count: int = 0
    start_time: float = field(default_factory=time.time)
    current_step: int = 1
    max_steps: int = 50
    is_working: bool = False
    status_message: str = ""

    # Modified files tracking for ledger and undo
    modified_files: List[str] = field(default_factory=list)
    undo_stack: List[FileUndoRecord] = field(default_factory=list)

    # Tool activity for the active turn
    current_turn_tools: List[ToolExecutionRecord] = field(default_factory=list)

    # Full conversation history: list of (role, text)
    history: List[Tuple[str, str]] = field(default_factory=list)

    # Last assistant answer for quick clipboard copy
    last_assistant_answer: str = ""

    def reset_turn(self) -> None:
        """Reset state before a new assistant turn begins."""
        self.current_turn_tools.clear()
        self.is_working = True
        self.status_message = "Thinking"

    def record_tool(
        self,
        tool_name: str,
        summary: str,
        duration_s: float = 0.0,
        success: bool = True,
        command: str = "",
        args: Optional[Dict[str, Any]] = None,
        output: str = "",
    ) -> None:
        """Record an executed tool action."""
        self.current_turn_tools.append(ToolExecutionRecord(
            tool_name=tool_name,
            summary=summary,
            duration_s=duration_s,
            success=success,
            command=command,
            args=args or {},
            output=output,
        ))

    def record_file_modification(self, file_path: str) -> None:
        """Track modified file path and capture pre-edit snapshot for undo rollback."""
        if not file_path:
            return
        if file_path not in self.modified_files:
            self.modified_files.append(file_path)
            try:
                p = Path(file_path)
                if p.exists() and p.is_file():
                    pre_content = p.read_text(encoding="utf-8", errors="replace")
                    self.undo_stack.append(FileUndoRecord(path=file_path, pre_edit_content=pre_content, existed_before=True))
                else:
                    self.undo_stack.append(FileUndoRecord(path=file_path, pre_edit_content=None, existed_before=False))
            except Exception:
                self.undo_stack.append(FileUndoRecord(path=file_path, pre_edit_content=None, existed_before=True))

    def rollback_last_modification(self) -> Optional[Tuple[str, str]]:
        """Rollback the last file mutation.
        
        Restores original pre-edit content or removes newly created files.
        Returns (file_path, description) or None if undo stack is empty.
        """
        if not self.undo_stack:
            return None
        rec = self.undo_stack.pop()
        if rec.path in self.modified_files:
            self.modified_files.remove(rec.path)

        p = Path(rec.path)
        if rec.existed_before:
            if rec.pre_edit_content is not None:
                try:
                    p.write_text(rec.pre_edit_content, encoding="utf-8")
                    return (rec.path, "restored original content")
                except Exception as e:
                    return (rec.path, f"error restoring: {e}")
            else:
                return (rec.path, "ledger entry removed")
        else:
            try:
                if p.exists():
                    p.unlink()
                return (rec.path, "removed newly created file")
            except Exception as e:
                return (rec.path, f"error deleting: {e}")

    def finish_turn(self, final_answer: str) -> None:
        """Finalize assistant turn."""
        self.is_working = False
        self.status_message = ""
        if final_answer:
            self.last_assistant_answer = final_answer
            self.history.append(("assistant", final_answer))
