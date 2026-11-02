# Julius — Three-Option Plan to Run Natively on Linux, macOS, and Windows

Author: Julius (acting as developer)
Audience: the person who will implement this
Scope: make the Julius agent install and run end-to-end (CLI, TUI, GUI, daemon, Playwright, clipboard, audio, keyring) on Linux, macOS, and native Windows — no WSL required.

---

## 0. Ground truth (evidence from the repo)

These are the concrete facts this plan is built on. Do not re-derive them.

| Area | Finding | File / Line |
|---|---|---|
| Windows gate | `install.sh` aborts on `MINGW*|MSYS*|CYGWIN*` shells | `install.sh:213-217` |
| Windows claim | README badge says `Linux | macOS | Windows`, but badge URL is a bare `https://shields.io` with no query | `README.md:5` |
| OS branching | No `sys.platform` / `os.name` / `platform.system()` in `src/` or entry points | full-tree search |
| Clipboard | Only `pbcopy` (macOS), `xclip` (Linux), `wl-copy` (Wayland). No Windows path | `src/cli/v3_tui.py:58-80` |
| CLI wrapper | `julius` is bash-only; detects `.venv/bin/python3` or `$VIRTUAL_ENV/bin/python3` | `julius:1-18` |
| CLI entry | `run_agent.py` — argparse, TUI, fallback REPL | `run_agent.py` |
| GUI entry | `julius_gui.py` (127 KB, PyQt6 + qasync + aiohttp) | `julius_gui.py` |
| Daemon | `juliusd.py` subprocess-launches `julius_gui.py` | `juliusd.py` |
| Packaged CLI wrapper | `scripts/julius-cli.sh` hardcodes `/opt/julius`, `~/.local/share/julius`, `.venv/bin/python3` | `scripts/julius-cli.sh:1-26` |
| Packaged GUI wrapper | Same pattern | `scripts/julius-gui.sh:1-26` |
| TUI launcher | `start_tui.sh` assumes macOS/.venv | `start_tui.sh:1-24` |
| Python binary wrapper | `julius_bin` shells to `./julius` | `julius_bin:1-4` |
| Deps split | Four manifests: `requirements.txt`, `-linux`, `-docker`, `-agent` — OS markers are partial | repo root |
| Packaged RPM | Fedora RPM spec exists | `julius.spec` |
| CI | `test-julius.yml`, `release.yml`, `run-cloud.yml`, `rust-ci.yml`, `rust.yml` — none cross-OS | `.github/workflows/` |
| Native compiled deps | `tree-sitter`, `numpy`, `sounddevice` (PortAudio), `PyQt6`, `playwright`, `pynput`, `PyAutoGUI` | `requirements.txt` |

---

## 1. Shared prerequisites (do these first regardless of option)

These unblock all three options. Budget: 1–2 days.

### P1. Lock the platform detection in one place

Create `src/platform_compat.py`:

```python
import os, sys, platform, shutil, subprocess
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS   = sys.platform == "darwin"
IS_LINUX   = sys.platform.startswith("linux")

def _is_wsl() -> bool:
    if not IS_LINUX:
        return False
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        return False

IS_WSL = _is_wsl()

def config_dir() -> Path:
    if IS_WINDOWS: return Path(os.environ.get("APPDATA", Path.home()/"AppData/Roaming"))/"Julius"
    if IS_MACOS:   return Path.home()/"Library/Application Support/Julius"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home()/".config"))/"julius"

def cache_dir() -> Path: ...
def data_dir() -> Path: ...

def copy_to_clipboard(text: str) -> bool:
    candidates = (["clip"] if IS_WINDOWS
                  else ["pbcopy"] if IS_MACOS
                  else ["wl-copy", "xclip -selection clipboard"])
    for c in candidates:
        try:
            subprocess.run(c.split(), input=text, text=True, check=True, timeout=5)
            return True
        except Exception:
            continue
    return False

def which(name: str) -> str | None:
    return shutil.which(name)

def shell_exec(cmd: str, check: bool = True, timeout: int = 300):
    if IS_WINDOWS:
        return subprocess.run(cmd, shell=True, check=check, timeout=timeout)
    return subprocess.run(cmd, shell=True, executable="/bin/bash", check=check, timeout=timeout)
```

Verify with a small test in `tests/test_platform_compat.py` that asserts exactly one of `IS_WINDOWS`/`IS_MACOS`/`IS_LINUX` is true.

### P2. Force UTF-8 everywhere

Grep for `open(` in `src/` and `*.py` at repo root, add `encoding="utf-8"` where missing. This is the single most common cross-platform bug.

### P3. Path hygiene

Replace string path concatenation with `pathlib.Path`. Never `"/tmp/foo"`; use `Path(tempfile.gettempdir())/"foo"`. Never `~/...`; use `Path.home()/...`.

### P4. `.gitattributes`

```
* text=auto
*.sh  text eol=lf
*.ps1 text eol=crlf
*.cmd text eol=crlf
*.py  text eol=lf
```

### P5. `.gitignore` additions

```
.venv/Scripts/
*.egg-info/
build/
dist/
*.msi
*.dmg
```

---

## 2. The three suggestions

Each option is self-contained and can ship without the others. Choose one based on how much platform "feel" you want.

---

### SUGGESTION A — Python-native unifier (recommended)

**Idea.** Replace every shell entry point with a single Python installer and a single Python launcher. Shell scripts become thin wrappers or are removed. One code path, three OSes.

**Why this one.** Python already runs on all three targets. Every shell script is a source of bugs. This eliminates the entire class of "bash doesn't exist on Windows" problems and gives users a single file to run everywhere.

**Trade-offs.** Slightly less idiomatic on each OS (no `.ps1`, no `.sh`), and Python must already be installed (or shipped). For a tool whose whole premise is "Python agent," that's acceptable.

#### A.1 — Files to create

1. `install.py` — cross-platform installer.
2. `julius.py` — cross-platform launcher (replaces `julius`, `julius_bin`, `start_tui.sh`).
3. `juliusd.py` — already Python; leave as is.
4. `scripts/dev.py` — dev convenience (fmt, lint, test) cross-platform.

#### A.2 — Steps to implement `install.py`

1. Parse CLI args: `--no-verify`, `--no-browser`, `--python <path>`, `--help`.
2. Detect OS via `platform_compat`.
3. Locate Python 3.10+: prefer `--python`, then `sys.executable`, then `shutil.which("python3")`, then `shutil.which("python")`. On Windows also try `py -3.12`.
4. Verify version >= (3, 10).
5. Create `.venv` at repo root using `python -m venv .venv`.
6. Compute venv python path: `.venv/bin/python` (POSIX) or `.venv/Scripts/python.exe` (Windows).
7. Upgrade pip inside the venv.
8. Install `-r requirements.txt` (see A.3 for the manifest cleanup).
9. Run `python -m playwright install chromium`. If `--no-browser`, skip.
10. Create `.env` from `.env.example` if missing (never overwrite).
11. Print a banner with the two commands: `python julius.py` and `python julius_gui.py`.
12. Exit 0 on success, non-zero with a clear message otherwise.

#### A.3 — Steps to clean up `requirements.txt`

1. Start from the current `requirements.txt` as the master.
2. Add environment markers per package:
   - `pyobjc-core; sys_platform == 'darwin'` and all other `pyobjc-*`, `macholib`, `py2app`.
   - `pywin32; sys_platform == 'win32'`.
   - `PyGetWindow; sys_platform == 'win32'` already present — keep.
3. Delete `requirements-linux.txt`, `requirements-docker.txt`, `requirements-agent.txt`. If anything was unique to them, fold into the master with markers.
4. Verify with three clean venvs (one per OS) that `pip install -r requirements.txt` succeeds.
5. For `sounddevice`: leave as is. Document per-OS system deps in README (PortAudio).

#### A.4 — Steps to implement `julius.py`

1. Resolve script directory via `Path(__file__).resolve().parent`.
2. Prefer `sys.executable` if inside a venv (detectable via `sys.prefix != sys.base_prefix`).
3. Else prefer `./.venv/bin/python` or `./.venv/Scripts/python.exe`.
4. Else fall back to `shutil.which("python3")` or `shutil.which("python")`.
5. `os.execv(python_bin, [python_bin, str(script_dir/"run_agent.py"), *sys.argv[1:]])`.
6. If venv missing and not inside one, print a clear error: `Run python install.py first`.
7. Support `julius.py --tui` to route to the TUI, `julius.py --gui` to route to `julius_gui.py`, and default to CLI.

#### A.5 — Wrapper files (thin, optional)

- `julius` (bash): `exec python3 "$(dirname "$0")/julius.py" "$@"`.
- `julius.cmd` (Windows CMD): `@python "%~dp0julius.py" %*`.
- `julius.ps1` (PowerShell): `& python "$PSScriptRoot\julius.py" @args`.

These exist only so users who type `./julius` still get the expected behavior. All logic is in `julius.py`.

#### A.6 — `scripts/julius-cli.sh` / `julius-gui.sh`

1. Replace hardcoded `/opt/julius` with the resolved script directory.
2. Replace `USER_DIR="/opt/julius"` paths with `platform_compat.data_dir()` inside a new Python entry that these scripts call.
3. Better: delete both and have the RPM spec call `julius.py` directly (see WS7 in the older plan).

#### A.7 — Verification per OS

For each of Linux, macOS, Windows:
1. Fresh clone.
2. `python install.py`.
3. `python julius.py --help` prints help.
4. `python julius.py "say hello"` reaches the agent loop.
5. `python julius_gui.py` opens the window.
6. `python -m pytest -q` passes.

Effort: 3–5 days.

---

### SUGGESTION B — Per-OS native scripts + CI matrix

**Idea.** Keep bash for POSIX and add a parallel PowerShell script for Windows. Duplicate the installer and launcher logic, but write each in the idiomatic language of the platform. Prove it with a GitHub Actions matrix on all three OSes.

**Why this one.** Feels native on each OS. Users get `.sh` on Linux/macOS and `.ps1` on Windows, plus a `.cmd` shim for CMD diehards. CI catches regressions per OS from day one.

**Trade-offs.** Two implementations to keep in sync. Every future change to install logic must be made twice. Easy to drift.

#### B.1 — Files to create

1. `install.ps1` — Windows installer.
2. `julius.ps1` — Windows launcher.
3. `julius.cmd` — CMD shim.
4. `start_tui.ps1` — TUI launcher.
5. `.github/workflows/cross-platform.yml` — three-OS matrix.
6. `scripts/install_windows_notes.md` — troubleshooting for the `.ps1` path.

#### B.2 — Steps to implement `install.ps1`

1. `[CmdletBinding()]` param block: `-NoVerify`, `-NoBrowser`, `-Python <path>`.
2. `Set-StrictMode -Version Latest` and `$ErrorActionPreference = "Stop"`.
3. Detect Python: try `-Python`, then `py -3.12`, then `py -3.11`, then `python`, then `python3`. Validate `>= 3.10` via `& $py -c "import sys;print(sys.version_info[:2])"`.
4. Create `.venv`: `& $py -m venv .venv`.
5. Use `& .venv\Scripts\python.exe -m pip install --upgrade pip`.
6. `& .venv\Scripts\python.exe -m pip install -r requirements.txt`.
7. If not `-NoBrowser`: `& .venv\Scripts\python.exe -m playwright install chromium`.
8. Copy `.env.example` to `.env` if `.env` missing.
9. Print summary: paths, python version, next steps.
10. Return exit code based on failures.

#### B.3 — Steps to implement `julius.ps1`

1. Resolve `$PSScriptRoot`.
2. Prefer `$PSScriptRoot\.venv\Scripts\python.exe`.
3. Else prefer `$env:VIRTUAL_ENV\Scripts\python.exe`.
4. Else fall back to `Get-Command python` / `python3`.
5. `& $python "$PSScriptRoot\run_agent.py" @args`.

#### B.4 — Steps to implement `julius.cmd`

```
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0julius.ps1" %*
```

Execution policy bypass is scoped to this call only.

#### B.5 — Steps to relax `install.sh`

Replace the hard error at `install.sh:213-217` with a handoff:

```bash
windows-shell)
    if [ -f "${SCRIPT_DIR}/install.ps1" ]; then
        if command -v pwsh >/dev/null 2>&1; then
            exec pwsh -NoProfile -File "${SCRIPT_DIR}/install.ps1" "$@"
        else
            error "PowerShell 7 (pwsh) not found."
            error "Install it: winget install Microsoft.PowerShell"
            exit 1
        fi
    fi
    error "install.ps1 not found next to install.sh"
    exit 1
    ;;
```

#### B.6 — Steps to add the CI matrix

`.github/workflows/cross-platform.yml`:

```yaml
name: cross-platform
on: [push, pull_request]
jobs:
  linux:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: sudo apt-get update && sudo apt-get install -y libportaudio2
      - run: bash install.sh --no-browser
      - run: python -m py_compile run_agent.py julius_gui.py juliusd.py julius_cli.py
      - run: python -c "from src.web_agent import WebAgent; print('ok')"
  macos:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: bash install.sh --no-browser
      - run: python -m py_compile run_agent.py julius_gui.py juliusd.py julius_cli.py
  windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pwsh ./install.ps1 -NoBrowser
      - run: python -m py_compile run_agent.py julius_gui.py juliusd.py julius_cli.py
      - run: python -c "from src.web_agent import WebAgent; print('ok')"
```

Add a second workflow or a matrix job running `pytest -q` on all three OSes once tests are OS-clean.

#### B.7 — Verification per OS

Same as A.7.

Effort: 4–6 days (two implementations plus CI).

---

### SUGGESTION C — Container + launcher hybrid

**Idea.** Ship a container image that always works, and pair it with a tiny native launcher per OS that pulls and runs the container. Native install becomes "install Docker Desktop (or Podman), then run `julius`".

**Why this one.** One runtime artifact. Deterministic dependencies. No cross-OS Python packaging problems. The Windows/macOS/Linux launcher is 30 lines and never changes.

**Trade-offs.** Requires Docker or Podman on the user's machine. GUI passthrough (X11/Wayland on Linux, XQuartz on macOS, WSLg on Windows) is fiddly. Audio in containers is unreliable. Not the best default for a desktop agent, but excellent as a guaranteed fallback and for CI.

#### C.1 — Files to create

1. `Dockerfile.crossplatform` — hardened, multi-stage image.
2. `julius-docker.sh`, `julius-docker.ps1` — thin launchers.
3. `docker-compose.crossplatform.yml` — GUI/audio passthrough variants.
4. `docs/install-container.md`.

#### C.2 — Steps to implement the Dockerfile

1. Base `python:3.12-slim-bookworm` (already used in `Dockerfile`).
2. Install system deps for PyQt6, Playwright, PortAudio, X11 (already listed in the existing `Dockerfile`).
3. Copy `requirements.txt` (single master after P1).
4. `pip install -r requirements.txt`.
5. `playwright install-deps && playwright install chromium`.
6. Copy the app.
7. `ENTRYPOINT ["python", "run_agent.py"]` with `CMD []`.
8. Tag as `julius:latest` and push to GHCR on release.

#### C.3 — Steps to implement `julius-docker.sh` (POSIX)

1. Detect engine: `docker` then `podman`.
2. If missing, print install hint (Docker Desktop / `apt install podman`).
3. Volume-mount the workspace: `-v "$PWD:/workspace"`.
4. Mount config: `-v "$HOME/.config/julius:/root/.config/julius"` (or the Windows equivalent via `%APPDATA%`).
5. Forward env: `--env-file .env`.
6. GUI passthrough: on Linux pass X11 socket; on macOS document XQuartz; on Windows use WSLg or skip GUI.
7. `exec $engine run --rm -it -v ... julius:latest "$@"`.

#### C.4 — Steps to implement `julius-docker.ps1` (Windows)

1. `Get-Command docker, podman`.
2. Volume mount: `-v "${PWD}:/workspace"` and `-v "$env:APPDATA\Julius:/root/.config/julius"`.
3. Env file: `--env-file .env`.
4. `docker run --rm -it ... julius:latest $args`.

#### C.5 — Steps to publish the image

1. Extend `.github/workflows/release.yml` with a `build-and-push` job.
2. Multi-arch: `linux/amd64`, `linux/arm64`.
3. Push to GHCR: `ghcr.io/<org>/julius:<tag>` and `:latest`.

#### C.6 — Verification per OS

1. Install Docker Desktop (macOS/Windows) or Podman (Linux).
2. `./julius-docker.sh --help` prints help.
3. `./julius-docker.sh "say hello"` reaches the agent.
4. GUI: on Linux with X11 works; on macOS/Windows document limitations.

Effort: 2–3 days for the container and launchers, plus user-side Docker install.

---

## 3. Comparison table

| Criterion | A: Python unifier | B: Per-OS native | C: Container hybrid |
|---|---|---|---|
| Code paths to maintain | 1 | 2 | 1 (container) + thin launchers |
| Native feel | Medium | High | Low |
| User prerequisites | Python 3.10+ | Python 3.10+ (Win: PowerShell 7) | Docker/Podman |
| GUI works out of the box | Yes | Yes | Linux: yes; mac/Win: fiddly |
| Audio works | Yes (with PortAudio) | Yes (with PortAudio) | Unreliable |
| CI cost | One job per OS | One job per OS | One build, run anywhere |
| Time to ship | 3–5 days | 4–6 days | 2–3 days |
| Risk of drift | Low | High | Low |
| Best for | Default distribution | Power users, native packaging | Guaranteed fallback, locked-down envs |

---

## 4. Recommended path

Do A first. It removes the Windows gate, unifies the launcher, and gives you one installer that CI can exercise on all three OSes. Then add C as a fallback for users who can't or won't install Python. Add B's PowerShell wrapper only if user demand for "native on Windows" is strong — it's the least valuable of the three for a Python-based project.

Combined rollout:

1. **Week 1**: Shared prerequisites (P1–P5). Ship `src/platform_compat.py` and update `src/cli/v3_tui.py` to use it for clipboard.
2. **Week 1–2**: Suggestion A. Ship `install.py`, `julius.py`, and thin wrappers. Delete the split requirement files. Verify on a real Windows 11 VM and a clean Ubuntu 22.04 VM.
3. **Week 2**: CI matrix from B.6 (independent of B's PowerShell scripts). Proves A works on all three OSes on every commit.
4. **Week 3**: Suggestion C. Publish the container image and thin launchers. This becomes the "guaranteed" path when native install fails.
5. **Week 3–4**: Suggestion B's PowerShell scripts if desired. Optional polish.
6. **Week 4**: Docs. Rewrite README install section with three tabs; replace the placeholder badge; add `docs/install-linux.md`, `docs/install-macos.md`, `docs/install-windows.md`.

---

## 5. Concrete fixes that apply to all three options

These are the bugs and rough edges that make Julius fail today on Windows regardless of which option you pick.

1. **`install.sh:213-217`** — replace hard error with handoff (or is made redundant by A).
2. **`src/cli/v3_tui.py:58-80`** — replace clipboard chain with `platform_compat.copy_to_clipboard`.
3. **`scripts/julius-cli.sh:3-6`** — hardcoded `/opt/julius` and `~/.local/share/julius`. Replace with `platform_compat.data_dir()` computed by a Python entry point.
4. **`scripts/julius-gui.sh:3-6`** — same fix.
5. **`julius:7-15`** — detects only `.venv/bin/python3`. Add `.venv/Scripts/python.exe` branch, or delegate to `julius.py`.
6. **`start_tui.sh:18-24`** — hardcoded `.venv` and POSIX activation. Add a `start_tui.ps1` or fold into `julius.py --tui`.
7. **`requirements.txt`** — the split manifests drift. Consolidate with markers and delete the rest.
8. **Encoding** — audit all `open()` calls; force `encoding="utf-8"`.
9. **Signals** — search for `signal.signal`, `os.kill`, `SIGTERM`, `SIGKILL`. On Windows these behave differently; wrap via `psutil.terminate` or guard.
10. **`README.md:5`** — replace the fake badge with a real one (shields.io path or a static SVG in-repo).

---

## 6. Acceptance criteria (all options)

From a fresh clone on each of Ubuntu 22.04, macOS 14, Windows 11:

1. Install completes without error, using that option's entry point.
2. `julius --help` prints the CLI help.
3. `julius "say hello"` reaches the agent loop and returns a response.
4. `julius --gui` opens the PyQt6 window and the web server binds a port.
5. `julius --tui` renders the Textual UI.
6. `pytest -q` passes.
7. Clipboard copy from the CLI works.
8. `juliusd.py` starts the daemon and stops cleanly.

---

## 7. Out of scope

- Signed/notarized macOS `.app` bundle.
- Microsoft Store or winget package.
- Full GUI theming per OS.
- Removing WSL or Docker support. Both stay as supported paths.
- Rewriting the runtime. All three options are plumbing on top of working Python.

---

## 8. Summary in one paragraph

Julius is a Python agent whose libraries already work on all three OSes; what's missing is a portable installer, a portable launcher, and clean dependency markers. Suggestion A (a Python installer + a Python launcher) solves this with one code path and 3–5 days of work. Suggestion B (per-OS shell and PowerShell scripts plus a CI matrix) feels more native but doubles the maintenance. Suggestion C (a container image with thin launchers) is the guaranteed fallback for any environment. Ship A first, add C as a fallback, treat B's PowerShell wrapper as optional polish, and back it all with the CI matrix from B.
