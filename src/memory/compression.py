"""
Conversation compression and macro-compaction engine for Julius.
Implements the multi-stage compaction pattern:
- Thinking block stripping (reclaims massive tokens while preserving logic)
- Structured synthesis of goals, file mutations, and active workspace state
- Preserved tail segments kept verbatim
- Critical system reminders marking the compaction boundary
"""

from __future__ import annotations

import logging
import re
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
        file_pattern = re.compile(
            r"(?:modified|created|edited|wrote|updated|changed|deleted)\s+(?:file\s+)?[`'\"]?([\w/.-]+\.[a-zA-Z0-9]+)[`'\"]?",
            re.IGNORECASE,
        )
        func_pattern = re.compile(r"(?:function|method|class)\s+[`'\"]?(\w+)[`'\"]?", re.IGNORECASE)
        error_pattern = re.compile(
            r"(?:error|bug|issue|problem|fail|crash|broken)\s*:?\s*(.+?)[.!]?\s*$",
            re.IGNORECASE | re.MULTILINE,
        )
        fail_pattern = re.compile(r"\b(failed|error|couldn't|unable|not working|broken)\b", re.IGNORECASE)

        for turn in turns:
            if not isinstance(turn, dict):
                continue
            content = turn.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            role = turn.get("role", "")
            if not isinstance(role, str):
                role = str(role)

            if role == "assistant":
                for match in file_pattern.finditer(content):
                    path = match.group(1)
                    if path not in files_modified:
                        files_modified.append(path)

                for match in func_pattern.finditer(content):
                    name = match.group(1)
                    if name not in functions_changed:
                        functions_changed.append(name)

                for match in error_pattern.finditer(content):
                    issue = match.group(1).strip()
                    if issue and issue not in known_issues and len(issue) > 5:
                        known_issues.append(issue)

                if fail_pattern.search(content):
                    result = "failed"

        summary_parts = []
        if files_modified:
            summary_parts.append(f"Modified files: {', '.join(files_modified)}")
        if functions_changed:
            summary_parts.append(f"Changed functions: {', '.join(functions_changed)}")
        if known_issues:
            summary_parts.append(f"Issues noted: {'; '.join(known_issues[:3])}")
        summary_text = " | ".join(summary_parts) if summary_parts else "Routine task execution completed."

        return CompressedTaskSummary(
            task_id="",
            summary=summary_text,
            files_modified=files_modified,
            functions_changed=functions_changed,
            result=result,
            known_issues=known_issues,
            turn_count=len(turns),
        )

    @staticmethod
    def strip_thinking_blocks(text: str) -> str:
        """Strip internal thinking/reasoning blocks to conserve context tokens."""
        if not text:
            return ""
        # Strip <thought>...</thought> or <thinking>...</thinking>
        cleaned = re.sub(r'<thought>[\s\S]*?</thought>', '', text, flags=re.IGNORECASE)
        cleaned = re.sub(r'<thinking>[\s\S]*?</thinking>', '', cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def compact_conversation(
        self,
        turns: List[Dict[str, Any]],
        preserved_tail_count: int = 4,
        git_diff_summary: str = "",
    ) -> Dict[str, Any]:
        """
        Execute macro-compaction over conversation turns:
        1. Preserves the most recent `preserved_tail_count` turns verbatim.
        2. Strips thinking blocks from older turns.
        3. Generates a structured summary of older turns (goals, files, decisions).
        4. Injects a boundary marker and critical system reminder.
        """
        if len(turns) <= preserved_tail_count:
            return {
                "compacted_turns": turns,
                "summary": "No compaction needed (turn count within preservation tail).",
                "is_compacted": False,
                "turns_summarized": 0,
            }

        # Split turns
        head_turns = turns[:-preserved_tail_count]
        tail_turns = turns[-preserved_tail_count:]

        # Extract structured knowledge from head turns
        task_summary = self.compress(head_turns)

        # Find primary user goals from early turns
        user_intents = []
        for t in head_turns:
            if t.get("role") == "user":
                msg = str(t.get("content", "")).strip()
                if msg and len(msg) < 300:
                    user_intents.append(msg)
                elif msg:
                    user_intents.append(msg[:300] + "...")

        # Construct markdown summary block
        summary_lines = [
            "### Compacted Prior Conversation Summary",
            "",
            f"**Initial Directives:** {user_intents[0] if user_intents else 'Session task'}",
        ]
        if len(user_intents) > 1:
            summary_lines.append(f"**Follow-up Requests:** {'; '.join(user_intents[1:4])}")

        if task_summary.files_modified:
            summary_lines.append(f"**Files Created / Modified:** {', '.join(task_summary.files_modified)}")
        if task_summary.functions_changed:
            summary_lines.append(f"**Functions/Symbols Modified:** {', '.join(task_summary.functions_changed)}")
        if git_diff_summary:
            summary_lines.append(f"**Workspace Git State:** {git_diff_summary}")
        if task_summary.known_issues:
            summary_lines.append(f"**Resolved Issues/Notes:** {'; '.join(task_summary.known_issues)}")

        summary_content = "\n".join(summary_lines)

        # Clean tail turns: strip thinking blocks from previous assistant messages
        cleaned_tail = []
        for turn in tail_turns:
            cleaned_turn = dict(turn)
            if cleaned_turn.get("role") == "assistant":
                content = str(cleaned_turn.get("content", ""))
                cleaned_turn["content"] = self.strip_thinking_blocks(content)
            cleaned_tail.append(cleaned_turn)

        # Assemble new compacted history
        boundary_marker = {
            "role": "system",
            "content": (
                "<system-reminder>\n"
                "The conversation history was compacted because it approached context limits. "
                "The prior turns have been summarized below; proceed from the preserved messages.\n"
                "</system-reminder>\n\n"
                + summary_content
            ),
            "is_compaction_marker": True,
        }

        compacted_turns = [boundary_marker] + cleaned_tail

        return {
            "compacted_turns": compacted_turns,
            "summary": summary_content,
            "is_compacted": True,
            "turns_summarized": len(head_turns),
            "files_modified": task_summary.files_modified,
        }
