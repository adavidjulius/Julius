#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Julius Agent — Installer
#
# Sets up the local Python environment, installs all dependencies, provisions
# Playwright browsers, builds the TUI, and verifies the installation.
#
# Usage:
#   ./install.sh                # full install (default)
#   ./install.sh --no-verify    # skip post-install verification
#   ./install.sh --no-browser   # skip Playwright browser install
#   ./install.sh --skip-wizard  # skip interactive AI provider wizard
#   ./install.sh --help         # print usage
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# Ensure standard system and package manager paths are included in PATH
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:${HOME}/.local/bin:${PATH}"

# ─── Colors & Styling ─────────────────────────────────────────────────────────

if [ -t 1 ] && command -v tput >/dev/null 2>&1 && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]; then
    COLOR_RESET="$(tput sgr0)"
    COLOR_BOLD="$(tput bold)"
    COLOR_DIM="$(tput dim)"
    COLOR_RED="$(tput setaf 1)"
    COLOR_GREEN="$(tput setaf 2)"
    COLOR_YELLOW="$(tput setaf 3)"
    COLOR_CYAN="$(tput setaf 6)"
    COLOR_JULIUS=$'\033[38;2;200;184;150m' # Brand Color #C8B896
else
    COLOR_RESET=""
    COLOR_BOLD=""
    COLOR_DIM=""
    COLOR_RED=""
    COLOR_GREEN=""
    COLOR_YELLOW=""
    COLOR_CYAN=""
    COLOR_JULIUS=$'\033[38;2;200;184;150m'
fi

# Restore cursor on any exit signal
trap 'tput cnorm 2>/dev/null || true' EXIT INT TERM

# ─── Julius ASCII Banner ───────────────────────────────────────────────────────

print_julius_banner() {
    local subtitle="${1:-Autonomous AI Copilot — Installer}"
    local cols="${COLUMNS:-}"
    if [ -z "${cols}" ] || [ "${cols}" -le 0 ] 2>/dev/null; then
        cols="$(stty size 2>/dev/null | awk '{print $2}')"
    fi
    if [ -z "${cols}" ] || [ "${cols}" -le 0 ] 2>/dev/null; then
        cols="$(tput cols 2>/dev/null || echo 80)"
    fi
    if [ -z "${cols}" ] || [ "${cols}" -le 0 ] 2>/dev/null; then
        cols=80
    fi

    printf '%s\n' "${COLOR_BOLD}${COLOR_JULIUS}"
    if [ "${cols}" -lt 52 ]; then
        printf '  ━━━  J U L I U S  ━━━\n'
    else
        cat <<'EOF'
  ╔═════╗ ╔╗   ╔╗ ╔╗      ╔═════╗ ╔╗   ╔╗ ╔═════╗
  ╚══╗  ║ ║║   ║║ ║║      ╚═╗ ╔═╝ ║║   ║║ ║ ╔═══╝
     ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ║ ╚═══╗
     ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ╚═══╗ ║
  ╔══╝  ║ ║╚═══╝║ ║╚════╗ ╔═╝ ╚═╗ ║╚═══╝║ ╔═══╝ ║
  ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝
EOF
    fi
    printf '%s' "${COLOR_RESET}"
    if [ -n "${subtitle}" ]; then
        printf '%s  %s%s\n\n' "${COLOR_JULIUS}" "${subtitle}" "${COLOR_RESET}"
    else
        printf '\n'
    fi
}

# ─── Argument Parsing ─────────────────────────────────────────────────────────

SKIP_VERIFY="${JULIUS_SKIP_VERIFY:-0}"
SKIP_BROWSER="${JULIUS_SKIP_BROWSER:-0}"
SKIP_WIZARD="${JULIUS_SKIP_WIZARD:-0}"
PYTHON_BIN="${JULIUS_PYTHON:-python3}"

print_usage() {
    cat <<EOF
${COLOR_BOLD}${COLOR_JULIUS}Usage:${COLOR_RESET} ./install.sh [options]

${COLOR_BOLD}${COLOR_JULIUS}Options:${COLOR_RESET}
  --no-verify     Skip the post-install verification step.
  --no-browser    Skip Playwright browser installation.
  --skip-wizard   Skip the interactive AI provider selection wizard.
  -h, --help      Show this help text and exit.

${COLOR_BOLD}${COLOR_JULIUS}Environment overrides:${COLOR_RESET}
  JULIUS_SKIP_VERIFY=1      same as --no-verify
  JULIUS_SKIP_BROWSER=1     same as --no-browser
  JULIUS_SKIP_WIZARD=1      same as --skip-wizard
  JULIUS_PYTHON=python3.12  override which python binary to use
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --no-verify)
            SKIP_VERIFY="1"
            ;;
        --no-browser)
            SKIP_BROWSER="1"
            ;;
        --skip-wizard|-y)
            SKIP_WIZARD="1"
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            printf '%sUnknown argument: %s%s\n' "${COLOR_RED}" "$1" "${COLOR_RESET}" >&2
            print_usage
            exit 2
            ;;
    esac
    shift
done

# ─── Platform Detection & Handoff ─────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}"

UNAME_S="$(uname -s 2>/dev/null || echo unknown)"
UNAME_M="$(uname -m 2>/dev/null || echo unknown)"
OS_FAMILY="unknown"
IS_WSL="0"

case "${UNAME_S}" in
    Linux*)
        OS_FAMILY="linux"
        if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
            IS_WSL="1"
        fi
        ;;
    Darwin*)
        OS_FAMILY="macos"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        OS_FAMILY="windows-shell"
        ;;
esac

if [ "${OS_FAMILY}" = "windows-shell" ]; then
    PWSH_BIN=""
    if command -v pwsh >/dev/null 2>&1; then
        PWSH_BIN="pwsh"
    elif command -v powershell.exe >/dev/null 2>&1; then
        PWSH_BIN="powershell.exe"
    fi
    if [ -n "${PWSH_BIN}" ] && [ -f "${SCRIPT_DIR}/install.ps1" ]; then
        exec "${PWSH_BIN}" -ExecutionPolicy Bypass -File "${SCRIPT_DIR}/install.ps1" "$@"
    else
        printf '%sPowerShell not found. Please run install.ps1 from PowerShell or WSL.%s\n' "${COLOR_RED}" "${COLOR_RESET}" >&2
        exit 1
    fi
fi

# ─── Python Resolution ────────────────────────────────────────────────────────

RESOLVED_PY=""
if [ -n "${JULIUS_PYTHON:-}" ] && command -v "${JULIUS_PYTHON}" >/dev/null 2>&1; then
    RESOLVED_PY="$(command -v "${JULIUS_PYTHON}")"
fi

if [ -z "${RESOLVED_PY}" ] && [ -x "${SCRIPT_DIR}/.venv/bin/python" ]; then
    if "${SCRIPT_DIR}/.venv/bin/python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        RESOLVED_PY="${SCRIPT_DIR}/.venv/bin/python"
    fi
fi

if [ -z "${RESOLVED_PY}" ]; then
    for cand in \
        python3.14 python3.13 python3.12 python3.11 python3.10 \
        /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3.10 /opt/homebrew/bin/python3 \
        /usr/local/bin/python3.14 /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 /usr/local/bin/python3.10 /usr/local/bin/python3 \
        python3 python; do
        if command -v "$cand" >/dev/null 2>&1; then
            p="$(command -v "$cand")"
            if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
                RESOLVED_PY="$p"
                break
            fi
        elif [ -x "$cand" ]; then
            if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
                RESOLVED_PY="$cand"
                break
            fi
        fi
    done
fi

if [ -z "${RESOLVED_PY}" ]; then
    printf '%sPython 3.10+ is required, but not found in PATH.%s\n' "${COLOR_RED}" "${COLOR_RESET}" >&2
    printf 'Please install Python 3.10+ (macOS: brew install python@3.12 | Ubuntu: sudo apt install python3 python3-venv)\n' >&2
    exit 1
fi

PYTHON_BIN="${RESOLVED_PY}"

if ! "${PYTHON_BIN}" -c 'import venv' 2>/dev/null; then
    printf '%sPython venv module missing for %s.%s\n' "${COLOR_RED}" "${PYTHON_BIN}" "${COLOR_RESET}" >&2
    printf 'Install it via: sudo apt-get install python3-venv\n' >&2
    exit 1
fi

# Print official Julius brand banner
if [ -t 1 ]; then
    print_julius_banner "Autonomous AI Copilot — Installer"
fi

# ─── Environment Files & Config Helpers ───────────────────────────────────────

ENV_FILE="${SCRIPT_DIR}/.env"
if [ ! -f "${ENV_FILE}" ]; then
    cat > "${ENV_FILE}" <<'ENVEOF'
JULIUS_MAX_STEPS=9999
JULIUS_HEADLESS=false
JULIUS_WS_PORT=8000
JULIUS_CLIENT_MAX_SIZE=104857600
ENVEOF
fi

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
    for target in "${ENV_FILE}" "${HOME}/.julius/.env" "${HOME}/.Julius/.env"; do
        if [ -f "${target}" ]; then
            if grep -qE "^${key}=" "${target}" 2>/dev/null; then
                if [[ "${OSTYPE}" == "darwin"* ]]; then
                    sed -i '' "s|^${key}=.*|${key}=${val}|" "${target}"
                else
                    sed -i "s|^${key}=.*|${key}=${val}|" "${target}"
                fi
            else
                printf '\n%s=%s\n' "${key}" "${val}" >> "${target}"
            fi
        fi
    done
}

_sync_config_toml_model() {
    local m="$1"
    local cfg="${HOME}/.config/julius/config.toml"
    mkdir -p "$(dirname "${cfg}")" 2>/dev/null || true
    if [ -f "${cfg}" ]; then
        if grep -qE '^model = ' "${cfg}" 2>/dev/null; then
            if [[ "${OSTYPE}" == "darwin"* ]]; then
                sed -i '' "s|^model = .*|model = \"${m}\"|" "${cfg}"
                sed -i '' 's|^onboarding_completed = .*|onboarding_completed = true|' "${cfg}"
            else
                sed -i "s|^model = .*|model = \"${m}\"|" "${cfg}"
                sed -i 's|^onboarding_completed = .*|onboarding_completed = true|' "${cfg}"
            fi
        else
            printf 'model = "%s"\nonboarding_completed = true\n' "${m}" >> "${cfg}"
        fi
    else
        cat > "${cfg}" <<EOF
# Julius Configuration
theme = "dark"
model = "${m}"
reduce_motion = false
onboarding_completed = true
EOF
    fi
}

_verify_api_key() {
    local prov="$1" key="$2"
    local status=""
    case "${prov}" in
        "NVIDIA")
            status="$(curl -s -o /dev/null -w "%{http_code}" -m 5 -H "Authorization: Bearer ${key}" https://integrate.api.nvidia.com/v1/models 2>/dev/null || echo "000")"
            ;;
        "OpenAI")
            status="$(curl -s -o /dev/null -w "%{http_code}" -m 5 -H "Authorization: Bearer ${key}" https://api.openai.com/v1/models 2>/dev/null || echo "000")"
            ;;
        "Anthropic")
            status="$(curl -s -o /dev/null -w "%{http_code}" -m 5 -H "x-api-key: ${key}" -H "anthropic-version: 2023-06-01" https://api.anthropic.com/v1/models 2>/dev/null || echo "000")"
            ;;
        "DeepSeek")
            status="$(curl -s -o /dev/null -w "%{http_code}" -m 5 -H "Authorization: Bearer ${key}" https://api.deepseek.com/models 2>/dev/null || echo "000")"
            ;;
        "Gemini")
            status="$(curl -s -o /dev/null -w "%{http_code}" -m 5 "https://generativelanguage.googleapis.com/v1beta/models?key=${key}" 2>/dev/null || echo "000")"
            ;;
        "xAI")
            status="$(curl -s -o /dev/null -w "%{http_code}" -m 5 -H "Authorization: Bearer ${key}" https://api.x.ai/v1/models 2>/dev/null || echo "000")"
            ;;
        *)
            status="200"
            ;;
    esac
}

_ask_key_input() {
    local name="$1" url="$2"
    printf '  %sEnter %s API key%s %s(%s)%s: ' \
        "${COLOR_BOLD}" "${name}" "${COLOR_RESET}" "${COLOR_DIM}" "${url}" "${COLOR_RESET}" >&2
    local inp=""
    if [ -t 0 ]; then
        read -r inp 2>/dev/null || true
    elif [ -c /dev/tty ]; then
        read -r inp < /dev/tty 2>/dev/null || true
    else
        read -r inp 2>/dev/null || true
    fi
    inp="$(echo -n "${inp}" | tr -d '\r\n' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    echo "${inp}"
}

# ─── Interactive AI Provider Setup Wizard ─────────────────────────────────────

_run_provider_wizard() {
    if [ "${SKIP_WIZARD:-0}" = "1" ] || [ "${CI:-0}" = "1" ] || [ ! -t 0 ] || [ ! -t 1 ]; then
        return 0
    fi

    printf '  %sAI Provider Setup%s\n' "${COLOR_BOLD}${COLOR_JULIUS}" "${COLOR_RESET}"
    printf '  %sSelect primary AI provider (↑/↓ to navigate, Enter to choose):%s\n\n' \
        "${COLOR_BOLD}" "${COLOR_RESET}"

    local PROVIDERS=(
        "1. NVIDIA Nemotron 550B   (Free · 1,000 credits · Recommended)"
        "2. Anthropic Claude       (claude-3-5-sonnet / haiku)"
        "3. OpenAI ChatGPT         (gpt-4o / o3-mini)"
        "4. DeepSeek               (deepseek-chat / deepseek-reasoner)"
        "5. Google Gemini          (gemini-2.0-flash / 2.5-pro)"
        "6. xAI Grok               (grok-2 / grok-3)"
        "7. Local Ollama           (private · no API key needed)"
        "8. Skip setup             (configure .env manually later)"
    )

    local SELECTED_IDX=0
    local TOTAL_PROVIDERS=${#PROVIDERS[@]}

    # Hide cursor while in menu
    printf '\033[?25l'

    while true; do
        local i=0
        for i in "${!PROVIDERS[@]}"; do
            if [ "$i" -eq "$SELECTED_IDX" ]; then
                printf "  %s❯ %s%s\033[K\n" "${COLOR_BOLD}${COLOR_JULIUS}" "${PROVIDERS[$i]}" "${COLOR_RESET}"
            else
                printf "    %s%s%s\033[K\n" "${COLOR_DIM}" "${PROVIDERS[$i]}" "${COLOR_RESET}"
            fi
        done

        local KEY_PRESS=""
        local ESC_REST=""
        IFS= read -rsn1 KEY_PRESS 2>/dev/null || true
        if [ "${KEY_PRESS:-}" = $'\x1b' ]; then
            # Integer timeout for compatibility across macOS and Linux bash
            read -rsn2 -t 1 ESC_REST 2>/dev/null || true
            KEY_PRESS="${KEY_PRESS:-}${ESC_REST:-}"
        fi

        case "${KEY_PRESS:-}" in
            $'\x1b[A'|$'\x1bOA'|k|K) # Arrow Up or k
                SELECTED_IDX=$(( (SELECTED_IDX - 1 + TOTAL_PROVIDERS) % TOTAL_PROVIDERS ))
                ;;
            $'\x1b[B'|$'\x1bOB'|j|J) # Arrow Down or j
                SELECTED_IDX=$(( (SELECTED_IDX + 1) % TOTAL_PROVIDERS ))
                ;;
            ""|$'\r'|$'\n') # Enter key
                break
                ;;
            [1-8]) # Number shortcut
                SELECTED_IDX=$((KEY_PRESS - 1))
                break
                ;;
            q|Q)
                SELECTED_IDX=7
                break
                ;;
        esac

        # Move terminal cursor back up
        printf "\033[%dA" "${TOTAL_PROVIDERS}"
    done

    # Restore cursor
    printf '\033[?25h\n'

    local _key=""
    case "${SELECTED_IDX}" in
        0) # NVIDIA
            if ! _has_real_key "NVIDIA_API_KEY"; then
                _key="$(_ask_key_input "NVIDIA Build NIM" "https://build.nvidia.com/explore/discover")"
                if [ -n "${_key}" ]; then
                    _set_env_key "NVIDIA_API_KEY" "${_key}"
                    _set_env_key "NVIDIA_NIM_API_KEY" "${_key}"
                    _set_env_key "JULIUS_DEFAULT_MODEL" "nvidia"
                    _sync_config_toml_model "nvidia/nemotron-3-ultra-550b-a55b"
                    _verify_api_key "NVIDIA" "${_key}"
                fi
            else
                _sync_config_toml_model "nvidia/nemotron-3-ultra-550b-a55b"
            fi
            ;;
        1) # Anthropic
            if ! _has_real_key "ANTHROPIC_API_KEY"; then
                _key="$(_ask_key_input "Anthropic Claude" "https://console.anthropic.com/keys")"
                if [ -n "${_key}" ]; then
                    _set_env_key "ANTHROPIC_API_KEY" "${_key}"
                    _set_env_key "JULIUS_DEFAULT_MODEL" "anthropic"
                    _sync_config_toml_model "claude-3-5-sonnet-20241022"
                    _verify_api_key "Anthropic" "${_key}"
                fi
            else
                _sync_config_toml_model "claude-3-5-sonnet-20241022"
            fi
            ;;
        2) # OpenAI
            if ! _has_real_key "OPENAI_API_KEY"; then
                _key="$(_ask_key_input "OpenAI" "https://platform.openai.com/api-keys")"
                if [ -n "${_key}" ]; then
                    _set_env_key "OPENAI_API_KEY" "${_key}"
                    _set_env_key "JULIUS_DEFAULT_MODEL" "openai"
                    _sync_config_toml_model "gpt-4o"
                    _verify_api_key "OpenAI" "${_key}"
                fi
            else
                _sync_config_toml_model "gpt-4o"
            fi
            ;;
        3) # DeepSeek
            if ! _has_real_key "DEEPSEEK_API_KEY"; then
                _key="$(_ask_key_input "DeepSeek" "https://platform.deepseek.com/api_keys")"
                if [ -n "${_key}" ]; then
                    _set_env_key "DEEPSEEK_API_KEY" "${_key}"
                    _set_env_key "JULIUS_DEFAULT_MODEL" "deepseek"
                    _sync_config_toml_model "deepseek-chat"
                    _verify_api_key "DeepSeek" "${_key}"
                fi
            else
                _sync_config_toml_model "deepseek-chat"
            fi
            ;;
        4) # Gemini
            if ! _has_real_key "GEMINI_API_KEY"; then
                _key="$(_ask_key_input "Google AI Studio" "https://aistudio.google.com/app/apikey")"
                if [ -n "${_key}" ]; then
                    _set_env_key "GEMINI_API_KEY" "${_key}"
                    _set_env_key "JULIUS_DEFAULT_MODEL" "gemini"
                    _sync_config_toml_model "gemini-2.0-flash"
                    _verify_api_key "Gemini" "${_key}"
                fi
            else
                _sync_config_toml_model "gemini-2.0-flash"
            fi
            ;;
        5) # xAI
            if ! _has_real_key "XAI_API_KEY" && ! _has_real_key "GROK_API_KEY"; then
                _key="$(_ask_key_input "xAI Grok" "https://console.x.ai/")"
                if [ -n "${_key}" ]; then
                    _set_env_key "XAI_API_KEY" "${_key}"
                    _set_env_key "GROK_API_KEY" "${_key}"
                    _set_env_key "JULIUS_DEFAULT_MODEL" "grok"
                    _sync_config_toml_model "grok-2"
                    _verify_api_key "xAI" "${_key}"
                fi
            else
                _sync_config_toml_model "grok-2"
            fi
            ;;
        6) # Ollama
            _set_env_key "JULIUS_DEFAULT_MODEL" "ollama"
            _sync_config_toml_model "ollama"
            ;;
        7) # Skip
            ;;
    esac
}

# Run provider selection wizard
_run_provider_wizard

# ─── Unified Progress Bar Engine ─────────────────────────────────────────────

VENV_DIR="${SCRIPT_DIR}/.venv"
VENV_PY="${VENV_DIR}/bin/python"
REQ_FILE="${SCRIPT_DIR}/requirements.txt"
REQ_AGENT_FILE="${SCRIPT_DIR}/requirements-agent.txt"
INSTALL_LOG="${SCRIPT_DIR}/.install.log"

: > "${INSTALL_LOG}"

SKIPPED_ITEMS=()
ERROR_ITEMS=()

SPINNERS=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
BAR_FILLED="████████████████████████████████████████"
BAR_EMPTY="░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░"
BAR_WIDTH=28
CURRENT_PCT=0
SPIN_CNT=0

render_progress_bar() {
    local pct="$1"
    local desc="$2"
    local spin_idx="${3:-0}"

    if [ "$pct" -gt 100 ]; then pct=100; fi
    if [ "$pct" -lt 0 ]; then pct=0; fi

    local filled=$(( (pct * BAR_WIDTH) / 100 ))
    local empty=$(( BAR_WIDTH - filled ))
    local spin="${SPINNERS[$(( spin_idx % ${#SPINNERS[@]} ))]}"
    local f_str="${BAR_FILLED:0:filled}"
    local e_str="${BAR_EMPTY:0:empty}"

    if [ -t 1 ]; then
        printf "\r  %s%s%s [%s%s%s%s%s] %s%3d%%%s  %-42s\033[K" \
            "${COLOR_JULIUS}" "${spin}" "${COLOR_RESET}" \
            "${COLOR_JULIUS}" "${f_str}" "${COLOR_DIM}" "${e_str}" "${COLOR_RESET}" \
            "${COLOR_JULIUS}" "${pct}" "${COLOR_RESET}" \
            "${desc}"
    fi
}

run_step() {
    local start_pct="$1"
    local end_pct="$2"
    local desc="$3"
    local timeout_sec="$4"
    shift 4

    local cur_pct=$start_pct
    local start_time
    start_time="$(date +%s 2>/dev/null || echo 0)"
    local timed_out=0

    # Launch background subshell redirecting all output to log file
    ( "$@" ) >> "${INSTALL_LOG}" 2>&1 &
    local cmd_pid=$!

    while kill -0 "$cmd_pid" 2>/dev/null; do
        local now
        now="$(date +%s 2>/dev/null || echo 0)"
        local elapsed=$(( now - start_time ))
        if [ "$timeout_sec" -gt 0 ] && [ "$elapsed" -ge "$timeout_sec" ]; then
            timed_out=1
            pkill -P "$cmd_pid" 2>/dev/null || true
            kill -9 "$cmd_pid" 2>/dev/null || true
            break
        fi

        if [ "$cur_pct" -lt $(( end_pct - 1 )) ]; then
            cur_pct=$(( cur_pct + 1 ))
        fi
        SPIN_CNT=$(( SPIN_CNT + 1 ))
        render_progress_bar "$cur_pct" "$desc" "$SPIN_CNT"
        sleep 0.06
    done

    wait "$cmd_pid" 2>/dev/null || true
    local rc=$?

    if [ "$timed_out" -eq 1 ]; then
        SKIPPED_ITEMS+=("${desc} (stuck/timed out after ${timeout_sec}s)")
    elif [ "$rc" -ne 0 ]; then
        SKIPPED_ITEMS+=("${desc} (failed with status ${rc} — skipped)")
    fi

    # Smoothly fill to end_pct
    while [ "$cur_pct" -lt "$end_pct" ]; do
        cur_pct=$(( cur_pct + 1 ))
        SPIN_CNT=$(( SPIN_CNT + 1 ))
        render_progress_bar "$cur_pct" "$desc" "$SPIN_CNT"
        sleep 0.01
    done

    CURRENT_PCT=$end_pct
    return 0
}

# ─── Individual Step Implementations ──────────────────────────────────────────

_step_venv() {
    if [ ! -x "${VENV_PY}" ] || ! "${VENV_PY}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    fi
    for f in "${VENV_DIR}/bin"/*; do
        if [ -f "$f" ] && [ ! -L "$f" ]; then
            sed -i '' "s#/Users/[^/]*/Desktop/Julius#${SCRIPT_DIR}#g" "$f" 2>/dev/null || \
            sed -i "s#/Users/[^/]*/Desktop/Julius#${SCRIPT_DIR}#g" "$f" 2>/dev/null || true
        fi
    done
    "${VENV_PY}" -m pip --version >/dev/null 2>&1 || "${VENV_PY}" -m ensurepip --upgrade 2>/dev/null || true
}

_step_requirements() {
    if "${VENV_PY}" -c "import aiohttp, playwright, textual, rich, src.agent_config, src.web_agent" 2>/dev/null; then
        return 0
    fi
    if [ -f "${REQ_FILE}" ]; then
        "${VENV_PY}" -m pip install -q -r "${REQ_FILE}"
    fi
}

_step_agent_requirements() {
    if [ -f "${REQ_AGENT_FILE}" ]; then
        "${VENV_PY}" -m pip install -q -r "${REQ_AGENT_FILE}"
    fi
}

_step_playwright() {
    if [ "${SKIP_BROWSER:-0}" = "1" ]; then
        return 0
    fi
    if "${VENV_PY}" -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); b.close(); p.stop()" 2>/dev/null; then
        return 0
    fi
    "${VENV_PY}" -m playwright install chromium
}

_step_tui() {
    if command -v npm >/dev/null 2>&1 && [ -d "${SCRIPT_DIR}/src/tui_ts" ]; then
        cd "${SCRIPT_DIR}/src/tui_ts"
        if [ ! -d "node_modules" ]; then
            npm install --silent
        fi
        npm run build --silent
    fi
}

_step_symlinks_fonts() {
    if [ -f "${SCRIPT_DIR}/julius" ]; then
        chmod +x "${SCRIPT_DIR}/julius"
    fi
    local linked=0
    for target_dir in "/opt/homebrew/bin" "${HOME}/.local/bin" "/usr/local/bin"; do
        if [ ! -d "${target_dir}" ]; then
            mkdir -p "${target_dir}" 2>/dev/null || true
        fi
        if [ -d "${target_dir}" ] && [ -w "${target_dir}" ]; then
            ln -sf "${SCRIPT_DIR}/julius" "${target_dir}/julius" 2>/dev/null && \
            ln -sf "${SCRIPT_DIR}/julius" "${target_dir}/Julius" 2>/dev/null && {
                linked=1
                break
            }
        fi
    done
    if [ "${linked}" -eq 0 ]; then
        mkdir -p "${HOME}/.local/bin" 2>/dev/null || true
        ln -sf "${SCRIPT_DIR}/julius" "${HOME}/.local/bin/julius" 2>/dev/null || true
        ln -sf "${SCRIPT_DIR}/julius" "${HOME}/.local/bin/Julius" 2>/dev/null || true
    fi

    if [ "${OS_FAMILY}" = "macos" ]; then
        local font_dir="${HOME}/Library/Fonts"
        mkdir -p "${font_dir}" 2>/dev/null || true
        if [ -d "${SCRIPT_DIR}/Julius_Fonts" ]; then
            cp -f "${SCRIPT_DIR}/Julius_Fonts"/Julius-*.ttf "${font_dir}/" 2>/dev/null || true
            cp -f "${SCRIPT_DIR}/Julius_Fonts"/Julius-*.otf "${font_dir}/" 2>/dev/null || true
        fi
        if [ -d "${SCRIPT_DIR}/Julius_Fonts/code" ]; then
            cp -f "${SCRIPT_DIR}/Julius_Fonts/code"/JetBrainsMono-*.ttf "${font_dir}/" 2>/dev/null || true
        fi
    elif [ "${OS_FAMILY}" = "linux" ] || [ "${OS_FAMILY}" = "wsl" ]; then
        local font_dir="${HOME}/.local/share/fonts"
        mkdir -p "${font_dir}" 2>/dev/null || true
        if [ -d "${SCRIPT_DIR}/Julius_Fonts" ]; then
            cp -f "${SCRIPT_DIR}/Julius_Fonts"/Julius-*.ttf "${font_dir}/" 2>/dev/null || true
            cp -f "${SCRIPT_DIR}/Julius_Fonts"/Julius-*.otf "${font_dir}/" 2>/dev/null || true
        fi
        if [ -d "${SCRIPT_DIR}/Julius_Fonts/code" ]; then
            cp -f "${SCRIPT_DIR}/Julius_Fonts/code"/JetBrainsMono-*.ttf "${font_dir}/" 2>/dev/null || true
        fi
        if command -v fc-cache >/dev/null 2>&1; then
            fc-cache -f "${font_dir}" 2>/dev/null || true
        fi
    fi
}

_step_verify() {
    if [ "${SKIP_VERIFY:-0}" = "1" ]; then
        return 0
    fi
    "${VENV_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
from src.agent_config import AgentConfig
from src.web_agent import WebAgent
from src.llm_web_client import WebLLMClient
from playwright.sync_api import sync_playwright
from aiohttp import web
app = web.Application()
"
}

# ─── Execute Progress Bar Pipeline ───────────────────────────────────────────

run_step 0  15 "Setting up virtual environment..."       30 _step_venv
run_step 15 45 "Installing Python dependencies..."        180 _step_requirements
run_step 45 60 "Installing agent dependencies..."         90  _step_agent_requirements
run_step 60 75 "Provisioning Chromium browser..."         120 _step_playwright
run_step 75 85 "Building TypeScript React TUI..."         60  _step_tui
run_step 85 92 "Configuring CLI commands & fonts..."      15  _step_symlinks_fonts
run_step 92 100 "Verifying installation..."               20  _step_verify

# Complete progress bar display
render_progress_bar 100 "Installation complete" "$SPIN_CNT"
if [ -t 1 ]; then
    printf '\n'
fi

# ─── At last: report ONLY if skipped or error ─────────────────────────────────

if [ "${#SKIPPED_ITEMS[@]}" -gt 0 ]; then
    printf '\n%s  ⚠ Skipped / Incomplete:%s\n' "${COLOR_YELLOW}" "${COLOR_RESET}"
    for item in "${SKIPPED_ITEMS[@]}"; do
        printf '    • %s\n' "${item}"
    done
fi

if [ "${#ERROR_ITEMS[@]}" -gt 0 ]; then
    printf '\n%s  ✗ Errors encountered:%s\n' "${COLOR_RED}" "${COLOR_RESET}"
    for item in "${ERROR_ITEMS[@]}"; do
        printf '    • %s\n' "${item}"
    done
    printf '    %s(See %s for installation logs)%s\n' "${COLOR_DIM}" "${INSTALL_LOG}" "${COLOR_RESET}"
fi

# Clean exit — not even success message when everything succeeds
exit 0
