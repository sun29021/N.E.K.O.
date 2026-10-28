<#
.SYNOPSIS
  N.E.K.O. one-command installer for a new Windows PC (e.g. the office desktop).

.DESCRIPTION
  Run from the unpacked NEKO-Setup folder:
      powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
  It will:
    1. CHECK the PC: Windows, CPU, RAM, NVIDIA GPU + video memory + driver, free disk, internet, existing tools
       and print what is present / missing.
    2. ASK before installing anything, then install what is missing:
         - uv (Python manager; brings its own Python 3.11)      - from GitHub/astral, no admin needed
         - Ollama portable (local AI model server)              - from github.com/ollama, NO startup entry
         - Neko's Python packages into a private .venv          - from PyPI
         - voice files (Kokoro), speech model (Whisper)         - from GitHub / Hugging Face
         - AI models sized for this GPU                         - from the Ollama library
       NVIDIA drivers are never installed silently: if yours is too old, the NVIDIA download page opens.
    3. ASK for the profile: your name, what the assistant is called, female or male voice, Bangla.
       Optional free cloud keys (Groq / Gemini) are typed by YOU here and stored only on this PC.
    4. Create Desktop + Start Menu shortcuts, run the self-test, and start Neko.
  Nothing is written outside the install folder, %LOCALAPPDATA%\NEKO and your shortcuts. Safe to re-run.

.PARAMETER InstallDir   Where Neko goes (default D:\NEKO if a D: drive exists, else %USERPROFILE%\NEKO).
.PARAMETER Models       auto | full | light | none   (which local AI models to download)
.PARAMETER Yes          Answer "yes" to the install questions (the profile questions are still asked).
.PARAMETER CheckOnly    Only check the PC and print the report.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [ValidateSet("auto", "full", "light", "none")][string]$Models = "auto",
    [switch]$Yes,
    [switch]$CheckOnly,
    # unattended / test runs: preset the profile answers and skip shortcuts, keys and auto-start
    [string]$UserName = "",
    [string]$AssistantName = "",
    [ValidateSet("", "female", "male")][string]$Voice = "",
    [switch]$NoShortcuts,
    [switch]$NoStart,
    [string]$ProfileDir = "",
    # where updates come from (your private GitHub repo); read from neko-update.json in the package if not given
    [string]$Repo = ""
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # much faster downloads in Windows PowerShell 5.1
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Here = $PSScriptRoot
$Package = Split-Path -Parent (Split-Path -Parent $Here)   # NEKO-Setup\neko\scripts\install -> NEKO-Setup\neko
if (-not (Test-Path (Join-Path $Package "src\neko\__init__.py"))) { $Package = Join-Path $Here "neko" }

function Say($text, $color = "Gray") { Write-Host $text -ForegroundColor $color }
function Step($n, $text) { Write-Host ""; Write-Host "[$n] $text" -ForegroundColor Cyan }
function Ask($question, $default = "Y") {
    if ($Yes) { return $true }
    $a = Read-Host "$question [$(if ($default -eq 'Y') {'Y/n'} else {'y/N'})]"
    if ([string]::IsNullOrWhiteSpace($a)) { $a = $default }
    return $a.Trim().ToLower().StartsWith("y")
}
function Download($url, $dest) {
    $dir = Split-Path -Parent $dest
    New-Item -ItemType Directory -Force $dir | Out-Null
    Say "    downloading $(Split-Path -Leaf $dest) ..."
    $tmp = "$dest.part"
    Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
    Move-Item -Force $tmp $dest
}

Write-Host ""
Write-Host "  N.E.K.O. installer" -ForegroundColor Yellow
Write-Host "  Neuro Electric Knowledge Operator - local + cloud AI assistant" -ForegroundColor DarkGray

# ------------------------------------------------------------------ 1. check the PC
Step 1 "Checking this PC"
$os = Get-CimInstance Win32_OperatingSystem
$cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1)
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$gpuName = ""; $vramMB = 0; $driver = ""
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($smi) {
    try {
        $q = & nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits 2>$null | Select-Object -First 1
        $parts = $q.Split(",") | ForEach-Object { $_.Trim() }
        $gpuName, $vramMB, $driver = $parts[0], [int]$parts[1], $parts[2]
    } catch { }
}
if (-not $gpuName) { $gpuName = ((Get-CimInstance Win32_VideoController | Select-Object -First 1).Name) }
if (-not $InstallDir) { $InstallDir = if (Test-Path "D:\") { "D:\NEKO" } else { Join-Path $env:USERPROFILE "NEKO" } }
$drive = (Split-Path -Qualifier $InstallDir)
$freeGB = [math]::Round((Get-PSDrive ($drive.TrimEnd(":"))).Free / 1GB)
$online = $false
try { Invoke-WebRequest "https://github.com" -UseBasicParsing -Method Head -TimeoutSec 8 | Out-Null; $online = $true } catch { }
$haveWinget = [bool](Get-Command winget -ErrorAction SilentlyContinue)
$uvExe = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uvExe -and (Test-Path "$InstallDir\tools\uv\uv.exe")) { $uvExe = "$InstallDir\tools\uv\uv.exe" }
$ollamaExe = "$InstallDir\ollama\app\ollama.exe"

$rows = @(
    @("Windows", "$($os.Caption) (build $($os.BuildNumber))", $(if ([int]$os.BuildNumber -ge 19045) { "ok" } else { "old - Windows 10 22H2 or 11 recommended" })),
    @("CPU", $cpu.Name.Trim(), "ok"),
    @("Memory", "$ramGB GB", $(if ($ramGB -ge 15) { "ok" } else { "low - 16 GB+ recommended" })),
    @("Graphics", "$gpuName$(if ($vramMB) { ", $([math]::Round($vramMB/1024)) GB" })", $(if ($vramMB -ge 6000) { "ok - GPU AI" } elseif ($vramMB) { "small GPU - lighter models" } else { "no NVIDIA GPU - CPU + cloud only" })),
    @("NVIDIA driver", $(if ($driver) { $driver } else { "-" }), "checked below"),
    @("Free disk ($drive)", "$freeGB GB", $(if ($freeGB -ge 45) { "ok" } elseif ($freeGB -ge 15) { "enough for light models" } else { "too little - free some space" })),
    @("Internet", $(if ($online) { "reachable" } else { "not reachable" }), $(if ($online) { "ok" } else { "needed for the install" })),
    @("uv / Python 3.11", $(if ($uvExe) { $uvExe } else { "missing" }), $(if ($uvExe) { "ok" } else { "will install" })),
    @("Ollama", $(if (Test-Path $ollamaExe) { $ollamaExe } else { "missing" }), $(if (Test-Path $ollamaExe) { "ok" } else { "will install (portable)" })),
    @("Install folder", $InstallDir, "")
)
foreach ($r in $rows) { "{0,-18} {1,-52} {2}" -f $r[0], $r[1], $r[2] | Write-Host }

# RTX 50-series (Blackwell) needs driver 572+, RTX 40/30 work from 551+
$needDriver = if ($gpuName -match "RTX\s*50\d\d") { 572 } else { 551 }
if ($vramMB -gt 0 -and $driver -and ([int]($driver.Split(".")[0]) -lt $needDriver)) {
    Say "  Your NVIDIA driver $driver is too old for $gpuName (needs $needDriver or newer)." Yellow
    if (Ask "  Open NVIDIA's driver download page now? (install it, then run this installer again)") {
        Start-Process "https://www.nvidia.com/Download/index.aspx"
    }
}
if ($CheckOnly) { Say "`nCheck only - nothing was changed." Green; exit 0 }
if (-not $online) { Say "`nThe install needs internet. Connect and run it again." Red; exit 1 }
if ($freeGB -lt 15) { Say "`nNot enough free disk space on $drive." Red; exit 1 }

# model plan by video memory
if ($Models -eq "auto") { $Models = if ($vramMB -ge 12000) { "full" } elseif ($vramMB -ge 6000) { "light" } else { "light" } }
$profileName = if ($vramMB -ge 12000) { "desktop-16gb" } else { "laptop-lite" }
$modelList = switch ($Models) {
    "full"  { if ($vramMB -ge 12000) { @("qwen3:14b", "qwen3:4b", "qwen2.5-coder:14b", "gemma3:12b", "bge-m3") } else { @("qwen3:8b", "qwen3:4b", "qwen2.5-coder:7b", "gemma3:4b", "bge-m3") } }
    "light" { if ($vramMB -ge 12000) { @("qwen3:14b", "qwen3:4b", "bge-m3") } else { @("llama3.2:3b", "qwen3:1.7b", "bge-m3") } }
    default { @() }
}
$sttModel = if ($vramMB -ge 6000) { "large-v3-turbo" } else { "small" }
$sttDevice = if ($vramMB -ge 6000) { "cuda" } else { "cpu" }
Say "`nPlan: profile $profileName, speech '$sttModel' on $sttDevice, models: $(if ($modelList) { $modelList -join ', ' } else { 'none' })" Green
if (-not (Ask "Install N.E.K.O. into $InstallDir now? (downloads roughly $(if ($Models -eq 'full') {'35'} elseif ($Models -eq 'light') {'18'} else {'6'}) GB)")) { exit 0 }

# ------------------------------------------------------------------ 2. install
# From here on, programs print progress and harmless warnings on stderr; Windows PowerShell 5.1 would treat
# those as fatal (seen in testing). Real failures are caught by checking each program's exit code instead.
$ErrorActionPreference = "Continue"
function Must($what) { if ($LASTEXITCODE -ne 0) { Say "
$what failed (exit code $LASTEXITCODE). Fix the message above and run the installer again - it continues where it stopped." Red; exit 1 } }
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
Step 2 "Copying N.E.K.O."
New-Item -ItemType Directory -Force $InstallDir | Out-Null
$App = Join-Path $InstallDir "app"
robocopy $Package $App /E /NFL /NDL /NJH /NJS /NP /XD .venv __pycache__ .pytest_cache | Out-Null
Say "    app files in $App"

# connect this copy to the update repo, so "Install update" works later
if (-not $Repo -and (Test-Path "$Here\neko-update.json")) { $Repo = (Get-Content "$Here\neko-update.json" -Raw | ConvertFrom-Json).repo }
if ($Repo) {
    $gitExe = (Get-Command git -ErrorAction SilentlyContinue).Source
    if (-not $gitExe -and $haveWinget -and (Ask "  Install Git (needed for one-click updates)?")) {
        winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
        $gitExe = @("C:\Program Files\Git\cmd\git.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if ($gitExe) {
        Say "    connecting to the update repo (if a GitHub sign-in window opens, sign in)..."
        Push-Location $App
        if (-not (Test-Path .git)) { & $gitExe init -q -b main }
        & $gitExe remote remove origin 2>$null
        & $gitExe remote add origin $Repo
        & $gitExe fetch -q origin main
        if ($LASTEXITCODE -eq 0) { & $gitExe reset -q --hard origin/main; Say "    connected - updates will come from $Repo" }
        else { Say "    couldn't reach the update repo now; Neko still works. Run the installer again later to connect." Yellow }
        Pop-Location
    } else { Say "    Git missing - one-click updates are off (Neko itself works)." Yellow }
}

Step 3 "Python (via uv, no admin)"
if (-not $uvExe) {
    $uvZip = "$InstallDir\tools\uv.zip"
    Download "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" $uvZip
    Expand-Archive -Force $uvZip "$InstallDir\tools\uv"
    Remove-Item $uvZip
    $uvExe = "$InstallDir\tools\uv\uv.exe"
}
$env:UV_PYTHON_INSTALL_DIR = "$InstallDir\tools\python"
if (-not (Test-Path "$App\.venv\Scripts\python.exe")) { & $uvExe venv --python 3.11 "$App\.venv" | Out-Null; Must "Creating the Python environment" }
$Py = "$App\.venv\Scripts\python.exe"
Say "    $( & $Py --version )"

Step 4 "Neko's Python packages (a few minutes)"
& $uvExe pip install --python $Py -r "$App\scripts\install\requirements.txt"
Must "Installing Neko's packages"
& $uvExe pip install --python $Py -e "$App"   # register Neko itself (python -m neko ...)
Must "Registering Neko"
if ($vramMB -ge 6000) {
    Say "    + NVIDIA speech libraries (about 2 GB) for fast GPU hearing"
    & $uvExe pip install --python $Py -r "$App\scripts\install\requirements-gpu.txt"
    Must "Installing the NVIDIA speech libraries"
}

Step 5 "Ollama (portable, no startup entry)"
if (-not (Test-Path $ollamaExe)) {
    $oz = "$InstallDir\ollama\ollama.zip"
    Download "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip" $oz
    Expand-Archive -Force $oz "$InstallDir\ollama\app"
    Remove-Item $oz
}
New-Item -ItemType Directory -Force "$InstallDir\ollama\models" | Out-Null
$paths = @{ ollama_exe = $ollamaExe; models_dir = "$InstallDir\ollama\models" } | ConvertTo-Json
[IO.File]::WriteAllText("$App\neko-paths.json", $paths, (New-Object Text.UTF8Encoding $false))

Step 6 "Voice files and speech model"
$kdir = "$InstallDir\data\voices\kokoro"
foreach ($f in @("kokoro-v1.0.onnx", "voices-v1.0.bin")) {
    if (-not (Test-Path "$kdir\$f")) { Download "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/$f" "$kdir\$f" }
}
$wdir = "$InstallDir\data\models\whisper"
Say "    speech model '$sttModel' (from Hugging Face)..."
& $Py -c "from faster_whisper import WhisperModel; WhisperModel('$sttModel', device='cpu', compute_type='int8', download_root=r'$wdir'); print('    ok')"

Step 7 "AI models (the big download)"
if ($modelList.Count -gt 0) {
    $env:OLLAMA_MODELS = "$InstallDir\ollama\models"; $env:OLLAMA_HOST = "127.0.0.1:11434"; $env:OLLAMA_NO_CLOUD = "1"
    $srv = Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden -PassThru
    Start-Sleep 4
    foreach ($m in $modelList) { Say "    $m"; & $ollamaExe pull $m }
    Stop-Process -Id $srv.Id -Force -ErrorAction SilentlyContinue
}

# ------------------------------------------------------------------ 3. profile
Step 8 "Your profile"
$user = if ($UserName) { $UserName } else { Read-Host "  Your name (what should the assistant call you?)" }
$name = if ($AssistantName) { $AssistantName } else { Read-Host "  The assistant's name [Neko]" }
if ([string]::IsNullOrWhiteSpace($name)) { $name = "Neko" }
$g = if ($Voice) { $Voice } else { Read-Host "  Voice: female or male? [female]" }
$gender = if ($g.Trim().ToLower().StartsWith("m")) { "male" } else { "female" }
$bn = if ($Yes) { $false } else { Ask "  Do you also talk to $name in Bangla? (she understands and can answer in native Bangla)" "N" }
$wake = @($name.ToLower())
if ($name.ToLower() -eq "neko") { $wake = @("neko", "nico", "niko", "neeko", "necko", "nekko") }
$wakeToml = ($wake | ForEach-Object { '"' + $_ + '"' }) -join ", "
$dataDir = if ($ProfileDir) { $ProfileDir } else { "$env:LOCALAPPDATA\NEKO" }
New-Item -ItemType Directory -Force $dataDir | Out-Null
$cfg = @"
config_version = 1
# Written by the N.E.K.O. installer on $(Get-Date -Format "yyyy-MM-dd HH:mm") for this PC ($gpuName).

[app]
user_name = "$($user.Replace('"', ''))"
assistant_name = "$($name.Replace('"', ''))"
verbosity = "balanced"
language = "$(if ($bn) { 'bn' } else { 'en' })"
personality = "warm, cheerful, caring and playful, like a close friend; honest about uncertainty"

[privacy]
allow_network = true
allow_cloud_models = true

[models]
profile = "$profileName"
num_ctx = $(if ($vramMB -ge 12000) { 16384 } else { 8192 })

[voice]
enabled = true
tts_engine = "edge"
gender = "$gender"
kokoro_dir = "$($kdir.Replace('\', '\\'))"
expressive = true
always_listen = true
wake_names = [$wakeToml]
stt_model = "$sttModel"
stt_device = "$sttDevice"
stt_model_dir = "$($wdir.Replace('\', '\\'))"
stt_language = "$(if ($bn) { '' } else { 'en' })"
follow_up_seconds = 15.0

[tools]
computer_control_enabled = true
allowed_roots = ["$($env:USERPROFILE.Replace('\', '\\'))\\Desktop", "$($env:USERPROFILE.Replace('\', '\\'))\\Documents", "$($env:USERPROFILE.Replace('\', '\\'))\\Downloads"]
writable_roots = ["$($InstallDir.Replace('\', '\\'))\\Notes"]
claude_code = true

[ui]
style = "orb"
always_on_top = true
"@
if ((Test-Path "$dataDir\config.toml") -and -not (Ask "  A Neko profile already exists on this PC. Replace it?" "N")) {
    Say "    kept the existing profile"
} else {
    if (Test-Path "$dataDir\config.toml") { Copy-Item "$dataDir\config.toml" "$dataDir\config.toml.bak-$(Get-Date -Format yyyyMMddHHmmss)" }
    [IO.File]::WriteAllText("$dataDir\config.toml", $cfg, (New-Object Text.UTF8Encoding $false))
}
New-Item -ItemType Directory -Force "$InstallDir\Notes" | Out-Null

if (-not $Yes -and (Ask "  Add free cloud brains now? (Groq + Gemini keys - you can also do this later in Settings)" "N")) {
    Say "    Get keys at https://console.groq.com/keys and https://aistudio.google.com/apikey" DarkGray
    $groq = Read-Host "    Paste your Groq key (or press Enter to skip)" -AsSecureString
    $gem = Read-Host "    Paste your Gemini key (or press Enter to skip)" -AsSecureString
    $plain = { param($s) [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)) }
    $lines = @("# N.E.K.O. cloud keys - private. Never share this file.", "[cloud]")
    $k1 = & $plain $groq; $k2 = & $plain $gem
    if ($k1) { $lines += "groq_key = `"$k1`"" }
    if ($k2) { $lines += "gemini_key = `"$k2`"" }
    [IO.File]::WriteAllText("$dataDir\secrets.toml", ($lines -join "`n") + "`n", (New-Object Text.UTF8Encoding $false))
    Say "    saved privately in $dataDir\secrets.toml"
}

# ------------------------------------------------------------------ 4. finish
Step 9 "Shortcuts, self-test, start"
$ws = New-Object -ComObject WScript.Shell
foreach ($lnkPath in $(if ($NoShortcuts) { @() } else { @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs")) })) {
    $l = $ws.CreateShortcut("$lnkPath\$name.lnk")
    $l.TargetPath = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
    $l.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$App\scripts\start-neko.ps1`""
    $l.WorkingDirectory = $App
    $l.WindowStyle = 7
    $l.IconLocation = "$App\packaging\neko.ico,0"
    $l.Save()
}
if (-not $NoShortcuts -and (Ask "Start $name automatically with Windows? (hidden - she appears when you say $name)")) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$App\scripts\autostart.ps1" -Enable
}
Push-Location $App
$test = & $Py -m unittest discover -s tests -t . 2>&1 | ForEach-Object { "$_" }
$test | Select-String -Pattern "^(Ran |OK|FAILED)" | ForEach-Object { Say "    self-test: $($_.Line)" }
$env:NEKO_CONFIG = "$dataDir\config.toml"
& $Py -m neko doctor
Remove-Item Env:NEKO_CONFIG
Pop-Location
Say "`nDone! Start $name with the Desktop icon (or the Start Menu)." Green
if (-not $NoStart -and (Ask "Start $name now?")) {
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "$App\scripts\start-neko.ps1")
}
