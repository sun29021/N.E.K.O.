<#
.SYNOPSIS
  One-click start: launches Ollama in a hidden window (if it is not already running), waits for it,
  then opens the N.E.K.O. HUD. Used by the "N.E.K.O." Desktop shortcut.
  To stop everything: tray icon -> Quit, then run scripts\stop-neko.ps1 (or reboot).
#>
param([switch]$Background)   # -Background: start hidden (used at Windows sign-in); she appears on "Neko"
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$listening = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "start-ollama.ps1"))
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        try { Invoke-RestMethod http://127.0.0.1:11434/api/version -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 1 }
    }
}
$uiArgs = @("-m", "neko", "ui") + $(if ($Background) { @("--background") } else { @() })
Start-Process -FilePath (Join-Path $Root ".venv\Scripts\pythonw.exe") -ArgumentList $uiArgs -WorkingDirectory $Root
