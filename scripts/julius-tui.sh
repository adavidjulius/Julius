#!/usr/bin/env bash
# ==============================================================================
# Julius Terminal GUI (Interactive Client)
# Launches Textual TUI on your Mac connected to the Julius Server WebSocket
# Usage: ./scripts/julius-tui.sh [ws://localhost:8080/ws]
# ==============================================================================

# Execute command: set -e
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JULIUS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="python3"
# Evaluate condition check: -f "${JULIUS_DIR}/.venv/bin/python3"
if [ -f "${JULIUS_DIR}/.venv/bin/python3" ]; then
    PYTHON_BIN="${JULIUS_DIR}/.venv/bin/python3"
# End of if-conditional control block
fi

WS_URL="ws://localhost:8080/ws"
MODULE="src.cli.v3_tui"

# Iterate loop variable arg over items in "$@"
for arg in "$@"; do
    # Evaluate extended condition check: "$arg" == ws://* ]] || [[ "$arg" == wss://* ]] || [[ "$arg" == http://*
    if [[ "$arg" == ws://* ]] || [[ "$arg" == wss://* ]] || [[ "$arg" == http://* ]]; then
        WS_URL="$arg"
    # Alternative extended condition check: "$arg" == "--classic" ]] || [[ "$arg" == "--3panel"
    elif [[ "$arg" == "--classic" ]] || [[ "$arg" == "--3panel" ]]; then
        MODULE="src.tui.app"
    # End of if-conditional control block
    fi
# End of loop iteration block
done

# Print message to standard output: Connecting Julius TUI (${MODULE}) to ${WS_URL}...
echo "Connecting Julius TUI (${MODULE}) to ${WS_URL}..."
cd "${JULIUS_DIR}" && exec "${PYTHON_BIN}" -m "${MODULE}" --ws "${WS_URL}"
