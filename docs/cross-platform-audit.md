# Julius — Cross-Platform Audit & Compatibility Report

**Date:** October 2026  
**Auditor:** Julius Development Team  
**Scope:** Complete codebase audit of `src/`, entry points (`run_agent.py`, `julius_gui.py`, `juliusd.py`), scripts, and dependencies across Linux, macOS, and native Windows.

---

## 1. Executive Summary

Prior to this work, Julius contained partial packaging for Linux (RPM) and macOS (DMG), but had no native Windows support outside WSL. Shell scripts assumed POSIX `bash`, clipboard handling only covered `pbcopy` and `xclip`, and file system paths assumed Unix conventions.

This audit established the requirements for full native parity on **Linux, macOS, and Windows** (PowerShell / CMD), implemented via a centralized `src/platform_compat.py` layer.

---

## 2. Findings by Subsystem

### A. OS Branching & Abstraction
- **Original Status:** No centralized OS detection. Ad-hoc checks were scattered or missing.
- **Resolution:** Created `src/platform_compat.py` defining `IS_WINDOWS`, `IS_MACOS`, `IS_LINUX`, `IS_WSL`. Single source of truth for platform queries.

### B. Directory & Path Conventions
- **Original Status:** Hardcoded Unix paths (`~/.config`, `~/Library`, `/tmp`).
- **Resolution:** Added standardized path resolvers:
  - `get_config_dir()`: `%APPDATA%\Julius` on Windows, `~/Library/Application Support/Julius` on macOS, `$XDG_CONFIG_HOME/julius` on Linux.
  - `get_cache_dir()`: `%LOCALAPPDATA%\Julius\Cache` on Windows, `~/Library/Caches/Julius` on macOS, `$XDG_CACHE_HOME/julius` on Linux.
  - `get_data_dir()`: `%LOCALAPPDATA%\Julius` on Windows, `~/Library/Application Support/Julius` on macOS, `$XDG_DATA_HOME/julius` on Linux.
  - `get_temp_dir()`: Resolves system temp directory via `tempfile.gettempdir()`.

### C. System Clipboard Integration
- **Original Status:** `src/cli/v3_tui.py` checked only `pbcopy`, `xclip`, and `wl-copy`. Failed on Windows.
- **Resolution:** Implemented `copy_to_clipboard(text)` in `src/platform_compat.py`:
  1. Windows: Native `clip.exe`
  2. macOS: Native `pbcopy`
  3. Linux: `wl-copy` (Wayland) -> `xclip` (X11)
  4. Universal fallback: `pyperclip`
  Delegated all call sites (`src/cli/v3_tui.py`, `run_agent.py`, `src/tui/app.py`) to this implementation.

### D. Entry Points & Wrappers
- **Original Status:** `julius`, `start_tui.sh`, `install.sh` were bash-only.
- **Resolution:**
  - Added Windows PowerShell runner: `julius.ps1`
  - Added Windows CMD batch runner: `julius.cmd`
  - Added Windows TUI launcher: `start_tui.ps1`
  - Added Universal Python launcher: `julius.py`
  - Added Windows native installer: `install.ps1`
  - Added Universal Python installer: `install.py`
  - Updated `install.sh` to delegate to `install.ps1` when invoked from Git Bash or MSYS on Windows.

### E. Dependencies & Packaging
- **Original Status:** Split ad-hoc requirement files with missing Windows platform markers.
- **Resolution:**
  - Consolidated markers in `requirements.txt`:
    - `pyobjc-*`, `macholib`, `py2app`, `altgraph`, `modulegraph` restricted with `; sys_platform == 'darwin'`.
    - `pywin32>=306`, `PyGetWindow==0.0.9` configured with `; sys_platform == 'win32'`.
  - Added Windows MSI/ZIP build script: `scripts/build_msi.ps1`.
  - Added GitHub Actions cross-platform matrix (`.github/workflows/cross-platform.yml`) testing Linux, macOS, and Windows on Python 3.11 and 3.12.

---

## 3. Verification Matrix

| Platform | Installer | CLI Runner | TUI | GUI Server | Status |
|---|---|---|---|---|---|
| **macOS** | `./install.sh` / `python install.py` | `./julius` / `python julius.py` | `./start_tui.sh` | `python julius_gui.py` | **Verified** |
| **Linux (Ubuntu/Fedora)** | `./install.sh` / `python install.py` | `./julius` / `python julius.py` | `./julius --tui` | `python julius_gui.py` | **Verified** |
| **Windows 10/11 (Native)** | `.\install.ps1` / `python install.py` | `.\julius.ps1` / `julius.cmd` | `.\start_tui.ps1` | `python julius_gui.py` | **Verified** |
| **Windows (WSL)** | `./install.sh` | `./julius` | `./start_tui.sh` | `python julius_gui.py` | **Verified** |
