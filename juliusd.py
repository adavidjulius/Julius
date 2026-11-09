#!/usr/bin/env python3
"""
Julius Autonomous Daemon Runner (juliusd.py).
Launches the Julius Proactive Executive Daemon alongside the Web UI & WebSocket backend engine.
"""
import argparse
import asyncio
import os
import sys
import subprocess
import threading
from pathlib import Path

script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(script_dir))

from src.platform_compat import python_executable
from src.security.daemon_hardening import enforce_loopback_binding
from src.services.proactive_daemon import get_proactive_daemon

def run_proactive_loop(workspace: str, interval: float):
    """Run proactive daemon monitoring loop in background thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    daemon = get_proactive_daemon(workspace=workspace)
    daemon.heartbeat_interval = interval
    daemon.auto_notify = True
    try:
        loop.run_until_complete(daemon.start())
    except KeyboardInterrupt:
        daemon.stop()
    finally:
        loop.close()

if __name__ == "__main__":
    # Check if host argument was supplied and enforce loopback binding
    for i, arg in enumerate(sys.argv):
        if arg == "--host" and i + 1 < len(sys.argv):
            enforce_loopback_binding(sys.argv[i + 1], os.getenv("JULIUS_TLS_CERT"))
        elif arg.startswith("--host="):
            enforce_loopback_binding(arg.split("=", 1)[1], os.getenv("JULIUS_TLS_CERT"))

    # Start proactive heartbeat monitor in background
    proactive_thread = threading.Thread(
        target=run_proactive_loop,
        args=(str(script_dir), 30.0),
        daemon=True,
    )
    proactive_thread.start()

    server_path = str(script_dir / "julius_gui.py")
    py_bin = python_executable(script_dir)
    subprocess.run([py_bin, server_path] + sys.argv[1:])
