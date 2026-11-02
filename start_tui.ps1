<#
.SYNOPSIS
    Start Julius Next-Gen TUI on Windows

.DESCRIPTION
    Launches the minimalist Julius TUI directly in Windows Terminal or PowerShell.
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$VenvPy = Join-Path $ScriptDir ".venv\Scripts\python.exe"

if (Test-Path $VenvPy) {
    $PythonBin = $VenvPy
} else {
    $PythonBin = "python.exe"
}

$RunScript = Join-Path $ScriptDir "run_agent.py"
& $PythonBin $RunScript @args
exit $LASTEXITCODE
