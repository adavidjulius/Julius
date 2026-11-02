#!/usr/bin/env bash
# ==============================================================================
# Julius iOS — Automated Prerequisites Verification Script
# ==============================================================================
# Checks host environment, developer tools, CLI utilities, and backend status.
# Usage: ./check_prerequisites.sh
# ==============================================================================

set -u

# Colors
C_RESET="\033[0m"
C_BOLD="\033[1m"
C_RED="\033[38;5;196m"
C_GREEN="\033[38;5;46m"
C_YELLOW="\033[38;5;220m"
C_BLUE="\033[38;5;39m"
C_GOLD="\033[38;5;179m"
C_DIM="\033[2m"

PASS="${C_GREEN}✔ PASS${C_RESET}"
WARN="${C_YELLOW}⚠ WARN${C_RESET}"
FAIL="${C_RED}✖ FAIL${C_RESET}"

total_checks=0
passed_checks=0
warn_checks=0
failed_checks=0

print_header() {
    echo -e "${C_BOLD}${C_GOLD}"
    echo "  ╔══════════════════════════════════════════════════════════════╗"
    echo "  ║             JULIUS iOS — PREREQUISITES VERIFIER              ║"
    echo "  ╚══════════════════════════════════════════════════════════════╝"
    echo -e "${C_RESET}"
}

check_item() {
    local label="$1"
    local status="$2"
    local detail="$3"
    total_checks=$((total_checks + 1))
    
    printf "  %-32s %-16b %b\n" "$label" "$status" "${C_DIM}${detail}${C_RESET}"
    if [[ "$status" == *PASS* ]]; then
        passed_checks=$((passed_checks + 1))
    elif [[ "$status" == *WARN* ]]; then
        warn_checks=$((warn_checks + 1))
    else
        failed_checks=$((failed_checks + 1))
    fi
}

print_header

echo -e "${C_BOLD}1. Host System & Hardware Architecture${C_RESET}"
# Architecture
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    check_item "Apple Silicon (arm64)" "$PASS" "Native Apple Silicon M-series detected"
else
    check_item "Processor Architecture" "$WARN" "Architecture: $ARCH (Apple Silicon recommended)"
fi

# macOS Version
OS_VER=$(sw_vers -productVersion 2>/dev/null || echo "Unknown")
OS_MAJOR=$(echo "$OS_VER" | cut -d. -f1)
if [ "$OS_MAJOR" -ge 14 ]; then
    check_item "macOS Version ($OS_VER)" "$PASS" "Sonoma / Sequoia compatible"
else
    check_item "macOS Version ($OS_VER)" "$FAIL" "Requires macOS 14.0 or newer"
fi

echo ""
echo -e "${C_BOLD}2. Apple Developer Toolchain${C_RESET}"

# Developer Directory
DEV_DIR=$(xcode-select -p 2>/dev/null || echo "")
if [ -n "$DEV_DIR" ]; then
    check_item "Developer Directory" "$PASS" "$DEV_DIR"
else
    check_item "Developer Directory" "$FAIL" "Run: xcode-select --install"
fi

# Full Xcode.app vs Command Line Tools
if [ -d "/Applications/Xcode.app" ]; then
    XCODE_VER=$(/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild -version 2>/dev/null | head -n 1 || echo "Xcode detected")
    check_item "Xcode.app Installed" "$PASS" "$XCODE_VER"
else
    check_item "Full Xcode.app" "$WARN" "Install Xcode from App Store for simulator & native device builds"
fi

# Swift Compiler
if command -v swift >/dev/null 2>&1; then
    SWIFT_V=$(swift --version 2>&1 | grep -o 'Apple Swift version [^ ]*' || echo "Swift Installed")
    check_item "Swift Compiler" "$PASS" "$SWIFT_V"
else
    check_item "Swift Compiler" "$FAIL" "Swift compiler not found"
fi

echo ""
echo -e "${C_BOLD}3. Build Tools & Package Managers${C_RESET}"

# Homebrew
if command -v brew >/dev/null 2>&1; then
    BREW_V=$(brew --version | head -n 1 | awk '{print $2}')
    check_item "Homebrew" "$PASS" "brew $BREW_V"
else
    check_item "Homebrew" "$FAIL" "Install from https://brew.sh"
fi

# Node.js & npx
if command -v node >/dev/null 2>&1; then
    NODE_V=$(node -v)
    check_item "Node.js & npx" "$PASS" "Node $NODE_V (used for skillfish tooling)"
else
    check_item "Node.js & npx" "$FAIL" "Run: brew install node"
fi

# Tuist
if command -v tuist >/dev/null 2>&1; then
    TUIST_V=$(tuist version 2>/dev/null || echo "Installed")
    check_item "Tuist CLI" "$PASS" "Tuist $TUIST_V"
else
    check_item "Tuist CLI" "$WARN" "Run: brew install --cask tuist"
fi

# Fastlane
if command -v fastlane >/dev/null 2>&1; then
    check_item "Fastlane" "$PASS" "Installed"
else
    check_item "Fastlane" "$WARN" "Run: brew install fastlane"
fi

# SwiftFormat
if command -v swiftformat >/dev/null 2>&1; then
    check_item "SwiftFormat" "$PASS" "Installed"
else
    check_item "SwiftFormat" "$WARN" "Run: brew install swiftformat"
fi

echo ""
echo -e "${C_BOLD}4. Julius Backend Connectivity${C_RESET}"

# Local Daemon (Port 9111)
BACKEND_STATUS=$(curl -s --connect-timeout 2 http://localhost:9111/api/health 2>/dev/null || echo "")
if [[ "$BACKEND_STATUS" == *"Julius"* || "$BACKEND_STATUS" == *"ok"* ]]; then
    check_item "Julius Daemon (:9111)" "$PASS" "Connected (http://localhost:9111/api/health)"
else
    check_item "Julius Daemon (:9111)" "$WARN" "Offline. Start via: python3 ipad_tui_server.py"
fi

echo ""
echo -e "${C_BOLD}────────────────────────────────────────────────────────────────${C_RESET}"
echo -e "Summary: ${C_GREEN}${passed_checks} passed${C_RESET}, ${C_YELLOW}${warn_checks} warnings${C_RESET}, ${C_RED}${failed_checks} failed${C_RESET} (Total: ${total_checks} checks)"

if [ "$failed_checks" -eq 0 ] && [ "$warn_checks" -eq 0 ]; then
    echo -e "\n${C_BOLD}${C_GREEN}🚀 All prerequisites are fulfilled! Ready to build Julius iOS.${C_RESET}\n"
elif [ "$failed_checks" -eq 0 ]; then
    echo -e "\n${C_BOLD}${C_YELLOW}⚡ Environment is ready for development.${C_RESET}"
    echo -e "To install recommended optional tools, run:\n"
    echo -e "  ${C_BOLD}brew bundle --file=\"\$(dirname \"\$0\")/Brewfile\"${C_RESET}\n"
else
    echo -e "\n${C_BOLD}${C_RED}❌ Please resolve the failed items above before proceeding.${C_RESET}\n"
fi
