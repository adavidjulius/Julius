# Backend-Frontend Event Contract Fix Report

**Report Date**: 2026-08-06  
**Status**: COMPLETE (All Priority 1–5 Gaps Resolved and Verified)  
**File Path**: `docs/backend_frontend_fix_report.md`

---

## Executive Summary

All critical session-freeze bugs caused by synchronous `input()` calls, dropped backend event emissions, invisible feature gaps (task resumption, plan approval, app builder verification), incomplete CLI slash command views, and event schema contract risks have been resolved. An automated CI guard and frontend event exhaustiveness test suite have been established to prevent future regressions.

---

## Priority 1 — Eliminate raw `input()` calls (Session Freeze Resolution)

### 1a. `src/web_agent.py` — Self-Heal Exhaustion
- **Root Cause**: Previously called `self.executor.ask_human(...)` synchronously when self-healing exhausted retries, invoking Python's `input()` on `sys.stdin` and freezing Textual event loops.
- **Fix Applied**: Updated `web_agent.py` (lines 409–425) to strictly route self-heal exhaustion questions through `_ask_user_question_async`, emitting the `ask_user_question` event and awaiting future resolution via Textual widgets (`QuestionOptionList`).
- **TTY/Non-TTY Fallback**: Updated `_ask_user_question_async` so that when `on_event` is `None`:
  - Interactive TTY: Uses `loop.run_in_executor(None, sys.stdin.readline)` to avoid blocking the event loop.
  - Non-Interactive Console: Immediately returns non-blocking default string without waiting or hanging.

### 1b. `src/action_executor.py:518` — Direct `ask_human` Execution Path
- **Fix Applied**: Updated `ActionExecutor.ask_human` to check for registered `on_ask_human` callbacks or use `sys.stdin.readline()` non-blocking fallbacks. Removed raw `input()` calls.

### 1c. Automated CI Guard Enforcement
- **Guard Script**: Created [scripts/check_no_raw_input.py](scripts/check_no_raw_input.py).
- **Result**: Scans `web_agent.py`, `action_executor.py`, `self_healer.py`, and `builder.py`. Zero raw `input()` calls detected. Pass exit code `0`.

---

## Priority 2 — Stop Dropping Backend Events (100% Coverage)

Every backend event type has been registered in [src/event_registry.py](src/event_registry.py) and assigned an explicit non-dropping handler in [src/cli/v3_tui.py](src/cli/v3_tui.py). `builder.py` events have been normalized to emit standardized `{"type": "pipeline", "stage": stage, "message": message}` schemas.

### Pass/Fail Audit Table

| Source Module | Event Name | Payload Shape | Frontend Handler (`v3_tui.py`) | Status |
| :--- | :--- | :--- | :--- | :--- |
| `web_agent.py` | `thought` | `{"type": "thought", "text": str}` | Appends to live `CollapsibleThinkingPanel` | **PASSED** |
| `web_agent.py` | `ask_user_question` | `{"type": "ask_user_question", "question": str, "options": list}` | Renders question card & interactive options | **PASSED** |
| `web_agent.py` | `confirm_action` | `{"type": "confirm_action", "action": str, "args": dict}` | Renders action gate card & confirmation options | **PASSED** |
| `web_agent.py` | `action` | `{"type": "action", "name": str, "args": dict}` | Renders code diff panel for file mutations | **PASSED** |
| `web_agent.py` | `status` | `{"type": "status", "message": str, "provider": str}` | Updates top header status line (`sub_title`) | **PASSED** |
| `web_agent.py` | `step_start` | `{"type": "step_start", "step": int, "max_steps": int}` | Updates step counter badge (`Step X/Y`) | **PASSED** |
| `web_agent.py` | `stream` | `{"type": "stream", "text": str}` | Appends live tokens to thinking sub-panel | **PASSED** |
| `web_agent.py` | `stream_end` | `{"type": "stream_end"}` | Finalizes streaming block | **PASSED** |
| `web_agent.py` | `error` | `{"type": "error", "message": str}` | Renders styled red error alert panel | **PASSED** |
| `web_agent.py` | `result` | `{"type": "result", "output": str, "success": bool}` | Renders concise result status line (Success / Failure) | **PASSED** |
| `web_agent.py` | `heal_start` | `{"type": "heal_start", "command": str}` | Renders yellow self-healing start badge | **PASSED** |
| `self_healer.py` | `heal_step` | `{"type": "heal_step", "attempt": int, "max_attempts": int, ...}` | Renders `Self-healing... (attempt X/Y)` progress | **PASSED** |
| `web_agent.py` | `heal_success` | `{"type": "heal_success", "summary": str}` | Renders green self-healing success badge | **PASSED** |
| `web_agent.py` | `heal_failed` | `{"type": "heal_failed", "summary": str}` | Renders red self-healing failure notification | **PASSED** |
| `web_agent.py` | `done` | `{"type": "done", "summary": str}` | Renders task completion summary panel | **PASSED** |
| `web_agent.py` | `converse` | `{"type": "converse", "message": str}` | Renders conversational output panel | **PASSED** |
| `web_agent.py` | `finished` | `{"type": "finished", "success": bool, "summary": str}` | Renders final run metrics and summary line | **PASSED** |
| `builder.py` | `pipeline` | `{"type": "pipeline", "stage": str, "message": str}` | Renders app builder pipeline progress lines | **PASSED** |
| `web_agent.py` | `plan_approval_requested` | `{"type": "plan_approval_requested", "plan": str}` | Renders plan approval panel with options | **PASSED** |

---

## Priority 3 — Invisible Feature Gaps Resolved

1. **3a. Task Resumption Disambiguation**:
   - In `web_agent.py` (`_handle_startup_resumption`), when multiple active tasks exist (`len(active_tasks) > 1`), the agent emits an `ask_user_question` event listing active tasks. The user explicitly selects which task to resume or chooses to start a new task.
2. **3b. `/plan` Approval Gate**:
   - In `/plan` mode, after generating the plan, the backend emits a `plan_approval_requested` event. The TUI renders an approval panel (`"1. Approve & Execute Plan"`, `"2. Request Plan Revisions"`, `"3. Cancel Plan"`), gating execution behind user selection.
3. **3c. App Builder Verification Gate**:
   - In `builder.py`, Stage 4 screenshots and verification results emit `pipeline` verification progress events asking for explicit user approval before finalizing app deployment.

---

## Priority 4 — Partial Feature Visibility Surface Fixes

- **/resume**: Updated `_handle_resume_command()` in `v3_tui.py` to surface `blockers`, `completed_subtasks` count, `files_in_progress`, and `session_count`.
- **/experiments**: Updated `_handle_experiments_command()` in `v3_tui.py` to display `mechanism_description`, `nearest_known_architecture`, and `result_metrics`.
- **/status**: Updated `_handle_status_command()` in `v3_tui.py` to dynamically execute `docker info` and check container health rather than returning a fixed string.

---

## Priority 5 — Event Registry & Exhaustiveness Test Suite

1. **Event Registry**: Defined `JuliusEventType` Enum in [src/event_registry.py](src/event_registry.py) listing all 19 event types.
2. **Exhaustiveness Unit Test**: Created [tests/test_event_exhaustiveness.py](tests/test_event_exhaustiveness.py).
   - `test_all_backend_events_have_frontend_handlers`: Parses `v3_tui.py` AST and verifies 100% handler coverage.
   - `test_exhaustiveness_test_fails_on_missing_handler`: "Tests the test" by injecting an unhandled event type and asserting that the test fails loudly with a descriptive error message.

---

## Automated Verification Suite Results

```bash
$ PYTHONPATH=. pytest tests/test_event_exhaustiveness.py
collected 2 items
tests/test_event_exhaustiveness.py .. [100%]
2 passed in 0.27s

$ python3 scripts/check_no_raw_input.py
Auditing backend modules for prohibited raw input() calls...
PASS src/web_agent.py: Clean
PASS src/action_executor.py: Clean
PASS src/self_healer.py: Clean
PASS src/app_builder/builder.py: Clean
Audit PASSED: Zero raw input() calls found.

$ PYTHONPATH=. pytest scripts/verify_backend_frontend_fix.py
collected 3 items
scripts/verify_backend_frontend_fix.py ... [100%]
3 passed in 0.98s
```
