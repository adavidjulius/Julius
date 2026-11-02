# Julius — Native Cross-Platform Support Plan

**Goal:** Make Julius install and run natively on **Linux, macOS, and Windows** (PowerShell / CMD, no WSL required), keeping WSL and Docker as fallbacks.

**Status today (evidence):**
- `install.sh` explicitly rejects MSYS/Cygwin/MinGW shells and requires WSL for Windows.
- No `sys.platform` / `os.name` / `platform.system()` branches anywhere under `src/`.
- `src/cli/v3_tui.py` clipboard helper handles `pbcopy` (macOS), `xclip` and `wl-copy` (Linux), but has no Windows clipboard path.
- Shell wrappers (`julius`, `julius_bin`, `install.sh`, `start_tui.sh`, most of `scripts/*.sh`) are bash-only.
- Packaging coverage: Fedora RPM spec (`julius.spec`), macOS DMG script (`scripts/build_dmg.sh`), Debian-only `Dockerfile`. No Windows installer.
- Requirements are split inconsistently across `requirements.txt`, `requirements-linux.txt`, `requirements-docker.txt`, `requirements-agent.txt`; OS markers are partial.
- Runtime deps that matter per-OS: PyQt6 (GUI), Playwright (browsers), sounddevice (PortAudio), pynput + PyAutoGUI (input), keyring (secrets), tree-sitter (compiled), numpy (wheels), SpeechRecognition.

---

## 1. Guiding principles

1. One code path, OS-aware at the edges. Detect the OS once, in one module, and branch only where it actually matters (paths, subprocess, clipboard, service manager, browser install).
2. Never break the current Linux/macOS/WSL experience. Windows support is additive.
3. Ship per-OS dependency manifests so `pip install` never has to guess.
4. Prefer libraries that already work on all three OSes (Playwright, PyQt6, keyring, tree-sitter, pynput, PyAutoGUI all do).
5. Every OS gets a first-class installer and a smoke test.

---

## 2. Workstreams

### WS1 — OS abstraction layer (foundation)

Add `src/platform_compat.py` as the single source of truth.

- `IS_WINDOWS`, `IS_MACOS`, `IS_LINUX`, `IS_WSL` booleans derived from `sys.platform` + `platform.system()` + `/proc/version` sniff.
- `get_config_dir()`, `get_cache_dir()`, `get_data_dir()` returning OS-appropriate paths:
  - macOS: `~/Library/Application Support/Julius`, `~/Library/Caches/Julius`
  - Linux: `$XDG_CONFIG_HOME/julius` or `~/.config/julius`, `~/.cache/julius`, `~/.local/share/julius`
  - Windows: `%APPDATA%\Julius`, `%LOCALAPPDATA%\Julius\Cache`, `%LOCALAPPDATA%\Julius`
- `copy_to_clipboard(text) -> bool` — Windows `clip.exe` or `pyperclip`, macOS `pbcopy`, Linux `wl-copy` / `xclip`.
- `open_in_default_app(path)` — `open` / `xdg-open` / `os.startfile`.
- `which(name)` — port of `shutil.which` with `.exe`/`.cmd` awareness.
- `python_executable()` — respects `.venv`, `VIRTUAL_ENV`, `sys.executable`, and the Windows `.venv\Scripts\python.exe` layout.
- `shell_exec(cmd, **kw)` — hides `shell=True` and `cmd /c` differences.

Then refactor the existing call sites to use it: `run_agent.py`, `julius_gui.py`, `src/cli/v3_tui.py` (clipboard), anything under `src/` that shells out today (audit will confirm).

**Deliverable:** one module, ~150 lines, no behavior change on Linux/macOS.

### WS2 — Dependency manifests per OS

Consolidate into a single source of truth plus per-OS markers.

- Keep `requirements.txt` as the canonical list, using environment markers (`sys_platform == 'darwin'`, `== 'win32'`, `== 'linux'`).
- Remove or regenerate the ad-hoc split files (`requirements-linux.txt`, `requirements-docker.txt`, `requirements-agent.txt`) so nothing drifts.
- Windows-specific adds:
  - `pywin32` (window handling, keyring backend)
  - `pyperclip` (clipboard fallback) — already present, keep.
  - `PyGetWindow`, `MouseInfo`, `PyRect`, `PyScreeze` are pulled in by `PyAutoGUI`; verify they install cleanly on Windows.
- macOS-only stays behind `darwin` markers: `pyobjc-core`, `pyobjc-framework-*`, `macholib`, `py2app`.
- Verify every package has a Windows wheel or a build path (tree-sitter, `sounddevice` need prebuilt wheels — they do as of 2024).
- PortAudio on Windows: `sounddevice` bundles it via wheel; on Linux it needs `libportaudio2`; on macOS `brew install portaudio`. Document per OS.

**Deliverable:** `requirements.txt` with clean markers; README table of per-OS system deps.

### WS3 — Installer scripts per OS

- **`install.sh`** — keep, but relax the OS gate: allow native Windows shells (Git Bash) to hand off to `install.ps1` instead of erroring. Optionally keep an `--wsl-required` flag for users who prefer the old behavior.
- **New `install.ps1`** — the Windows counterpart:
  - Detect Python 3.10+ (`py -3.12`, `py -3.11`, `python`, `python3`).
  - Create `.venv` at project root using `python -m venv .venv`.
  - Activate via `.venv\Scripts\Activate.ps1`.
  - `pip install -r requirements.txt`.
  - `playwright install chromium`.
  - Create `.env` from `.env.example` if missing.
  - Print a completion banner with the two launch commands (`./julius.ps1` and `python julius_gui.py`).
  - Support `-NoVerify` and `-NoBrowser` flags to mirror `install.sh`.
- **New `install.py`** (optional) — a Python rewrite of `install.sh` that runs identically on all three OSes. This is the cleanest long-term answer; the shell scripts then become thin wrappers.
- **New `julius.ps1`** — PowerShell wrapper mirroring `julius` (bash): detects `.venv\Scripts\python.exe`, `$env:VIRTUAL_ENV\Scripts\python.exe`, or `python` on PATH, then `& $python $scriptDir\run_agent.py @args`.
- **New `julius.cmd`** — tiny CMD shim that calls `julius.ps1` for users who live in CMD.
- **`start_tui.sh`** — either keep bash-only and add `start_tui.ps1`, or fold into `julius` / `julius.ps1` with a `--tui` flag.

**Deliverable:** parity scripts; both installers produce the same runtime layout.

### WS4 — Runtime code portability

Audit every subprocess call and every hardcoded path.

- Replace `subprocess.run(["pbcopy"], ...)` style calls with `platform_compat.copy_to_clipboard`.
- Replace `os.system("systemctl ...")` (if any remain) with a `ServiceManager` abstraction: systemd on Linux, `launchctl` on macOS, `sc.exe` / Task Scheduler on Windows. If the daemon is optional, degrade gracefully on Windows.
- Any use of `chmod`, `chown`, `chmod +x` inside Python code must be guarded by `if not IS_WINDOWS`.
- Path handling: audit for `/tmp`, `/var`, `~/.julius`, `~/Library`, `/usr/local`. Move all such constants into `platform_compat`.
- Browser profile dirs currently use `chrome_profile/`, `webkit_profile/` at workspace root — that is fine, but the default when the user has not chosen a workspace should be an OS-specific app-data dir.
- Signal handling: `signal.SIGKILL`, `SIGTERM`, `SIGHUP` differ on Windows. Guard or replace with `psutil.terminate()`.
- Encoding: open all text files with `encoding="utf-8"` explicitly (Windows default is `cp1252`).

**Deliverable:** zero raw OS-specific subprocess calls outside `platform_compat`.

### WS5 — GUI (PyQt6 + Playwright + audio/input)

- PyQt6 already supports all three OSes. Confirm `qasync` works on Windows (it does).
- Playwright: after install, call `playwright install chromium`. On Linux also call `playwright install-deps` (needs sudo) — documented, not automated silently. On macOS/Windows, browser binaries ship standalone.
- PyAutoGUI / pynput / PyGetWindow: work on all three; add to the Windows manifest.
- sounddevice: depends on PortAudio. Bundled on macOS and Windows wheels; on Linux depends on `libportaudio2` (already in `Dockerfile`). Add OS-specific note to README and a check at startup that logs a clean message if PortAudio is missing.
- keyring: uses Windows Credential Manager, macOS Keychain, and Secret Service on Linux. Already cross-platform; verify Linux Secret Service fallback.
- Voice models in `custom_voice_models/` are platform-agnostic; no change.

**Deliverable:** `python julius_gui.py` runs on clean Windows 11 and clean Ubuntu 22.04 with only the documented system deps installed.

### WS6 — CLI / TUI

- `src/cli/v3_tui.py` is Textual-based; Textual supports Windows terminals (Windows Terminal, PowerShell 7, and modern ConHost). Document the minimum: Windows Terminal + PowerShell 7 recommended; CMD with legacy ConHost may have rendering issues.
- The clipboard helper must add the Windows branch (`platform_compat.copy_to_clipboard` already covers it once WS1 lands).
- Any TTY checks (`sys.stdin.isatty()`, `shutil.get_terminal_size`) work on Windows; verify the banner alignment on `cmd.exe`.
- `run_agent.py` uses `input()` and `console.input()` — both fine on Windows.

**Deliverable:** `./julius`-equivalent (`julius.ps1`) launches the same TUI on Windows.

### WS7 — Packaging

Per-OS distribution, each verifiable in CI.

- **Linux**: existing `julius.spec` (Fedora RPM). Add a `.deb` build (nfpm or `dpkg-deb`) and an AppImage path. Provide a `pipx` install path too.
- **macOS**: existing `scripts/build_dmg.sh`. Keep. Add a Homebrew tap formula for `julius`.
- **Windows**: add `scripts/build_msi.ps1` producing an MSI via WiX or `pynsist` (bundles Python + app). Also ship a portable ZIP with a pre-built `.venv` bootstrapper.
- **Universal fallback**: `pipx install julius-agent` once packaged on PyPI. This is the single least-effort cross-platform channel and should be prioritized.

**Deliverable:** a real install path on each OS: RPM/DEB/AppImage, DMG/Homebrew, MSI/ZIP, and PyPI/pipx.

### WS8 — CI matrix (proves it, keeps it working)

Add a GitHub Actions workflow (` .github/workflows/cross-platform.yml`) with three jobs:

- `ubuntu-latest` — apt install `python3 python3-venv libportaudio2 libxkbcommon-x11-0 libxcb-*`; run `bash install.sh --no-browser`; then `python -m py_compile` on all entry points; run a headless smoke test (`python -c "from src.web_agent import WebAgent; print('ok')"`).
- `macos-latest` — brew tap or use preinstalled Python; run `bash install.sh --no-browser`; same smoke test.
- `windows-latest` — run `pwsh install.ps1 -NoBrowser`; same smoke test.

Add a fourth job that runs the unit test suite (`pytest -q`) on all three OSes with `--no-browser`.

**Deliverable:** red/green signal on every push for all three OSes.

---

## 3. Sequencing and milestones

Each milestone ends with all existing Linux/macOS tests still green.

**M0 — Audit (1–2 days).**
Enumerate every OS-specific call: subprocess invocations, path literals, signal usage, file encodings, service-manager calls. Produce `docs/cross-platform-audit.md`. No code changes.

**M1 — Foundation (2–3 days).**
Land `src/platform_compat.py` with unit tests for path resolution, clipboard, and OS detection. Refactor clipboard in `src/cli/v3_tui.py` to use it. Nothing else changes.

**M2 — Dependency cleanup (1 day).**
Rewrite `requirements.txt` with proper markers. Delete the split requirement files or generate them from the master (choose one; prefer delete). Verify `pip install -r requirements.txt` on all three OSes in a scratch venv.

**M3 — Windows wrappers and installer (3–4 days).**
Land `install.ps1`, `julius.ps1`, `julius.cmd`, `start_tui.ps1`. Relax `install.sh` to defer to `install.ps1` when it detects a native Windows shell. Verify end-to-end on a Windows 11 VM: clone, install, run CLI, run TUI, run GUI.

**M4 — Runtime portability (3–5 days).**
Sweep the codebase: replace the OS-specific branches the audit found. Guard `chmod`. Force `encoding="utf-8"` on all text I/O. Signal-safe daemon shutdown. Verify no regressions on Linux and macOS.

**M5 — GUI hardening (2–3 days).**
Fix any Windows-specific GUI issues (DPI scaling, font fallback, Playwright browser path, PortAudio check). Manual smoke test on Windows 11.

**M6 — CI matrix (1 day).**
Land `.github/workflows/cross-platform.yml`. Get all three OS jobs green.

**M7 — Packaging (varies).**
- PyPI/pipx path: 1–2 days. Highest impact.
- Windows MSI/ZIP: 2–3 days.
- Linux .deb/AppImage: 1–2 days.
- Homebrew formula: 0.5 day.

**M8 — Documentation (1 day).**
Rewrite README install section with three tabs (Linux / macOS / Windows). Add `docs/install-windows.md`, `docs/install-macos.md`, `docs/install-linux.md`. Replace the placeholder platform badge with a real one.

---

## 4. Risks and mitigations

- **Textual rendering on CMD/legacy ConHost.** Mitigation: document Windows Terminal + PowerShell 7 as the supported combo; degrade to the plain REPL fallback in `run_agent.py` when a modern terminal is not detected.
- **PortAudio missing on Linux servers.** Mitigation: install script checks for `libportaudio2` and prompts; the runtime catches the import error and continues without audio.
- **PyQt6 wheel availability on Windows for Python 3.13.** Mitigation: pin minimum Python to 3.11 on Windows for the first release; verify against the latest wheels before advertising 3.13.
- **Playwright browsers on locked-down Windows.** Mitigation: `--no-browser` install flag, and document manual `playwright install chromium`.
- **tree-sitter wheels.** Mitigation: verify at M2; fall back to a source build with documented toolchain (`visual-build-tools` on Windows) if a wheel is missing.
- **Path-separator bugs.** Mitigation: use `pathlib.Path` everywhere; forbid string concatenation of paths in code review.
- **Line endings.** Mitigation: add `.gitattributes` with `* text=auto` and `*.sh text eol=lf`, `*.ps1 text eol=crlf`.

---

## 5. Files to be created or modified (target list)

Created:
- `src/platform_compat.py`
- `install.ps1`, `julius.ps1`, `julius.cmd`, `start_tui.ps1`
- `scripts/build_msi.ps1`
- `.github/workflows/cross-platform.yml`
- `.gitattributes`
- `docs/PLAN-cross-platform.md` (this file)
- `docs/cross-platform-audit.md` (from M0)
- `docs/install-windows.md`, `docs/install-macos.md`, `docs/install-linux.md`
- `requirements-windows.txt` (only if markers in the master manifest prove insufficient)

Modified:
- `install.sh` (relax Windows gate, delegate to `install.ps1`)
- `requirements.txt` (canonical, with markers)
- `run_agent.py` (use `platform_compat` for paths and clipboard)
- `julius_gui.py` (PortAudio check, Playwright path, DPI scaling)
- `src/cli/v3_tui.py` (clipboard via `platform_compat`)
- `README.md` (per-OS install tabs; real platform badge)
- `.gitignore` (Windows venv layout, `*.egg-info`, `build/`, `dist/`)

Deleted (after M2):
- `requirements-linux.txt`, `requirements-docker.txt`, `requirements-agent.txt` (fold into master).

---

## 6. Acceptance criteria

A clean install is considered successful on any OS when, from a fresh clone:

1. `install.sh` (Linux/macOS) or `pwsh install.ps1` (Windows) completes without error.
2. `./julius --help` (or `julius.ps1 -Help`) prints the CLI help.
3. `./julius "say hello"` reaches the agent loop and returns a response.
4. `python julius_gui.py` starts the Qt window and the web server binds the configured port.
5. The TUI starts and renders the banner in a normal terminal.
6. `pytest -q` passes on all three OSes in the CI matrix.
7. Clipboard copy from the CLI works on all three OSes.

---

## 7. Out of scope (for now)

- A signed/notarized macOS `.app` bundle (existing `build_dmg.sh` covers DMG, not notarization).
- A Microsoft Store or winget package.
- Full GUI theming per OS (functional parity first, then polish).
- Removing WSL support. It stays as a supported path.

---

## 8. Summary

The work is mostly plumbing, not redesign. The runtime is Python and its major libs (PyQt6, Playwright, Textual, keyring, tree-sitter) already run on all three OSes. The real gaps are:

1. A single `platform_compat` module to centralize OS branching.
2. Clean per-OS dependency manifests.
3. A Windows installer and wrapper scripts (parity with `install.sh` and `julius`).
4. A CI matrix that runs on all three OSes so the claim stays true.

Everything else — RPM, DMG, MSI, pipx — is packaging on top of a codebase that already works. Sequencing the work behind the platform layer (M1) and the dependency cleanup (M2) makes the rest low risk.
