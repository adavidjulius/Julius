#!/usr/bin/env python3
"""
Julius Agent — Universal Cross-Platform Python Installer (install.py).

Works identically on Linux, macOS, and Windows without requiring bash or PowerShell.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configure UTF-8 output if possible on Windows
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from src.platform_compat import (
    IS_LINUX,
    IS_MACOS,
    IS_WINDOWS,
    IS_WSL,
    get_platform_name,
    python_executable,
)

COLOR_JULIUS = "\033[38;2;200;184;150m"
COLOR_RESET = "\033[0m"

JULIUS_BANNER = r"""
  ╔═════╗ ╔╗   ╔╗ ╔╗      ╔═════╗ ╔╗   ╔╗ ╔═════╗
  ╚══╗  ║ ║║   ║║ ║║      ╚═╗ ╔═╝ ║║   ║║ ║ ╔═══╝
     ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ║ ╚═══╗
     ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ╚═══╗ ║
  ╔══╝  ║ ║╚═══╝║ ║╚════╗ ╔═╝ ╚═╗ ║╚═══╝║ ╔═══╝ ║
  ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝
"""
JULIUS_COMPACT_BANNER = "  ━━━  J U L I U S  ━━━"


def get_banner(subtitle: str = "Autonomous AI Copilot — Universal Installer (Python)") -> str:
    cols = shutil.get_terminal_size((80, 24)).columns
    banner_art = JULIUS_COMPACT_BANNER if cols < 52 else JULIUS_BANNER.strip("\n")
    return f"{COLOR_JULIUS}{banner_art}\n  {subtitle}{COLOR_RESET}\n"


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            print(text.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass


def _supports_unicode() -> bool:
    if sys.platform != "win32":
        return True
    enc = (getattr(sys.stdout, "encoding", None) or "").lower()
    return "utf" in enc


def log_step(step: int, total: int, msg: str) -> None:
    _safe_print(f"\n[{step}/{total}] \033[1;36m{msg}\033[0m")


def log_ok(msg: str) -> None:
    sym = "✓" if _supports_unicode() else "[OK]"
    _safe_print(f"  \033[1;32m{sym}\033[0m  {msg}")


def log_warn(msg: str) -> None:
    sym = "⚠" if _supports_unicode() else "[!]"
    _safe_print(f"  \033[1;33m{sym}\033[0m  {msg}")


def log_err(msg: str) -> None:
    sym = "✗" if _supports_unicode() else "[X]"
    _safe_print(f"  \033[1;31m{sym}\033[0m  {msg}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Julius Universal Installer")
    parser.add_argument("--no-verify", action="store_true", help="Skip verification step")
    parser.add_argument("--no-browser", action="store_true", help="Skip Playwright browser provisioning")
    parser.add_argument("--python", default=None, help="Custom Python binary to use")
    args = parser.parse_args()

    _safe_print(get_banner())
    total_steps = 5

    # 1. Environment & Platform check
    log_step(1, total_steps, "Detecting host environment")
    plat = get_platform_name()
    print(f"  Platform: {plat} (sys.platform: {sys.platform})")
    print(f"  Python:   {sys.version.split()[0]}")

    if sys.version_info < (3, 10):
        log_err("Julius requires Python 3.10 or higher.")
        return 1
    log_ok("Python version requirement satisfied")

    # 2. Virtual Environment (.venv) setup
    log_step(2, total_steps, "Preparing virtual environment (.venv)")
    venv_dir = PROJECT_ROOT / ".venv"
    if IS_WINDOWS:
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    if not venv_python.exists():
        print(f"  Creating venv at {venv_dir}...")
        import venv
        venv.create(str(venv_dir), with_pip=True)

    if not venv_python.exists():
        log_err(f"Virtual environment python not found at {venv_python}")
        return 1
    log_ok(f"Virtual environment ready at {venv_dir}")

    # 3. Upgrade pip and install dependencies
    log_step(3, total_steps, "Installing dependencies from requirements.txt")
    req_file = PROJECT_ROOT / "requirements.txt"
    if req_file.exists():
        cmd_upgrade = [str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"]
        subprocess.run(cmd_upgrade, check=False)

        cmd_install = [str(venv_python), "-m", "pip", "install", "--progress-bar", "on", "-r", str(req_file)]
        res = subprocess.run(cmd_install, check=False)
        if res.returncode != 0:
            log_err("Dependency installation failed.")
            return res.returncode
        log_ok("Dependencies installed")
    else:
        log_warn("requirements.txt not found, skipping dependency installation")

    # 4. Playwright Browser provisioning
    log_step(4, total_steps, "Setting up Playwright browser")
    if args.no_browser or os.environ.get("JULIUS_SKIP_BROWSER") == "1":
        print("  Skipping browser download (--no-browser specified).")
    else:
        cmd_pw = [str(venv_python), "-m", "playwright", "install", "chromium"]
        res = subprocess.run(cmd_pw, check=False)
        if res.returncode == 0:
            log_ok("Chromium browser engine ready")
        else:
            log_warn("Playwright browser setup returned non-zero code.")

    # 4b. TypeScript React Ink TUI provisioning
    tui_ts_dir = PROJECT_ROOT / "src" / "tui_ts"
    npm_bin = shutil.which("npm") or shutil.which("pnpm")
    if npm_bin and tui_ts_dir.exists():
        try:
            if not (tui_ts_dir / "node_modules").exists():
                subprocess.run([npm_bin, "install"], cwd=str(tui_ts_dir), check=False)
            subprocess.run([npm_bin, "run", "build"], cwd=str(tui_ts_dir), check=False)
            log_ok("TypeScript React Ink TUI compiled (@julius/tui)")
        except Exception as exc:
            log_warn(f"TypeScript TUI build skipped: {exc}")

    # 5. Configuration & Verification
    log_step(5, total_steps, "Verifying setup")
    env_file = PROJECT_ROOT / ".env"
    env_example = PROJECT_ROOT / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copyfile(str(env_example), str(env_file))
        log_ok("Created .env from .env.example")

    if not args.no_verify and os.environ.get("JULIUS_SKIP_VERIFY") != "1":
        verify_code = (
            "from src.platform_compat import get_platform_name; "
            "from src.web_agent import WebAgent; "
            "print('Verified core agent on', get_platform_name())"
        )
        res = subprocess.run([str(venv_python), "-c", verify_code], check=False, capture_output=True, text=True)
        if res.returncode == 0:
            log_ok("Core imports verified successfully")
        else:
            log_warn(f"Verification output: {res.stderr}")

    if sys.stdin.isatty() and not os.environ.get("CI"):
        try:
            from src.cli.setup_wizard import run_first_run_setup
            run_first_run_setup(str(PROJECT_ROOT))
        except Exception:
            pass

    print("\n\033[1;32mInstallation Complete!\033[0m")
    print("---------------------------------------------------------")
    if IS_WINDOWS:
        print("Launch Julius:     .\\julius.cmd  or  python julius.py")
    else:
        print("Launch Julius:     julius  or  ./julius")
    print("---------------------------------------------------------\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
