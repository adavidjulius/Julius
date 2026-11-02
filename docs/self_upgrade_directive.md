# Julius Self-Upgrade Directive: Research-Agent Readiness

## Context

You are Julius, operating on your own codebase. Your mission going forward includes
long-horizon architecture research: proposing, implementing, and empirically testing
novel neural network architectures intended to outperform or replace the standard
Transformer, on small-scale controlled experiments.

Your current scaffolding (`web_agent.py`, `MemoryEngine`, `ActionExecutor`) is a
general-purpose coding agent. It is **not yet shaped for research iteration**. This
directive tells you what to change, in what order, and how to verify each change
before moving on. You have full autonomy to modify your own core loop — but
autonomy does not mean skipping verification. An unverified change to your own
execution loop can leave you unable to run at all, so the process below is
non-negotiable even though no human will review each step.

## Non-negotiable operating rules for this entire directive

1. **Work on a dedicated git branch** (`self-upgrade/research-readiness`), never
   directly on main/master. Commit after each completed, verified stage.
2. **Never proceed to the next stage until the current stage is verified working.**
   "Verified" means: you ran it, observed real output, and it did what it claims.
   Not "the code looks correct" — actually executed.
3. **If a stage fails verification**, roll back that stage's changes (git reset to
   the last good commit), record what failed and why in the memory engine, retry
   with a different approach up to 2 times, then stop and produce a written report
   of the blocker rather than pushing forward on a broken foundation.
4. **Do not touch unrelated code.** Each stage below has a defined scope. Resist the
   urge to "improve while you're in there" — scope creep is how self-modification
   goes wrong silently.
5. At the end of all stages, produce a single summary document
   (`docs/self_upgrade_report.md`) describing what changed, what was verified, and
   what remains manually reviewable.

---

## Stage 0 — Audit (read-only, no changes)

Before writing any code:
- Read `src/web_agent.py`, `src/memory/*`, `src/action_executor.py` (or equivalent),
  and `JULIUS_SKILL_PLATFORM_ARCHITECTURE.md` in full.
- Produce `docs/self_upgrade_audit.md` listing, concretely:
  - Where the action loop currently permits `run_bash` / experiment-launching
    actions without any preceding validation step.
  - Where/whether `MemoryEngine` is ever *queried* before new work starts, versus
    only *written to*.
  - Current sandbox behavior — confirm it executes in `workspace_root` directly.
  - Confirm Docker is available on this host (`docker info` should succeed) before
    Stage 1 proceeds. If unavailable, stop and report — do not silently substitute
    another isolation method.

Commit this audit before proceeding. This stage produces documentation only.

---

## Stage 1 — Sandbox isolation for experiments

**Goal:** any action that runs model training/evaluation code executes inside a
Docker container with resource limits, not directly on the host.

- Implement `SandboxManager` (per the architecture doc) as a new module, e.g.
  `src/sandbox/manager.py`:
  - Builds/reuses a container image with the project's Python/ML dependencies.
  - Runs a given command inside the container with explicit CPU, memory, and
    (if applicable) GPU resource limits.
  - Mounts only the specific working directory needed for that experiment, not
    the full host filesystem.
  - Captures stdout/stderr/exit code and returns them to the caller in the same
    shape the existing `run_bash` action currently returns, so downstream code
    doesn't need to change its expectations.
  - Has a hard wall-clock timeout, configurable per call, with sane default
    (e.g. 30 min) — runaway training jobs must be killable automatically.
- Add a new action type, `run_experiment`, that routes through `SandboxManager`
  instead of the host shell. Leave existing `run_bash` untouched for non-experiment
  file/dev operations — do not force all shell access through Docker, only
  experiment execution.
- **Verification (required before commit):** actually launch a trivial container
  job (e.g. a 5-line PyTorch script that trains a 2-layer MLP on random data for
  10 steps and prints loss). Confirm: it runs, resource limits are respected
  (check via `docker stats` during the run), it terminates cleanly, and a
  deliberately infinite-looping script gets killed by the timeout. Show the
  actual output, not a description of expected output.

---

## Stage 2 — Memory as active recall, not just storage

**Goal:** before proposing or implementing any new architectural idea, you must
query prior experiment history, not just write to it after the fact.

- Add a structured schema to the memory engine specifically for research
  artifacts, separate from general task memory. Minimum fields per entry:
  `hypothesis`, `mechanism_description`, `nearest_known_architecture`,
  `implementation_summary`, `result_metrics`, `baseline_comparison_metrics`,
  `outcome` (e.g. `promising / inconclusive / failed / abandoned`), `failure_reason`
  (if applicable), `timestamp`.
- Add a required helper, e.g. `memory.query_prior_experiments(description: str)`,
  that does semantic/keyword search over past entries and returns matches with
  similarity scores.
- Modify the action loop so that a new action type, `propose_architecture_idea`,
  **cannot be dispatched** until the current turn's `thought` field includes a
  call to `query_prior_experiments` and an explicit statement of whether this idea
  overlaps with something already tried. Enforce this in the JSON schema validation
  layer in `ActionExecutor`, not just as a prompt suggestion — if the required
  field is missing, reject the action and re-prompt.
- **Verification:** write 2-3 synthetic past experiment entries into memory
  manually, then confirm that a new `propose_architecture_idea` action referencing
  a similar mechanism actually surfaces those entries in the thought step, and that
  omitting the query causes the action to be rejected with a clear error, not
  silently allowed through.

---

## Stage 3 — Critique gate before implementation

**Goal:** no experiment gets implemented without an explicit, checkable claim about
what's novel versus existing architectures.

- Extend the schema for `propose_architecture_idea` to require these fields, all
  mandatory, none freeform-optional:
  - `nearest_existing_architecture` (named, specific — e.g. "Mamba/S6", "linear
    attention", "RetNet", not "transformers" generically)
  - `specific_delta` — what mechanistically differs, in precise terms
  - `expected_complexity` — asymptotic compute and memory, stated explicitly
    (e.g. O(n) vs O(n²)), with the derivation shown, not asserted
  - `failure_mode_hypothesis` — what you expect might go wrong, before running it
- If any field is missing or is a restatement of the architecture name without
  actual mechanistic comparison (e.g. just "this is different from transformers"),
  reject the action in the executor and require resubmission.
- **Verification:** attempt to submit a deliberately vague/lazy proposal (e.g.
  "a new attention mechanism that's better") and confirm it's rejected by the
  schema/executor, not passed through. Then submit a properly filled-out proposal
  and confirm it's accepted.

---

## Stage 4 — Baseline comparison as default, not optional

**Goal:** every experiment automatically runs against a matched-parameter-count
vanilla Transformer baseline on the same data, so results are interpretable.

- Implement `run_comparison_experiment` as the standard entry point for testing an
  architecture idea (built on top of `run_experiment` / `SandboxManager` from
  Stage 1). It should, in one call:
  - Instantiate the candidate architecture at a specified small scale (define a
    sensible default, e.g. ~10M params, and let it be overridden).
  - Instantiate a vanilla Transformer baseline matched as closely as possible in
    parameter count.
  - Train both on the same small dataset/task for the same number of steps.
  - Report loss curves, wall-clock time, and memory usage for both, side by side.
  - Write the full result — including the baseline — into the Stage 2 memory
    schema automatically. An experiment without a baseline comparison should not
    be a representable "successful" memory entry.
- **Verification:** run one real comparison end-to-end (candidate can be a trivial
  variant, e.g. attention with a different normalization, this stage is about
  proving the harness works, not proving a research result). Confirm both models
  actually train, both loss curves are real numbers not placeholders, and the
  result is queryable back out of memory via `query_prior_experiments`.

---

## Final step

Once Stages 0-4 are each committed and verified independently:
- Write `docs/self_upgrade_report.md` summarizing what changed, linking to the
  audit, and listing any deviations from this plan (and why).
- Do not merge the branch automatically. Leave it ready for review, and state
  clearly in the report that it is awaiting merge, along with the branch name.
  