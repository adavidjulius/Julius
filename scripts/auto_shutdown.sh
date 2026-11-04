#!/bin/bash
# ==============================================================================
# Julius Auto-Shutdown & Sleep Helper for macOS
# Allows Julius or the user to initiate a graceful shutdown or sleep after tasks.
# ==============================================================================

set -euo pipefail

MODE="${1:-shutdown}" # Options: shutdown | sleep
DELAY="${2:-30}"     # Grace period in seconds before triggering (default: 30s)

echo "========================================================"
echo "  Julius System Power Manager (${MODE})"
echo "========================================================"
echo "Action: System ${MODE} will execute in ${DELAY} seconds."
echo "Press Ctrl+C at any time during this countdown to cancel."
echo "--------------------------------------------------------"

# Countdown with audible warning on the last 5 seconds
for (( i=DELAY; i>0; i-- )); do
  if [ "$i" -le 5 ]; then
    printf "\r[WARNING] System %s in %2d seconds... (Ctrl+C to abort) \a" "$MODE" "$i"
  else
    printf "\rSystem %s in %2d seconds... (Ctrl+C to abort)" "$MODE" "$i"
  fi
  sleep 1
done

echo -e "\nExecuting ${MODE} now..."

if [ "$MODE" = "sleep" ]; then
  # Safe, instant sleep (preserves open work, no sudo needed)
  pmset sleepnow
elif [ "$MODE" = "shutdown" ]; then
  # Graceful macOS shutdown via AppleScript System Events (does not require sudo)
  osascript -e 'tell application "System Events" to shut down' 2>/dev/null || {
    echo "AppleScript shutdown failed. Attempting fallback power down..."
    # If AppleScript is restricted in your Terminal permissions, standard shutdown command:
    sudo shutdown -h now
  }
else
  echo "Unknown mode: ${MODE}. Expected 'shutdown' or 'sleep'."
  exit 1
fi

