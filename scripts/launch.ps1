<#
.SYNOPSIS
  Launches N.E.K.O.  Default: desktop HUD.  -Chat: terminal chat.  -SafeMode: text only, no tools.
#>
param([switch]$Chat, [switch]$SafeMode)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VPy = Join-Path $Root ".venv\Scripts\python.exe"
$VPyw = Join-Path $Root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $VPy)) { Write-Host "Run scripts\setup.ps1 -Apply first." -ForegroundColor Red; exit 1 }

$port = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue
if (-not $port) {
    Write-Host "Note: Ollama is not running. Open another PowerShell window and run scripts\start-ollama.ps1" -ForegroundColor Yellow
}
if ($SafeMode) {
    # Safe mode: no computer control, no voice, reduced motion; uses the zero-download profile.
    $safe = Join-Path $env:TEMP "neko-safe-mode.toml"
    @"
config_version = 1
[models]
profile = "existing-only"
[voice]
enabled = false
[tools]
computer_control_enabled = false
[ui]
reduced_motion = true
"@ | Set-Content -Encoding utf8 $safe
    $env:NEKO_CONFIG = $safe
    Write-Host "SAFE MODE: text only, no computer control, existing model only." -ForegroundColor Cyan
}
if ($Chat) { & $VPy -m neko chat } else { Start-Process -FilePath $VPyw -ArgumentList "-m", "neko", "ui" -WorkingDirectory $Root }
