# Share (or stop sharing) Neko's call page inside YOUR Tailscale network only.
#   -Enable   tailscale serve --bg --https=<HttpsPort> http://127.0.0.1:<Port>   (tailnet only, never the internet)
#   -Disable  tailscale serve --https=<HttpsPort> off
#   -Status   show what Tailscale is sharing
# Run from Command Center > Phone > Turn on calls (or by hand). Other Tailscale shares are left alone.
param(
    [switch]$Enable,
    [switch]$Disable,
    [switch]$Status,
    [int]$Port = 8791,
    [int]$HttpsPort = 8443
)
$ErrorActionPreference = "Stop"
$ts = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
if (-not $ts) { $ts = "C:\Program Files\Tailscale\tailscale.exe" }
if (-not (Test-Path $ts)) { Write-Output "Tailscale is not installed on this PC."; exit 2 }
if ($Port -lt 1024 -or $Port -gt 65535 -or $HttpsPort -lt 1 -or $HttpsPort -gt 65535) { Write-Output "Bad port."; exit 2 }

if ($Enable) {
    & $ts serve --bg --yes "--https=$HttpsPort" "http://127.0.0.1:$Port"
    if ($LASTEXITCODE -ne 0) { Write-Output "Tailscale refused (is HTTPS enabled for your tailnet?)."; exit 1 }
    Write-Output "Calls shared inside your tailnet on https port $HttpsPort."
} elseif ($Disable) {
    & $ts serve "--https=$HttpsPort" off
    Write-Output "Calls are no longer shared."
} else {
    & $ts serve status
}
