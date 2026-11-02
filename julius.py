#!/usr/bin/env python3
"""
Julius Agent — Universal Cross-Platform Launcher (julius.py).

Launches Julius CLI, TUI, or GUI using the virtual environment across
Linux, macOS, and Windows.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.platform_compat import IS_WINDOWS, python_executable


def main() -> int:
    args = sys.argv[1:]

    # Check for mode shortcuts
    target_script = PROJECT_ROOT / "run_agent.py"
    if args and args[0] == "--gui":
        target_script = PROJECT_ROOT / "julius_gui.py"
        args = args[1:]
    elif args and args[0] == "--tui":
        target_script = PROJECT_ROOT / "run_agent.py"
        # run_agent.py launches TUI by default when interactive
        args = args[1:]

    py_bin = python_executable(PROJECT_ROOT)

    cmd = [py_bin, str(target_script)] + args

    if IS_WINDOWS:
        res = subprocess.run(cmd)
        return res.returncode
    else:
        try:
            os.execv(py_bin, cmd)
        except OSError:
            res = subprocess.run(cmd)
            return res.returncode


if __name__ == "__main__":
    sys.exit(main())
