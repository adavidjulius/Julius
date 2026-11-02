#!/bin/bash
# run_research.sh — Automated Oppo A16 Research Launcher
# Starts USB monitoring, logs ADB/serial changes, detects MTK Preloader
# Usage: chmod +x run_research.sh && ./run_research.sh

# Execute command: set -e
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SESSION_LOG="$LOG_DIR/research_$TIMESTAMP.log"

mkdir -p "$LOG_DIR"

# Activate virtual environment if present
activate_venv() {
    # Evaluate condition check: -f "$SCRIPT_DIR/.venv/bin/activate"
    if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
        # Source and evaluate environment script: "$SCRIPT_DIR/.venv/bin/activate"
        source "$SCRIPT_DIR/.venv/bin/activate"
        # Print message to standard output: [VENV] Activated .venv
        echo "[VENV] Activated .venv"
    # Alternative condition check: -f "$SCRIPT_DIR/OPPO A16/mtkenv/bin/activate"
    elif [ -f "$SCRIPT_DIR/OPPO A16/mtkenv/bin/activate" ]; then
        # Source and evaluate environment script: "$SCRIPT_DIR/OPPO A16/mtkenv/bin/activate"
        source "$SCRIPT_DIR/OPPO A16/mtkenv/bin/activate"
        # Print message to standard output: [VENV] Activated mtkenv
        echo "[VENV] Activated mtkenv"
    # End of if-conditional control block
    fi
# Execute command: }
}

# Execute command: log() {
log() {
    # Print message to standard output: [$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$SESSION_LOG
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$SESSION_LOG"
# Execute command: }
}

# Execute command: banner() {
banner() {
    # Execute command: echo
    echo
    # Print message to standard output: ╔══════════════════════════════════════╗
    echo "╔══════════════════════════════════════╗"
    # Print message to standard output: ║   Oppo A16 Research Launcher        ║
    echo "║   Oppo A16 Research Launcher        ║"
    # Print message to standard output: ║   macOS — Apple Silicon             ║
    echo "║   macOS — Apple Silicon             ║"
    # Print message to standard output: ╚══════════════════════════════════════╝
    echo "╚══════════════════════════════════════╝"
    # Execute command: echo
    echo
# Execute command: }
}

# Execute command: banner
banner
# Execute command: log "Research session started"
log "Research session started"
# Execute command: log "Log file: $SESSION_LOG"
log "Log file: $SESSION_LOG"
# Execute command: echo
echo

# Activate venv
activate_venv

# 1. Environment check
echo "=== 1. Environment Check ===" | tee -a "$SESSION_LOG"
# Execute command: log "Host: $(uname -m) / $(sw_vers -productName) $(sw_vers -productVersion)"
log "Host: $(uname -m) / $(sw_vers -productName) $(sw_vers -productVersion)"
# Execute command: log "ADB: $(which adb 2>/dev/null || echo 'NOT FOUND')"
log "ADB: $(which adb 2>/dev/null || echo 'NOT FOUND')"
# Execute command: log "Fastboot: $(which fastboot 2>/dev/null || echo 'NOT FOUND')"
log "Fastboot: $(which fastboot 2>/dev/null || echo 'NOT FOUND')"
# Execute command: log "Python: $(python3 --version 2>/dev/null || echo 'NOT FOUND')"
log "Python: $(python3 --version 2>/dev/null || echo 'NOT FOUND')"
# Execute command: echo
echo

# 2. Initial device state snapshot
echo "=== 2. Device Snapshot ===" | tee -a "$SESSION_LOG"

ADB_DEVICES=$(adb devices 2>/dev/null | grep -v "List of devices" | grep -v "^$" || true)
# Evaluate condition check: -n "$ADB_DEVICES"
if [ -n "$ADB_DEVICES" ]; then
    # Execute command: log "ADB devices connected:"
    log "ADB devices connected:"
    # Print message to standard output: $ADB_DEVICES" | while read line; do log "  $line; done
    echo "$ADB_DEVICES" | while read line; do log "  $line"; done
    
    # Get device info for each connected device
    echo "$ADB_DEVICES" | while read serial state; do
        # Evaluate condition check: "$state" = "device"
        if [ "$state" = "device" ]; then
            # Execute command: log "Querying $serial..."
            log "Querying $serial..."
            MODEL=$(adb -s "$serial" shell getprop ro.product.model 2>/dev/null || echo "unknown")
            ANDROID=$(adb -s "$serial" shell getprop ro.build.version.release 2>/dev/null || echo "?")
            PLATFORM=$(adb -s "$serial" shell getprop ro.board.platform 2>/dev/null || echo "?")
            # Execute command: log "  Model: $MODEL | Android: $ANDROID | SoC: $PLATFORM"
            log "  Model: $MODEL | Android: $ANDROID | SoC: $PLATFORM"
            
            # Save full device info snapshot
            SNAPSHOT="$LOG_DIR/device_${serial}_${TIMESTAMP}.txt"
            # Execute command: {
            {
                # Print message to standard output: Device: $serial
                echo "Device: $serial"
                # Print message to standard output: Time: $(date)
                echo "Time: $(date)"
                # Print message to standard output: --- getprop ---
                echo "--- getprop ---"
                # Execute command: adb -s "$serial" shell getprop 2>/dev/null
                adb -s "$serial" shell getprop 2>/dev/null
            # Execute command: } > "$SNAPSHOT"
            } > "$SNAPSHOT"
            # Execute command: log "  Snapshot saved: $SNAPSHOT"
            log "  Snapshot saved: $SNAPSHOT"
        # End of if-conditional control block
        fi
    # End of loop iteration block
    done
# Fallback branch when preceding conditions evaluate to false
else
    # Execute command: log "No ADB devices connected"
    log "No ADB devices connected"
# End of if-conditional control block
fi
# Execute command: echo
echo

# 3. USB tree
echo "=== 3. USB Device Tree ===" | tee -a "$SESSION_LOG"
# Execute command: system_profiler SPUSBDataType 2>/dev/null | grep -B2 -A8 -i 'oppo\|mediatek\|android\|mt6765' | tee -a "$SESSION_LOG" || log "No Oppo/MediaTek USB devices found"
system_profiler SPUSBDataType 2>/dev/null | grep -B2 -A8 -i 'oppo\|mediatek\|android\|mt6765' | tee -a "$SESSION_LOG" || log "No Oppo/MediaTek USB devices found"
# Execute command: echo
echo

# 4. Serial ports
echo "=== 4. Serial Ports ===" | tee -a "$SESSION_LOG"
CU_DEVICES=$(ls /dev/cu.* 2>/dev/null || true)
# Evaluate condition check: -n "$CU_DEVICES"
if [ -n "$CU_DEVICES" ]; then
    # Execute command: log "Available serial ports:"
    log "Available serial ports:"
    # Iterate loop variable dev over items in /dev/cu.*
    for dev in /dev/cu.*; do
        # Execute command: log "  $dev"
        log "  $dev"
    # End of loop iteration block
    done
    
    # Detect MTK Preloader
    if ls /dev/cu.usbmodem* &>/dev/null 2>&1; then
        # Execute command: log "⚠️  MEDIATEK PRELOADER DETECTED: $(ls /dev/cu.usbmodem*)"
        log "⚠️  MEDIATEK PRELOADER DETECTED: $(ls /dev/cu.usbmodem*)"
        # Execute command: log "  → Run: screen $(ls /dev/cu.usbmodem* | head -1) 115200"
        log "  → Run: screen $(ls /dev/cu.usbmodem* | head -1) 115200"
        # Execute command: log "  → Or use MTKClient: cd 'OPPO A16/mtkclient' && python mtk.py"
        log "  → Or use MTKClient: cd 'OPPO A16/mtkclient' && python mtk.py"
    # End of if-conditional control block
    fi
# Fallback branch when preceding conditions evaluate to false
else
    # Execute command: log "No serial ports found"
    log "No serial ports found"
# End of if-conditional control block
fi
# Execute command: echo
echo

# 5. IOReg MediaTek scan
echo "=== 5. IOReg MediaTek Scan ===" | tee -a "$SESSION_LOG"
MTK_IOREG=$(ioreg -p IOUSB -w0 -l 2>/dev/null | grep -iE 'mediatek|0e8d|0bb4' || true)
# Evaluate condition check: -n "$MTK_IOREG"
if [ -n "$MTK_IOREG" ]; then
    # Execute command: log "MediaTek USB devices found in IOReg:"
    log "MediaTek USB devices found in IOReg:"
    # Print message to standard output: $MTK_IOREG" | tee -a "$SESSION_LOG
    echo "$MTK_IOREG" | tee -a "$SESSION_LOG"
# Fallback branch when preceding conditions evaluate to false
else
    # Execute command: log "No MediaTek devices in IOReg (device in ADB mode — expected)"
    log "No MediaTek devices in IOReg (device in ADB mode — expected)"
# End of if-conditional control block
fi
# Execute command: echo
echo

# 6. Start monitoring (optional)
echo "=== 6. Monitor ===" | tee -a "$SESSION_LOG"
# Evaluate condition check: "${1:-}" = "--monitor"
if [ "${1:-}" = "--monitor" ]; then
    INTERVAL="${2:-5}"
    # Execute command: log "Starting continuous monitoring (interval: ${INTERVAL}s)..."
    log "Starting continuous monitoring (interval: ${INTERVAL}s)..."
    # Execute command: log "Press Ctrl+C to stop."
    log "Press Ctrl+C to stop."
    # Execute command: echo
    echo
    
    # Run the USB monitor in foreground
    bash "$SCRIPT_DIR/macos_equivalent/monitor_usb.sh" "$INTERVAL"
# Fallback branch when preceding conditions evaluate to false
else
    # Execute command: log "Monitor not started (use --monitor flag to start continuous monitoring)"
    log "Monitor not started (use --monitor flag to start continuous monitoring)"
    # Execute command: log "Or run directly: ./macos_equivalent/monitor_usb.sh"
    log "Or run directly: ./macos_equivalent/monitor_usb.sh"
# End of if-conditional control block
fi
# Execute command: echo
echo

# Summary
log "Research launcher completed."
# Execute command: log "Log file: $SESSION_LOG"
log "Log file: $SESSION_LOG"
# Execute command: log "Output files in: $LOG_DIR/"
log "Output files in: $LOG_DIR/"
# Execute command: echo
echo
# Print message to standard output: Quick commands:
echo "Quick commands:"
# Print message to standard output:   ./macos_equivalent/check_environment.sh    — Full environment check
echo "  ./macos_equivalent/check_environment.sh    — Full environment check"
# Print message to standard output:   ./macos_equivalent/adb_helpers.sh info     — Device info
echo "  ./macos_equivalent/adb_helpers.sh info     — Device info"
# Print message to standard output:   ./macos_equivalent/mtk_helpers.sh detect   — MTK device detection
echo "  ./macos_equivalent/mtk_helpers.sh detect   — MTK device detection"
# Print message to standard output:   ./macos_equivalent/monitor_usb.sh          — USB monitor
echo "  ./macos_equivalent/monitor_usb.sh          — USB monitor"
# Print message to standard output:   ./run_research.sh --monitor                — Full research + monitor
echo "  ./run_research.sh --monitor                — Full research + monitor"
