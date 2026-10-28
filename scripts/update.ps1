<#
.SYNOPSIS
  Update N.E.K.O. from your private GitHub repo - safely.

.DESCRIPTION
  -Check : looks for a newer version and prints what's new (nothing changes).
  -Apply : 1. verified database backup   2. downloads the new code (git, fast-forward only)
           3. installs packages if the requirements changed   4. runs the self-test
           If any step fails, it goes back to the version you had. Your profile, memory and keys
           (%LOCALAPPDATA%\NEKO) are never touched. Restart Neko afterwards (the app does it for you).
  Exit codes: 0 = done / up to date, 10 = update available (-Check), 1 = failed (rolled back).
#>
[CmdletBinding()]
param([switch]$Check, [switch]$Apply)
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"
function Say($t, $c = "Gray") { Write-Host $t -ForegroundColor $c }
if (-not (Test-Path (Join-Path $Root ".git"))) { Say "This copy of Neko isn't connected to the update repo yet (see docs\UPDATES.md)." Yellow; exit 1 }
$git = (Get-Command git -ErrorAction SilentlyContinue).Source
if (-not $git) { Say "Git isn't installed (winget install Git.Git)." Yellow; exit 1 }

& $git -C $Root fetch --quiet origin main 2>$null
if ($LASTEXITCODE -ne 0) { Say "Couldn't reach the update repo (offline, or not signed in to GitHub)." Yellow; exit 1 }
$behind = [int](& $git -C $Root rev-list --count HEAD..origin/main)
$current = (Select-String (Join-Path $Root "src\neko\__init__.py") -Pattern '__version__').Line.Split('"')[1]
$remoteInit = & $git -C $Root show origin/main:src/neko/__init__.py 2>$null
$latest = (($remoteInit | Select-String '__version__').Line -split '"')[1]
if ($behind -eq 0) { Say "Neko $current is up to date." Green; exit 0 }
Say "Update available: $current -> $latest ($behind change(s)):" Cyan
& $git -C $Root log --format="  - %s" HEAD..origin/main | Select-Object -First 15
if (-not $Apply) { exit 10 }

$before = (& $git -C $Root rev-parse HEAD).Trim()
$dirty = & $git -C $Root status --porcelain --untracked-files=no
if ($dirty) { Say "This copy has local code changes - not updating automatically:" Yellow; $dirty; exit 1 }
Say "1/4 backup" Cyan
& $Py -m neko backup
if ($LASTEXITCODE -ne 0) { Say "Backup failed - update cancelled (nothing changed)." Red; exit 1 }
Say "2/4 new code" Cyan
$reqBefore = & $git -C $Root rev-parse HEAD:scripts/install/requirements.txt 2>$null
& $git -C $Root merge --ff-only --quiet origin/main
if ($LASTEXITCODE -ne 0) { Say "Couldn't apply the new code - nothing changed." Red; exit 1 }
function Rollback($why) {
    Say "$why - going back to the previous version." Red
    & $git -C $Root reset --hard --quiet $before
    exit 1
}
Say "3/4 packages" Cyan
$reqAfter = & $git -C $Root rev-parse HEAD:scripts/install/requirements.txt 2>$null
$uv = @((Get-Command uv -ErrorAction SilentlyContinue).Source, (Join-Path (Split-Path -Parent $Root) "tools\uv\uv.exe")) |
    Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if ($reqAfter -ne $reqBefore) {
    if ($uv) { & $uv pip install --python $Py -r (Join-Path $Root "scripts\install\requirements.txt") }
    else { & $Py -m pip install -q -r (Join-Path $Root "scripts\install\requirements.txt") }
    if ($LASTEXITCODE -ne 0) { Rollback "Installing packages failed" }
}
if ($uv) { & $uv pip install --python $Py -e $Root | Out-Null } else { & $Py -m pip install -q -e $Root | Out-Null }
Say "4/4 self-test" Cyan
Push-Location $Root
$out = & $Py -m unittest discover -s tests -t . 2>&1 | ForEach-Object { "$_" }
$ok = $LASTEXITCODE -eq 0
Pop-Location
$out | Select-String -Pattern "^(Ran |OK|FAILED)" | ForEach-Object { Say "    $($_.Line)" }
if (-not $ok) { Rollback "The self-test failed" }
Say "Updated to $latest. Restart Neko to use it." Green
exit 0
