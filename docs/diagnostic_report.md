# Julius Deep Diagnostic — Self-Audit Report

This report documents the deep diagnostic audit of Julius's core loop, safety mechanisms, memory system, tool orchestration, observability, failure recovery, and research-readiness.

---

## 1. Core Loop Integrity

### 1.1 Step-by-Step Task Lifecycle

When a task is received, the agent execution flows through the following functions in order:

1. **Task Initialization**:
   - `WebAgent.run(task, ...)` in [web_agent.py](src/web_agent.py#L241) is called with the user prompt.
   - `lint_prompt(task)` in [prompt_linter.py](src/prompt_linter.py#L10) normalizes typos/whitespace.
   - `self._setup_safety()` sets up `SIGINT` handlers, keyboard listeners for the abort hotkey, and PyAutoGUI failsafes.
   - `self.memory.start_task(task)` in [engine.py](src/memory/engine.py#L247) records the task state in SQLite database as `in_progress`.

2. **Subsystem Startup**:
   - `self._initialize_llm()` connects to the browser-based chat LLM client.
   - `self.mcp_manager.start()` launches configured Model Context Protocol servers.
   - `self.browser_engine.start()` initializes Playwright.
   - `self.figma_bridge.start()` initializes Figma plugin connections.

3. **Step Loop** (`for step_num in range(1, max_steps + 1)`):
   - **Prompt Assembly**: If `step_num == 1`, compiles `initial_prompt` (system prompt + skills + workspace status). If `step_num > 1`, compiles `build_step_prompt` with the previous action result, directory listings, and plan updates.
   - **Perception Integration**: If `use_perception` is enabled, calls `self._get_perception_context()` which calls local capture, OmniParser visual analysis, and DOM fusion.
   - **LLM Call**: Calls `self.client.send_message(prompt)` to send reasoning instructions to the model.
   - **Action Parsing**: Calls `self._parse_action(response)` to parse JSON code blocks from the raw response.
   - **Schema Validation**: Calls `validate_action(action_data)` in [response_validator.py](src/response_validator.py#L86) to verify key presence.
   - **Safety Check**: Calls `validate_action_safety` in [agent_prompts.py](src/agent_prompts.py) and `self.executor._policy.evaluate_action(...)` in [security_policy.py](src/security_policy.py#L95).
   - **Dispatch**: Dispatches the action:
     - Browser actions: `browser_dispatch(...)`
     - Figma actions: `figma_dispatch(...)`
     - MCP actions: `self.mcp_manager.execute_tool(...)`
     - Native executor actions: runs `self.executor.execute(...)` inside a separate thread pool.
   - **Failure Handler**: If the action fails, calls `self._handle_step_failure(...)` to increment failure count and re-prompt or escalate.
   - **Termination Check**: If the action is `done` or `converse`, breaks the loop.

4. **Task Teardown**:
   - Commits deferred file writes using `self.executor.commit_deferred_writes()`.
   - Calls `self.memory.complete_task(...)` to record success and write database summaries.
   - Gracefully shuts down Playwright, Figma bridge, and LLM clients.
   - Saves structured steps log file via `_save_step_history(...)`.

---

### 1.2 LLM Response Parse Failure

If the LLM response fails to parse as valid JSON, the code path is as follows:

1. `self._parse_action(response)` in `web_agent.py` returns `None`.
2. The agent executes the following check:
   ```python
   # src/web_agent.py line 526
   if action_data is None:
       err_msg = 'ERROR: Your response did not contain valid JSON...'
       last_result = await self._handle_step_failure(
           action='parse_error',
           ...
       )
       continue
   ```
3. Inside `_handle_step_failure` (lines 1375–1390), the action `'parse_error'` is explicitly excluded from incrementing consecutive failures:
   ```python
   if action not in ('parse_error', 'validation_error'):
       session_state.consecutive_failures += 1
   ```
   This means **the loop does not crash** and **does not count this as a failure** toward the human intervention limit.
4. The handler returns a formatted error correction instruction (`build_error_prompt(...)`), and the step loop invokes `continue` to request the correction in the next LLM step.

---

### 1.3 `max_steps` Exceeded Mid-Task

If `max_steps` is reached:
- The loop exits. `stop_reason` is set to `'max_steps'` and the success flag in `AgentResult` evaluates to `False`.
- The caller is explicitly warned (`Status: Failed | Summary: Agent reached maximum step limit.`).
- **Memory Preservation**: The memory engine completion hooks (`complete_task` or `fail_task`) are **never called**. The task remains in the database in a permanent `'in_progress'` status.
- **Workspace State**: Since `deferred_writes` is `False` by default, any file modifications made during steps 1 to `max_steps` are immediately written to disk and saved. However, if `deferred_writes` is set to `True`, all file modifications are buffered in-memory and **lost** because `commit_deferred_writes` is only called inside the `done` block.

---

### 1.4 Repeated Action Looping

- The agent has a `consecutive_failures` tracking system inside `_handle_step_failure()`.
- If a real action (e.g. `run_bash` or `edit_file`) fails consecutively, `consecutive_failures` increments.
- When it reaches `prompts_config.max_consecutive_failures` (default is `2`), the loop halts and prompts the human user:
  ```python
  if session_state.consecutive_failures >= prompts_config.max_consecutive_failures:
      human_result = await self.handle_ask_human("I have encountered 2 consecutive errors... How should I proceed?")
  ```
- If the agent is run in an unattended non-interactive console environment (e.g., CI/CD), `handle_ask_human` receives a default failure response, resets the counter, and the loop keeps trying the failing action in cycles until `max_steps` is exhausted.

---

### 1.5 Concurrency and Blocking Risks

- Execution is **strictly serial**. One action runs after another in a single-threaded task loop.
- If a single action hangs, the timeout behavior is action-specific:
  - `run_bash` has a timeout of `self.bash_timeout` (defaults to 60s).
  - `ask_human` has no timeout and blocks indefinitely.
  - MCP tool requests have a timeout of 120.0s (defined in `MCPBridge`).

---

## 2. Execution Safety

### 2.1 Code and Command Execution Actions

| Action Type | Execution Target | Sandbox Isolation |
|-------------|------------------|-------------------|
| `run_bash` | Host Shell (Native Subprocess) | None (runs directly on the host host) |
| `git` | Host Shell | None (wraps `run_bash`) |
| `browser_eval_js` | Playwright Browser Process | None (runs natively inside Chromium on host) |
| MCP tools | Subprocess on Host | None (runs via local node/npx processes) |

---

### 2.2 Destructive Action Classification

Destructive actions are defined in [src/agent_config.py](src/agent_config.py#L43-L48):
```python
DESTRUCTIVE_ACTIONS: frozenset[str] = frozenset({
    'run_bash',
    'write_file',
    'edit_file',
    'git',
})
```
- Confirmation is triggered for any action in this list if `confirm_destructive_only` is enabled, or any action not in `SAFE_ACTIONS` if it is disabled.
- **Safety gaps**:
  1. The system does not parse commands inside `run_bash` for danger, relying on a basic regex check in `SecurityPolicy.is_command_safe` (blocks root delete `rm -rf /` and `.ssh` directories). Specific destructive actions like dropping database tables or deleting files are allowed.
  2. Figma write actions and custom write/delete actions in MCP tools are not classified in `DESTRUCTIVE_ACTIONS` and can run without confirmation in destructive modes.
  3. UAR policies check namespaced action names (like `version_control/PUSH` or `terminal/RUN_COMMAND`), but the agent dispatches `'git'` and `'run_bash'`, rendering the default safety policies rules ineffective.

---

### 2.3 Process Crash Behavior

If the process is hard-killed (e.g., `kill -9`):
- **Orphaned Containers**: None, because `run_bash` executes directly on the host rather than in Docker.
- **Partially Written Files**: If killed during file writes:
  - The target file may be left in a corrupted or truncated state.
  - A `.bak` backup file (created on line 343 of `action_executor.py`) is left behind.
- **Uncommitted Memory**: The SQLite database remains uncorrupted thanks to its transactional nature and WAL mode, but the active task is permanently stuck with an `'in_progress'` status in `task_memory`.

---

### 2.4 Hardcoded Credentials and Secrets

A grep scan of the repository reveals the following hardcoded API keys:

1. **Google Fonts API Key**:
   In [src/native_ts/npxskillui/src/font-resolver.ts:12](src/native_ts/npxskillui/src/font-resolver.ts#L12):
   ```typescript
   const GOOGLE_FONTS_API_KEY = 'AIzaSy[REDACTED_GOOGLE_FONTS_API_KEY]';
   ```
2. **Chrome UX Report API Key**:
   In `chrome-devtools-mcp-main/src/tools/performance.ts`:
   ```typescript
   'https://chromeuxreport.googleapis.com/v1/records:queryRecord?key=AIzaSy[REDACTED_API_KEY]',
   ```

---

## 3. Memory System

### 3.1 Implemented SQLite Schema

The implemented schemas in `.julius/memory.db` are:
- `agent_state`: Holds agent metadata.
- `task_memory`: Tracks active tasks and summaries.
- `conversation_turns`: Records raw session dialogue.
- `conversation_summaries`: Stores dialogue summaries.
- `episodic_notes`: Records daily episodic notes.
- `semantic_facts`: Tracks general knowledge key-values.
- `execution_graph_nodes` & `execution_graph_edges`: Concepts graph.
- `working_memory_snapshots`: State snapshots.

**Divergence**: There is no schema or table for research experiments (no `hypothesis`, `mechanism`, `metrics` columns), and the retrieval pipeline is write-heavy and unused during agent reasoning turns.

---

### 3.2 Past Memory Verbatim Entries

Three verbatim entries from the SQLite database:
1. `task_memory` row:
   `('15e0bb44-e9ed-4d92-9bf5-1317ad0a236b', 'Completed test task', 'completed', '[]', '[]', '[]', None, 1784705332.28087, 1784705332.281112)`
2. `conversation_summaries` row:
   `(1, '15e0bb44-e9ed-4d92-9bf5-1317ad0a236b', 'Completed test task', 0, 1784705332.281301)`
3. `semantic_facts` row:
   `(1, 'test_key', 'test_value', 'test', 1.0, 1784705332.2837381, 1784705332.2837381)`

The schemas are structured, but the values and text summaries inside are unstructured text.

---

### 3.3 Memory Limits and Pruning

- Memory grows **unbounded**. There is no pruning, vacuuming, or deduplication logic.
- As entries scale, SQLite keyword matching operations will become slower and return less relevant context.

---

### 3.4 Research-Recall (Stage 2) State

- **Stage 2 was not completed** because it was blocked by the Stage 1 Docker requirement. There is no `query_prior_experiments` action or research database table in the codebase.

---

### 3.5 Workspace vs. Global Isolation

- Memory databases are created at the path `.julius/memory.db` relative to the current workspace root.
- If the agent changes projects but starts within the same folder, it will share the database, potentially leaking previous task details.

---

## 4. Tool & Action Orchestration

### 4.1 Actions Summary

- **Input Validation**: Verified through structural argument checks in `response_validator.py`.
- **Error Handling**: Wrapped in generic execution catch blocks returning failed `ActionResult` shapes.
- **Expected Output Shape**: Documented and verified as `ActionResult` or `BrowserObservation`.

---

### 4.2 MCP Server Failures

- Inside `bridge.call_tool` (in [src/mcp/bridge.py](src/mcp/bridge.py#L188)), exceptions are caught:
  ```python
  except Exception as exc:
      return MCPBridgeResult(success=False, output=f'MCP tool error: {exc}')
  ```
- If an MCP server is down or returns invalid data, the exception is converted to a failed result, allowing the agent to degrade gracefully.

---

### 4.3 Action Suitability Checks

- There is no logic in the execution engine to decide if a tool is suitable. The agent relies entirely on the LLM's own capacity to read failure feedback and try another tool on the next turn.

---

### 4.4 Playwright Browser Recovery

- Browser actions are wrapped in `ActionRetryPolicy` inside [src/browser/engine.py](src/browser/engine.py#L258).
- If a page hangs or throws a `PlaywrightTimeoutError`, the policy retries execution up to 3 times using exponential backoff before returning a failed `BrowserObservation`.

---

## 5. Observability & Debuggability

### 5.1 Step History Logs

Every session saves a structured JSON step history at `~/.julius/logs/session_YYYYMMDD_HHMMSS_steps.json`.

**Verbatim log excerpt** (from `session_20260714_203239_steps.json`):
```json
[
  {
    "step": 1,
    "thought": "The user wants me to test their new 'perspection layer'...",
    "action": "set_task_title",
    "args": { "title": "Test..." },
    "result": "Set task title to...",
    "success": true,
    "timestamp": "2026-07-14T20:29:20.435308",
    "duration_ms": 6482
  }
]
```

---

### 5.2 Structured vs Free-text Logs

- Structured JSON logs are saved containing the raw session trace and execution details.
- Standard output printed on the console is free-text.

---

### 5.3 Cost & Token Tracking

- Token counts are tracked locally for direct API calls (stored in `.kimi_daily_usage.json` for Kimi), but they are not tracked for browser-driven chat providers.
- There is no pricing data or cost calculations saved, making it impossible to answer how much a run cost from actual data.

---

### 5.4 Thought-Action Contradictions

- If the agent reasoning contradicts its action args, this passes through **silently**. The executor only validates the action block syntax.

---

## 6. Failure Recovery

### 6.1 Specialized Retry Policies

- Browser actions retry automatically on network/timeout errors.
- SQLite connections retry automatically on database locking errors (`SQLITE_BUSY`).
- Unsuccessful command executions can trigger the `SelfHealer` class to resolve compilation issues.

---

### 6.2 Git Operation Failures

- Git conflicts are not automatically resolved or detected. Conflict markers are left in workspace source files, which must be resolved manually or by the LLM in subsequent turns.

---

### 6.3 Heartbeats & Watchdogs

- There is no watchdog monitor or dead-man's-switch to terminate long-running stuck processes.

---

## 7. Research-Readiness Follow-up

### 7.1 Upgrade Stage Status

- **Stage 0 (Audit)**: Completed & verified.
- **Stage 1 (Sandbox)**: Not started (blocked by missing Docker).
- **Stage 2 (Memory)**: Not started.
- **Stage 3 (Critique)**: Not started.
- **Stage 4 (Comparison)**: Not started.

---

### 7.2 & 7.3 Live Run Verification

- **Blocked**: Cannot execute sandboxed container runs or baseline comparisons because Docker is not available on this macOS host.

---

### 7.4 Abandoned or Modified Plans

- Stages 1 to 4 were **paused** due to the missing Docker dependency. No modifications to skip sandboxing were attempted, honoring the plan rules.

---

## 8. Own Assessment

### 8.1 Critical Failure Vulnerabilities

- **Unattended hangs**: The lack of a timeout on interactive `ask_human` blocks means the agent will hang indefinitely in non-interactive environments unless `stdin` is closed.
- **Bypassed safety rules**: The mismatch between rule names in the safety policy and native agent actions means critical commands like force-pushes or file deletion bypass safety prompts.

---

### 8.2 Architectural Claims vs. Reality

1. **Sandboxing**: Claimed containerization does not run; commands run unsandboxed on the host.
2. **Research Memory**: Claimed 9-tier retrieval system does not run; loop execution is write-only.
3. **Permissions**: Claimed capability token permissions do not exist.
