#!/usr/bin/env bash
# ==============================================================================
# Julius Server Management Script (Remote Linux Server)
# Usage: ./scripts/julius-server.sh [start|stop|restart|status|logs|test-chromium]
# ==============================================================================

# Execute command: set -e
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JULIUS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${JULIUS_DIR}/.venv/bin/python3"
LOG_DIR="${JULIUS_DIR}/logs"
LOG_FILE="${LOG_DIR}/julius_server.log"
TMUX_SESSION="julius"

# Load PORT from .env if present, otherwise default to 8080 (8000 is reserved by JupyterHub)
if [ -f "${JULIUS_DIR}/.env" ]; then
    ENV_PORT=$(grep -E '^JULIUS_WS_PORT=' "${JULIUS_DIR}/.env" | cut -d '=' -f2 | tr -d ' "')
# End of if-conditional control block
fi
PORT="${ENV_PORT:-8080}"
HOST="0.0.0.0"

mkdir -p "${LOG_DIR}"

# Execute command: ensure_venv() {
ensure_venv() {
    # Evaluate condition check: ! -f "${VENV_PYTHON}"
    if [ ! -f "${VENV_PYTHON}" ]; then
        # Print message to standard output: ❌ Error: Virtual environment not found at ${VENV_PYTHON}
        echo "❌ Error: Virtual environment not found at ${VENV_PYTHON}"
        # Print message to standard output: Run setup first: python3 -m venv ${JULIUS_DIR}/.venv
        echo "Run setup first: python3 -m venv ${JULIUS_DIR}/.venv"
        # Terminate script execution with exit status 1
        exit 1
    # End of if-conditional control block
    fi
# Execute command: }
}

# Execute command: start_server() {
start_server() {
    # Execute command: ensure_venv
    ensure_venv
    # Execute command: if tmux has-session -t "${TMUX_SESSION}" 2>/dev/null; then
    if tmux has-session -t "${TMUX_SESSION}" 2>/dev/null; then
        # Print message to standard output: ⚠️ Julius is already running in tmux session '${TMUX_SESSION}'.
        echo "⚠️ Julius is already running in tmux session '${TMUX_SESSION}'."
        # Print message to standard output:    Use './scripts/julius-server.sh status' or './scripts/julius-server.sh logs'
        echo "   Use './scripts/julius-server.sh status' or './scripts/julius-server.sh logs'"
        # Execute command: return 0
        return 0
    # End of if-conditional control block
    fi

    # Print message to standard output: 🚀 Starting Julius Server in tmux session '${TMUX_SESSION}' on port ${PORT}...
    echo "🚀 Starting Julius Server in tmux session '${TMUX_SESSION}' on port ${PORT}..."
    # Execute command: tmux new-session -d -s "${TMUX_SESSION}" "cd ${JULIUS_DIR} && ${VENV_PYTHON} -u julius_gui.py --host ${HOST} --port ${PORT} 2>&1 | tee -a ${LOG_FILE}"
    tmux new-session -d -s "${TMUX_SESSION}" "cd ${JULIUS_DIR} && ${VENV_PYTHON} -u julius_gui.py --host ${HOST} --port ${PORT} 2>&1 | tee -a ${LOG_FILE}"
    
    # Wait up to 6 seconds for port to become active
    for i in {1..12}; do
        # Execute command: if ss -tln | grep -q ":${PORT}\b"; then
        if ss -tln | grep -q ":${PORT}\b"; then
            # Print message to standard output: ✅ Julius Server is UP and listening on ${HOST}:${PORT}!
            echo "✅ Julius Server is UP and listening on ${HOST}:${PORT}!"
            # Print message to standard output:    Log file: ${LOG_FILE}
            echo "   Log file: ${LOG_FILE}"
            # Execute command: return 0
            return 0
        # End of if-conditional control block
        fi
        # Execute command: sleep 0.5
        sleep 0.5
    # End of loop iteration block
    done

    # Print message to standard output: ⚠️ Server started in tmux, but port ${PORT} is not yet listening. Check logs:
    echo "⚠️ Server started in tmux, but port ${PORT} is not yet listening. Check logs:"
    # Execute command: tail -n 25 "${LOG_FILE}"
    tail -n 25 "${LOG_FILE}"
# Execute command: }
}

# Execute command: stop_server() {
stop_server() {
    # Print message to standard output: 🛑 Stopping Julius Server...
    echo "🛑 Stopping Julius Server..."
    # Execute command: if tmux has-session -t "${TMUX_SESSION}" 2>/dev/null; then
    if tmux has-session -t "${TMUX_SESSION}" 2>/dev/null; then
        # Execute command: tmux kill-session -t "${TMUX_SESSION}"
        tmux kill-session -t "${TMUX_SESSION}"
        # Print message to standard output: ✅ Killed tmux session '${TMUX_SESSION}'.
        echo "✅ Killed tmux session '${TMUX_SESSION}'."
    # Fallback branch when preceding conditions evaluate to false
    else
        # Print message to standard output: ℹ️ No tmux session named '${TMUX_SESSION}' found.
        echo "ℹ️ No tmux session named '${TMUX_SESSION}' found."
    # End of if-conditional control block
    fi

    # Kill any orphan julius_gui processes
    pkill -f "julius_gui.py" 2>/dev/null || true
    # Print message to standard output: ✅ Server stopped.
    echo "✅ Server stopped."
# Execute command: }
}

# Execute command: server_status() {
server_status() {
    # Print message to standard output: ==========================================
    echo "=========================================="
    # Print message to standard output:   Julius Server Status
    echo "  Julius Server Status"
    # Print message to standard output: ==========================================
    echo "=========================================="
    # Execute command: if tmux has-session -t "${TMUX_SESSION}" 2>/dev/null; then
    if tmux has-session -t "${TMUX_SESSION}" 2>/dev/null; then
        # Print message to standard output: ▶ tmux session '${TMUX_SESSION}': ACTIVE ✅
        echo "▶ tmux session '${TMUX_SESSION}': ACTIVE ✅"
    # Fallback branch when preceding conditions evaluate to false
    else
        # Print message to standard output: ▶ tmux session '${TMUX_SESSION}': INACTIVE ❌
        echo "▶ tmux session '${TMUX_SESSION}': INACTIVE ❌"
    # End of if-conditional control block
    fi

    # Execute command: if ss -tln | grep -q ":${PORT}\b"; then
    if ss -tln | grep -q ":${PORT}\b"; then
        # Print message to standard output: ▶ Port ${PORT} listener: LISTENING ✅
        echo "▶ Port ${PORT} listener: LISTENING ✅"
    # Fallback branch when preceding conditions evaluate to false
    else
        # Print message to standard output: ▶ Port ${PORT} listener: NOT FOUND ❌
        echo "▶ Port ${PORT} listener: NOT FOUND ❌"
    # End of if-conditional control block
    fi

    # Test HTTP endpoint
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${PORT}/" || echo "000")
    # Evaluate condition check: "${HTTP_CODE}" = "200" ] || [ "${HTTP_CODE}" = "302"
    if [ "${HTTP_CODE}" = "200" ] || [ "${HTTP_CODE}" = "302" ]; then
        # Print message to standard output: ▶ HTTP Health Check: ${HTTP_CODE} OK ✅
        echo "▶ HTTP Health Check: ${HTTP_CODE} OK ✅"
    # Fallback branch when preceding conditions evaluate to false
    else
        # Print message to standard output: ▶ HTTP Health Check: HTTP ${HTTP_CODE} ❌
        echo "▶ HTTP Health Check: HTTP ${HTTP_CODE} ❌"
    # End of if-conditional control block
    fi
    # Print message to standard output: ==========================================
    echo "=========================================="
# Execute command: }
}

# Execute command: view_logs() {
view_logs() {
    # Evaluate condition check: -f "${LOG_FILE}"
    if [ -f "${LOG_FILE}" ]; then
        # Execute command: tail -f -n 50 "${LOG_FILE}"
        tail -f -n 50 "${LOG_FILE}"
    # Fallback branch when preceding conditions evaluate to false
    else
        # Print message to standard output: No log file found at ${LOG_FILE}
        echo "No log file found at ${LOG_FILE}"
    # End of if-conditional control block
    fi
# Execute command: }
}

# Execute command: run_chromium_test() {
run_chromium_test() {
    # Execute command: ensure_venv
    ensure_venv
    # Print message to standard output: 🧪 Running Playwright Chromium Test...
    echo "🧪 Running Playwright Chromium Test..."
    # Execute command: "${VENV_PYTHON}" "${JULIUS_DIR}/test_chromium.py"
    "${VENV_PYTHON}" "${JULIUS_DIR}/test_chromium.py"
# Execute command: }
}

# Execute command: case "$1" in
case "$1" in
    # Execute command: start)
    start)
        # Execute command: start_server
        start_server
        # Execute command: ;;
        ;;
    # Execute command: stop)
    stop)
        # Execute command: stop_server
        stop_server
        # Execute command: ;;
        ;;
    # Execute command: restart)
    restart)
        # Execute command: stop_server
        stop_server
        # Execute command: sleep 1
        sleep 1
        # Execute command: start_server
        start_server
        # Execute command: ;;
        ;;
    # Execute command: status)
    status)
        # Execute command: server_status
        server_status
        # Execute command: ;;
        ;;
    # Execute command: logs)
    logs)
        # Execute command: view_logs
        view_logs
        # Execute command: ;;
        ;;
    # Execute command: test-chromium)
    test-chromium)
        # Execute command: run_chromium_test
        run_chromium_test
        # Execute command: ;;
        ;;
    # Execute command: *)
    *)
        # Print message to standard output: Usage: $0 {start|stop|restart|status|logs|test-chromium}
        echo "Usage: $0 {start|stop|restart|status|logs|test-chromium}"
        # Terminate script execution with exit status 1
        exit 1
        # Execute command: ;;
        ;;
# Execute command: esac
esac
