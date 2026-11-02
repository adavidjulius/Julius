<#
.SYNOPSIS
    Build Windows Installer (MSI / ZIP package) for Julius

.DESCRIPTION
    Packages Julius agent and virtual environment dependencies into a distributable
    portable bundle and MSI installer definition.
#>

param(
    [string]$Version = "3.1.0",
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = (Get-Item $ScriptDir).Parent.FullName

$DistPath = Join-Path $ProjectRoot $OutputDir
if (-not (Test-Path $DistPath)) {
    New-Item -ItemType Directory -Path $DistPath | Out-Null
}

$PackageName = "Julius-$Version-win64"
$PackageDir = Join-Path $DistPath $PackageName

Write-Host "Creating portable package directory at $PackageDir..." -ForegroundColor Cyan
if (Test-Path $PackageDir) {
    Remove-Item -Recurse -Force $PackageDir
}
New-Item -ItemType Directory -Path $PackageDir | Out-Null

# Copy source and runtime files
$IncludeItems = @(
    "src",
    "run_agent.py",
    "julius.py",
    "julius.ps1",
    "julius.cmd",
    "start_tui.ps1",
    "julius_gui.py",
    "requirements.txt",
    "README.md",
    "LICENSE"
)

foreach ($item in $IncludeItems) {
    $src = Join-Path $ProjectRoot $item
    if (Test-Path $src) {
        Copy-Item -Recurse -Path $src -Destination (Join-Path $PackageDir $item)
    }
}

# Create portable zip
$ZipOutput = Join-Path $DistPath "$PackageName.zip"
Write-Host "Archiving package into $ZipOutput..." -ForegroundColor Cyan
Compress-Archive -Path "$PackageDir\*" -DestinationPath $ZipOutput -Force

Write-Host "`nPackage built successfully: $ZipOutput" -ForegroundColor Green
