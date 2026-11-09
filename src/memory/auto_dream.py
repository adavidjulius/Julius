"""
Auto-Dream Background Memory Consolidation Engine for Julius (WS1.1 / WS1.2).
Consolidates memories across sessions:
- Prunes duplicate or conflicting memory entries
- Reconciles outdated facts against the current workspace
- Regenerates and sorts the MEMORY.md index
- Enforces read-only shell boundaries outside .julius/memory/
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .auto_memory import AutoMemoryManager, MemoryRecord

logger = logging.getLogger(__name__)


@dataclass
class DreamConsolidationReport:
    success: bool
    memories_reviewed: int
    duplicates_merged: int
    obsolete_pruned: int
    memories_retained: int
    duration_ms: float
    details: str = ""


class AutoDreamEngine:
    """Consolidation engine that audits and prunes auto-memories in the background."""

    def __init__(
        self,
        workspace_root: Optional[str] = None,
        memory_manager: Optional[AutoMemoryManager] = None,
        min_sessions_threshold: int = 5,
        min_hours_threshold: float = 24.0,
    ) -> None:
        self.workspace_root = Path(workspace_root or ".").resolve()
        self.manager = memory_manager or AutoMemoryManager(workspace_root=str(self.workspace_root))
        self.min_sessions_threshold = min_sessions_threshold
        self.min_hours_threshold = min_hours_threshold
        self.state_file = self.manager.memory_dir / ".dream_state.json"

    def _load_state(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"session_count": 0, "last_dream_timestamp": 0.0}

    def _save_state(self, state: Dict[str, Any]) -> None:
        try:
            self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Failed to save dream state: {exc}")

    def record_session(self) -> None:
        """Increment session counter towards consolidation threshold."""
        state = self._load_state()
        state["session_count"] = state.get("session_count", 0) + 1
        self._save_state(state)

    def should_dream(self) -> Tuple[bool, str]:
        """Check if session threshold or elapsed time qualifies for consolidation."""
        state = self._load_state()
        sessions = state.get("session_count", 0)
        last_ts = state.get("last_dream_timestamp", 0.0)
        elapsed_hours = (time.time() - last_ts) / 3600.0 if last_ts > 0 else 999.0

        if sessions >= self.min_sessions_threshold:
            return True, f"{sessions} sessions reached threshold ({self.min_sessions_threshold})"
        if elapsed_hours >= self.min_hours_threshold and len(self.manager.list_memories()) > 2:
            return True, f"{elapsed_hours:.1f}h elapsed since last dream"
        return False, f"Idle ({sessions}/{self.min_sessions_threshold} sessions, {elapsed_hours:.1f}h elapsed)"

    def run_dream_consolidation(self, force: bool = False) -> DreamConsolidationReport:
        """
        Execute memory consolidation:
        - Reviews all memory records.
        - Identifies near-duplicate titles and merges their contents.
        - Verifies paths against current repository; flags obsolete memories.
        - Regenerates the MEMORY.md index.
        """
        start_time = time.time()
        if not force:
            qualifies, reason = self.should_dream()
            if not qualifies:
                return DreamConsolidationReport(
                    success=True,
                    memories_reviewed=0,
                    duplicates_merged=0,
                    obsolete_pruned=0,
                    memories_retained=len(self.manager.list_memories()),
                    duration_ms=0.0,
                    details=f"Skipped: {reason}",
                )

        logger.info("[AutoDream] Starting memory consolidation pass...")
        records = self.manager.list_memories()
        reviewed_count = len(records)
        duplicates_merged = 0
        obsolete_pruned = 0

        # Group by normalized title/slug to find duplicates
        seen_keys: Dict[str, MemoryRecord] = {}
        to_remove: List[str] = []

        for rec in records:
            # Check if reference is totally obsolete (e.g. references file deleted long ago)
            is_valid, reason = self.manager.verify_memory_against_workspace(rec)
            if not is_valid and rec.memory_type == "reference":
                logger.info(f"[AutoDream] Pruning obsolete reference: {rec.slug} ({reason})")
                to_remove.append(rec.slug)
                obsolete_pruned += 1
                continue

            norm_title = rec.title.lower().replace('-', ' ').replace('_', ' ').strip()
            if norm_title in seen_keys:
                primary = seen_keys[norm_title]
                # If primary has -dup or -copy in slug, swap so the cleaner slug is kept as primary
                if ("dup" in primary.slug or "copy" in primary.slug) and not ("dup" in rec.slug or "copy" in rec.slug):
                    to_remove.append(primary.slug)
                    merged_content = rec.content + "\n\n" + primary.content
                    rec.content = merged_content
                    seen_keys[norm_title] = rec
                    self.manager.save_memory(
                        slug=rec.slug,
                        title=rec.title,
                        description=rec.description,
                        memory_type=rec.memory_type,
                        content=rec.content,
                        why=rec.why,
                        how_to_apply=rec.how_to_apply,
                    )
                else:
                    merged_content = primary.content + "\n\n" + rec.content
                    primary.content = merged_content
                    to_remove.append(rec.slug)
                    self.manager.save_memory(
                        slug=primary.slug,
                        title=primary.title,
                        description=primary.description,
                        memory_type=primary.memory_type,
                        content=primary.content,
                        why=primary.why,
                        how_to_apply=primary.how_to_apply,
                    )
                duplicates_merged += 1
            else:
                seen_keys[norm_title] = rec

        # Execute removals
        for slug in to_remove:
            self.manager.remove_memory(slug)

        # Update dream state
        state = self._load_state()
        state["session_count"] = 0
        state["last_dream_timestamp"] = time.time()
        self._save_state(state)

        duration = (time.time() - start_time) * 1000.0
        retained = len(self.manager.list_memories())

        report = DreamConsolidationReport(
            success=True,
            memories_reviewed=reviewed_count,
            duplicates_merged=duplicates_merged,
            obsolete_pruned=obsolete_pruned,
            memories_retained=retained,
            duration_ms=duration,
            details=f"Consolidated {reviewed_count} memories -> {retained} retained ({duplicates_merged} merged, {obsolete_pruned} pruned) in {duration:.1f}ms",
        )
        logger.info(f"[AutoDream] Consolidation completed: {report.details}")
        return report
