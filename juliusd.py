#!/usr/bin/env python3
"""
Julius Daemon Runner (juliusd.py).
Launches the Julius Web UI & WebSocket backend engine (julius_gui.py).
"""
import os
import sys
import subprocess
from pathlib import Path

script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(script_dir))

from src.platform_compat import python_executable
from src.security.daemon_hardening import enforce_loopback_binding

if __name__ == "__main__":
    # Check if host argument was supplied and enforce loopback binding
    for i, arg in enumerate(sys.argv):
        if arg == "--host" and i + 1 < len(sys.argv):
            enforce_loopback_binding(sys.argv[i + 1], os.getenv("JULIUS_TLS_CERT"))
        elif arg.startswith("--host="):
            enforce_loopback_binding(arg.split("=", 1)[1], os.getenv("JULIUS_TLS_CERT"))

    server_path = str(script_dir / "julius_gui.py")
    py_bin = python_executable(script_dir)
    subprocess.run([py_bin, server_path] + sys.argv[1:])
