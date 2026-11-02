#!/usr/bin/env bash
# ==============================================================================
# Julius TUI Launcher
# Launches the interactive Julius Terminal Interface on your Mac
# ==============================================================================

# Resolve script directory even if invoked via symlink
TARGET_FILE="${BASH_SOURCE[0]}"
# Repeat loop while condition evaluates to true: [ -L "${TARGET_FILE}" ]
while [ -L "${TARGET_FILE}" ]; do
    TARGET_DIR="$(cd -P "$(dirname "${TARGET_FILE}")" >/dev/null 2>&1 && pwd)"
    TARGET_FILE="$(readlink "${TARGET_FILE}")"
    # Execute command: [[ ${TARGET_FILE} != /* ]] && TARGET_FILE="${TARGET_DIR}/${TARGET_FILE}"
    [[ ${TARGET_FILE} != /* ]] && TARGET_FILE="${TARGET_DIR}/${TARGET_FILE}"
# End of loop iteration block
done
SCRIPT_DIR="$(cd -P "$(dirname "${TARGET_FILE}")" >/dev/null 2>&1 && pwd)"

cd "${SCRIPT_DIR}"

# Evaluate condition check: ! -d ".venv"
if [ ! -d ".venv" ]; then
    # Print message to standard output: ❌ Error: .venv not found in ${SCRIPT_DIR}.
    echo "❌ Error: .venv not found in ${SCRIPT_DIR}."
    # Terminate script execution with exit status 1
    exit 1
# End of if-conditional control block
fi

# Ensure Julius typography (text) and JetBrains Mono (coding) are active on macOS host
if [ "$(uname -s)" = "Darwin" ]; then
    MAC_FONTS="${HOME}/Library/Fonts"
    mkdir -p "${MAC_FONTS}" 2>/dev/null || true
    # Evaluate condition check: ! -f "${MAC_FONTS}/Julius-Regular.ttf" ] && [ -d "${SCRIPT_DIR}/Julius_Fonts"
    if [ ! -f "${MAC_FONTS}/Julius-Regular.ttf" ] && [ -d "${SCRIPT_DIR}/Julius_Fonts" ]; then
        cp -f "${SCRIPT_DIR}/Julius_Fonts"/Julius-*.ttf "${MAC_FONTS}/" 2>/dev/null || true
    # End of if-conditional control block
    fi
    # Evaluate condition check: ! -f "${MAC_FONTS}/JetBrainsMono-Regular.ttf" ] && [ -d "${SCRIPT_DIR}/Julius_Fonts/code"
    if [ ! -f "${MAC_FONTS}/JetBrainsMono-Regular.ttf" ] && [ -d "${SCRIPT_DIR}/Julius_Fonts/code" ]; then
        cp -f "${SCRIPT_DIR}/Julius_Fonts/code"/JetBrainsMono-*.ttf "${MAC_FONTS}/" 2>/dev/null || true
    # End of if-conditional control block
    fi
# End of if-conditional control block
fi

# Reset cursor to normal pointer and normal block cursor
printf '\e]22;default\a\e[2 q' 2>/dev/null || true
# Register signal trap event handler: "printf '\e]22;default\a\e[0 q' 2>/dev/null || true" EXIT
trap "printf '\e]22;default\a\e[0 q' 2>/dev/null || true" EXIT

# Source and evaluate environment script: .venv/bin/activate
source .venv/bin/activate
# Replace current shell process with: ./julius "$@"
exec ./julius "$@"
