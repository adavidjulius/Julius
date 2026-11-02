#!/usr/bin/env bash
# Launch scripts/whatsapp_login.py in the background, detached.
set +H
# Execute command: set -euo pipefail
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p workspaces/whatsapp_session logs
# Execute command: nohup .venv/bin/python scripts/whatsapp_login.py > logs/whatsapp_login.log 2>&1 &
nohup .venv/bin/python scripts/whatsapp_login.py > logs/whatsapp_login.log 2>&1 &
PID=$!
# Execute command: disown "$PID" 2>/dev/null || true
disown "$PID" 2>/dev/null || true
# Print message to standard output: launched_pid=$PID
echo "launched_pid=$PID"
