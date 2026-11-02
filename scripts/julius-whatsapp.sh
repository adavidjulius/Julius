#!/usr/bin/env bash
# ==============================================================================
# Julius WhatsApp Personal Agent Management Script
# Usage: ./scripts/julius-whatsapp.sh [status|connect|disconnect|pause|resume|stop|qr|logs]
# ==============================================================================

# Execute command: set -e
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JULIUS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${JULIUS_DIR}/logs"
LOG_FILE="${LOG_DIR}/julius_server.log"

# Load PORT from .env if present
if [ -f "${JULIUS_DIR}/.env" ]; then
    ENV_PORT=$(grep -E '^JULIUS_WS_PORT=' "${JULIUS_DIR}/.env" | cut -d '=' -f2 | tr -d ' "')
# End of if-conditional control block
fi
PORT="${ENV_PORT:-8080}"
API_URL="http://127.0.0.1:${PORT}/api/whatsapp"

# Execute command: check_curl() {
check_curl() {
    # Execute command: if ! command -v curl &>/dev/null; then
    if ! command -v curl &>/dev/null; then
        # Print message to standard output: ❌ Error: curl is required.
        echo "❌ Error: curl is required."
        # Terminate script execution with exit status 1
        exit 1
    # End of if-conditional control block
    fi
# Execute command: }
}

# Execute command: cmd_status() {
cmd_status() {
    # Execute command: check_curl
    check_curl
    # Print message to standard output: 📱 Fetching Julius WhatsApp Agent status from ${API_URL}/status...
    echo "📱 Fetching Julius WhatsApp Agent status from ${API_URL}/status..."
    response=$(curl -s -f "${API_URL}/status" 2>/dev/null || true)
    # Evaluate condition check: -z "$response"
    if [ -z "$response" ]; then
        # Print message to standard output: ⚠️ Julius server does not appear to be running on port ${PORT}.
        echo "⚠️ Julius server does not appear to be running on port ${PORT}."
        # Print message to standard output:    Start the server with: ./scripts/julius-server.sh start
        echo "   Start the server with: ./scripts/julius-server.sh start"
        # Terminate script execution with exit status 1
        exit 1
    # End of if-conditional control block
    fi
    # Print message to standard output: $response" | python3 -m json.tool || echo "$response
    echo "$response" | python3 -m json.tool || echo "$response"
# Execute command: }
}

# Execute command: cmd_connect() {
cmd_connect() {
    # Execute command: check_curl
    check_curl
    # Print message to standard output: 🚀 Connecting WhatsApp browser adapter...
    echo "🚀 Connecting WhatsApp browser adapter..."
    response=$(curl -s -X POST "${API_URL}/connect" 2>/dev/null || true)
    # Print message to standard output: $response" | python3 -m json.tool || echo "$response
    echo "$response" | python3 -m json.tool || echo "$response"
    # Print message to standard output: 💡 If QR code is needed for first-time login, run: ./scripts/julius-whatsapp.sh qr
    echo "💡 If QR code is needed for first-time login, run: ./scripts/julius-whatsapp.sh qr"
# Execute command: }
}

# Execute command: cmd_disconnect() {
cmd_disconnect() {
    # Execute command: check_curl
    check_curl
    # Print message to standard output: 🛑 Disconnecting WhatsApp...
    echo "🛑 Disconnecting WhatsApp..."
    # Execute command: curl -s -X POST "${API_URL}/disconnect" | python3 -m json.tool || true
    curl -s -X POST "${API_URL}/disconnect" | python3 -m json.tool || true
    # Print message to standard output: ✅ WhatsApp adapter disconnected.
    echo "✅ WhatsApp adapter disconnected."
# Execute command: }
}

# Execute command: cmd_pause() {
cmd_pause() {
    # Execute command: check_curl
    check_curl
    # Print message to standard output: ⏸ Pausing WhatsApp auto-responses...
    echo "⏸ Pausing WhatsApp auto-responses..."
    # Execute command: curl -s -X POST "${API_URL}/pause" | python3 -m json.tool || true
    curl -s -X POST "${API_URL}/pause" | python3 -m json.tool || true
# Execute command: }
}

# Execute command: cmd_resume() {
cmd_resume() {
    # Execute command: check_curl
    check_curl
    # Print message to standard output: ▶ Resuming WhatsApp auto-responses...
    echo "▶ Resuming WhatsApp auto-responses..."
    # Execute command: curl -s -X POST "${API_URL}/resume" | python3 -m json.tool || true
    curl -s -X POST "${API_URL}/resume" | python3 -m json.tool || true
# Execute command: }
}

# Execute command: cmd_stop() {
cmd_stop() {
    # Execute command: check_curl
    check_curl
    # Print message to standard output: 🛑 EMERGENCY STOP: Halting all WhatsApp message sends and clearing pending approvals...
    echo "🛑 EMERGENCY STOP: Halting all WhatsApp message sends and clearing pending approvals..."
    # Execute command: curl -s -X POST "${API_URL}/stop" | python3 -m json.tool || true
    curl -s -X POST "${API_URL}/stop" | python3 -m json.tool || true
# Execute command: }
}

# Execute command: cmd_qr() {
cmd_qr() {
    # Execute command: check_curl
    check_curl
    # Print message to standard output: 📷 Fetching WhatsApp login QR code...
    echo "📷 Fetching WhatsApp login QR code..."
    response=$(curl -s "${API_URL}/qr" 2>/dev/null || true)
    has_qr=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print('yes' if data.get('qr') else 'no')" 2>/dev/null || echo "no")
    # Evaluate condition check: "$has_qr" = "yes"
    if [ "$has_qr" = "yes" ]; then
        # Print message to standard output: ✅ QR code is active! Scan it from your phone's WhatsApp -> Linked Devices:
        echo "✅ QR code is active! Scan it from your phone's WhatsApp -> Linked Devices:"
        # Print message to standard output:    You can view the QR code in the Julius Web Portal at:
        echo "   You can view the QR code in the Julius Web Portal at:"
        # Print message to standard output:    http://localhost:${PORT}/api/whatsapp/qr
        echo "   http://localhost:${PORT}/api/whatsapp/qr"
    # Fallback branch when preceding conditions evaluate to false
    else
        # Print message to standard output: ℹ️ No QR code required (already authenticated or page still loading).
        echo "ℹ️ No QR code required (already authenticated or page still loading)."
        # Print message to standard output: $response" | python3 -m json.tool || echo "$response
        echo "$response" | python3 -m json.tool || echo "$response"
    # End of if-conditional control block
    fi
# Execute command: }
}

# Execute command: cmd_logs() {
cmd_logs() {
    # Evaluate condition check: -f "${LOG_FILE}"
    if [ -f "${LOG_FILE}" ]; then
        # Print message to standard output: 📋 Tailing WhatsApp logs from ${LOG_FILE}...
        echo "📋 Tailing WhatsApp logs from ${LOG_FILE}..."
        # Execute command: grep -i "whatsapp" "${LOG_FILE}" | tail -n 50 || tail -n 50 "${LOG_FILE}"
        grep -i "whatsapp" "${LOG_FILE}" | tail -n 50 || tail -n 50 "${LOG_FILE}"
    # Fallback branch when preceding conditions evaluate to false
    else
        # Print message to standard output: ⚠️ Log file not found at ${LOG_FILE}
        echo "⚠️ Log file not found at ${LOG_FILE}"
    # End of if-conditional control block
    fi
# Execute command: }
}

# Execute command: case "${1:-status}" in
case "${1:-status}" in
    # Execute command: status)
    status)
        # Execute command: cmd_status
        cmd_status
        # Execute command: ;;
        ;;
    # Execute command: connect|start)
    connect|start)
        # Execute command: cmd_connect
        cmd_connect
        # Execute command: ;;
        ;;
    # Execute command: disconnect)
    disconnect)
        # Execute command: cmd_disconnect
        cmd_disconnect
        # Execute command: ;;
        ;;
    # Execute command: pause)
    pause)
        # Execute command: cmd_pause
        cmd_pause
        # Execute command: ;;
        ;;
    # Execute command: resume)
    resume)
        # Execute command: cmd_resume
        cmd_resume
        # Execute command: ;;
        ;;
    # Execute command: stop|emergency)
    stop|emergency)
        # Execute command: cmd_stop
        cmd_stop
        # Execute command: ;;
        ;;
    # Execute command: qr)
    qr)
        # Execute command: cmd_qr
        cmd_qr
        # Execute command: ;;
        ;;
    # Execute command: logs)
    logs)
        # Execute command: cmd_logs
        cmd_logs
        # Execute command: ;;
        ;;
    # Execute command: *)
    *)
        # Print message to standard output: Usage: $0 {status|connect|disconnect|pause|resume|stop|qr|logs}
        echo "Usage: $0 {status|connect|disconnect|pause|resume|stop|qr|logs}"
        # Terminate script execution with exit status 1
        exit 1
        # Execute command: ;;
        ;;
# Execute command: esac
esac
