<#
.SYNOPSIS
  Share THIS PC's AI (Ollama) with your other devices - only inside your private Tailscale network.

.DESCRIPTION
  Run on the office PC. Ollama keeps listening only on this PC (127.0.0.1); Tailscale forwards port 11434
  to it for devices signed in to YOUR Tailscale account (end-to-end encrypted). Nothing is opened to the
  internet or your office LAN, and no Windows firewall rule is changed. Your laptop's Neko then finds this
  PC automatically (models.office_url = "auto") and uses its GPU.

  Needs: Tailscale installed and signed in with the same account as the laptop (https://tailscale.com/download).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\share-gpu.ps1          # share
  powershell -ExecutionPolicy Bypass -File scripts\share-gpu.ps1 -Stop    # stop sharing
  powershell -ExecutionPolicy Bypass -File scripts\share-gpu.ps1 -Status
#>
[CmdletBinding()]
param([switch]$Stop, [switch]$Status)
$ErrorActionPreference = "Continue"
$ts = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
if (-not $ts -and (Test-Path "C:\Program Files\Tailscale\tailscale.exe")) { $ts = "C:\Program Files\Tailscale\tailscale.exe" }
if (-not $ts) {
    Write-Host "Tailscale isn't installed. Get it from https://tailscale.com/download, sign in with the SAME account" -ForegroundColor Yellow
    Write-Host "as your laptop, then run this again." -ForegroundColor Yellow
    exit 1
}
if ($Stop) {
    & $ts serve --tcp=11434 off
    Write-Host "Stopped sharing this PC's AI." -ForegroundColor Green
    exit 0
}
if ($Status) { & $ts serve status; exit 0 }
$self = & $ts status --json | ConvertFrom-Json
if (-not $self.Self.Online) { Write-Host "Tailscale isn't connected. Open Tailscale and sign in, then run this again." -ForegroundColor Yellow; exit 1 }
try { Invoke-RestMethod http://127.0.0.1:11434/api/version -TimeoutSec 3 | Out-Null }
catch { Write-Host "Ollama isn't running on this PC yet - start Neko (or scripts\start-ollama.ps1) first." -ForegroundColor Yellow; exit 1 }
Write-Host "This shares this PC's AI with the devices in your Tailscale network ($($self.Self.UserID) / $($self.MagicDNSSuffix))." -ForegroundColor Cyan
$a = Read-Host "Share it now? [Y/n]"
if ($a -and -not $a.Trim().ToLower().StartsWith("y")) { exit 0 }
& $ts serve --bg --tcp=11434 tcp://127.0.0.1:11434
if ($LASTEXITCODE -ne 0) {
    Write-Host "Tailscale refused. If it printed a link about enabling 'Serve', open it, allow it, and run this again." -ForegroundColor Yellow
    exit 1
}
$name = $self.Self.DNSName.Split(".")[0]
Write-Host ""
Write-Host "Shared. On the laptop, Neko finds it automatically (Settings: office_url = auto)." -ForegroundColor Green
Write-Host "Address, if you ever need it: http://$($name):11434  (only reachable inside your Tailscale network)"
