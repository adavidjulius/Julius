# Julius Limitations & Errors

## Current Limitations
- **Interactive MCP/tool permission prompts are invisible blockers** (ROADMAP #200). Workers that require user permission are marked as *blocked* and cannot proceed until the prompt is resolved.
- **Tool‑permission gating**: Added `tool_permission_required` worker status and event classification. Startup evidence now records `tool_permission_prompt_detected` and classifies timeout evidence as `tool_permission_required`.
- **Readiness snapshots** now mark tool‑permission‑gated workers as blocked, not ready/idle.
- **Test coverage gaps**: Full runtime test, clippy, and fmt checks are pending verification (see verification status in `progress.txt`).

## Reported Errors / Issues
- Workers may hang awaiting invisible permission prompts, causing timeout evidence and stalled pipelines.
- Some unit tests pass (11 passing) but integration/regression tests for the new permission handling are still failing or not yet executed.
- No explicit runtime exceptions are logged in the current logs, but the above functional blockers constitute operational errors.
