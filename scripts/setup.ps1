<#
.SYNOPSIS
  Prepares N.E.K.O. on this computer. Safe to run more than once.

.DESCRIPTION
  By default this is a DRY RUN: it only checks your computer and prints what it
  WOULD do. Nothing changes until you add -Apply.

  With -Apply it will:
    1. create a private Python environment in <project>\.venv
    2. install N.E.K.O. and the pinned desktop UI package (PySide6) into it
    3. optionally install voice packages (-WithVoice) and wake word (-WithWakeWord)
    4. create %LOCALAPPDATA%\NEKO\config.toml from the template if it does not exist

  It NEVER: downloads AI models, installs drivers, changes Windows settings,
  edits PATH or the registry, registers services or startup entries, or touches
  D:\Ollama.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Apply
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Apply -WithVoice
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$WithVoice,
    [switch]$WithWakeWord,
    [string]$Python = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$DataDir = Join-Path $env:LOCALAPPDATA "NEKO"
$UserConfig = Join-Path $DataDir "config.toml"

function Say($msg, $color = "Gray") { Write-Host $msg -ForegroundColor $color }
function Plan($msg) { Say "  [plan] $msg" "Cyan" }
function Ok($msg) { Say "  [ ok ] $msg" "Green" }
function Warn($msg) { Say "  [warn] $msg" "Yellow" }
function Fail($msg) { Say "  [FAIL] $msg" "Red"; exit 1 }

Say "N.E.K.O. setup  ($(if ($Apply) { 'APPLY mode - changes will be made' } else { 'DRY RUN - nothing will change' }))" "White"
Say "Project folder: $Root"

# ---------------------------------------------------------------- 1. Windows
$os = Get-CimInstance Win32_OperatingSystem
if ([int]$os.BuildNumber -lt 19041) { Fail "Windows 10 2004 (build 19041) or newer is required; found $($os.Caption) build $($os.BuildNumber)" }
Ok "$($os.Caption) build $($os.BuildNumber)"

# ---------------------------------------------------------------- 2. Python 3.11-3.13
function Get-PyVersion($exe) {
    try { $v = & $exe -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null; return $v.Trim() } catch { return $null }
}
$candidates = @()
if ($Python) { $candidates += $Python }
# -Filter only understands * and ?, so match broadly here and let the version check below decide.
$uvPy = Get-ChildItem "$env:APPDATA\uv\python" -Directory -Filter "cpython-3.1*" -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName "python.exe" }
$candidates += $uvPy
foreach ($v in "3.12", "3.11", "3.13") {
    try { $p = & py "-$v" -c "import sys;print(sys.executable)" 2>$null; if ($p) { $candidates += $p.Trim() } } catch {}
}
$PyExe = $null
foreach ($c in $candidates) {
    if (-not $c -or -not (Test-Path $c)) { continue }
    $ver = Get-PyVersion $c
    if ($ver -in @("3.11", "3.12", "3.13")) { $PyExe = $c; break }
}
if (-not $PyExe) {
    Warn "No Python 3.11-3.13 found. (Python 3.14 works for the core but some voice packages may not have 3.14 wheels yet.)"
    Say  "      Install Python 3.12 from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH'),"
    Say  "      then run this script again. Or pass -Python C:\path\to\python.exe"
    exit 1
}
Ok "Python $(Get-PyVersion $PyExe) at $PyExe"

# ---------------------------------------------------------------- 3. disk space
$drive = (Get-Item $Root).PSDrive.Name
$free = [math]::Round((Get-PSDrive $drive).Free / 1GB, 1)
$need = 1.5; if ($WithVoice) { $need += 1.0 }
if ($free -lt $need + 5) { Fail "Only $free GB free on ${drive}: - need about $need GB plus a 5 GB safety margin" }
Ok "$free GB free on ${drive}: (packages need about $need GB)"

# ---------------------------------------------------------------- 4. existing models are left alone
if (Test-Path "D:\Ollama\models") { Ok "Existing Ollama models in D:\Ollama\models will not be touched" }

# ---------------------------------------------------------------- 5. plan
$extras = @("ui")
if ($WithVoice) { $extras += "voice" }
if ($WithWakeWord) { $extras += "wakeword" }
$spec = ".[" + ($extras -join ",") + "]"
Say ""
Say "What this script will do:" "White"
if (Test-Path (Join-Path $Venv "Scripts\python.exe")) { Ok ".venv already exists - it will be reused" } else { Plan "create virtual environment $Venv" }
Plan "pip install -e `"$spec`"   (versions pinned in pyproject.toml)"
if (Test-Path $UserConfig) { Ok "config exists at $UserConfig - it will NOT be overwritten" } else { Plan "create $UserConfig from config\user.example.toml" }
if ($WithVoice) { Warn "Voice packages are installed, but speech MODELS are not downloaded. See docs\MODEL_GUIDE.md." }

if (-not $Apply) {
    Say ""
    Say "Dry run finished. Re-run with -Apply to make these changes." "White"
    exit 0
}

# ---------------------------------------------------------------- 6. apply
Say ""
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    & $PyExe -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Fail "could not create the virtual environment" }
    Ok "created $Venv"
}
$VPy = Join-Path $Venv "Scripts\python.exe"
& $VPy -m pip install --upgrade "pip>=24" | Out-Host
Push-Location $Root
try {
    & $VPy -m pip install -e $spec | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "package installation failed - see the messages above and docs\TROUBLESHOOTING.md" }
} finally { Pop-Location }
Ok "installed N.E.K.O. with extras: $($extras -join ', ')"

if (-not (Test-Path $UserConfig)) {
    New-Item -ItemType Directory -Force $DataDir | Out-Null
    Copy-Item (Join-Path $Root "config\user.example.toml") $UserConfig
    Ok "created $UserConfig"
}

& $VPy -m neko config-check
Say ""
Say "Setup complete. Next steps:" "White"
Say "  1. Start the model server:   powershell -File scripts\start-ollama.ps1"
Say "  2. Check everything:         powershell -File scripts\doctor.ps1"
Say "  3. Launch N.E.K.O.:          powershell -File scripts\launch.ps1"
