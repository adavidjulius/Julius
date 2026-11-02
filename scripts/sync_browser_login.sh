#!/usr/bin/env bash
# ==============================================================================
# Julius Browser Login & Remote Session Sync Helper
# Usage: ./scripts/sync_browser_login.sh [deepseek|chatgpt|gemini|grok|perplexity]
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

PROVIDER="${1:-deepseek}"
cd "${JULIUS_DIR}" && exec "${PYTHON_BIN}" scripts/sync_browser_login.py "${PROVIDER}"
