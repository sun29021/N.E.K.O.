<#
.SYNOPSIS
  Turn "start N.E.K.O. with Windows" on or off (a shortcut in YOUR Startup folder - no admin, no service,
  no registry). With it on, Neko starts hidden at sign-in, keeps listening, and appears when you say "Neko".

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\autostart.ps1 -Enable
  powershell -ExecutionPolicy Bypass -File scripts\autostart.ps1 -Disable
#>
[CmdletBinding()]
param([switch]$Enable, [switch]$Disable, [string]$Name = "N.E.K.O.")
$ErrorActionPreference = "Stop"
$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "$Name.lnk"
if ($Disable) {
    if (Test-Path $lnk) { Remove-Item $lnk }
    Write-Host "Autostart off ($lnk removed)."
    exit 0
}
if (-not $Enable) { Write-Host "Autostart is $(if (Test-Path $lnk) { 'ON' } else { 'OFF' }) ($lnk)"; exit 0 }
$root = Split-Path -Parent $PSScriptRoot
$ws = New-Object -ComObject WScript.Shell
$l = $ws.CreateShortcut($lnk)
$l.TargetPath = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
$l.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$root\scripts\start-neko.ps1`" -Background"
$l.WorkingDirectory = $root
$l.WindowStyle = 7
$l.IconLocation = "$root\packaging\neko.ico,0"
$l.Description = "Start Neko hidden at sign-in (she appears when you say her name)"
$l.Save()
Write-Host "Autostart on: $lnk"
