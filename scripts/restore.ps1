<#
.SYNOPSIS
  Restores the N.E.K.O. database from a backup file after verifying it.
  Close N.E.K.O. first. The current database is kept as neko.db.before-restore.
#>
param([Parameter(Mandatory = $true)][string]$BackupFile)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VPy = Join-Path $Root ".venv\Scripts\python.exe"
if (Get-Process -Name pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Root*" }) {
    Write-Host "N.E.K.O. seems to be running. Quit it from the tray icon first." -ForegroundColor Red; exit 1
}
& $VPy -m neko verify-backup $BackupFile
if ($LASTEXITCODE -ne 0) { Write-Host "Backup failed verification; nothing was changed." -ForegroundColor Red; exit 1 }
$answer = Read-Host "Replace the current database with this backup? Type YES to continue"
if ($answer -ne "YES") { Write-Host "Cancelled."; exit 0 }
& $VPy -m neko restore $BackupFile
