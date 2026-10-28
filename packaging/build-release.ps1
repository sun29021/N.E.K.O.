<#
.SYNOPSIS
  Builds a clean source release zip + SHA-256. Dry run by default; -Apply writes dist\.
  Refuses to package anything that looks like personal data, secrets, models or environments.
#>
param([switch]$Apply)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$version = (Select-String -Path (Join-Path $Root "pyproject.toml") -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
$include = @("src", "tests", "docs", "scripts", "config", "packaging",
             "README.md", "AGENTS.md", "LICENSE", "CHANGELOG.md", "pyproject.toml", ".gitignore", ".env.example")
$forbidden = '\.(db|db-wal|db-shm|sqlite|gguf|onnx|safetensors|bin|wav|log|jsonl)$|(^|\\)(\.env|config\.toml|\.venv|venv|backups|logs|__pycache__)(\\|$)'

$files = foreach ($item in $include) {
    $p = Join-Path $Root $item
    if (Test-Path $p -PathType Container) { Get-ChildItem $p -Recurse -File } elseif (Test-Path $p) { Get-Item $p }
}
$files = $files | Where-Object { $_.FullName -notmatch '\\__pycache__\\' -and $_.Extension -ne '.pyc' }
$bad = $files | Where-Object { $_.FullName.Substring($Root.Length) -match $forbidden -and $_.Name -ne ".env.example" }
if ($bad) {
    Write-Host "Refusing to build - these files must not be shared:" -ForegroundColor Red
    $bad | ForEach-Object { Write-Host "  $($_.FullName)" }
    exit 1
}
Write-Host "Release neko-$version would contain $($files.Count) files:"
$files | ForEach-Object { "  " + $_.FullName.Substring($Root.Length + 1) } | Select-Object -First 200
if (-not $Apply) { Write-Host "Dry run. Add -Apply to write dist\neko-$version.zip"; exit 0 }

$dist = Join-Path $Root "dist"
New-Item -ItemType Directory -Force $dist | Out-Null
$stage = Join-Path $env:TEMP "neko-release-$version"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
foreach ($f in $files) {
    $rel = $f.FullName.Substring($Root.Length + 1)
    $dest = Join-Path $stage "neko-$version\$rel"
    New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
    Copy-Item $f.FullName $dest
}
$zip = Join-Path $dist "neko-$version.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path (Join-Path $stage "neko-$version") -DestinationPath $zip
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
"$hash  neko-$version.zip" | Set-Content -Encoding ascii "$zip.sha256"
Remove-Item -Recurse -Force $stage
Write-Host "Wrote $zip" -ForegroundColor Green
Write-Host "SHA-256: $hash"
