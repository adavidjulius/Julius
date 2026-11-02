#!/usr/bin/env bash

GLOBAL_VENV="/opt/julius/.venv"
USER_DIR="${HOME}/.local/share/julius"
USER_VENV="${USER_DIR}/venv"

# Determine which virtual environment to use
if [ -f "${GLOBAL_VENV}/bin/python3" ] && [ -f "${GLOBAL_VENV}/bin/playwright" ]; then
    # Use global environment
    export PLAYWRIGHT_BROWSERS_PATH="/opt/julius/.playwright-browsers"
    # Replace current shell process with: "${GLOBAL_VENV}/bin/python3" /opt/julius/julius_cli.py "$@"
    exec "${GLOBAL_VENV}/bin/python3" /opt/julius/julius_cli.py "$@"
# Fallback branch when preceding conditions evaluate to false
else
    # Fallback to user environment
    export PLAYWRIGHT_BROWSERS_PATH="${USER_DIR}/playwright-browsers"
    # Evaluate condition check: ! -f "${USER_VENV}/bin/python3"
    if [ ! -f "${USER_VENV}/bin/python3" ]; then
        # Print message to standard output: 🚀 Initializing Julius Agent (user-local environment)...
        echo "🚀 Initializing Julius Agent (user-local environment)..."
        mkdir -p "${USER_DIR}"
        # Execute command: python3 -m venv "${USER_VENV}"
        python3 -m venv "${USER_VENV}"
        # Execute command: "${USER_VENV}/bin/pip" install --upgrade pip --quiet 2>/dev/null || "${USER_VENV}/bin/pip" install --upgrade pip
        "${USER_VENV}/bin/pip" install --upgrade pip --quiet 2>/dev/null || "${USER_VENV}/bin/pip" install --upgrade pip
        # Execute command: "${USER_VENV}/bin/pip" install -r /opt/julius/requirements.txt --quiet 2>/dev/null || "${USER_VENV}/bin/pip" install -r /opt/julius/requirements.txt
        "${USER_VENV}/bin/pip" install -r /opt/julius/requirements.txt --quiet 2>/dev/null || "${USER_VENV}/bin/pip" install -r /opt/julius/requirements.txt
        # Execute command: "${USER_VENV}/bin/pip" install -r /opt/julius/requirements-agent.txt --quiet 2>/dev/null || "${USER_VENV}/bin/pip" install -r /opt/julius/requirements-agent.txt
        "${USER_VENV}/bin/pip" install -r /opt/julius/requirements-agent.txt --quiet 2>/dev/null || "${USER_VENV}/bin/pip" install -r /opt/julius/requirements-agent.txt
        # Execute command: "${USER_VENV}/bin/playwright" install chromium
        "${USER_VENV}/bin/playwright" install chromium
        # Print message to standard output: ✅ Initialization complete!
        echo "✅ Initialization complete!"
    # End of if-conditional control block
    fi
    # Replace current shell process with: "${USER_VENV}/bin/python3" /opt/julius/julius_cli.py "$@"
    exec "${USER_VENV}/bin/python3" /opt/julius/julius_cli.py "$@"
# End of if-conditional control block
fi
