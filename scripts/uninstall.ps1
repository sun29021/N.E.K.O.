<#
.SYNOPSIS
  Removes N.E.K.O.'s Python environment. Dry run by default.
  -Apply             delete <project>\.venv
  -AlsoDeleteData    ALSO delete %LOCALAPPDATA%\NEKO (memories, history, logs, backups) - asks again first
  Never touches D:\Ollama or any model files.
#>
param([switch]$Apply, [switch]$AlsoDeleteData)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Data = Join-Path $env:LOCALAPPDATA "NEKO"
Write-Host "Would remove: $Venv"
if ($AlsoDeleteData) { Write-Host "Would ALSO remove your personal data: $Data" -ForegroundColor Yellow }
Write-Host "Will NOT touch: D:\Ollama, your models, or the project source files."
if (-not $Apply) { Write-Host "Dry run. Add -Apply to proceed."; exit 0 }
if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv; Write-Host "Removed $Venv" }
if ($AlsoDeleteData -and (Test-Path $Data)) {
    $a = Read-Host "Type DELETE to permanently remove $Data (make a backup first if unsure)"
    if ($a -eq "DELETE") { Remove-Item -Recurse -Force $Data; Write-Host "Removed $Data" } else { Write-Host "Kept $Data" }
}
