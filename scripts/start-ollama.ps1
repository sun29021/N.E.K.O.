<#
.SYNOPSIS
  Starts your EXISTING portable Ollama (D:\Ollama) for N.E.K.O., in this window.

.DESCRIPTION
  Why this is needed: Ollama's portable zip has no tray app. When no server is
  running, "ollama list" tries to launch the tray app and prints
  "Error: could not locate ollama app". The fix is to run "ollama serve"
  yourself - that is all this script does.

  Settings apply ONLY to this window's process (nothing is saved to Windows):
    OLLAMA_MODELS=D:\Ollama\models   use the models you already downloaded
    OLLAMA_HOST=127.0.0.1:11434      only this computer can connect
    OLLAMA_NOPRUNE=1                 never delete "unused" model files
    OLLAMA_MAX_LOADED_MODELS=2       one GPU chat model + the CPU-only memory embedder (N.E.K.O. still
                                     keeps only one chat model loaded)
    OLLAMA_NUM_PARALLEL=1            one request at a time
    OLLAMA_NO_CLOUD=1                disable Ollama cloud features
    OLLAMA_VULKAN=0                  skip Vulkan/iGPU discovery (your log showed slow GPU discovery)
  Optional:
    -KvCacheQ8   halve KV-cache memory (OLLAMA_FLASH_ATTENTION=1, OLLAMA_KV_CACHE_TYPE=q8_0)

  Keep this window open while you use N.E.K.O. Press Ctrl+C to stop the server.
#>
[CmdletBinding()]
param(
    [string]$OllamaExe = "D:\Ollama\app\ollama.exe",
    [string]$ModelsDir = "D:\Ollama\models",
    [switch]$KvCacheQ8,
    [switch]$CheckOnly
)
$ErrorActionPreference = "Stop"
# A PC set up by scripts\install\install.ps1 records its own Ollama paths here (the laptop uses D:\Ollama).
$pathsFile = Join-Path (Split-Path -Parent $PSScriptRoot) "neko-paths.json"
if ((Test-Path $pathsFile) -and -not $PSBoundParameters.ContainsKey("OllamaExe")) {
    $p = Get-Content $pathsFile -Raw | ConvertFrom-Json
    $OllamaExe, $ModelsDir = $p.ollama_exe, $p.models_dir
}
if (-not (Test-Path $OllamaExe)) { Write-Host "Ollama not found at $OllamaExe (pass -OllamaExe)" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $ModelsDir)) { Write-Host "Models folder not found: $ModelsDir" -ForegroundColor Red; exit 1 }

$listening = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    $proc = Get-Process -Id $listening[0].OwningProcess -ErrorAction SilentlyContinue
    Write-Host "Something is already listening on port 11434: $($proc.ProcessName) (PID $($proc.Id))." -ForegroundColor Yellow
    Write-Host "If that is Ollama, you're done. Otherwise close it first." -ForegroundColor Yellow
    exit 0
}
if ($CheckOnly) { Write-Host "Port 11434 is free; Ollama is not running."; exit 0 }

$env:OLLAMA_MODELS = $ModelsDir
$env:OLLAMA_HOST = "127.0.0.1:11434"
$env:OLLAMA_NOPRUNE = "1"
$env:OLLAMA_MAX_LOADED_MODELS = "2"   # one GPU chat model + the small CPU-only embedder
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_NO_CLOUD = "1"
$env:OLLAMA_VULKAN = "0"
$env:OLLAMA_KEEP_ALIVE = "5m"
if ($KvCacheQ8) { $env:OLLAMA_FLASH_ATTENTION = "1"; $env:OLLAMA_KV_CACHE_TYPE = "q8_0" }

$log = Join-Path (Split-Path $ModelsDir -Parent) "serve-neko.log"
Write-Host "Starting Ollama: $OllamaExe serve" -ForegroundColor Cyan
Write-Host "Models: $ModelsDir   Log: $log   (your original serve.log is left untouched)"
Write-Host "Leave this window open. Ctrl+C stops the server." -ForegroundColor Cyan
# Ollama writes its normal log to stderr. Windows PowerShell 5.1 turns native stderr into error
# records, which would abort the script under "Stop" - so relax it and pass lines through as text.
$ErrorActionPreference = "Continue"
& $OllamaExe serve 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append
