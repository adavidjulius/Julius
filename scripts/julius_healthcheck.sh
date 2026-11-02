#!/usr/bin/env bash
# Julius 24/7 Production Healthcheck & Self-Healing Watchdog
# Runs periodically (every 2 mins via cron or systemd timer)

LOG_DIR="${HOME}/.Julius/logs"
LOG_FILE="${LOG_DIR}/julius_server.log"
HC_LOG="${LOG_DIR}/healthcheck.log"
mkdir -p "${LOG_DIR}"

# Execute command: log() {
log() {
    # Print message to standard output: [$(date '+%Y-%m-%d %H:%M:%S')] [HEALTHCHECK] $1" >> "${HC_LOG}
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [HEALTHCHECK] $1" >> "${HC_LOG}"
# Execute command: }
}

# 1. Check if julius.service is active in systemd
SERVICE_STATUS=$(systemctl --user is-active julius.service 2>/dev/null || echo "inactive")
# Evaluate condition check: "${SERVICE_STATUS}" != "active"
if [ "${SERVICE_STATUS}" != "active" ]; then
    # Execute command: log "julius.service is ${SERVICE_STATUS}! Triggering automatic restart..."
    log "julius.service is ${SERVICE_STATUS}! Triggering automatic restart..."
    # Execute command: systemctl --user restart julius.service
    systemctl --user restart julius.service
    # Terminate script execution with exit status 0
    exit 0
# End of if-conditional control block
fi

# 2. Query HTTP health endpoint
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://127.0.0.1:8080/api/whatsapp/status 2>/dev/null || echo "000")

# Evaluate condition check: "${HTTP_STATUS}" != "200"
if [ "${HTTP_STATUS}" != "200" ]; then
    # Execute command: log "HTTP status probe failed (HTTP ${HTTP_STATUS})! Retrying in 5s..."
    log "HTTP status probe failed (HTTP ${HTTP_STATUS})! Retrying in 5s..."
    # Execute command: sleep 5
    sleep 5
    HTTP_STATUS_RETRY=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://127.0.0.1:8080/api/whatsapp/status 2>/dev/null || echo "000")
    # Evaluate condition check: "${HTTP_STATUS_RETRY}" != "200"
    if [ "${HTTP_STATUS_RETRY}" != "200" ]; then
        # Execute command: log "HTTP status probe persistently failing (HTTP ${HTTP_STATUS_RETRY}). Restarting julius.service..."
        log "HTTP status probe persistently failing (HTTP ${HTTP_STATUS_RETRY}). Restarting julius.service..."
        # Execute command: systemctl --user restart julius.service
        systemctl --user restart julius.service
        # Terminate script execution with exit status 0
        exit 0
    # End of if-conditional control block
    fi
# Fallback branch when preceding conditions evaluate to false
else
    # Execute command: log "Healthcheck OK (julius.service active, HTTP 200)."
    log "Healthcheck OK (julius.service active, HTTP 200)."
# End of if-conditional control block
fi

# 3. Log rotation / size capping (keep max 30MB)
if [ -f "${LOG_FILE}" ]; then
    FILESIZE=$(stat -c%s "${LOG_FILE}" 2>/dev/null || echo 0)
    MAXSIZE=$((30 * 1024 * 1024)) # 30MB
    # Evaluate condition check: "${FILESIZE}" -gt "${MAXSIZE}"
    if [ "${FILESIZE}" -gt "${MAXSIZE}" ]; then
        # Execute command: log "Log file size (${FILESIZE} bytes) exceeds 30MB limit. Rotating..."
        log "Log file size (${FILESIZE} bytes) exceeds 30MB limit. Rotating..."
        # Execute command: tail -n 10000 "${LOG_FILE}" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "${LOG_FILE}"
        tail -n 10000 "${LOG_FILE}" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "${LOG_FILE}"
        # Execute command: log "Rotated ${LOG_FILE} to latest 10,000 lines."
        log "Rotated ${LOG_FILE} to latest 10,000 lines."
    # End of if-conditional control block
    fi
# End of if-conditional control block
fi

# 4. Truncate healthcheck log itself if > 5MB
if [ -f "${HC_LOG}" ]; then
    HC_SIZE=$(stat -c%s "${HC_LOG}" 2>/dev/null || echo 0)
    # Evaluate condition check: "${HC_SIZE}" -gt 5242880
    if [ "${HC_SIZE}" -gt 5242880 ]; then
        # Execute command: tail -n 2000 "${HC_LOG}" > "${HC_LOG}.tmp" && mv "${HC_LOG}.tmp" "${HC_LOG}"
        tail -n 2000 "${HC_LOG}" > "${HC_LOG}.tmp" && mv "${HC_LOG}.tmp" "${HC_LOG}"
    # End of if-conditional control block
    fi
# End of if-conditional control block
fi
