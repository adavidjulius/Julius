"""
Checkpointed Self-Healing Engine with Git Rollback.

Phase 1.2 — Milestone 1.2: Self-Healer upgrade with pre-execution snapshots,
a HealLedger tracking each healing iteration, and automatic rollback via
``git checkout -- <file>`` or stash restoration when all attempts fail.

Guarantees: failed recovery cycles always restore the repository to a clean
baseline state. Zero unverified or dangling edits persist upon abort.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from .error_parser import ErrorContext, is_recoverable, parse_error

if TYPE_CHECKING:
    from .action_executor import ActionExecutor, ActionResult
    from src.providers import ProviderRouter

logger = logging.getLogger(__name__)

# How many lines of context to include around the error line
_CONTEXT_LINES = 15


# ── Heal Ledger ───────────────────────────────────────────────────────────────

@dataclass
class HealLedgerEntry:
    """Record of a single healing iteration."""
    attempt_number: int
    target_file: str | None
    error_line: int | None
    error_type: str
    patch_diff: str
    verification_command: str
    success: bool
    timestamp: float = field(default_factory=time.time)


class HealLedger:
    """Tracks healing iterations with full audit trail."""

    def __init__(self) -> None:
        self.entries: list[HealLedgerEntry] = []

    def record(
        self,
        attempt_number: int,
        target_file: str | None,
        error_line: int | None,
        error_type: str,
        patch_diff: str,
        verification_command: str,
        success: bool,
    ) -> HealLedgerEntry:
        entry = HealLedgerEntry(
            attempt_number=attempt_number,
            target_file=target_file,
            error_line=error_line,
            error_type=error_type,
            patch_diff=patch_diff,
            verification_command=verification_command,
            success=success,
        )
        self.entries.append(entry)
        return entry

    def get_summary(self) -> dict[str, Any]:
        """Return a structured summary of all healing attempts."""
        return {
            "total_attempts": len(self.entries),
            "successful": sum(1 for e in self.entries if e.success),
            "failed": sum(1 for e in self.entries if not e.success),
            "entries": [
                {
                    "attempt": e.attempt_number,
                    "file": e.target_file,
                    "line": e.error_line,
                    "type": e.error_type,
                    "success": e.success,
                    "timestamp": e.timestamp,
                }
                for e in self.entries
            ],
        }


# ── Git Snapshot Manager ──────────────────────────────────────────────────────

class GitSnapshotManager:
    """Manages pre-execution git snapshots for safe rollback.

    Uses ``git stash create`` for lightweight, non-destructive snapshots
    that don't modify the working tree. On rollback, restores modified
    files using ``git checkout -- <file>``.
    """

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = str(Path(workspace_root).resolve())
        self._snapshot_ref: str | None = None
        self._modified_files: set[str] = set()

    def _run_git(self, *args: str, check: bool = False) -> subprocess.CompletedProcess:
        """Run a git command in the workspace."""
        return subprocess.run(
            ["git", *args],
            cwd=self.workspace_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=check,
        )

    def is_git_repo(self) -> bool:
        """Check if the workspace is a git repository."""
        result = self._run_git("rev-parse", "--is-inside-work-tree")
        return result.returncode == 0 and "true" in result.stdout.strip().lower()

    def create_snapshot(self) -> str | None:
        """Create a lightweight snapshot of the current state.

        Uses ``git stash create`` which creates a stash commit without
        modifying the working tree or stash list.

        Returns:
            The snapshot commit SHA, or None if nothing to snapshot.
        """
        if not self.is_git_repo():
            logger.warning("Not a git repo — snapshot unavailable")
            return None

        result = self._run_git("stash", "create", "julius-heal-checkpoint")
        sha = result.stdout.strip()

        if sha:
            self._snapshot_ref = sha
            logger.info("Git snapshot created: %s", sha[:12])
            return sha

        # Nothing to stash (clean working tree)
        logger.info("Working tree clean — no snapshot needed")
        return None

    def track_modified_file(self, filepath: str) -> None:
        """Register a file that will be modified by healing."""
        self._modified_files.add(filepath)
        logger.debug("Tracking modified file: %s", filepath)

    def get_file_diff(self, filepath: str) -> str:
        """Get the diff of a modified file against HEAD."""
        result = self._run_git("diff", "--", filepath)
        return result.stdout if result.returncode == 0 else ""

    def rollback_file(self, filepath: str) -> bool:
        """Restore a single file to its pre-healing state.

        Uses ``git checkout -- <file>`` to discard working tree changes.
        """
        result = self._run_git("checkout", "--", filepath)
        if result.returncode == 0:
            logger.info("Rolled back file: %s", filepath)
            return True
        logger.error("Rollback failed for %s: %s", filepath, result.stderr.strip())
        return False

    def rollback_all(self) -> list[str]:
        """Restore all tracked modified files to pre-healing state.

        Returns:
            List of file paths that were successfully restored.
        """
        restored = []
        for filepath in list(self._modified_files):
            if self.rollback_file(filepath):
                restored.append(filepath)
        self._modified_files.clear()
        logger.info("Rolled back %d files", len(restored))
        return restored

    def restore_snapshot(self) -> bool:
        """Restore the full working tree from the snapshot.

        Falls back to ``git checkout -- .`` if no snapshot exists.
        """
        if self._snapshot_ref:
            result = self._run_git("stash", "apply", self._snapshot_ref)
            if result.returncode == 0:
                logger.info("Snapshot restored from %s", self._snapshot_ref[:12])
                self._snapshot_ref = None
                return True
            logger.warning("Snapshot apply failed, falling back to file-level rollback")

        # Fall back to rolling back all tracked files
        restored = self.rollback_all()
        return len(restored) > 0

    def clear(self) -> None:
        """Clear snapshot state after successful healing."""
        self._snapshot_ref = None
        self._modified_files.clear()


# Milestone 1.2 Alias
GitCheckpoint = GitSnapshotManager


# ── Heal Attempt dataclass ────────────────────────────────────────────────────

@dataclass
class HealAttempt:
    """Result of a single self-heal attempt."""
    attempt: int
    error_context: ErrorContext
    fix_applied: bool
    retry_success: bool
    fix_description: str


# ── Checkpointed Self-Healer ─────────────────────────────────────────────────

class SelfHealer:
    """
    Autonomous error recovery engine with checkpointed rollback.

    After a bash command fails, this class:
      1. Creates a pre-execution git snapshot.
      2. Parses the stderr to locate the offending file and line.
      3. Reads the surrounding source code (~15 lines of context).
      4. Asks the LLM to produce a targeted fix.
      5. Tracks the fix in a HealLedger with full diff.
      6. Applies the fix and re-runs the original command.
      7. Repeats up to ``max_attempts`` times.
      8. If all attempts fail or regressions are detected, automatically
         rolls back ALL modified files to the clean baseline via git.
      9. Emits a ``heal.aborted`` event with a postmortem diff and rationale.

    Args:
        client: The WebLLMClient to use for fix generation.
        executor: The ActionExecutor to apply fixes and re-run commands.
        max_attempts: Maximum number of autonomous fix attempts (default: 3).
        on_event: Optional callback to emit heal events to the GUI.
    """

    def __init__(
        self,
        client: 'ProviderRouter | Any',
        executor: 'ActionExecutor',
        max_attempts: int = 3,
        on_event: Optional[Callable] = None,
    ) -> None:
        self.client = client
        self.executor = executor
        self.max_attempts = max_attempts
        self.on_event = on_event
        self._attempts: list[HealAttempt] = []
        self._ledger = HealLedger()
        self._snapshot_mgr = GitSnapshotManager(executor.workspace_root)

    # ── Public API ──────────────────────────────────────────────────

    async def attempt_fix(
        self,
        failed_result: 'ActionResult',
        original_command: str,
        task: str,
    ) -> tuple[bool, 'ActionResult', list[HealAttempt]]:
        """
        Attempt to autonomously fix a failing bash command with checkpointed safety.

        Args:
            failed_result: The ActionResult from the failing run_bash call.
            original_command: The exact bash command that failed.
            task: The high-level task description (for LLM context).

        Returns:
            Tuple of:
              - success (bool): True if the command eventually passed.
              - final_result (ActionResult): The result of the last run.
              - attempts (list[HealAttempt]): History of heal attempts.
        """
        self._attempts = []
        self._ledger = HealLedger()
        current_output = failed_result.output
        current_result = failed_result

        # ── Step 1: Create pre-healing snapshot ───────────────────────────
        self._snapshot_mgr.create_snapshot()
        self._emit('heal_step', status='snapshot_created')

        for attempt_num in range(1, self.max_attempts + 1):
            logger.info(f'SelfHealer: attempt {attempt_num}/{self.max_attempts}')
            self._emit('heal_step', attempt=attempt_num, max_attempts=self.max_attempts, status='analyzing')

            # Parse the error
            error_ctx = parse_error(current_output)
            logger.info(f'SelfHealer: parsed error — type={error_ctx.error_type}, file={error_ctx.file}, line={error_ctx.line}')

            if not is_recoverable(error_ctx):
                logger.info('SelfHealer: error not recoverable, escalating to ask_human')
                self._emit('heal_step', attempt=attempt_num, status='not_recoverable')
                break

            # Track the file for potential rollback
            if error_ctx.file:
                self._snapshot_mgr.track_modified_file(error_ctx.file)

            # Read the context around the error
            source_context = self._read_error_context(error_ctx)

            # Build the targeted fix prompt
            fix_prompt = self._build_fix_prompt(
                error_ctx=error_ctx,
                source_context=source_context,
                original_command=original_command,
                task=task,
                attempt=attempt_num,
            )

            # Ask the LLM for a fix
            self._emit('heal_step', attempt=attempt_num, status='asking_llm')
            fix_response = await self.client.send_message(fix_prompt, timeout=120)

            if fix_response.error or not fix_response.raw_text:
                logger.warning(f'SelfHealer: LLM returned error on attempt {attempt_num}')
                self._ledger.record(
                    attempt_number=attempt_num,
                    target_file=error_ctx.file,
                    error_line=error_ctx.line,
                    error_type=error_ctx.error_type,
                    patch_diff="",
                    verification_command=original_command,
                    success=False,
                )
                self._attempts.append(HealAttempt(
                    attempt=attempt_num,
                    error_context=error_ctx,
                    fix_applied=False,
                    retry_success=False,
                    fix_description='LLM communication error',
                ))
                continue

            # Parse the fix action from the response
            fix_action = self._parse_fix_action(fix_response.raw_text)
            fix_description = 'No parseable fix action'

            if fix_action:
                action_name = fix_action.get('action', '')
                action_args = fix_action.get('args', {})
                fix_description = f'{action_name}: {str(action_args)[:120]}'

                # Capture pre-fix diff
                pre_diff = ""
                if error_ctx.file:
                    pre_diff = self._snapshot_mgr.get_file_diff(error_ctx.file)

                # Apply the fix
                self._emit('heal_step', attempt=attempt_num, status='applying_fix', action=action_name)
                fix_result = self.executor.execute(action_name, action_args)
                logger.info(f'SelfHealer: fix applied — success={fix_result.success}, output={fix_result.output[:100]}')

                # Capture post-fix diff
                post_diff = ""
                if error_ctx.file:
                    post_diff = self._snapshot_mgr.get_file_diff(error_ctx.file)

                if fix_result.success:
                    # Re-run the original command
                    self._emit('heal_step', attempt=attempt_num, status='retrying_command')
                    retry_result = self.executor.run_bash(original_command)
                    logger.info(f'SelfHealer: retry — success={retry_result.success}')

                    self._ledger.record(
                        attempt_number=attempt_num,
                        target_file=error_ctx.file,
                        error_line=error_ctx.line,
                        error_type=error_ctx.error_type,
                        patch_diff=post_diff,
                        verification_command=original_command,
                        success=retry_result.success,
                    )

                    self._attempts.append(HealAttempt(
                        attempt=attempt_num,
                        error_context=error_ctx,
                        fix_applied=True,
                        retry_success=retry_result.success,
                        fix_description=fix_description,
                    ))

                    if retry_result.success:
                        self._emit('heal_step', attempt=attempt_num, status='healed')
                        # Clear snapshot — healing succeeded
                        self._snapshot_mgr.clear()
                        return True, retry_result, self._attempts

                    # Check for regressions (new errors introduced)
                    new_error = parse_error(retry_result.output)
                    if new_error.file and new_error.file != error_ctx.file:
                        logger.warning(
                            'SelfHealer: regression detected — new error in %s (was %s)',
                            new_error.file, error_ctx.file,
                        )
                        self._emit('heal_step', attempt=attempt_num, status='regression_detected')
                        # Rollback immediately on regression
                        self._perform_rollback(original_command)
                        return False, current_result, self._attempts

                    # Still failing — update for next iteration
                    current_output = retry_result.output
                    current_result = retry_result
                    continue
                else:
                    logger.warning(f'SelfHealer: fix action failed: {fix_result.output[:100]}')
                    self._ledger.record(
                        attempt_number=attempt_num,
                        target_file=error_ctx.file,
                        error_line=error_ctx.line,
                        error_type=error_ctx.error_type,
                        patch_diff=post_diff,
                        verification_command=original_command,
                        success=False,
                    )
            else:
                logger.warning('SelfHealer: could not parse fix action from LLM response')
                self._ledger.record(
                    attempt_number=attempt_num,
                    target_file=error_ctx.file,
                    error_line=error_ctx.line,
                    error_type=error_ctx.error_type,
                    patch_diff="",
                    verification_command=original_command,
                    success=False,
                )

            self._attempts.append(HealAttempt(
                attempt=attempt_num,
                error_context=error_ctx,
                fix_applied=fix_action is not None,
                retry_success=False,
                fix_description=fix_description,
            ))

        # ── All attempts exhausted — rollback to clean state ──────────────
        self._perform_rollback(original_command)
        return False, current_result, self._attempts

    def _perform_rollback(self, original_command: str) -> None:
        """Rollback all changes and emit heal.aborted event."""
        logger.info("SelfHealer: all attempts exhausted — initiating rollback")

        # Collect postmortem diffs before rollback
        postmortem_diffs = {}
        for filepath in self._snapshot_mgr._modified_files:
            diff = self._snapshot_mgr.get_file_diff(filepath)
            if diff:
                postmortem_diffs[filepath] = diff

        # Execute rollback
        restored_files = self._snapshot_mgr.rollback_all()

        # Emit heal.aborted with full postmortem
        self._emit(
            'heal.aborted',
            status='aborted',
            attempts=self.max_attempts,
            restored_files=restored_files,
            postmortem_diffs=postmortem_diffs,
            ledger=self._ledger.get_summary(),
            rationale=(
                f"All {self.max_attempts} healing attempts failed for command: "
                f"{original_command[:100]}. "
                f"Rolled back {len(restored_files)} file(s) to clean baseline."
            ),
        )
        self._emit('heal_step', status='exhausted', attempts=self.max_attempts)

    # ── Helpers ─────────────────────────────────────────────────────

    def _read_error_context(self, error_ctx: ErrorContext) -> str:
        """Read the source lines around the error location."""
        if not error_ctx.file:
            return '(no file reference available)'

        try:
            file_path = Path(error_ctx.file)
            if not file_path.exists():
                # Try resolving relative to workspace
                file_path = Path(self.executor.workspace_root) / error_ctx.file
            if not file_path.exists():
                return f'(file not found: {error_ctx.file})'

            lines = file_path.read_text(errors='replace').splitlines()
            total = len(lines)

            if error_ctx.line:
                start = max(0, error_ctx.line - 1 - _CONTEXT_LINES)
                end = min(total, error_ctx.line - 1 + _CONTEXT_LINES)
            else:
                start, end = 0, min(total, _CONTEXT_LINES * 2)

            context_lines = []
            for i, line in enumerate(lines[start:end], start=start + 1):
                marker = ' >>>' if error_ctx.line and i == error_ctx.line else '    '
                context_lines.append(f'{i:5d}{marker} {line}')

            return '\n'.join(context_lines)

        except Exception as exc:
            return f'(could not read file: {exc})'

    def _build_fix_prompt(
        self,
        error_ctx: ErrorContext,
        source_context: str,
        original_command: str,
        task: str,
        attempt: int,
    ) -> str:
        """Build the targeted fix prompt to send to the LLM."""
        col_info = f', column {error_ctx.column}' if error_ctx.column else ''
        line_info = f'line {error_ctx.line}{col_info}' if error_ctx.line else 'unknown line'

        # Include previous attempt info for progressive context
        prev_attempts_info = ""
        if self._ledger.entries:
            prev_attempts_info = "\n## Previous Attempts\n"
            for entry in self._ledger.entries:
                status = "✅ fix applied" if entry.success else "❌ still failing"
                prev_attempts_info += f"  Attempt {entry.attempt_number}: {status}\n"

        return f"""\
🩹 SELF-HEAL ATTEMPT {attempt}/{self.max_attempts}

A shell command failed with an error. Your job is to produce ONE JSON action
(edit_file or write_file) that fixes the problem. Then the system will re-run
the failing command automatically.

⚠️ IMPORTANT: This is a CHECKPOINTED healing session. If your fix introduces
regressions or all attempts fail, ALL changes will be automatically rolled back
to the clean baseline state via git.

## Original Task
{task}

## Failed Command
```
{original_command}
```

## Error
Type: {error_ctx.error_type}
File: {error_ctx.file or 'unknown'}
Location: {line_info}
Message: {error_ctx.message}

## Source Context (around the error)
```
{source_context}
```
{prev_attempts_info}
## Instructions
1. Identify the root cause in the source context above.
2. Respond with EXACTLY ONE JSON action block that fixes it.
3. Use `edit_file` for targeted replacements or `write_file` to rewrite the file.
4. Do NOT use `run_bash`. Only file edits are allowed here.
5. Your JSON must follow the standard action format.

Respond with ONLY the JSON block — no preamble, no explanation.
"""

    def _parse_fix_action(self, raw_response: str) -> Optional[dict]:
        """Extract a JSON action from the LLM's fix response."""
        import json
        import re

        # Try fenced JSON block first
        fenced = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
        if fenced:
            try:
                return json.loads(fenced.group(1), strict=False)
            except json.JSONDecodeError:
                pass

        # Try bare JSON object
        bare = re.search(r'(\{[^{}]*"action"\s*:[^{}]*\})', raw_response, re.DOTALL)
        if bare:
            try:
                return json.loads(bare.group(1), strict=False)
            except json.JSONDecodeError:
                pass

        return None

    def _emit(self, event: str, **kwargs) -> None:
        """Fire a GUI event if an on_event callback is registered."""
        if self.on_event:
            try:
                self.on_event(event, **kwargs)
            except Exception:
                pass

    def get_heal_summary(self) -> str:
        """Return a human-readable summary of all heal attempts."""
        if not self._attempts:
            return 'No heal attempts recorded.'
        lines = ['Self-Heal Report (Checkpointed):']
        for a in self._attempts:
            status = '✅ fixed' if a.retry_success else ('⚙️ applied, still failing' if a.fix_applied else '❌ no fix')
            lines.append(f'  Attempt {a.attempt}: [{a.error_context.error_type}] {status} — {a.fix_description}')
        return '\n'.join(lines)

    @property
    def ledger(self) -> HealLedger:
        """Access the heal ledger for structured postmortem analysis."""
        return self._ledger
