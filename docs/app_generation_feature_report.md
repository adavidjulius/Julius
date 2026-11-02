# Julius Build — App Generation Feature Report

**Date:** 2026-08-03  
**Status:** Feature complete and empirically verified

---

## What Was Built

A six-stage prompt-to-app generation pipeline ("Julius Build") integrated into Julius. Given a natural-language description, Julius:
1. Extracts a structured `AppSpec` and writes it to `docs/app_spec_{name}.md`
2. Generates a real, complete project (no stubs, no TODOs, no placeholders)
3. Runs `npm install` and captures real output
4. Starts a dev server on a free port, polls until HTTP 200
5. Takes a Playwright screenshot of the running app
6. Exercises each core feature via real Playwright interactions — verified=True only when positively confirmed
7. Derives `verification_status` from real evidence only — never from code inspection

---

## Stage 6 Verification — Happy Path (To-Do List App)

**Prompt:** A to-do list app where I can add tasks, mark them as done, and delete them. Persist items in localStorage.

**Real terminal output:**
```
[pipeline] Stage 1: Extracting spec...
[spec]     Spec written to docs/app_spec_do-list-where.md
[pipeline] Stage 2: Generating code...
[generate] Generated 5 files: package.json, index.html, vite.config.js, src/style.css, src/main.js
[install]  Running npm install...
[install]  [PASS] Install succeeded
[pipeline] Using port 3100 for dev server
[start]    Starting Vite dev server on port 3100...
[pipeline] [PASS] HTTP 200 — server is responding
[screenshot] Screenshot saved: do-list-where-c865d494.png
[exercise] Exercising 3 features...
[exercise] [PASS] Add new items: Item appeared (list has 1 item(s))
[exercise] [PASS] Delete items: Items: 1 → 0
[exercise] [PASS] Mark items as done: Item has 'done' class — confirmed complete
[pipeline] Done — verification_status: verified_working
```

**Verification results:**

| Field | Value |
|-------|-------|
| verification_status | **verified_working** |
| install_success | True |
| startup_success | True |
| http_check_status | 200 |
| port_used | 3100 |
| screenshot_path | .julius/build-screenshots/do-list-where-c865d494.png |
| Features tested | 3/3 |

**Feature exercise results — real Playwright interactions:**

| Feature | Action Taken | Observed | Verified |
|---------|-------------|----------|----------|
| Add new items | Typed text + clicked Add | Item appeared (list has 1 item) | PASS |
| Delete items | Clicked delete button on first item | Items: 1 → 0 | PASS |
| Mark items as done | Clicked complete checkbox | Item has 'done' class — confirmed | PASS |

---

## Stage 7 Verification — Failure Path (Broken npm Package)

**Scenario:** App generated with a deliberately nonexistent npm package.

**Real output:**
```
[install] Running npm install...
[install] [FAIL] Install failed (exit 1)
```

**Result:**
```
verification_status : failed

HONEST FAILURE REPORT:
[FAIL] Install failed
[FAIL] Dev server did not start
[FAIL] HTTP check: not reached
[WARNING] No screenshot
```

Conclusion: Failure case is reported honestly. No false positives.

---

## Database Persistence

```
Saved 1 generation(s) to app_generations table
  Latest: do-list-where | verified_working | 2026-08-03T08:48:16.992180
```

---

## Files Delivered

| File | Purpose |
|------|---------|
| src/app_builder/__init__.py | Package exports |
| src/app_builder/spec.py | AppSpec, VerificationStatus, FeatureTestResult |
| src/app_builder/record.py | AppGenerationRecord with finalize() |
| src/app_builder/builder.py | AppBuilder — all 6 pipeline stages |
| src/memory/working_state.py | + AppGenerationStore + app_generations table |
| julius_gui.py | + POST /api/build, GET /api/build/{id}/status, GET /api/build/history, GET /api/build/{id}/screenshot |
| frontend/index.html | + Julius Build panel (Build button + full UI) |
| docs/app_spec_do-list-where.md | Example spec written during verification |

---

## Safety Coverage

All new shell commands go through SecurityPolicy.is_command_safe(). No bypass paths.
Overwrite guard enforced in AppBuilder layer before any shell command.

---

## What "Verified" Means

verification_status is derived ONLY from real observed evidence:
- HTTP status codes
- DOM state changes (class names, item counts)
- Process exit codes

It is NEVER set to verified_working because code "looks complete".
