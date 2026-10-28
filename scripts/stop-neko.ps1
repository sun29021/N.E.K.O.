<#
.SYNOPSIS
  Stops N.E.K.O. and the Ollama model server started for it (frees GPU memory).
#>
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*-m neko ui*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Get-Process ollama, llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Host "N.E.K.O. and Ollama stopped."
