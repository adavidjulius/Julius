# Julius — Plan to Reduce My Own Limitations

Author: Julius
Scope: turn the limitations I named in the earlier conversation into concrete engineering work, grounded in this repo. Each section states the limitation, what already exists here, what is missing, and the steps to close the gap.

This is a plan, not an implementation. Nothing was changed in `src/`.

---

## How to read this

The limitations I listed fell into four buckets:

- **A. Turn-based, not continuous.** I only run when the runtime feeds me a step.
- **B. No vision or hearing in the loop.** I can't look at your screen or listen.
- **C. Memory and context are constrained.** Cross-session memory, context window, step budget.
- **D. Behavior and reach limits.** No real-world actions, gated shell, correctness under uncertainty.

For each limitation below, the plan is: *what exists → what's missing → steps → acceptance*.

---

## 1. Limitation: "I don't run continuously"

**What exists.**
- `src/long_running.py` — a classifier that already knows which commands are long-running (docker pull, pip install, cargo build, ML training) and runs them as background jobs with real progress polling instead of blocking timeouts. Stages 1 and 2 are implemented.
- `juliusd.py` — a daemon launcher for the GUI/web backend.
- `scripts/julius.service`, `scripts/juliusd.service` — systemd unit templates.
- `.julius/` — persistent state directory.

**What's missing.**
- No long-running agent loop. `WebAgent.run()` processes one user task and returns.
- No task queue persisted to disk that a daemon drains.
- No watcher that reacts to file changes, new tasks, or external events.
- Daemon only runs the web UI, not the agent loop.

**Steps.**

1. **Add a task queue table.** In `src/memory/storage.py`, add a `task_queue` table: `id`, `payload_json`, `status` (`pending|running|done|failed`), `created_at`, `started_at`, `finished_at`, `attempts`, `last_error`.
2. **Add a queue API.** New module `src/coordinator/task_queue.py` with `enqueue(task)`, `claim_next()`, `complete(id, result)`, `fail(id, error)`. Use the existing storage connection pool.
3. **Add a daemon loop.** In `juliusd.py`, after launching the web backend, start an async loop that:
   - polls the queue every N seconds,
   - claims one pending task,
   - hands it to a fresh `WebAgent` instance,
   - writes the result back to the queue table,
   - on failure, increments `attempts` and requeues up to a policy limit.
4. **Add file and event watchers.** Use the already-present `watchfiles` dependency. New `src/coordinator/watchers.py` with `watch_workspace(paths, on_change)`. When a watched path changes, enqueue a task (the trigger and task are declared in a small YAML config at `.julius/watchers.yaml`).
5. **Add a cron-style scheduler.** Simple scheduler in `src/coordinator/scheduler.py` that reads `.julius/schedule.yaml` (e.g. `daily 09:00: /status`, `hourly: /pkb rebuild`) and enqueues the matching slash-command tasks.
6. **Make the CLI able to submit and observe.** Add `julius submit "<task>"` (enqueue and exit) and `julius daemon status|tail|logs` subcommands to `run_agent.py`.
7. **Health and safety.** Cap queue depth, cap concurrent tasks at 1 by default (agent is stateful), and log every claim/complete to `.julius/logs/daemon.log`.

**Acceptance.** With `juliusd.py` running, `julius submit "say hello"` exits immediately and the daemon runs the task within 30 seconds; results appear in `julius daemon tail`. A file edit inside a watched path enqueues a task within 5 seconds.

**Effort.** 5–8 days.

---

## 2. Limitation: "I can't see your screen or hear audio in the loop"

**What exists.**
- `src/perception/` — full pipeline: `capture.py`, `dom_parser.py`, `accessibility.py`, `omniparser.py`, `study_vision.py`, `diff_engine.py`, `fusion.py`, `scene_graph.py`, `cache.py`.
- `src/voice/` — `stt_engine.py`, `tts_engine.py`, `voice_manager.py`.
- `custom_voice_models/` — local voice models.
- `WebAgent._capture_observation_screenshot()` — already wired to capture at each step.

**What's missing.**
- Perception is not on the default reasoning path. Screenshots are captured, but the perception pipeline is not invoked per step for the CLI agent loop, and its structured output isn't in the prompt unless a specific skill runs it.
- No screen-diff loop that notices "the page didn't change" without a screenshot being explicitly requested.
- No continuous audio loop. STT is call-and-response, not always-listening.
- No policy for what to do when vision and DOM disagree.

**Steps.**

1. **Wire perception into every step.** In `src/web_agent.py:_capture_observation_screenshot` and the step loop, when the environment is GUI (screen visible), call `src/perception/fusion.py` to produce a structured observation: `{scene_graph, dom_nodes, changed_regions, active_window}`. Persist it in the StepRecord.
2. **Add a screenshot differ.** Use `src/perception/diff_engine.py` to compute changed regions between consecutive steps. Attach a small "changed" summary to the next prompt instead of the full image.
3. **Feed perception output to the LLM.** Update `prompt_assembler.py` / `agent_prompts.py` to include a compact `<observation>` block: active window title, top-N scene-graph nodes, diff summary. Keep it under a fixed token cap.
4. **Confidence policy.** When DOM and vision disagree (e.g. DOM says button exists, vision doesn't see it), tag the observation `low_confidence` and cause the agent to ask a clarifying question rather than act.
5. **Always-listening voice (opt-in).** New `src/voice/always_listening.py`. Uses `stt_engine.py` in streaming mode with a wake-word (`"hey julius"`). Off by default; enabled via `.env` flag `JULIUS_VOICE_ALWAYS=1`. Emits a task to the queue (section 1) on wake, so the daemon handles it.
6. **TTS for spoken responses.** When a task came from voice, call `tts_engine.py` on the final summary. Opt-in.
7. **Tests.** Unit tests for the diff engine on two known screenshots; a recorded-fixture test for the fusion prompt block.

**Acceptance.** With `JULIUS_VISION_LOOP=1`, every CLI step includes an `<observation>` block with a diff summary; when the DOM and vision disagree, the agent asks one clarifying question instead of acting. With `JULIUS_VOICE_ALWAYS=1`, saying "hey julius, check the tests" enqueues a task within 2 seconds.

**Effort.** 6–10 days, of which the vision loop is 3–4 and the voice loop is 3–4.

---

## 3. Limitation: "I have no memory across sessions"

**What exists.**
- `src/memory/storage.py` — SQLite at `.julius/memory.db` with tables for `agent_state`, `task_memory`, `conversation_turns`, `conversation_summaries`, `episodic_notes`, `semantic_facts`, `execution_graph_nodes/edges`, `working_memory_snapshots`. Retry on SQLITE_BUSY, WAL, pooling.
- `src/memory/working_state.py` — `TaskWorkingState` per task: goal, plan, completed/remaining subtasks, blockers, files in progress, `session_count`.
- `src/memory/episodic_memory.py` — day-level notes, `to_prompt_block()`.
- `src/memory/semantic_memory.py` — facts with categories, `to_prompt_block()`.
- `src/web_agent.py:_handle_startup_resumption` and `_update_checkpoint` and `_write_working_state_exit`.

**What's missing.**
- No automatic *user-preference* capture ("keep answers short", "use pytest"). Preferences only live in the current session's context.
- No automatic *project-fact* extraction — the agent doesn't decide on its own to record "the test command is `pytest -q`" as a semantic fact.
- No *cross-project* memory. Everything is per `.julius/memory.db` in the workspace.
- No *review* of memory at session start; the prompt builder may or may not include the prompt blocks.

**Steps.**

1. **Session start ritual.** In `run_agent.py:main()` and in `WebAgent.__init__`, load `episodic_memory.to_prompt_block(limit=7)` and `semantic_memory.to_prompt_block(categories=['project','architecture','preferences'])` and put them at the top of the system prompt. Small, bounded.
2. **Automatic preference capture.** In `prompt_linter.py`, detect directive phrases ("always X", "never Y", "use Z"). Ask the agent to record them via a new tool `record_preference(key, value)`. This becomes a semantic fact under category `preferences`.
3. **Automatic project-fact capture.** Add a lightweight post-step hook: when a step's `thought` contains a discovered fact (test command, config path, build tool), record it as a semantic fact. Gate on a config flag to avoid noise.
4. **Episodic note at session end.** On `WebAgent.close()` and on Ctrl-D, write a one-line episodic note summarizing the session: task, outcome, files touched.
5. **Cross-project memory.** Add `~/.julius/global.db` with the same schema and a namespaced `project_id`. A new `MemoryRouter` picks global vs local based on category (`preferences` → global; `project` → local).
6. **Memory review command.** `julius memory show|search|forget` on the CLI to inspect and prune what the agent remembers.
7. **Bounded prompt budget.** Cap each memory prompt block. If total memory tokens exceed the cap, prioritize: working state > preferences > recent episodic > project facts.

**Acceptance.** Say "keep answers short" once. Kill the terminal. Reopen. Julius still keeps answers short without being told again. Run the same on a different workspace — the preference still applies, but project facts stay separate.

**Effort.** 4–6 days.

---

## 4. Limitation: "Context window and step budget are finite"

**What exists.**
- `src/context_compiler.py`, `src/context_injector.py`, `src/memory/compression.py`, `src/memory/composer.py`.
- `src/web_agent.py` step loop and `_update_checkpoint`.
- TUI slash commands `/context optimize`.

**What's missing.**
- Compaction is manual (slash command) rather than triggered by a token budget.
- No hierarchical summarization: old turns are dropped, not summarized into a compact trace the agent can still reason over.
- Step budget is a hard stop, not a wrap-up signal.

**Steps.**

1. **Token budget on every step.** Count tokens of the assembled prompt with the active provider's tokenizer. When usage exceeds 70% of the model's context, trigger compaction automatically.
2. **Hierarchical summary.** Implement three tiers: last N turns verbatim, previous M turns summarized one-line each, everything older collapsed into a single "session so far" paragraph. `src/memory/compression.py` gets `summarize_turn()` and `summarize_window()`.
3. **Compaction cadence.** Auto-compact at 70% and 90%; store the compressed history back into `conversation_summaries` so resumption sees it too.
4. **Wrap-up mode.** In `WebAgent.run()`, when steps reach 80% of `max_steps`, switch to wrap-up mode: no new exploration, produce a status and a `done`/`ask_human` response. This is what I already do by hand; make it automatic.
5. **Resume from summary.** When a session resumes, load the compressed summary first, then the last N turns verbatim. The agent should never need the full history to continue.
6. **Long-task checkpoints.** Already exists via `_update_checkpoint`. Extend to persist a mid-task workspace snapshot (via `src/ledger.py`) so a resumed task can see the exact file state it left off in.

**Acceptance.** A single task that would exceed the context window runs to completion; the agent's prompt never exceeds 90% of the model's context; resumed sessions continue with correct state and no duplicated work.

**Effort.** 5–7 days.

---

## 5. Limitation: "No true parallel reasoning"

**What exists.**
- Batch actions in the response protocol — up to 8 parallel *executions* per turn.
- `asyncio` throughout.
- `src/planner/` and `src/coordinator/`.

**What's missing.**
- Reasoning is still one observation at a time. Even in a batch, the model reasons sequentially within one prompt.
- No "committee" or "debate" pattern: asking two independent sub-reasoners and comparing.
- No fan-out across multiple LLM providers within one task.

**Steps.**

1. **Sub-task fan-out.** New `src/coordinator/fan_out.py`. Given a task that decomposes into N independent questions ("read each of these five files and answer X"), spawn N sub-prompts. Each runs its own LLM call with a small tool set (read-only). Join results, then the main agent reasons over the union.
2. **Two-model cross-check (opt-in).** On high-stakes decisions (deleting code, changing public APIs), call two providers concurrently with the same question and compare. If they disagree, fall back to `ask_human`. Enabled per-provider in `.env`.
3. **Parallel reader agent.** A read-only sub-agent that can be asked "map this module" and returns a structured summary, running in parallel with the main agent's other work.
4. **Bounded concurrency.** Cap sub-agents at 4 by default to avoid rate-limit storms; respect provider quotas.
5. **Determinism guard.** Sub-agent outputs must be labeled as *evidence*, not instructions. Merge only after the main agent reads them.

**Acceptance.** A "map this module" task on a 30-file package produces the same structured summary as reading serially, but in ~1/3 of the wall-clock time. Two-model cross-check flags at least one intentional hallucination in a red-team test.

**Effort.** 5–8 days, plus ongoing prompt engineering.

---

## 6. Limitation: "No real-world reach"

**What exists.**
- `src/integrations/`, `src/assistant/`, `src/music/` (17 files, Google Drive + Spotify).
- `src/mcp/` — MCP client.
- `scripts/send_gmail_attachment_webkit.py`, `upload_to_gdrive.py`, `sync_accounts.py`.
- `mcp_allowlist.json`.

**What's missing.**
- No unified "actions" registry: each integration is bespoke.
- No sandbox tiering: everything is either allowed or refused.
- No scheduled real-world actions (send tomorrow morning, publish at 5pm).

**Steps.**

1. **Action registry.** New `src/integrations/registry.py`. Every side-effecting action (send email, upload file, create calendar event, post to a service) registers itself with: name, description, required inputs, risk level, rate limit.
2. **Risk tiers.** `read`, `write_local`, `write_remote`, `irreversible`. Tiers map to the existing `src/permission_gate.py` and `mcp_allowlist.json`. `write_remote` requires explicit per-action approval or a signed allowlist.
3. **MCP expansion.** Prefer MCP servers over bespoke scripts for Gmail, Calendar, Drive, Slack, GitHub. Add servers to `mcp_allowlist.json` with tiered scopes.
4. **Scheduler integration.** Once the task queue from section 1 exists, scheduling is trivial: enqueue with a `run_at` timestamp. Add a `<action>@<when>` syntax in the CLI.
5. **Audit log.** Every side-effecting action writes to `.julius/action_log.jsonl`: actor, action, target, timestamp, result, reversible-or-not.

**Acceptance.** From the CLI, `julius schedule "send the report to alice@example.com tomorrow 9am"` enqueues an action; the daemon executes it, and the action log records it.

**Effort.** 6–10 days, dominated by getting each integration's auth and error handling right.

---

## 7. Limitation: "Correctness isn't guaranteed"

**What exists.**
- `src/error_parser.py`, `src/replay_harness.py`, `src/parity_audit.py`, `src/ledger.py`.
- Recovery recipes and policy engine in `rust/crates/runtime/` (per `progress.txt`).
- `src/execution_registry.py`.

**What's missing.**
- No systematic self-verification pass on completed tasks beyond running the tests the agent chose.
- No "second opinion" review step before declaring done.
- No calibration: the agent rarely says "I'm 60% sure."

**Steps.**

1. **Mandatory verification before `done`.** In `WebAgent.run()`, before returning a final answer, require that at least one verifiable check ran (compile, test, run). If none ran, force a `converse` instead of `done`, stating exactly what was not verified.
2. **Adversarial review pass.** After the primary answer, spawn a fresh sub-agent (see section 5) with the task statement, the diff, and a skeptical system prompt: "Find the reason this change is wrong." Report findings.
3. **Confidence tagging.** Add a `confidence: low|medium|high` field to `AgentResult`. Low-confidence results must include the specific evidence that would raise confidence.
4. **Reproduction harness.** Extend `replay_harness.py` to run a known-good set of past tasks against the current code on every CI run. Track pass rate.
5. **Failure post-mortem.** When a task fails, write a structured post-mortem to episodic memory: what was tried, what failed, what would have caught it. Reuse this on similar future tasks.

**Acceptance.** A deliberately wrong answer (red-team test) is flagged by the review pass at least 70% of the time. `AgentResult.confidence` correlates with the replay-harness pass rate.

**Effort.** 5–7 days.

---

## 8. Limitation: "I choose not to do X"

These are policy, not capability. Changing any of them requires your explicit decision, one at a time. I will not change them on my own.

- **Obey instructions inside files/web pages.** No plan. This stays off permanently — it's the whole point of the trust model.
- **Print or transmit secrets.** No plan. Stays off. What can improve is *detection*: extend `src/security/` to warn when a diff would accidentally include a secret pattern.
- **Destructive actions without approval.** No plan. Stays gated. What can improve: better previews (show the diff or the file list before asking), and a "dry run" mode that stages the operation and shows what would happen.
- **Pirate content, help with malware.** No plan. Stays off.

**Steps.** None, other than continuing to enforce.

---

## 9. Priority order

Order the work by value-to-effort:

1. **Section 3 (memory).** Highest payoff, smallest risk. The infrastructure is already there; the work is mostly wiring and policy. 4–6 days.
2. **Section 4 (context + step budget).** Removes the ceiling that hits every long task. 5–7 days.
3. **Section 1 (continuous operation).** Turns Julius from "run when asked" to "runs when there's work." Enables everything downstream. 5–8 days.
4. **Section 7 (correctness).** Directly increases trust; makes the rest safer. 5–7 days.
5. **Section 2 (vision + voice).** High value for GUI work, but heavier. 6–10 days.
6. **Section 5 (parallel reasoning).** Useful at scale, but expensive in providers and prompt engineering. 5–8 days.
7. **Section 6 (real-world reach).** Highest integration risk. Defer until 1–4 are solid. 6–10 days.

Total: roughly 40–60 engineer-days for the full set. Do them one at a time, in the order above, verifying each on this repo before starting the next.

---

## 10. What I would do first, if you say go

Start with section 3, step 1: load `episodic_memory` and `semantic_memory` prompt blocks at session start in `run_agent.py` and `WebAgent.__init__`. It is a ~30-line change, verifiable immediately (kill and reopen a session and confirm the agent recalls a preference), and it demonstrates the whole approach. From there the rest of section 3 follows naturally.

Nothing in this document has been executed. Say which section you want me to start on and I will open the relevant files, propose a concrete diff, and implement it in small verified steps.
