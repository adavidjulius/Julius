@echo off
REM Julius CLI Windows CMD Launcher
setlocal

set "SCRIPT_DIR=%~dp0"
if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    set "PYTHON_BIN=%SCRIPT_DIR%.venv\Scripts\python.exe"
) else if defined VIRTUAL_ENV (
    if exist "%VIRTUAL_ENV%\Scripts\python.exe" (
        set "PYTHON_BIN=%VIRTUAL_ENV%\Scripts\python.exe"
    ) else (
        set "PYTHON_BIN=python"
    )
) else (
    set "PYTHON_BIN=python"
)

"%PYTHON_BIN%" "%SCRIPT_DIR%run_agent.py" %*
exit /b %ERRORLEVEL%
