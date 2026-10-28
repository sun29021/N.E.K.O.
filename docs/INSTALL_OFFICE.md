# Installing N.E.K.O. on another PC (e.g. the office desktop)

Office PC: Ryzen 7 7800X3D, 32 GB DDR5, MSI RTX 5060 Ti **16 GB**. The installer detects all of this itself.

## 1. Make the package (on the laptop)
```powershell
powershell -ExecutionPolicy Bypass -File D:\PROJECT\N.E.K.O\scripts\build-dist.ps1
```
This creates `D:\NEKO-Data\dist\NEKO-Setup.zip` (about 0.5 MB: code, tests, docs, installer - no personal
data, no keys, no models). The build stops if it finds a config, database, shortcut or API key in it.

## 2. Copy it to the office PC
USB stick, OneDrive, or any way you like. Unzip it anywhere (e.g. the Desktop).

## 3. Run ONE command (or double-click `INSTALL.cmd`)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\NEKO-Setup\install.ps1
```
What happens, in order:
1. **Check**: Windows version, CPU, RAM, GPU + video memory, NVIDIA driver, free disk, internet, uv/Python,
   Ollama. It prints a table of what is there and what is missing. (Only want the check?
   add `-CheckOnly`.)
2. **Driver**: an RTX 50-series card needs NVIDIA driver 572 or newer. If yours is older, it offers to open
   NVIDIA's download page - install it, then run the installer again. Drivers are never installed silently.
3. **Asks once**, then installs into `D:\NEKO` (or `%USERPROFILE%\NEKO` without a D: drive):
   - uv + its own Python 3.11 (no admin, nothing added to Windows)
   - Neko's Python packages, plus NVIDIA's speech libraries when there is a GPU with 6 GB+
   - Ollama **portable** (no startup entry, no service) in `D:\NEKO\ollama`
   - Kokoro voice files and the Whisper speech model (`large-v3-turbo` on a 6 GB+ GPU)
   - AI models for the GPU. On 16 GB, "full": qwen3:14b, qwen3:4b, qwen2.5-coder:14b, gemma3:12b, bge-m3
     (about 35 GB). Use `-Models light` for about 13 GB, or `-Models none` to skip.
4. **Profile**: your name, the assistant's name (her wake word follows it), **female or male voice**, and
   whether you speak Bangla too. Optional: paste your free Groq/Gemini keys (typed by you, stored only in
   `%LOCALAPPDATA%\NEKO\secrets.toml` on that PC).
5. Desktop + Start Menu shortcuts, self-test, health check, then it offers to start her.

Re-running is safe: finished steps are skipped and your profile is kept unless you choose to replace it.

## After installing
- **Share its GPU with the laptop**: install Tailscale (same account as the laptop), then run
  `powershell -ExecutionPolicy Bypass -File D:\NEKO\app\scripts\share-gpu.ps1` - see docs/UPDATES.md.
- **Updates**: tray icon > Install update when Neko says one is ready.

## Notes
- The office Neko has its own memory (the laptop's isn't copied). Sync can come later.
- Uses the `desktop-16gb` profile: qwen3:14b for chat and reasoning, 16k-token context, GPU speech.
- Natural voices (English + native Bangla, female/male) need internet; offline she uses Kokoro (English).
- Uninstall: delete `D:\NEKO`, `%LOCALAPPDATA%\NEKO` and the two shortcuts.
