# Julius Universal Web Interface Launcher
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Launching Julius Universal Web Interface..." -ForegroundColor Green
Write-Host "Interconnected: Desktop, Apple iOS, Android APK, Julius Apps" -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan

Set-Location -Path $PSScriptRoot
python server.py --open

