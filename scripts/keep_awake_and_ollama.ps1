# ==============================================================================
# Julius Local Ollama Server - Windows Keep-Awake & Auto-Start Configuration
# Run this once in PowerShell as Administrator on your Windows laptop.
# ==============================================================================

Write-Host ">>> Configuring Windows Power Settings to Prevent Deep Sleep..." -ForegroundColor Cyan

# 1. Disable Sleep / Standby when plugged in (AC Power)
powercfg /change standby-timeout-ac 0
Write-Host "  [OK] Standby timeout on AC set to NEVER (0)" -ForegroundColor Green

# 2. Disable Hibernate when plugged in (AC Power)
powercfg /change hibernate-timeout-ac 0
Write-Host "  [OK] Hibernate timeout on AC set to NEVER (0)" -ForegroundColor Green

# 3. Prevent sleep when laptop lid is closed on AC Power (0 = Do Nothing)
powercfg /setacvalueindex scheme_current sub_buttons lidaction 0
Write-Host "  [OK] Lid-close action on AC set to DO NOTHING" -ForegroundColor Green

# 4. Disable unattended sleep timeout (prevents auto-sleeping after 2 minutes)
powercfg /setacvalueindex scheme_current sub_sleep 7bc4a2f9-d8fc-4469-b07b-33eb785aaca0 0
Write-Host "  [OK] Unattended sleep timeout set to NEVER (0)" -ForegroundColor Green

# 5. Apply the power scheme immediately
powercfg /setactive scheme_current
Write-Host "  [OK] Power scheme updated and activated" -ForegroundColor Green

# 6. Prevent Network Adapters (Wi-Fi) from powering down
Get-NetAdapter | ForEach-Object {
    Disable-NetAdapterPowerManagement -Name $_.Name -ErrorAction SilentlyContinue
}
Write-Host "  [OK] Wi-Fi adapter power-saving disabled" -ForegroundColor Green

# 7. Configure Ollama Environment Variables to listen on all interfaces
[System.Environment]::SetEnvironmentVariable('OLLAMA_HOST', '0.0.0.0:11434', 'Machine')
[System.Environment]::SetEnvironmentVariable('OLLAMA_ORIGINS', '*', 'Machine')
[System.Environment]::SetEnvironmentVariable('OLLAMA_HOST', '0.0.0.0:11434', 'User')
[System.Environment]::SetEnvironmentVariable('OLLAMA_ORIGINS', '*', 'User')
Write-Host "  [OK] OLLAMA_HOST configured to 0.0.0.0:11434" -ForegroundColor Green

# 8. Ensure Firewall rule is active for port 11434
Remove-NetFirewallRule -DisplayName "Ollama API" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "Ollama API" -Direction Inbound -LocalPort 11434 -Protocol TCP -Action Allow | Out-Null
Write-Host "  [OK] Inbound Firewall Rule for port 11434 verified" -ForegroundColor Green

# 9. Verify current IP Address
$ips = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254*" }).IPAddress
Write-Host "`n>>> Current Windows Laptop IPv4 Addresses:" -ForegroundColor Yellow
foreach ($ip in $ips) {
    Write-Host "    http://$($ip):11434" -ForegroundColor Cyan
}

Write-Host "`n>>> Setup Complete! Your laptop will now stay awake 24/7 on AC power." -ForegroundColor Green
Write-Host "Ollama is ready to serve inference requests continuously." -ForegroundColor Green
