#!/usr/bin/env python3
"""
Julius CLI entrypoint script.
Launches run_agent.py with command line arguments.
"""
import sys
import subprocess
import os

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    runner_path = os.path.join(script_dir, "run_agent.py")
    subprocess.run([sys.executable, runner_path] + sys.argv[1:])
