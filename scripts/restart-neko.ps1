# Restart N.E.K.O.: close every running copy, then start one fresh (model server is left running).
# Double-click-safe: no admin rights, no settings changed.
$ErrorActionPreference = "SilentlyContinue"
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -match '-m neko ui' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 2
& powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "start-neko.ps1")
