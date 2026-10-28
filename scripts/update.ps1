<#
.SYNOPSIS
  Safe update procedure. Dry run by default; -Apply to perform it.

  1. backs up the database (verified)            3. reinstalls pinned dependencies into .venv
  2. shows what changed (git log/diff if a repo) 4. runs the database migrations + config check + tests
  It never downloads code from anywhere by itself: you obtain the new version
  (git pull or a verified release zip - see docs\SHARING_AND_DISTRIBUTION.md) first.
#>
param([switch]$Apply)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VPy)) { Write-Host "Run scripts\setup.ps1 -Apply first." -ForegroundColor Red; exit 1 }
if (Test-Path (Join-Path $Root ".git")) {
    Write-Host "Local changes / recent commits:" -ForegroundColor Cyan
    git -C $Root status --short
    git -C $Root log --oneline -5
}
if (-not $Apply) { Write-Host "Dry run. Re-run with -Apply after you have the new version in place."; exit 0 }
& $VPy -m neko backup
if ($LASTEXITCODE -ne 0) { Write-Host "Backup failed - update aborted." -ForegroundColor Red; exit 1 }
Push-Location $Root
try { & $VPy -m pip install -e ".[ui]" | Out-Host } finally { Pop-Location }
& $VPy -m neko config-check
& $VPy -m unittest discover -s (Join-Path $Root "tests") -t $Root
Write-Host "Update finished. Migrations run automatically on next launch (a pre-migration backup is taken)." -ForegroundColor Green
Write-Host "Rollback: restore the backup with scripts\restore.ps1 and check out the previous version." -ForegroundColor Green
