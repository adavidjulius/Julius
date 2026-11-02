"""
Conversation compression: raw conversation → structured summary.
After every task, compresses the raw conversation into a structured memory record.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CompressedTaskSummary:
    """Structured summary of a completed task."""
    task_id: str
    summary: str
    files_modified: List[str] = field(default_factory=list)
    functions_changed: List[str] = field(default_factory=list)
    result: str = "success"  # success, failed, partial
    known_issues: List[str] = field(default_factory=list)
    turn_count: int = 0


class ConversationCompressor:
    """
    Compresses raw conversation turns into structured summaries.
    Uses heuristics to extract key information without an LLM call.
    For richer summaries, an LLM-based summarizer can be plugged in.
    """

    def __init__(self) -> None:
        pass

    def compress(self, turns: List[Dict[str, Any]]) -> CompressedTaskSummary:
        """
        Compress a list of conversation turns into a structured summary.
        Extracts: files modified, functions changed, result status, issues.
        Returns an empty summary if turns is empty or invalid.
        """
        import re

        # Input validation
        if not turns or not isinstance(turns, list):
            logger.debug("Compression: Empty or invalid turns list, returning empty summary")
            return CompressedTaskSummary(
                task_id="",
                summary="No conversation turns to compress",
                files_modified=[],
                functions_changed=[],
                result="success",
                known_issues=[],
                turn_count=0,
            )

        files_modified: List[str] = []
        functions_changed: List[str] = []
        known_issues: List[str] = []
        result = "success"

        # Patterns to extract from assistant turns
        file_pattern = re.compile(r"(?:modified|created|edited|wrote|updated|changed|deleted)\s+(?:file\s+)?[`'\"]?([\w/.-]+(?:\.\w+)?)[`'\"]?", re.IGNORECASE)
        func_pattern = re.compile(r"(?:function|method|class)\s+[`'\"]?(\w+)[`'\"]?", re.IGNORECASE)
        error_pattern = re.compile(r"(?:error|bug|issue|problem|fail|crash|broken)\s*:?\s*(.+?)[.!]?\s*$", re.IGNORECASE | re.MULTILINE)
        fail_pattern = re.compile(r"\b(failed|error|couldn't|unable|not working|broken)\b", re.IGNORECASE)

        for turn in turns:
            # Validate each turn
            if not isinstance(turn, dict):
                continue
            content = turn.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            role = turn.get("role", "")
            if not isinstance(role, str):
                role = str(role)

            if role == "assistant":
                # Extract file modifications
                for match in file_pattern.finditer(content):
                    path = match.group(1)
                    if path not in files_modified:
                        files_modified.append(path)

                # Extract function changes
                for match in func_pattern.finditer(content):
                    name = match.group(1)
                    if name not in functions_changed:
                        functions_changed.append(name)

                # Extract known issues
                for match in error_pattern.finditer(content):
                    issue = match.group(1).strip()
                    if issue and issue not in known_issues and len(issue) > 5:
                        known_issues.append(issue)

                # Check for failure signals
                if fail_pattern.search(content):
                    result = "partial"

        # Deduplicate and clean
        files_modified = list(dict.fromkeys(files_modified))
        functions_changed = list(dict.fromkeys(functions_changed))
        known_issues = list(dict.fromkeys(known_issues))

        # Build summary
        summary_parts = []
        if files_modified:
            summary_parts.append(f"Modified {len(files_modified)} files")
        if functions_changed:
            summary_parts.append(f"Changed {len(functions_changed)} functions")
        if known_issues:
            summary_parts.append(f"Issues: {'; '.join(known_issues[:3])}")

        summary = ". ".join(summary_parts) if summary_parts else "Task completed"

        return CompressedTaskSummary(
            task_id="",
            summary=summary,
            files_modified=files_modified,
            functions_changed=functions_changed,
            result=result,
            known_issues=known_issues,
            turn_count=len(turns),
        )

    def generate_episodic_note(self, task_summaries: List[CompressedTaskSummary]) -> str:
        """Generate a day-level episodic note from multiple task summaries."""
        if not task_summaries:
            return "No tasks completed."

        total = len(task_summaries)
        success_count = sum(1 for t in task_summaries if t.result == "success")
        all_files = set()
        all_issues = set()

        for t in task_summaries:
            all_files.update(t.files_modified)
            all_issues.update(t.known_issues)

        parts = [f"Completed {success_count}/{total} tasks."]
        if all_files:
            parts.append(f"Files: {', '.join(list(all_files)[:5])}")
        if all_issues:
            parts.append(f"Issues: {'; '.join(list(all_issues)[:3])}")

        return " ".join(parts)
