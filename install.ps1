<#
.SYNOPSIS
    Julius Agent — Native Windows PowerShell Installer

.DESCRIPTION
    Sets up the local Python virtual environment, installs cross-platform
    dependencies, provisions Playwright browsers, and verifies the setup.

.PARAMETER NoVerify
    Skip post-install environment verification.

.PARAMETER NoBrowser
    Skip Playwright Chromium browser provisioning.

.PARAMETER PythonPath
    Specify custom Python executable path.

.EXAMPLE
    pwsh install.ps1
    pwsh install.ps1 -NoBrowser
    powershell -ExecutionPolicy Bypass -File install.ps1
#>

[CmdletBinding()]
param(
    [switch]$NoVerify,
    [switch]$NoBrowser,
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

function Write-Step($num, $total, $title) {
    Write-Host "`n[$num/$total] $title" -ForegroundColor Cyan
}

function Write-Ok($msg) {
    Write-Host "  [OK] $msg" -ForegroundColor Green
}

function Write-Info($msg) {
    Write-Host "  -> $msg" -ForegroundColor Gray
}

function Write-Warn($msg) {
    Write-Host "  [!] $msg" -ForegroundColor Yellow
}

function Write-Err($msg) {
    Write-Host "  [X] $msg" -ForegroundColor Red
}

function Print-Banner {
    $esc = [char]27
    $brand = "$esc[1;38;2;200;184;150m"
    $dim = "$esc[2m"
    $reset = "$esc[0m"

    Write-Host @"
$brand
  ╔═════╗ ╔╗   ╔╗ ╔╗      ╔═════╗ ╔╗   ╔╗ ╔═════╗
  ╚══╗  ║ ║║   ║║ ║║      ╚═╗ ╔═╝ ║║   ║║ ║ ╔═══╝
     ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ║ ╚═══╗
     ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ╚═══╗ ║
  ╔══╝  ║ ║╚═══╝║ ║╚════╗ ╔═╝ ╚═╗ ║╚═══╝║ ╔═══╝ ║
  ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝
$reset$brand
  Autonomous AI Copilot — Native Windows Installer
$reset
"@
}

Print-Banner

$TotalSteps = 6

# ── 1. Locate Python 3.10+ ──────────────────────────────────────────────────
Write-Step 1 $TotalSteps "Checking Python environment"

$ResolvedPython = ""

if ($PythonPath -and (Test-Path $PythonPath)) {
    $ResolvedPython = $PythonPath
} else {
    $Candidates = @(
        "py.exe -3.12",
        "py.exe -3.11",
        "py.exe -3.10",
        "python.exe",
        "python3.exe"
    )

    foreach ($cand in $Candidates) {
        try {
            $parts = $cand -split " "
            $cmd = $parts[0]
            $args = if ($parts.Length -gt 1) { $parts[1..($parts.Length-1)] } else { @() }
            $versionOutput = & $cmd @args -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($versionOutput) {
                $ver = [version]$versionOutput.Trim()
                if ($ver.Major -eq 3 -and $ver.Minor -ge 10) {
                    $ResolvedPython = $cand
                    break
                }
            }
        } catch {
            continue
        }
    }
}

if (-not $ResolvedPython) {
    Write-Err "Python 3.10 or higher not found."
    Write-Host "Please install Python from https://www.python.org/downloads/ or via winget:" -ForegroundColor Yellow
    Write-Host "  winget install Python.Python.3.12" -ForegroundColor White
    exit 1
}

Write-Ok "Found Python: $ResolvedPython"

# ── 2. Create Virtual Environment (.venv) ────────────────────────────────────
Write-Step 2 $TotalSteps "Configuring Python virtual environment (.venv)"

$VenvDir = Join-Path $ScriptDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Info "Creating virtual environment at $VenvDir..."
    $pyParts = $ResolvedPython -split " "
    $baseCmd = $pyParts[0]
    $baseArgs = if ($pyParts.Length -gt 1) { $pyParts[1..($pyParts.Length-1)] } else { @() }
    & $baseCmd @baseArgs -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to create virtual environment."
        exit 1
    }
}
Write-Ok "Virtual environment ready at $VenvDir"

# ── 3. Upgrade pip, setuptools, wheel ────────────────────────────────────────
Write-Step 3 $TotalSteps "Upgrading package manager tools"
& $VenvPython -m pip install --upgrade pip setuptools wheel --quiet
Write-Ok "pip upgraded"

# ── 4. Install Requirements ──────────────────────────────────────────────────
Write-Step 4 $TotalSteps "Installing project dependencies from requirements.txt"
$ReqFile = Join-Path $ScriptDir "requirements.txt"
if (Test-Path $ReqFile) {
    & $VenvPython -m pip install -r $ReqFile
    if ($LASTEXITCODE -ne 0) {
        Write-Err "pip install failed."
        exit 1
    }
    Write-Ok "Dependencies installed successfully"
} else {
    Write-Warn "requirements.txt not found, skipping."
}

# ── 5. Playwright Browser Provisioning ───────────────────────────────────────
Write-Step 5 $TotalSteps "Setting up Playwright browser engine"
if ($NoBrowser -or $env:JULIUS_SKIP_BROWSER -eq "1") {
    Write-Info "Skipping browser download (--NoBrowser specified)."
} else {
    Write-Info "Installing Chromium browser for web interactions..."
    & $VenvPython -m playwright install chromium
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Playwright browser installation exited with code $LASTEXITCODE."
    } else {
        Write-Ok "Chromium browser engine ready"
    }
}

# ── 6. Environment & Configuration Check ─────────────────────────────────────
Write-Step 6 $TotalSteps "Verifying installation"
$EnvFile = Join-Path $ScriptDir ".env"
$EnvExample = Join-Path $ScriptDir ".env.example"

if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
    Copy-Item $EnvExample $EnvFile
    Write-Ok "Created .env configuration from .env.example"
}

if (-not $NoVerify -and ($env:JULIUS_SKIP_VERIFY -ne "1")) {
    & $VenvPython -c "from src.platform_compat import get_platform_name; from src.web_agent import WebAgent; print('Platform:', get_platform_name())"
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Core imports verified successfully"
    } else {
        Write-Warn "Core verification test failed."
    }
}

Write-Host "`nInstallation Complete!" -ForegroundColor Green
Write-Host "----------------------------------------------------" -ForegroundColor Gray
Write-Host "Launch Julius CLI / TUI:     .\julius.ps1" -ForegroundColor White
Write-Host "Launch Julius GUI:           .\.venv\Scripts\python.exe julius_gui.py" -ForegroundColor White
Write-Host "----------------------------------------------------`n" -ForegroundColor Gray
