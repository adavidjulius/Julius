<#
.SYNOPSIS
    Julius CLI PowerShell Runner

.DESCRIPTION
    Launches Julius CLI/TUI on native Windows using the virtual environment.
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$VenvPy = Join-Path $ScriptDir ".venv\Scripts\python.exe"

if (Test-Path $VenvPy) {
    $PythonBin = $VenvPy
} elseif ($env:VIRTUAL_ENV -and (Test-Path "$env:VIRTUAL_ENV\Scripts\python.exe")) {
    $PythonBin = "$env:VIRTUAL_ENV\Scripts\python.exe"
} else {
    $PythonBin = "python.exe"
}

$RunScript = Join-Path $ScriptDir "run_agent.py"
& $PythonBin $RunScript @args
exit $LASTEXITCODE
