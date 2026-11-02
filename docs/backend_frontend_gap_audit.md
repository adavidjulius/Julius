# Julius Diagnostic: Backend Interaction Points Needing Frontend UI

## Executive Summary
This document provides an evidence-based audit of all points where the backend expects to communicate with or wait on the user, comparing backend event emissions and blocking calls against actual frontend (`v3_tui.py`, `v2_tui.py`, `src/tui/app.py`) rendering handlers.

---

## 1. Every Point Where the Backend Blocks Waiting on the User

### 1.1 `ask_human` Call Sites Audit

| Call Site File & Line | Trigger Condition | Data Sent | Frontend Event Emitted | Frontend Rendering Handler (`v3_tui.py`) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `src/web_agent.py:365-372` | LLM outputs action `ask_human` during agent loop | `question: str`, `options: list[str]` | `ask_user_question` | `_handle_agent_event` renders `q_panel` and `QuestionOptionList` | **HANDLED** |
| `src/web_agent.py:409-413` | Autonomous self-heal fails after max attempts (`self_heal_attempts`) | `f"Self-heal exhausted after {len(heal_log)} attempts...\nWhat should I do next?"` | **NONE** (Calls `self.executor.ask_human()` synchronously) | **NONE** — No event emitted; calls raw Python `input()` on `sys.stdin` | **CRITICAL BUG (SESSION FREEZE)** |
| `src/self_healer.py:108` | Unrecoverable error during fix analysis | Escalates to caller (`web_agent.py`) | **NONE** | **NONE** — Escalates to `web_agent.py:409`, triggering raw `input()` | **CRITICAL BUG (SESSION FREEZE)** |
| `src/action_executor.py:518` | Direct execution of `ask_human` | `question: str` | **NONE** | Prints to stdout and calls `input('Your answer: ')` | **UNHANDLED IN TUI/GUI** |

> [!CAUTION]
> **Critical Audit Finding**: `src/web_agent.py:409` directly calls `self.executor.ask_human()` when self-healing exhausts retries. Because `self.executor.ask_human()` executes synchronous `input()`, it blocks Python's `sys.stdin` underneath the Textual TUI. No UI widget is rendered, and the TUI freezes indefinitely.

---

### 1.2 Destructive-Action Confirmation Path Audit

- **Policy Definition**: `DESTRUCTIVE_ACTIONS = frozenset({'run_bash', 'write_file', 'edit_file', 'git'})` in `src/agent_config.py`.
- **Confirmation Logic**: `AgentConfig.needs_confirmation(action_name)` returns `True` when `confirm_actions=True` (default).
- **Event Emitted**: `confirm_action` (`self._emit('confirm_action', action=action_name, args=args)`).
- **Data Shape**: `{"type": "confirm_action", "action": str, "args": dict}`.
- **Frontend Coverage (`v3_tui.py`)**:
  - `_handle_agent_event` listens for `event_type == "confirm_action"`.
  - Renders `Panel` title `"Action Gate"` and populates `QuestionOptionList` with `[y] Accept Action` and `[n] Decline Action`.
  - Sets `self._pending_confirmation = True`.
- **Gap Identified**:
  - In `WebAgent._get_human_confirmation` (`src/web_agent.py:845-855`), if `self.on_event` callback is not registered (or in fallback CLI modes), `_get_human_confirmation` falls back to synchronous `input(prompt_str)`.
  - In non-TTY background tasks or subagent invocations, `input()` throws `EOFError` or blocks, silently declining actions or hanging execution.

---

### 1.3 Other Blocking & Response-Awaiting Backend Events

1. **Task Resumption Disambiguation (`src/web_agent.py:541-572`)**:
   - **Behavior**: When multiple active tasks exist for a project, the backend loops over `active_tasks` and picks the first matching task or automatically archives non-matching tasks.
   - **Gap**: The backend never emits an event asking the user *which* task they intended to resume. It silently makes an arbitrary choice or archives state without user confirmation.
2. **`/plan` Implementation Approval Gate**:
   - **Behavior**: `/plan` mode generates a plan.
   - **Gap**: There is no explicit `plan_approval_requested` event emitted by the backend loop. Approval relies on manual user follow-up prompt `/act`.
3. **App Builder Verification & Deployment Gate (`src/app_builder/builder.py`)**:
   - **Behavior**: Generates full-stack app, executes npm install, starts server, takes Playwright screenshot, and exercises features.
   - **Gap**: Emits `pipeline` events but provides no interactive approval gate for the user to review the Playwright screenshot or confirm deployment.

---

## 2. Every Event Type Emitted by the Backend

| Source Module | Event Name | Emitted Payload / Data Shape | Frontend Handling (`v3_tui.py`) | Status |
| :--- | :--- | :--- | :--- | :--- |
| `web_agent.py` | `thought` | `{"type": "thought", "text": str}` | Appends to `CollapsibleThinkingPanel` | **HANDLED** |
| `web_agent.py` | `ask_user_question` | `{"type": "ask_user_question", "question": str, "options": list}` | Renders question panel & option list | **HANDLED** |
| `web_agent.py` | `confirm_action` | `{"type": "confirm_action", "action": str, "args": dict}` | Renders action gate card & option list | **HANDLED** |
| `web_agent.py` | `action` | `{"type": "action", "name": str, "args": dict}` | Renders diff for `write_file`/`edit_file` | **PARTIAL** |
| `web_agent.py` | `status` | `{"type": "status", "message": str, "provider": str}` | **Ignored** (no status bar update) | **DROPPED** |
| `web_agent.py` | `step_start` | `{"type": "step_start", "step": int, "max_steps": int}` | **Ignored** | **DROPPED** |
| `web_agent.py` | `stream` | `{"type": "stream", "text": str}` | **Ignored** | **DROPPED** |
| `web_agent.py` | `stream_end` | `{"type": "stream_end"}` | **Ignored** | **DROPPED** |
| `web_agent.py` | `error` | `{"type": "error", "message": str}` | **Ignored** | **DROPPED** |
| `web_agent.py` | `result` | `{"type": "result", "output": str, "success": bool}` | **Ignored** | **DROPPED** |
| `web_agent.py` | `heal_start` | `{"type": "heal_start", "command": str}` | **Ignored** | **DROPPED** |
| `web_agent.py` | `heal_success` | `{"type": "heal_success", "summary": str}` | **Ignored** | **DROPPED** |
| `web_agent.py` | `heal_failed` | `{"type": "heal_failed", "summary": str}` | **Ignored** | **DROPPED** |
| `web_agent.py` | `done` | `{"type": "done", "summary": str}` | **Ignored** | **DROPPED** |
| `web_agent.py` | `converse` | `{"type": "converse", "message": str}` | **Ignored** | **DROPPED** |
| `web_agent.py` | `finished` | `{"type": "finished", "success": bool, "summary": str, ...}` | **Ignored** | **DROPPED** |
| `self_healer.py` | `heal_step` | `{"type": "heal_step", "attempt": int, "status": str, ...}` | **Ignored** | **DROPPED** |
| `builder.py` | `pipeline` | `{"stage": str, "message": str}` | **Ignored** (uses `stage` key instead of `type`) | **DROPPED** |

---

## 3. Backend Feature Surfaces Lacking Complete Frontend Counterparts

1. **Self-Healing Diagnostics (`src/self_healer.py`)**:
   - Backend performs up to 3 autonomous fix iterations when bash commands fail.
   - Frontend drops all `heal_start`, `heal_step`, `heal_success`, `heal_failed` events. The user sees no visual indication that self-healing is active.
2. **Task Resumption State (`WorkingStateManager`)**:
   - CLI command `/resume` shows task ID, goal, last state, next subtask.
   - **Gaps**: Does not display `blockers` array, `completed_subtasks` history, `files_in_progress` list, or `session_count`.
3. **Research Experiment History (`MemoryStorage`)**:
   - CLI command `/experiments` shows experiment ID, hypothesis, outcome.
   - **Gaps**: Omits `mechanism_description`, `nearest_known_architecture`, and full `result_metrics` JSON object.
4. **System Health Status (`/status`)**:
   - `/status` checks `shutil.which("docker")` and LLM provider.
   - **Gaps**: Hardcodes sandbox status (`/tmp/sandbox`) regardless of actual container health; does not report container memory allocation or Docker daemon responsiveness.
5. **Full-Stack App Generator (`src/app_builder/builder.py`)**:
   - Backend contains full multi-stage web application generator.
   - **Gaps**: No TUI command or UI view exists to initiate, monitor, or preview generated web applications.

---

## 4. Root Cause Analysis: The Approval-Prompt Bug

### Bug Description
When self-healing attempts are exhausted, the backend requests user direction (`"What should I do next?"`), but the session hangs with no prompt displayed.

### Precise Technical Cause
1. **Bypassed Event System**: In `src/web_agent.py` line 409, when `healed` is `False`, the code calls `human_result = self.executor.ask_human(...)` directly rather than invoking `await self._ask_user_question_async(...)`.
2. **Direct Synchronous I/O**: `self.executor.ask_human()` executes `input('Your answer: ')` on `sys.stdin`.
3. **TUI Stoppage**: Because Textual manages `sys.stdin` and terminal drawing, calling synchronous `input()` suspends event loop execution. No event (`ask_user_question`) is dispatched to `v3_tui.py`, no widget is rendered, and terminal input is captured by raw `input()`, freezing the session.

---

## 5. Severity Ranking & Structural Recommendations

### 5.1 Gap Severity Ranking

```
┌─────────────────────────────────────────────────────────────────────────┐
│ SEVERITY 1: CRITICAL (Session Freeze / Process Hang)                    │
├─────────────────────────────────────────────────────────────────────────┤
│ • Self-heal exhaustion calling synchronous ask_human() (web_agent.py)  │
│ • Unhandled ask_human() execution in ActionExecutor without TUI callback │
└─────────────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────────┐
│ SEVERITY 2: HIGH (Invisible Execution & Mismatched Contracts)          │
├─────────────────────────────────────────────────────────────────────────┤
│ • Self-healing progress events (heal_step) completely dropped           │
│ • App Builder events dropped due to schema mismatch (stage vs type)     │
│ • Silent task archiving during resumption without user selection        │
└─────────────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────────┐
│ SEVERITY 3: MEDIUM (Partial Feature Visibility)                         │
├─────────────────────────────────────────────────────────────────────────┤
│ • /resume missing blockers, completed subtasks, files in progress       │
│ • /experiments missing metrics and mechanism details                    │
│ • /status reporting hardcoded sandbox health                            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 5.2 Structural Process Recommendations

1. **Mandatory Event Registry & Schema Contract**:
   - Define an explicit `JuliusEvent` dataclass / Enum registry for all events emitted across `web_agent.py`, `self_healer.py`, and `builder.py`.
   - Standardize event schema to require `type: str` and `timestamp: float`.

2. **Strict Prohibition of Raw `input()` in Backend Modules**:
   - Ban `input()` calls inside `ActionExecutor` and `WebAgent`.
   - Require all human interaction to route through async futures resolved by the active UI layer (`_ask_user_question_async` or `_get_human_confirmation`).

3. **Frontend Event Exhaustiveness Unit Tests**:
   - Add automated test assertions verifying that every event type in `JuliusEvent` has a corresponding non-dropping handler in `v3_tui.py`.
