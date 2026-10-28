<#
.SYNOPSIS
  Builds the installer package for another PC: D:\NEKO-Data\dist\NEKO-Setup (+ NEKO-Setup.zip).

.DESCRIPTION
  The package holds Neko's code, tests, docs and the installer - no personal data, no keys, no .venv,
  no models (the installer downloads those on the new PC). Copy the zip to the other PC (USB / OneDrive),
  unzip it, and double-click INSTALL.cmd (or run install.ps1).
#>
[CmdletBinding()]
param([string]$OutDir = "D:\NEKO-Data\dist")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Setup = Join-Path $OutDir "NEKO-Setup"
if (Test-Path $Setup) { Remove-Item -Recurse -Force $Setup }
New-Item -ItemType Directory -Force "$Setup\neko" | Out-Null
foreach ($item in @("src", "tests", "scripts", "docs", "packaging", "pyproject.toml", "README.md", "AGENTS.md", "CHANGELOG.md")) {
    $from = Join-Path $Root $item
    if (Test-Path $from -PathType Container) {
        robocopy $from "$Setup\neko\$item" /E /NFL /NDL /NJH /NJS /NP /XD __pycache__ .pytest_cache /XF *.pyc neko-paths.json | Out-Null
    } elseif (Test-Path $from) { Copy-Item $from "$Setup\neko\$item" }
}
Copy-Item "$Root\scripts\install\install.ps1" "$Setup\install.ps1"
$cmd = "@echo off`r`necho Installing N.E.K.O. - keep this window open.`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"%~dp0install.ps1`"`r`npause`r`n"
[IO.File]::WriteAllText("$Setup\INSTALL.cmd", $cmd, (New-Object Text.ASCIIEncoding))
$readme = @"
N.E.K.O. setup package (built $(Get-Date -Format "yyyy-MM-dd HH:mm") from version $((Select-String "$Root\src\neko\__init__.py" -Pattern '__version__').Line.Split('"')[1]))

1. Unzip this folder anywhere on the new PC.
2. Double-click INSTALL.cmd   (or in a terminal:  powershell -ExecutionPolicy Bypass -File .\install.ps1 )
3. Answer the questions (your name, the assistant's name, female or male voice, Bangla).

It checks the PC first, asks before installing, and never installs drivers silently.
Check only:  powershell -ExecutionPolicy Bypass -File .\install.ps1 -CheckOnly
Details: neko\docs\INSTALL_OFFICE.md
"@
[IO.File]::WriteAllText("$Setup\README.txt", $readme, (New-Object Text.UTF8Encoding $false))
# safety: the package must not contain personal data or keys
$bad = Get-ChildItem -Recurse $Setup -File | Where-Object { $_.Name -match '^(secrets\.toml|config\.toml|neko\.db.*|.*\.lnk)$' }
if ($bad) { throw "personal files found in the package: $($bad.FullName -join ', ')" }
$hits = Get-ChildItem -Recurse $Setup -File -Include *.py, *.toml, *.ps1, *.md, *.txt |
    Select-String -Pattern 'gsk_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{30,}|AQ\.[A-Za-z0-9_\-]{30,}' |
    Where-Object { $_.Line -notmatch 'abcdefghijklmnop' }   # the redaction test's obvious fake key
if ($hits) { throw "something that looks like an API key is in the package: $($hits.Path -join ', ')" }
$zip = Join-Path $OutDir "NEKO-Setup.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $Setup -DestinationPath $zip
"{0}  ({1:N1} MB)" -f $zip, ((Get-Item $zip).Length / 1MB)
