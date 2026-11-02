"""
Julius Platform Compatibility Layer.

Single source of truth for OS-specific branching, paths, subprocess execution,
and clipboard interactions across Linux, macOS, and Windows.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, List, Optional, Union

# ── 1. OS & Architecture Detection ──────────────────────────────────────────

SYSTEM_NAME = platform.system().lower()

IS_WINDOWS: bool = sys.platform.startswith("win") or SYSTEM_NAME == "windows"
IS_MACOS: bool = sys.platform == "darwin" or SYSTEM_NAME == "darwin"
IS_LINUX: bool = (sys.platform.startswith("linux") or SYSTEM_NAME == "linux") and not IS_WINDOWS and not IS_MACOS


def _check_is_wsl() -> bool:
    """Sniff whether the host environment is Windows Subsystem for Linux."""
    if not IS_LINUX:
        return False
    try:
        proc_ver = Path("/proc/version")
        if proc_ver.exists():
            content = proc_ver.read_text(encoding="utf-8", errors="ignore").lower()
            return "microsoft" in content or "wsl" in content
    except Exception:
        pass
    return False


IS_WSL: bool = _check_is_wsl()


def get_platform_name() -> str:
    """Return normalized platform identifier: 'windows', 'macos', 'wsl', or 'linux'."""
    if IS_WSL:
        return "wsl"
    if IS_WINDOWS:
        return "windows"
    if IS_MACOS:
        return "macos"
    return "linux"


# ── 2. Standard Directory Resolution ─────────────────────────────────────────

def get_home_dir() -> Path:
    """Return user's home directory."""
    return Path.home()


def get_config_dir(app_name: str = "Julius") -> Path:
    """
    Return OS-appropriate user configuration directory:
    - macOS: ~/Library/Application Support/Julius
    - Windows: %APPDATA%/Julius (or ~/AppData/Roaming/Julius)
    - Linux / WSL: $XDG_CONFIG_HOME/julius (or ~/.config/julius)
    """
    if IS_WINDOWS:
        app_data = os.environ.get("APPDATA")
        base = Path(app_data) if app_data else get_home_dir() / "AppData" / "Roaming"
        target = base / app_name
    elif IS_MACOS:
        target = get_home_dir() / "Library" / "Application Support" / app_name
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg_config) if xdg_config else get_home_dir() / ".config"
        target = base / app_name.lower()

    target.mkdir(parents=True, exist_ok=True)
    return target


def get_cache_dir(app_name: str = "Julius") -> Path:
    """
    Return OS-appropriate user cache directory:
    - macOS: ~/Library/Caches/Julius
    - Windows: %LOCALAPPDATA%/Julius/Cache
    - Linux / WSL: $XDG_CACHE_HOME/julius (or ~/.cache/julius)
    """
    if IS_WINDOWS:
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else get_home_dir() / "AppData" / "Local"
        target = base / app_name / "Cache"
    elif IS_MACOS:
        target = get_home_dir() / "Library" / "Caches" / app_name
    else:
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        base = Path(xdg_cache) if xdg_cache else get_home_dir() / ".cache"
        target = base / app_name.lower()

    target.mkdir(parents=True, exist_ok=True)
    return target


def get_data_dir(app_name: str = "Julius") -> Path:
    """
    Return OS-appropriate user data / state directory:
    - macOS: ~/Library/Application Support/Julius
    - Windows: %LOCALAPPDATA%/Julius
    - Linux / WSL: $XDG_DATA_HOME/julius (or ~/.local/share/julius)
    """
    if IS_WINDOWS:
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else get_home_dir() / "AppData" / "Local"
        target = base / app_name
    elif IS_MACOS:
        target = get_home_dir() / "Library" / "Application Support" / app_name
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg_data) if xdg_data else get_home_dir() / ".local" / "share"
        target = base / app_name.lower()

    target.mkdir(parents=True, exist_ok=True)
    return target


def get_temp_dir() -> Path:
    """Return OS-appropriate temporary directory."""
    return Path(tempfile.gettempdir())


# ── 3. Cross-Platform Clipboard ──────────────────────────────────────────────

def copy_to_clipboard(text: str) -> bool:
    """
    Copy text to system clipboard across macOS, Windows, and Linux.
    Tries native OS utilities first, then falls back to pyperclip if installed.
    """
    if not text:
        return False

    # 1. Native Windows: clip.exe
    if IS_WINDOWS:
        try:
            proc = subprocess.run(
                ["clip"],
                input=text,
                text=True,
                capture_output=True,
                check=False,
                timeout=5,
            )
            if proc.returncode == 0:
                return True
        except Exception:
            pass

    # 2. Native macOS: pbcopy
    elif IS_MACOS:
        try:
            proc = subprocess.run(
                ["pbcopy"],
                input=text,
                text=True,
                capture_output=True,
                check=False,
                timeout=5,
            )
            if proc.returncode == 0:
                return True
        except Exception:
            pass

    # 3. Native Linux: wl-copy (Wayland) then xclip (X11)
    elif IS_LINUX:
        try:
            proc = subprocess.run(
                ["wl-copy"],
                input=text,
                text=True,
                capture_output=True,
                check=False,
                timeout=5,
            )
            if proc.returncode == 0:
                return True
        except Exception:
            pass

        try:
            proc = subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text,
                text=True,
                capture_output=True,
                check=False,
                timeout=5,
            )
            if proc.returncode == 0:
                return True
        except Exception:
            pass

    # 4. Universal Fallback: pyperclip
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        pass

    return False


def get_clipboard_text() -> str:
    """
    Retrieve text from system clipboard across macOS, Linux, and Windows.
    Returns empty string if unavailable or empty.
    """
    # 1. Native Windows: PowerShell Get-Clipboard
    if IS_WINDOWS:
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout:
                return res.stdout
        except Exception:
            pass

    # 2. Native macOS: pbpaste
    elif IS_MACOS:
        try:
            res = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout:
                return res.stdout
        except Exception:
            pass

    # 3. Native Linux: wl-paste (Wayland) then xclip (X11)
    elif IS_LINUX:
        try:
            res = subprocess.run(
                ["wl-paste"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout:
                return res.stdout
        except Exception:
            pass

        try:
            res = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout:
                return res.stdout
        except Exception:
            pass

    # 4. Universal Fallback: pyperclip
    try:
        import pyperclip
        return pyperclip.paste() or ""
    except Exception:
        pass

    return ""


# ── 4. Executable & File System Utilities ────────────────────────────────────

def which(name: str) -> Optional[str]:
    """
    Find executable on PATH, appending Windows extensions (.exe, .cmd, .bat)
    if running on Windows.
    """
    if IS_WINDOWS:
        for ext in ("", ".exe", ".cmd", ".bat"):
            candidate = shutil.which(name + ext if not name.lower().endswith(ext) else name)
            if candidate:
                return candidate
        return None
    return shutil.which(name)


def python_executable(workspace_dir: Optional[Union[str, Path]] = None) -> str:
    """
    Resolve the preferred Python interpreter:
    1. Active virtual environment from sys.prefix (if not system python)
    2. Local .venv inside workspace_dir:
       - Windows: .venv/Scripts/python.exe
       - POSIX:   .venv/bin/python
    3. Active VIRTUAL_ENV environment variable
    4. sys.executable
    """
    # 1. Inside a virtualenv already
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        return sys.executable

    ws = Path(workspace_dir) if workspace_dir else Path.cwd()

    # 2. Workspace .venv
    if IS_WINDOWS:
        local_venv_py = ws / ".venv" / "Scripts" / "python.exe"
    else:
        local_venv_py = ws / ".venv" / "bin" / "python"

    if local_venv_py.is_file():
        return str(local_venv_py.absolute())

    # 3. VIRTUAL_ENV env var
    venv_env = os.environ.get("VIRTUAL_ENV")
    if venv_env:
        v_path = Path(venv_env)
        cand = (v_path / "Scripts" / "python.exe") if IS_WINDOWS else (v_path / "bin" / "python")
        if cand.is_file():
            return str(cand.absolute())

    # 4. Fallback to current sys.executable
    return sys.executable


def safe_chmod(path: Union[str, Path], mode: int) -> None:
    """Safely apply chmod only on POSIX systems (no-op on Windows)."""
    if not IS_WINDOWS:
        try:
            os.chmod(path, mode)
        except OSError:
            pass


def open_in_default_app(path: Union[str, Path]) -> bool:
    """Open a file or directory in the user's default OS application."""
    target = str(path)
    try:
        if IS_WINDOWS:
            os.startfile(target)  # type: ignore[attr-defined]
            return True
        elif IS_MACOS:
            subprocess.run(["open", target], check=False, timeout=10)
            return True
        else:
            subprocess.run(["xdg-open", target], check=False, timeout=10)
            return True
    except Exception:
        return False


def shell_exec(
    cmd: Union[str, List[str]],
    cwd: Optional[Union[str, Path]] = None,
    timeout: int = 300,
    check: bool = False,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """
    Execute a shell command with OS-appropriate execution behavior:
    - Windows: cmd.exe / powershell compatible
    - POSIX: /bin/bash or default shell
    """
    if isinstance(cmd, str):
        if IS_WINDOWS:
            return subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                timeout=timeout,
                check=check,
                text=True,
                capture_output=True,
                **kwargs,
            )
        else:
            bash_bin = shutil.which("bash") or "/bin/sh"
            return subprocess.run(
                cmd,
                shell=True,
                executable=bash_bin,
                cwd=cwd,
                timeout=timeout,
                check=check,
                text=True,
                capture_output=True,
                **kwargs,
            )
    else:
        return subprocess.run(
            cmd,
            shell=False,
            cwd=cwd,
            timeout=timeout,
            check=check,
            text=True,
            capture_output=True,
            **kwargs,
        )
