<#
.SYNOPSIS
  Read-only health report for N.E.K.O. Changes nothing.
#>
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$VPy = Join-Path $Root ".venv\Scripts\python.exe"

Write-Host "=== N.E.K.O. doctor (read-only) ===" -ForegroundColor White
Write-Host "Windows: $((Get-CimInstance Win32_OperatingSystem).Caption)"
$gpu = & nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,temperature.gpu --format=csv,noheader 2>$null
if ($gpu) { Write-Host "NVIDIA: $gpu" } else { Write-Host "NVIDIA: nvidia-smi not available" -ForegroundColor Yellow }
$port = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue
Write-Host ("Port 11434 (Ollama): " + $(if ($port) { "listening" } else { "nothing listening - run scripts\start-ollama.ps1" }))

if (Test-Path $VPy) {
    & $VPy -m neko doctor
} else {
    Write-Host ".venv not found - run scripts\setup.ps1 first. Falling back to system Python for core checks." -ForegroundColor Yellow
    $env:PYTHONPATH = Join-Path $Root "src"
    & python -m neko doctor
}
Write-Host ""
Write-Host "Logs: $env:LOCALAPPDATA\NEKO\logs   Data: $env:LOCALAPPDATA\NEKO"
