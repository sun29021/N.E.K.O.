<#
.SYNOPSIS
  Backs up N.E.K.O.'s database and config to a folder of your choice (default: %LOCALAPPDATA%\NEKO\backups).
  The database copy is made with SQLite's online backup API and verified (integrity check + SHA-256).
  Model files are NOT copied (they are large and can be re-acquired; see docs\BACKUP_AND_RECOVERY.md).
#>
param([string]$Destination = "")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VPy = Join-Path $Root ".venv\Scripts\python.exe"
$Data = Join-Path $env:LOCALAPPDATA "NEKO"
if (-not (Test-Path $VPy)) { Write-Host "Run scripts\setup.ps1 -Apply first." -ForegroundColor Red; exit 1 }

& $VPy -m neko backup
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$latest = Get-ChildItem (Join-Path $Data "backups") -Filter "neko-*.db" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (Test-Path (Join-Path $Data "config.toml")) {
    Copy-Item (Join-Path $Data "config.toml") (Join-Path $Data "backups\config-$($latest.BaseName).toml")
}
if ($Destination) {
    New-Item -ItemType Directory -Force $Destination | Out-Null
    Copy-Item $latest.FullName, "$($latest.FullName).sha256" -Destination $Destination
    Copy-Item (Join-Path $Data "backups\config-$($latest.BaseName).toml") -Destination $Destination -ErrorAction SilentlyContinue
    Write-Host "Copied to $Destination" -ForegroundColor Green
}
Write-Host "Reminder: backups contain your memories and conversations. Keep them private." -ForegroundColor Yellow
