#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Julius Agent — Installer
#
# Sets up the local Python environment, installs all dependencies, provisions
# Playwright browsers, and verifies the installation.
#
# Supports: macOS, Linux, and WSL.
#
# Usage:
#   ./install.sh                # full install (default)
#   ./install.sh --no-verify    # skip post-install verification
#   ./install.sh --no-browser   # skip Playwright browser install
#   ./install.sh --help         # print usage
#
# Environment overrides:
#   JULIUS_SKIP_VERIFY=1      same as --no-verify
#   JULIUS_SKIP_BROWSER=1     same as --no-browser
#   JULIUS_PYTHON=python3.12  override which python binary to use
# ──────────────────────────────────────────────────────────────────────────────

# Execute command: set -euo pipefail
set -euo pipefail

# Ensure standard system and package manager paths are included in PATH
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:${HOME}/.local/bin:${PATH}"

# ─── Pretty printing ─────────────────────────────────────────────────────────

# Evaluate condition check: -t 1 ] && command -v tput >/dev/null 2>&1 && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8
if [ -t 1 ] && command -v tput >/dev/null 2>&1 && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]; then
    COLOR_RESET="$(tput sgr0)"
    COLOR_BOLD="$(tput bold)"
    COLOR_DIM="$(tput dim)"
    COLOR_RED="$(tput setaf 1)"
    COLOR_GREEN="$(tput setaf 2)"
    COLOR_YELLOW="$(tput setaf 3)"
    COLOR_BLUE="$(tput setaf 4)"
    COLOR_CYAN="$(tput setaf 6)"
    COLOR_MAGENTA="$(tput setaf 5)"
    COLOR_JULIUS=$'\033[38;2;200;184;150m' # Brand Color #C8B896
# Fallback branch when preceding conditions evaluate to false
else
    COLOR_RESET=""
    COLOR_BOLD=""
    COLOR_DIM=""
    COLOR_RED=""
    COLOR_GREEN=""
    COLOR_YELLOW=""
    COLOR_BLUE=""
    COLOR_CYAN=""
    COLOR_MAGENTA=""
    COLOR_JULIUS=""
# End of if-conditional control block
fi

CURRENT_STEP=0
TOTAL_STEPS=7

# Execute command: step() {
step() {
    CURRENT_STEP=$((CURRENT_STEP + 1))
    # Output formatted terminal string: '\n%s[%d/%d]%s %s%s%s\n' \
    printf '\n%s[%d/%d]%s %s%s%s\n' \
        "${COLOR_BOLD}${COLOR_JULIUS}" "${CURRENT_STEP}" "${TOTAL_STEPS}" "${COLOR_RESET}" \
        "${COLOR_BOLD}" "$1" "${COLOR_RESET}"
# Execute command: }
}

# Execute command: info()  { printf '%s  ->%s %s\n' "${COLOR_JULIUS}" "${COLOR_RESET}" "$1"; }
info()  { printf '%s  ->%s %s\n' "${COLOR_JULIUS}" "${COLOR_RESET}" "$1"; }
# Execute command: ok()    { printf '%s  ✓%s  %s\n' "${COLOR_GREEN}" "${COLOR_RESET}" "$1"; }
ok()    { printf '%s  ✓%s  %s\n' "${COLOR_GREEN}" "${COLOR_RESET}" "$1"; }
# Execute command: warn()  { printf '%s  ⚠%s  %s\n' "${COLOR_YELLOW}" "${COLOR_RESET}" "$1"; }
warn()  { printf '%s  ⚠%s  %s\n' "${COLOR_YELLOW}" "${COLOR_RESET}" "$1"; }
# Execute command: error() { printf '%s  ✗%s  %s\n' "${COLOR_RED}" "${COLOR_RESET}" "$1" 1>&2; }
error() { printf '%s  ✗%s  %s\n' "${COLOR_RED}" "${COLOR_RESET}" "$1" 1>&2; }

# Execute command: print_banner() {
print_banner() {
    # Output formatted terminal string: '%s\n' "${COLOR_BOLD}${COLOR_JULIUS}"
    printf '%s\n' "${COLOR_BOLD}${COLOR_JULIUS}"
    # Execute command: cat <<'EOF'
    cat <<'EOF'
  ╔═════╗ ╔╗   ╔╗ ╔╗      ╔═════╗ ╔╗   ╔╗ ╔═════╗
  ╚══╗  ║ ║║   ║║ ║║      ╚═╗ ╔═╝ ║║   ║║ ║ ╔═══╝
     ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ║ ╚═══╗
     ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ╚═══╗ ║
  ╔══╝  ║ ║╚═══╝║ ║╚════╗ ╔═╝ ╚═╗ ║╚═══╝║ ╔═══╝ ║
  ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝
EOF
    # Output formatted terminal string: '%s' "${COLOR_RESET}"
    printf '%s' "${COLOR_RESET}"
    # Output formatted terminal string: '%s  Autonomous Web Agent — Installer%s\n' "${COLOR_JULIUS}" "${COLOR_RESET}"
    printf '%s  Autonomous Web Agent — Installer%s\n' "${COLOR_JULIUS}" "${COLOR_RESET}"
# Execute command: }
}

# Execute command: print_usage() {
print_usage() {
    # Execute command: cat <<EOF
    cat <<EOF
${COLOR_BOLD}${COLOR_JULIUS}Usage:${COLOR_RESET} ./install.sh [options]

${COLOR_BOLD}${COLOR_JULIUS}Options:${COLOR_RESET}
  --no-verify     Skip the post-install verification step.
  --no-browser    Skip Playwright browser installation.
  -h, --help      Show this help text and exit.

${COLOR_BOLD}${COLOR_JULIUS}Environment overrides:${COLOR_RESET}
  JULIUS_SKIP_VERIFY    set to 1 to skip verification
  JULIUS_SKIP_BROWSER   set to 1 to skip Playwright browser install
  JULIUS_PYTHON         python binary to use (default: python3)
EOF
# Execute command: }
}

# ─── Argument parsing ─────────────────────────────────────────────────────────

SKIP_VERIFY="${JULIUS_SKIP_VERIFY:-0}"
SKIP_BROWSER="${JULIUS_SKIP_BROWSER:-0}"
PYTHON_BIN="${JULIUS_PYTHON:-python3}"

# Repeat loop while condition evaluates to true: [ "$#" -gt 0 ]
while [ "$#" -gt 0 ]; do
    # Execute command: case "$1" in
    case "$1" in
        # Execute command: --no-verify)
        --no-verify)
            SKIP_VERIFY="1"
            # Execute command: ;;
            ;;
        # Execute command: --no-browser)
        --no-browser)
            SKIP_BROWSER="1"
            # Execute command: ;;
            ;;
        # Execute command: -h|--help)
        -h|--help)
            # Execute command: print_usage
            print_usage
            # Terminate script execution with exit status 0
            exit 0
            # Execute command: ;;
            ;;
        # Execute command: *)
        *)
            # Execute command: error "unknown argument: $1"
            error "unknown argument: $1"
            # Execute command: print_usage
            print_usage
            # Terminate script execution with exit status 2
            exit 2
            # Execute command: ;;
            ;;
    # Execute command: esac
    esac
    # Execute command: shift
    shift
# End of loop iteration block
done

# ─── Troubleshooting hints ────────────────────────────────────────────────────

# Execute command: print_troubleshooting() {
print_troubleshooting() {
    # Execute command: cat <<EOF
    cat <<EOF

${COLOR_BOLD}${COLOR_JULIUS}Troubleshooting${COLOR_RESET}
${COLOR_JULIUS}───────────────────────────────────────────────────────────────${COLOR_RESET}

  ${COLOR_BOLD}${COLOR_JULIUS}1. Python 3.10+ not found${COLOR_RESET}
     Julius requires Python 3.10 or higher.
     macOS (Homebrew):
       brew install python@3.12
     Ubuntu/Debian:
       sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
     Fedora/RHEL:
       sudo dnf install -y python3 python3-pip

  ${COLOR_BOLD}${COLOR_JULIUS}2. venv module missing${COLOR_RESET}
     On some Linux distros, venv is a separate package:
       sudo apt-get install -y python3-venv       # Debian/Ubuntu
       sudo dnf install -y python3-virtualenv     # Fedora

  ${COLOR_BOLD}${COLOR_JULIUS}3. Playwright browsers fail to install${COLOR_RESET}
     Try installing system dependencies first:
       playwright install-deps
     Then retry:
       playwright install chromium

  ${COLOR_BOLD}${COLOR_JULIUS}4. macOS: Xcode CLT missing${COLOR_RESET}
     Some Python packages need a C compiler:
       xcode-select --install

  ${COLOR_BOLD}${COLOR_JULIUS}5. pip install fails with "externally-managed-environment"${COLOR_RESET}
     This installer uses a virtual environment (.venv) to avoid that issue.
     If you see this error, make sure you are running install.sh directly
     and not pip-installing into the system Python.

  ${COLOR_BOLD}${COLOR_JULIUS}6. 'julius' command not found after install${COLOR_RESET}
     The CLI wrapper lives at:
       ${SCRIPT_DIR}/julius
     Run it directly or add the project directory to your PATH.

EOF
# Execute command: }
}

# Register signal trap event handler: 'rc=$?; if [ "$rc" -ne 0 ]; then error "Installation failed (exit ${rc})"; print_troubleshooting; fi' EXIT
trap 'rc=$?; if [ "$rc" -ne 0 ]; then error "Installation failed (exit ${rc})"; print_troubleshooting; fi' EXIT

# ─── Helpers ──────────────────────────────────────────────────────────────────

# Execute command: require_cmd() {
require_cmd() {
    # Execute command: command -v "$1" >/dev/null 2>&1
    command -v "$1" >/dev/null 2>&1
# Execute command: }
}

# ─── Step 1: Detect OS / arch / WSL ──────────────────────────────────────────

# Execute command: print_banner
print_banner
# Execute command: step "Detecting host environment"
step "Detecting host environment"

UNAME_S="$(uname -s 2>/dev/null || echo unknown)"
UNAME_M="$(uname -m 2>/dev/null || echo unknown)"
OS_FAMILY="unknown"
IS_WSL="0"

# Execute command: case "${UNAME_S}" in
case "${UNAME_S}" in
    # Execute command: Linux*)
    Linux*)
        OS_FAMILY="linux"
        # Execute command: if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
        if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
            IS_WSL="1"
        # End of if-conditional control block
        fi
        # Execute command: ;;
        ;;
    # Execute command: Darwin*)
    Darwin*)
        OS_FAMILY="macos"
        # Execute command: ;;
        ;;
    # Execute command: MINGW*|MSYS*|CYGWIN*)
    MINGW*|MSYS*|CYGWIN*)
        OS_FAMILY="windows-shell"
        # Execute command: ;;
        ;;
# Execute command: esac
esac

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Execute command: info "uname:        ${UNAME_S} ${UNAME_M}"
info "uname:        ${UNAME_S} ${UNAME_M}"
# Execute command: info "os family:    ${OS_FAMILY}"
info "os family:    ${OS_FAMILY}"
# Execute command: info "project dir:  ${SCRIPT_DIR}"
info "project dir:  ${SCRIPT_DIR}"
# Evaluate condition check: "${IS_WSL}" = "1"
if [ "${IS_WSL}" = "1" ]; then
    # Execute command: info "wsl:          yes"
    info "wsl:          yes"
# End of if-conditional control block
fi

# Execute command: case "${OS_FAMILY}" in
case "${OS_FAMILY}" in
    # Execute command: linux|macos)
    linux|macos)
        # Execute command: ok "Supported platform detected"
        ok "Supported platform detected"
        # Execute command: ;;
        ;;
    # Execute command: windows-shell)
    windows-shell)
        # Execute command: warn "Detected native Windows shell (${UNAME_S})."
        warn "Detected native Windows shell (${UNAME_S})."
        PWSH_BIN=""
        # Execute command: if require_cmd pwsh; then
        if require_cmd pwsh; then
            PWSH_BIN="pwsh"
        # Execute command: elif require_cmd powershell.exe; then
        elif require_cmd powershell.exe; then
            PWSH_BIN="powershell.exe"
        # End of if-conditional control block
        fi

        # Evaluate condition check: -n "${PWSH_BIN}" ] && [ -f "${SCRIPT_DIR}/install.ps1"
        if [ -n "${PWSH_BIN}" ] && [ -f "${SCRIPT_DIR}/install.ps1" ]; then
            # Execute command: info "Handing off installation to native PowerShell installer (${PWSH_BIN} install.ps1)..."
            info "Handing off installation to native PowerShell installer (${PWSH_BIN} install.ps1)..."
            # Replace current shell process with: "${PWSH_BIN}" -ExecutionPolicy Bypass -File "${SCRIPT_DIR}/install.ps1" "$@"
            exec "${PWSH_BIN}" -ExecutionPolicy Bypass -File "${SCRIPT_DIR}/install.ps1" "$@"
        # Fallback branch when preceding conditions evaluate to false
        else
            # Execute command: error "PowerShell not found to run native Windows installation."
            error "PowerShell not found to run native Windows installation."
            # Execute command: error "Please run install.ps1 from PowerShell or install inside WSL."
            error "Please run install.ps1 from PowerShell or install inside WSL."
            # Terminate script execution with exit status 1
            exit 1
        # End of if-conditional control block
        fi
        # Execute command: ;;
        ;;
    # Execute command: *)
    *)
        # Execute command: error "Unsupported or unknown OS: ${UNAME_S}"
        error "Unsupported or unknown OS: ${UNAME_S}"
        # Execute command: error "Supported: Linux, macOS, and native Windows (PowerShell/CMD) or WSL."
        error "Supported: Linux, macOS, and native Windows (PowerShell/CMD) or WSL."
        # Terminate script execution with exit status 1
        exit 1
        # Execute command: ;;
        ;;
# Execute command: esac
esac

# ─── Step 2: Check Python ────────────────────────────────────────────────────

# Execute command: step "Checking Python installation"
step "Checking Python installation"

RESOLVED_PY=""

# 1. User override via JULIUS_PYTHON
if [ -n "${JULIUS_PYTHON:-}" ] && command -v "${JULIUS_PYTHON}" >/dev/null 2>&1; then
    RESOLVED_PY="$(command -v "${JULIUS_PYTHON}")"
# End of if-conditional control block
fi

# 2. Check if .venv already exists with a valid Python 3.10+
if [ -z "${RESOLVED_PY}" ] && [ -x "${SCRIPT_DIR}/.venv/bin/python" ]; then
    # Execute command: if "${SCRIPT_DIR}/.venv/bin/python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    if "${SCRIPT_DIR}/.venv/bin/python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        RESOLVED_PY="${SCRIPT_DIR}/.venv/bin/python"
    # End of if-conditional control block
    fi
# End of if-conditional control block
fi

# 3. Search common candidates in PATH and standard Homebrew/Unix locations
if [ -z "${RESOLVED_PY}" ]; then
    # Execute command: for cand in \
    for cand in \
        python3.14 python3.13 python3.12 python3.11 python3.10 \
        /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3.10 /opt/homebrew/bin/python3 \
        /usr/local/bin/python3.14 /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 /usr/local/bin/python3.10 /usr/local/bin/python3 \
        python3 python; do
        # Execute command: if command -v "$cand" >/dev/null 2>&1; then
        if command -v "$cand" >/dev/null 2>&1; then
            p="$(command -v "$cand")"
            # Execute command: if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
                RESOLVED_PY="$p"
                # Execute command: break
                break
            # End of if-conditional control block
            fi
        # Alternative condition check: -x "$cand"
        elif [ -x "$cand" ]; then
            # Execute command: if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
                RESOLVED_PY="$cand"
                # Execute command: break
                break
            # End of if-conditional control block
            fi
        # End of if-conditional control block
        fi
    # End of loop iteration block
    done
# End of if-conditional control block
fi

# Evaluate condition check: -z "${RESOLVED_PY}"
if [ -z "${RESOLVED_PY}" ]; then
    # Execute command: if command -v python3 >/dev/null 2>&1; then
    if command -v python3 >/dev/null 2>&1; then
        CURRENT_VER="$(python3 --version 2>&1 || true)"
        # Execute command: error "Python 3.10+ is required, but found ${CURRENT_VER}"
        error "Python 3.10+ is required, but found ${CURRENT_VER}"
    # Fallback branch when preceding conditions evaluate to false
    else
        # Execute command: error "Python 3.10+ not found in PATH."
        error "Python 3.10+ not found in PATH."
    # End of if-conditional control block
    fi
    # Execute command: error "Please install Python 3.10+ and re-run, or set JULIUS_PYTHON to a valid Python 3.10+ binary."
    error "Please install Python 3.10+ and re-run, or set JULIUS_PYTHON to a valid Python 3.10+ binary."
    # Terminate script execution with exit status 1
    exit 1
# End of if-conditional control block
fi

PYTHON_BIN="${RESOLVED_PY}"
PYTHON_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
# Execute command: ok "Found: ${PYTHON_VERSION} (${PYTHON_BIN})"
ok "Found: ${PYTHON_VERSION} (${PYTHON_BIN})"

# Check for venv module
if ! "${PYTHON_BIN}" -c 'import venv' 2>/dev/null; then
    # Execute command: error "Python venv module not available for ${PYTHON_BIN}."
    error "Python venv module not available for ${PYTHON_BIN}."
    # Execute command: error "Install it with: sudo apt-get install python3-venv (Debian/Ubuntu)"
    error "Install it with: sudo apt-get install python3-venv (Debian/Ubuntu)"
    # Terminate script execution with exit status 1
    exit 1
# End of if-conditional control block
fi

# Execute command: ok "venv module available"
ok "venv module available"

# ─── Step 3: Create virtual environment ──────────────────────────────────────

# Execute command: step "Setting up virtual environment"
step "Setting up virtual environment"

VENV_DIR="${SCRIPT_DIR}/.venv"
VENV_PY="${VENV_DIR}/bin/python"

# Execute command: if [ -x "${VENV_PY}" ] && "${VENV_PY}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
if [ -x "${VENV_PY}" ] && "${VENV_PY}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    # Execute command: info "Virtual environment already exists at ${VENV_DIR}"
    info "Virtual environment already exists at ${VENV_DIR}"
    # Fix any stale shebang paths if the project directory was moved
    for f in "${VENV_DIR}/bin"/*; do
        # Evaluate condition check: -f "$f" ] && [ ! -L "$f"
        if [ -f "$f" ] && [ ! -L "$f" ]; then
            # Execute command: sed -i '' "s#/Users/[^/]*/Desktop/Julius#${SCRIPT_DIR}#g" "$f" 2>/dev/null || true
            sed -i '' "s#/Users/[^/]*/Desktop/Julius#${SCRIPT_DIR}#g" "$f" 2>/dev/null || true
        # End of if-conditional control block
        fi
    # End of loop iteration block
    done
    # Execute command: ok "Re-using existing .venv"
    ok "Re-using existing .venv"
# Fallback branch when preceding conditions evaluate to false
else
    # Execute command: info "Creating virtual environment at ${VENV_DIR}"
    info "Creating virtual environment at ${VENV_DIR}"
    # Execute command: "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    # Execute command: ok "Virtual environment created"
    ok "Virtual environment created"
# End of if-conditional control block
fi

# Ensure pip is ready without hanging on low internet
info "Checking pip package manager..."
# Execute command: "${VENV_PY}" -m pip --version >/dev/null 2>&1 || "${VENV_PY}" -m ensurepip --upgrade 2>/dev/null || true
"${VENV_PY}" -m pip --version >/dev/null 2>&1 || "${VENV_PY}" -m ensurepip --upgrade 2>/dev/null || true
# Execute command: ok "pip is ready"
ok "pip is ready"

# ─── Step 4: Install Python dependencies ─────────────────────────────────────

# Execute command: step "Installing Python dependencies"
step "Installing Python dependencies"

REQ_FILE="${SCRIPT_DIR}/requirements.txt"
REQ_AGENT_FILE="${SCRIPT_DIR}/requirements-agent.txt"

# Check if core dependencies are already present to conserve low internet bandwidth
if "${VENV_PY}" -c "import aiohttp, playwright, textual, rich, src.agent_config, src.web_agent" 2>/dev/null; then
    # Execute command: ok "Core Python dependencies already installed"
    ok "Core Python dependencies already installed"
# Fallback branch when preceding conditions evaluate to false
else
    # Evaluate condition check: -f "${REQ_FILE}"
    if [ -f "${REQ_FILE}" ]; then
        # Execute command: info "Installing from requirements.txt (live progress & size enabled)..."
        info "Installing from requirements.txt (live progress & size enabled)..."
        # Execute command: "${VENV_PY}" -m pip install --progress-bar on -r "${REQ_FILE}"
        "${VENV_PY}" -m pip install --progress-bar on -r "${REQ_FILE}"
        # Execute command: ok "requirements.txt installed"
        ok "requirements.txt installed"
    # Fallback branch when preceding conditions evaluate to false
    else
        # Execute command: warn "requirements.txt not found — skipping"
        warn "requirements.txt not found — skipping"
    # End of if-conditional control block
    fi

    # Evaluate condition check: -f "${REQ_AGENT_FILE}"
    if [ -f "${REQ_AGENT_FILE}" ]; then
        # Execute command: info "Installing from requirements-agent.txt (live progress & size enabled)..."
        info "Installing from requirements-agent.txt (live progress & size enabled)..."
        # Execute command: "${VENV_PY}" -m pip install --progress-bar on -r "${REQ_AGENT_FILE}"
        "${VENV_PY}" -m pip install --progress-bar on -r "${REQ_AGENT_FILE}"
        # Execute command: ok "requirements-agent.txt installed"
        ok "requirements-agent.txt installed"
    # Fallback branch when preceding conditions evaluate to false
    else
        # Execute command: warn "requirements-agent.txt not found — skipping"
        warn "requirements-agent.txt not found — skipping"
    # End of if-conditional control block
    fi
# End of if-conditional control block
fi

# ─── Step 5: Install Playwright browsers ─────────────────────────────────────

# Execute command: step "Installing Playwright browsers"
step "Installing Playwright browsers"

# Evaluate condition check: "${SKIP_BROWSER}" = "1"
if [ "${SKIP_BROWSER}" = "1" ]; then
    # Execute command: warn "Browser installation skipped (--no-browser or JULIUS_SKIP_BROWSER=1)"
    warn "Browser installation skipped (--no-browser or JULIUS_SKIP_BROWSER=1)"
# Fallback branch when preceding conditions evaluate to false
else
    # Check if Playwright Chromium already runs
    if "${VENV_PY}" -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); b.close(); p.stop()" 2>/dev/null; then
        # Execute command: ok "Playwright Chromium browser already installed and operational"
        ok "Playwright Chromium browser already installed and operational"
    # Fallback branch when preceding conditions evaluate to false
    else
        # Execute command: info "Provisioning Chromium browser via Playwright (downloading ~150MB with live progress)..."
        info "Provisioning Chromium browser via Playwright (downloading ~150MB with live progress)..."
        # Execute command: if "${VENV_PY}" -m playwright install chromium; then
        if "${VENV_PY}" -m playwright install chromium; then
            # Execute command: ok "Playwright Chromium installed"
            ok "Playwright Chromium installed"
        # Fallback branch when preceding conditions evaluate to false
        else
            # Execute command: warn "Could not install Playwright browsers automatically (low internet or network issue)."
            warn "Could not install Playwright browsers automatically (low internet or network issue)."
            # Execute command: warn "You can retry manually later via: ${VENV_DIR}/bin/playwright install chromium"
            warn "You can retry manually later via: ${VENV_DIR}/bin/playwright install chromium"
        # End of if-conditional control block
        fi
    # End of if-conditional control block
    fi
# End of if-conditional control block
fi

# ─── Step 5b: TypeScript React Ink TUI ──────────────────────────────────────
if command -v npm >/dev/null 2>&1 && [ -d "${SCRIPT_DIR}/src/tui_ts" ]; then
    step "Building high-performance TypeScript React Ink TUI"
    (
        cd "${SCRIPT_DIR}/src/tui_ts"
        if [ ! -d "node_modules" ]; then
            npm install --silent
        fi
        npm run build --silent
    ) && ok "TypeScript React Ink TUI compiled (@julius/tui)" || warn "TypeScript TUI build skipped (fallback to Textual available)"
fi

# ─── Step 6: Create default .env (if missing) ────────────────────────────────

step "Configuring environment"

ENV_FILE="${SCRIPT_DIR}/.env"

if [ -f "${ENV_FILE}" ]; then
    ok ".env already exists — keeping your current configuration"
else
    info "Creating default .env configuration..."
    cat > "${ENV_FILE}" <<'ENVEOF'
JULIUS_MAX_STEPS=9999
JULIUS_HEADLESS=false
JULIUS_WS_PORT=8000
JULIUS_CLIENT_MAX_SIZE=104857600
ENVEOF
    ok ".env created with default values"
fi

# ─── Interactive API Key Setup Wizard ────────────────────────────────────────

_has_real_key() {
    local val
    val="$(grep -E "^${1}=" "${ENV_FILE}" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs 2>/dev/null)"
    [ -n "${val}" ] && \
    [ "${val}" != "YOUR_NVIDIA_API_KEY_HERE" ] && \
    [ "${val}" != "YOUR_OPENAI_API_KEY_HERE" ] && \
    [ "${val}" != "YOUR_ANTHROPIC_API_KEY_HERE" ] && \
    [ "${val}" != "YOUR_DEEPSEEK_API_KEY_HERE" ] && \
    [ "${val}" != "YOUR_GEMINI_API_KEY_HERE" ] && \
    [ "${val}" != "YOUR_GROQ_API_KEY_HERE" ] && \
    [ "${val}" != "YOUR_XAI_API_KEY_HERE" ] && \
    [ "${val}" != "YOUR_MOONSHOT_API_KEY_HERE" ] && \
    [ "${val}" != "YOUR_PERPLEXITY_API_KEY_HERE" ]
}

_set_env_key() {
    local key="$1" val="$2"
    if grep -qE "^${key}=" "${ENV_FILE}" 2>/dev/null; then
        if [[ "${OSTYPE}" == "darwin"* ]]; then
            sed -i '' "s|^${key}=.*|${key}=${val}|" "${ENV_FILE}"
        else
            sed -i "s|^${key}=.*|${key}=${val}|" "${ENV_FILE}"
        fi
    else
        printf '\n%s=%s\n' "${key}" "${val}" >> "${ENV_FILE}"
    fi
}

# Only run wizard if running in an interactive terminal
if [ -t 0 ] && [ -t 1 ]; then

    # ── Model Selection ─────────────────────────────────────────────────────
    printf '\n%s╔══════════════════════════════════════════════════════════════╗%s\n' \
        "${COLOR_BOLD}${COLOR_JULIUS}" "${COLOR_RESET}"
    printf '%s║          🧠  Julius — AI Provider Setup Wizard              ║%s\n' \
        "${COLOR_BOLD}${COLOR_JULIUS}" "${COLOR_RESET}"
    printf '%s╚══════════════════════════════════════════════════════════════╝%s\n' \
        "${COLOR_BOLD}${COLOR_JULIUS}" "${COLOR_RESET}"
    printf '\n%s  Select your primary AI model provider:%s\n\n' \
        "${COLOR_BOLD}" "${COLOR_RESET}"
    printf '  %s[1]%s  NVIDIA Nemotron 550B   %s(Free · 1,000 credits · Recommended)%s\n' \
        "${COLOR_JULIUS}" "${COLOR_RESET}" "${COLOR_DIM}" "${COLOR_RESET}"
    printf '  %s[2]%s  Anthropic Claude       %s(claude-3-5-sonnet / haiku)%s\n' \
        "${COLOR_JULIUS}" "${COLOR_RESET}" "${COLOR_DIM}" "${COLOR_RESET}"
    printf '  %s[3]%s  OpenAI ChatGPT         %s(gpt-4o / o3-mini)%s\n' \
        "${COLOR_JULIUS}" "${COLOR_RESET}" "${COLOR_DIM}" "${COLOR_RESET}"
    printf '  %s[4]%s  DeepSeek               %s(deepseek-chat / deepseek-reasoner)%s\n' \
        "${COLOR_JULIUS}" "${COLOR_RESET}" "${COLOR_DIM}" "${COLOR_RESET}"
    printf '  %s[5]%s  Google Gemini          %s(gemini-2.0-flash / 2.5-pro)%s\n' \
        "${COLOR_JULIUS}" "${COLOR_RESET}" "${COLOR_DIM}" "${COLOR_RESET}"
    printf '  %s[6]%s  xAI Grok               %s(grok-2 / grok-3)%s\n' \
        "${COLOR_JULIUS}" "${COLOR_RESET}" "${COLOR_DIM}" "${COLOR_RESET}"
    printf '  %s[7]%s  Local Ollama           %s(private · no API key needed)%s\n' \
        "${COLOR_JULIUS}" "${COLOR_RESET}" "${COLOR_DIM}" "${COLOR_RESET}"
    printf '  %s[8]%s  Skip setup             %s(configure .env manually later)%s\n\n' \
        "${COLOR_DIM}" "${COLOR_RESET}" "${COLOR_DIM}" "${COLOR_RESET}"
    printf '  %sEnter choice [1–8, default: 1]:%s ' \
        "${COLOR_BOLD}${COLOR_JULIUS}" "${COLOR_RESET}"

    WIZARD_CHOICE=""
    read -r WIZARD_CHOICE 2>/dev/null || true
    WIZARD_CHOICE="${WIZARD_CHOICE:-1}"

    _prompt_key() {
        local provider_name="$1" env_var="$2" key_url="$3"
        printf '\n%s  ┌──────────────────────────────────────────────────────────┐%s\n' \
            "${COLOR_JULIUS}" "${COLOR_RESET}"
        printf '%s  │  %s API Key%s\n' \
            "${COLOR_JULIUS}" "${provider_name}" "${COLOR_RESET}"
        printf '%s  │  Get yours free at: %s%s%s\n' \
            "${COLOR_DIM}" "${COLOR_CYAN}" "${key_url}" "${COLOR_RESET}"
        printf '%s  └──────────────────────────────────────────────────────────┘%s\n' \
            "${COLOR_JULIUS}" "${COLOR_RESET}"
        printf '  %sPaste your API key (or press Enter to skip):%s ' \
            "${COLOR_BOLD}" "${COLOR_RESET}"
        local api_key_input=""
        read -r api_key_input 2>/dev/null || true
        echo "${api_key_input}"
    }

    case "${WIZARD_CHOICE}" in
        1|"")
            if ! _has_real_key "NVIDIA_API_KEY"; then
                _nvidia_key="$(_prompt_key "NVIDIA Build NIM" "NVIDIA_API_KEY" "https://build.nvidia.com/explore/discover")"
                if [ -n "${_nvidia_key}" ]; then
                    _set_env_key "NVIDIA_API_KEY" "${_nvidia_key}"
                    _set_env_key "JULIUS_DEFAULT_MODEL" "nvidia"
                    ok "NVIDIA API key saved ✓"
                else
                    warn "Skipped — you can add NVIDIA_API_KEY to .env later"
                fi
            else
                ok "NVIDIA API key already configured ✓"
            fi
            ;;
        2)
            if ! _has_real_key "ANTHROPIC_API_KEY"; then
                _anth_key="$(_prompt_key "Anthropic Claude" "ANTHROPIC_API_KEY" "https://console.anthropic.com/keys")"
                if [ -n "${_anth_key}" ]; then
                    _set_env_key "ANTHROPIC_API_KEY" "${_anth_key}"
                    _set_env_key "JULIUS_DEFAULT_MODEL" "anthropic"
                    ok "Anthropic API key saved ✓"
                else
                    warn "Skipped — you can add ANTHROPIC_API_KEY to .env later"
                fi
            else
                ok "Anthropic API key already configured ✓"
            fi
            ;;
        3)
            if ! _has_real_key "OPENAI_API_KEY"; then
                _oai_key="$(_prompt_key "OpenAI ChatGPT" "OPENAI_API_KEY" "https://platform.openai.com/api-keys")"
                if [ -n "${_oai_key}" ]; then
                    _set_env_key "OPENAI_API_KEY" "${_oai_key}"
                    _set_env_key "JULIUS_DEFAULT_MODEL" "openai"
                    ok "OpenAI API key saved ✓"
                else
                    warn "Skipped — you can add OPENAI_API_KEY to .env later"
                fi
            else
                ok "OpenAI API key already configured ✓"
            fi
            ;;
        4)
            if ! _has_real_key "DEEPSEEK_API_KEY"; then
                _ds_key="$(_prompt_key "DeepSeek" "DEEPSEEK_API_KEY" "https://platform.deepseek.com/api_keys")"
                if [ -n "${_ds_key}" ]; then
                    _set_env_key "DEEPSEEK_API_KEY" "${_ds_key}"
                    _set_env_key "JULIUS_DEFAULT_MODEL" "deepseek"
                    ok "DeepSeek API key saved ✓"
                else
                    warn "Skipped — you can add DEEPSEEK_API_KEY to .env later"
                fi
            else
                ok "DeepSeek API key already configured ✓"
            fi
            ;;
        5)
            if ! _has_real_key "GEMINI_API_KEY"; then
                _gem_key="$(_prompt_key "Google Gemini" "GEMINI_API_KEY" "https://aistudio.google.com/app/apikey")"
                if [ -n "${_gem_key}" ]; then
                    _set_env_key "GEMINI_API_KEY" "${_gem_key}"
                    _set_env_key "JULIUS_DEFAULT_MODEL" "gemini"
                    ok "Gemini API key saved ✓"
                else
                    warn "Skipped — you can add GEMINI_API_KEY to .env later"
                fi
            else
                ok "Gemini API key already configured ✓"
            fi
            ;;
        6)
            if ! _has_real_key "XAI_API_KEY"; then
                _xai_key="$(_prompt_key "xAI Grok" "XAI_API_KEY" "https://console.x.ai")"
                if [ -n "${_xai_key}" ]; then
                    _set_env_key "XAI_API_KEY" "${_xai_key}"
                    _set_env_key "GROK_API_KEY" "${_xai_key}"
                    _set_env_key "JULIUS_DEFAULT_MODEL" "grok"
                    ok "xAI API key saved ✓"
                else
                    warn "Skipped — you can add XAI_API_KEY to .env later"
                fi
            else
                ok "xAI API key already configured ✓"
            fi
            ;;
        7)
            info "Ollama selected — no API key needed"
            _set_env_key "JULIUS_DEFAULT_MODEL" "ollama"
            ok "Default provider set to local Ollama ✓"
            ;;
        8)
            warn "Setup wizard skipped — edit .env to configure API keys before running Julius"
            ;;
        *)
            warn "Invalid selection '${WIZARD_CHOICE}' — skipping API key setup"
            ;;
    esac
fi
# ─────────────────────────────────────────────────────────────────────────────

# Execute command: info "Current configuration:"
info "Current configuration:"
# Repeat loop while condition evaluates to true: IFS= read -r line
while IFS= read -r line; do
    # Execute command: [[ -z "${line}" || "${line}" == \#* ]] && continue
    [[ -z "${line}" || "${line}" == \#* ]] && continue
    # Execute command: info "  ${line}"
    info "  ${line}"
# End of loop iteration block
done < "${ENV_FILE}"

# Make the CLI wrapper executable
if [ -f "${SCRIPT_DIR}/julius" ]; then
    # Modify file permissions: +x "${SCRIPT_DIR}/julius"
    chmod +x "${SCRIPT_DIR}/julius"
    # Execute command: ok "CLI wrapper 'julius' is executable"
    ok "CLI wrapper 'julius' is executable"
# End of if-conditional control block
fi

# Auto-link global commands: julius and Julius
info "Configuring global commands ('julius' and 'Julius')..."
GLOBAL_LINKED=0

# Iterate loop variable target_dir over items in "/opt/homebrew/bin" "${HOME}/.local/bin" "/usr/local/bin"
for target_dir in "/opt/homebrew/bin" "${HOME}/.local/bin" "/usr/local/bin"; do
    # Evaluate condition check: ! -d "${target_dir}"
    if [ ! -d "${target_dir}" ]; then
        mkdir -p "${target_dir}" 2>/dev/null || true
    # End of if-conditional control block
    fi

    # Evaluate condition check: -d "${target_dir}" ] && [ -w "${target_dir}"
    if [ -d "${target_dir}" ] && [ -w "${target_dir}" ]; then
        # Execute command: ln -sf "${SCRIPT_DIR}/julius" "${target_dir}/julius" 2>/dev/null && \
        ln -sf "${SCRIPT_DIR}/julius" "${target_dir}/julius" 2>/dev/null && \
        ln -sf "${SCRIPT_DIR}/julius" "${target_dir}/Julius" 2>/dev/null && {
            # Execute command: ok "Created global symlinks in ${target_dir} (julius & Julius)"
            ok "Created global symlinks in ${target_dir} (julius & Julius)"
            GLOBAL_LINKED=1
            # Execute command: break
            break
        # Execute command: }
        }
    # End of if-conditional control block
    fi
# End of loop iteration block
done

# Evaluate condition check: "${GLOBAL_LINKED}" -eq 0
if [ "${GLOBAL_LINKED}" -eq 0 ]; then
    mkdir -p "${HOME}/.local/bin" 2>/dev/null || true
    # Execute command: ln -sf "${SCRIPT_DIR}/julius" "${HOME}/.local/bin/julius" 2>/dev/null || true
    ln -sf "${SCRIPT_DIR}/julius" "${HOME}/.local/bin/julius" 2>/dev/null || true
    # Execute command: ln -sf "${SCRIPT_DIR}/julius" "${HOME}/.local/bin/Julius" 2>/dev/null || true
    ln -sf "${SCRIPT_DIR}/julius" "${HOME}/.local/bin/Julius" 2>/dev/null || true
    # Execute command: ok "Created user symlinks in ~/.local/bin (julius & Julius)"
    ok "Created user symlinks in ~/.local/bin (julius & Julius)"
# End of if-conditional control block
fi

# Install Julius typography (text) and JetBrains Mono (coding)
info "Installing Julius typography & JetBrains Mono coding fonts..."
# Evaluate condition check: "${OS_FAMILY}" = "macos"
if [ "${OS_FAMILY}" = "macos" ]; then
    MAC_FONT_DIR="${HOME}/Library/Fonts"
    mkdir -p "${MAC_FONT_DIR}" 2>/dev/null || true
    # Evaluate condition check: -d "${SCRIPT_DIR}/Julius_Fonts"
    if [ -d "${SCRIPT_DIR}/Julius_Fonts" ]; then
        cp -f "${SCRIPT_DIR}/Julius_Fonts"/Julius-*.ttf "${MAC_FONT_DIR}/" 2>/dev/null || true
        cp -f "${SCRIPT_DIR}/Julius_Fonts"/Julius-*.otf "${MAC_FONT_DIR}/" 2>/dev/null || true
    # End of if-conditional control block
    fi
    # Evaluate condition check: -d "${SCRIPT_DIR}/Julius_Fonts/code"
    if [ -d "${SCRIPT_DIR}/Julius_Fonts/code" ]; then
        cp -f "${SCRIPT_DIR}/Julius_Fonts/code"/JetBrainsMono-*.ttf "${MAC_FONT_DIR}/" 2>/dev/null || true
    # End of if-conditional control block
    fi
    # Execute command: ok "Installed Julius & JetBrains Mono fonts to ${MAC_FONT_DIR}"
    ok "Installed Julius & JetBrains Mono fonts to ${MAC_FONT_DIR}"
# Alternative condition check: "${OS_FAMILY}" = "linux" ] || [ "${OS_FAMILY}" = "wsl"
elif [ "${OS_FAMILY}" = "linux" ] || [ "${OS_FAMILY}" = "wsl" ]; then
    LINUX_FONT_DIR="${HOME}/.local/share/fonts"
    mkdir -p "${LINUX_FONT_DIR}" 2>/dev/null || true
    # Evaluate condition check: -d "${SCRIPT_DIR}/Julius_Fonts"
    if [ -d "${SCRIPT_DIR}/Julius_Fonts" ]; then
        cp -f "${SCRIPT_DIR}/Julius_Fonts"/Julius-*.ttf "${LINUX_FONT_DIR}/" 2>/dev/null || true
        cp -f "${SCRIPT_DIR}/Julius_Fonts"/Julius-*.otf "${LINUX_FONT_DIR}/" 2>/dev/null || true
    # End of if-conditional control block
    fi
    # Evaluate condition check: -d "${SCRIPT_DIR}/Julius_Fonts/code"
    if [ -d "${SCRIPT_DIR}/Julius_Fonts/code" ]; then
        cp -f "${SCRIPT_DIR}/Julius_Fonts/code"/JetBrainsMono-*.ttf "${LINUX_FONT_DIR}/" 2>/dev/null || true
    # End of if-conditional control block
    fi
    # Execute command: if command -v fc-cache >/dev/null 2>&1; then
    if command -v fc-cache >/dev/null 2>&1; then
        # Execute command: fc-cache -f "${LINUX_FONT_DIR}" 2>/dev/null || true
        fc-cache -f "${LINUX_FONT_DIR}" 2>/dev/null || true
    # End of if-conditional control block
    fi
    # Execute command: ok "Installed Julius & JetBrains Mono fonts to ${LINUX_FONT_DIR}"
    ok "Installed Julius & JetBrains Mono fonts to ${LINUX_FONT_DIR}"
# End of if-conditional control block
fi

# ─── Step 7: Post-install verification ────────────────────────────────────────

# Execute command: step "Verifying installation"
step "Verifying installation"

# Evaluate condition check: "${SKIP_VERIFY}" = "1"
if [ "${SKIP_VERIFY}" = "1" ]; then
    # Execute command: warn "Verification skipped (--no-verify or JULIUS_SKIP_VERIFY=1)"
    warn "Verification skipped (--no-verify or JULIUS_SKIP_VERIFY=1)"
# Fallback branch when preceding conditions evaluate to false
else
    # Test 1: Core imports
    info "Checking core module imports..."
    # Execute command: if "${VENV_PY}" -c "
    if "${VENV_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
from src.agent_config import AgentConfig
from src.web_agent import WebAgent
from src.llm_web_client import WebLLMClient
print('All core modules imported successfully')
" 2>/dev/null; then
        # Execute command: ok "Core modules import cleanly"
        ok "Core modules import cleanly"
    # Fallback branch when preceding conditions evaluate to false
    else
        # Execute command: error "Failed to import core modules"
        error "Failed to import core modules"
        # Terminate script execution with exit status 1
        exit 1
    # End of if-conditional control block
    fi

    # Test 2: Playwright is importable
    info "Checking Playwright..."
    # Execute command: if "${VENV_PY}" -c "from playwright.sync_api import sync_playwright; print('Playwright OK')" 2>/dev/null; then
    if "${VENV_PY}" -c "from playwright.sync_api import sync_playwright; print('Playwright OK')" 2>/dev/null; then
        # Execute command: ok "Playwright is available"
        ok "Playwright is available"
    # Fallback branch when preceding conditions evaluate to false
    else
        # Execute command: warn "Playwright import failed — browser automation may not work"
        warn "Playwright import failed — browser automation may not work"
    # End of if-conditional control block
    fi

    # Test 3: aiohttp server can be created
    info "Checking aiohttp server creation..."
    # Execute command: if "${VENV_PY}" -c "
    if "${VENV_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
from aiohttp import web
app = web.Application()
print('Server creation OK')
" 2>/dev/null; then
        # Execute command: ok "Server module loads cleanly"
        ok "Server module loads cleanly"
    # Fallback branch when preceding conditions evaluate to false
    else
        # Execute command: warn "Server module check failed — may need manual review"
        warn "Server module check failed — may need manual review"
    # End of if-conditional control block
    fi
# End of if-conditional control block
fi

# ─── Done ─────────────────────────────────────────────────────────────────────

# Output formatted terminal string: '\n%s═══════════════════════════════════════════════════════════════%s\n' \
printf '\n%s═══════════════════════════════════════════════════════════════%s\n' \
    "${COLOR_BOLD}${COLOR_JULIUS}" "${COLOR_RESET}"
# Output formatted terminal string: '%s  ✓ %sJulius Agent is installed and ready!%s\n' \
printf '%s  ✓ %sJulius Agent is installed and ready!%s\n' \
    "${COLOR_GREEN}" "${COLOR_BOLD}${COLOR_JULIUS}" "${COLOR_RESET}"
# Output formatted terminal string: '%s═══════════════════════════════════════════════════════════════%s\n\n' \
printf '%s═══════════════════════════════════════════════════════════════%s\n\n' \
    "${COLOR_BOLD}${COLOR_JULIUS}" "${COLOR_RESET}"

# Execute command: cat <<EOF
cat <<EOF
  ${COLOR_BOLD}${COLOR_JULIUS}Project:${COLOR_RESET}   ${SCRIPT_DIR}
  ${COLOR_BOLD}${COLOR_JULIUS}Venv:${COLOR_RESET}      ${VENV_DIR}
  ${COLOR_BOLD}${COLOR_JULIUS}Python:${COLOR_RESET}    ${PYTHON_VERSION}

  ${COLOR_BOLD}${COLOR_JULIUS}Getting Started:${COLOR_RESET}

  ${COLOR_DIM}# Activate the virtual environment${COLOR_RESET}
  source ${VENV_DIR}/bin/activate

  ${COLOR_DIM}# Start the Julius Web UI${COLOR_RESET}
  python3 julius_gui.py

  ${COLOR_DIM}# Or use the CLI wrapper directly${COLOR_RESET}
  ./julius "create a landing page"

  ${COLOR_DIM}# Run with a specific LLM provider${COLOR_RESET}
  ./julius -p gemini "refactor this codebase"

  ${COLOR_BOLD}${COLOR_JULIUS}Available Providers:${COLOR_RESET}  deepseek, chatgpt, gemini, grok, perplexity

  ${COLOR_BOLD}${COLOR_JULIUS}Configuration:${COLOR_RESET}
  Edit ${COLOR_BOLD}${COLOR_JULIUS}.env${COLOR_RESET} to change server settings (port, max steps, headless mode).

EOF

# Clear the failure trap on clean exit
trap - EXIT
