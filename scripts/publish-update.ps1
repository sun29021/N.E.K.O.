<#
.SYNOPSIS
  Publish the laptop's current N.E.K.O. as an update for your other PCs (push to your private GitHub repo).

.DESCRIPTION
  Runs the full self-test first and refuses to publish if it fails, if personal files are tracked, or if
  anything that looks like an API key is in the code. Then commits (if there are changes) and pushes.
  The other PCs see "Update available" and install it when you click Update.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\publish-update.ps1 -Message "Better Bangla voice"
#>
[CmdletBinding()]
param([string]$Message = "")
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"
Push-Location $Root
try {
    Write-Host "Self-test..." -ForegroundColor Cyan
    & $Py -m unittest discover -s tests -t . 2>&1 | ForEach-Object { "$_" } | Select-String -Pattern "^(Ran |OK|FAILED)" | ForEach-Object { $_.Line }
    if ($LASTEXITCODE -ne 0) { Write-Host "Tests fail - not publishing." -ForegroundColor Red; exit 1 }
    git add -A
    $files = git diff --cached --name-only
    $bad = $files | Where-Object { $_ -match '(^|/)(\.venv|secrets\.toml|config\.toml|neko-paths\.json|phone\.json)|\.db$|\.lnk$' }
    if ($bad) { Write-Host "Personal files staged - not publishing: $bad" -ForegroundColor Red; git reset -q; exit 1 }
    $keys = git grep --cached -n -E 'gsk_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|AQ\.[A-Za-z0-9_-]{30,}|[0-9]{8,10}:AA[A-Za-z0-9_-]{30,}' |
        Where-Object { $_ -notmatch 'abcdefghijklmnop' }
    if ($keys) { Write-Host "Something that looks like an API key is in the code - not publishing:`n$keys" -ForegroundColor Red; git reset -q; exit 1 }
    if ($files) {
        $v = (Select-String "src\neko\__init__.py" -Pattern '__version__').Line.Split('"')[1]
        if (-not $Message) { $Message = "N.E.K.O. $v" }
        git commit -q -m $Message
    }
    git push origin main
    if ($LASTEXITCODE -ne 0) { Write-Host "Push failed (signed in to GitHub? repo connected? see docs\UPDATES.md)." -ForegroundColor Red; exit 1 }
    Write-Host "Published. Other PCs will offer the update." -ForegroundColor Green
} finally { Pop-Location }
