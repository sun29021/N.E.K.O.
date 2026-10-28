# Installation manual (beginner-friendly)

This guide brings N.E.K.O. from "project files on disk" to "talking to you". Every step says what
it does and what you should see. Nothing here changes Windows settings. Total time: about 20–40
minutes, mostly waiting for downloads you approve.

**Words you'll see**
- *PowerShell*: the blue/black command window. Open it with Start → type `PowerShell` → Enter.
- *Virtual environment (.venv)*: a private folder where N.E.K.O.'s Python packages live, so nothing
  else on your PC is affected.
- *Ollama*: the program that runs the AI model. You already have it in `D:\Ollama`.
- *Model*: the AI "brain" file. You already have one: `llama3.2:3b`.

---

## Step 1 — Open PowerShell in the project folder
```powershell
cd D:\PROJECT\N.E.K.O
```
You should see the prompt change to `PS D:\PROJECT\N.E.K.O>`.

## Step 2 — Check Python
```powershell
py -0p
```
**Expected:** a list including `3.14` and/or `Astral/CPython3.11.17`. N.E.K.O. prefers Python
3.11–3.13. Your computer already has 3.11.17 (installed by uv), and setup will find it.
**If nothing suitable is listed:** install Python 3.12 from https://www.python.org/downloads/windows/
(tick "Add python.exe to PATH"), close and reopen PowerShell, and repeat.

## Step 3 — Dry run of the setup (changes nothing)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```
*What it does:* checks Windows, Python, disk space and your existing Ollama models, then prints a
plan. `-ExecutionPolicy Bypass` applies only to this one command, so you don't need to change any
Windows setting.
**Expected:** lines like `[ ok ] Python 3.11 at …`, `[ ok ] Existing Ollama models in D:\Ollama\models
will not be touched`, then `[plan] create virtual environment …` and "Dry run finished".

## Step 4 — Install (about 1.5 GB download of Python packages)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Apply
```
*What it does:* creates `.venv`, installs N.E.K.O. plus PySide6 (the window toolkit) from the
Python Package Index, and copies `config\user.example.toml` to `%LOCALAPPDATA%\NEKO\config.toml`
(only if that file doesn't already exist).
**Expected ending:** `Configuration is valid.` and "Setup complete. Next steps: …".
**Common errors:**
- *"pip install failed"*: check your internet connection and run the same command again (it is safe
  to repeat). If PySide6 fails on Python 3.14, re-run with `-Python` pointing at 3.11:
  `-Python "$env:APPDATA\uv\python\cpython-3.11.17-windows-x86_64-none\python.exe"`.
- *"Only N GB free"*: free some space on D: (or wherever the project is) and retry.

Want voice too? Add `-WithVoice` (≈1 GB more). You can do this later.

## Step 5 — Start the model server (your existing Ollama)
Open a **second** PowerShell window:
```powershell
cd D:\PROJECT\N.E.K.O
powershell -ExecutionPolicy Bypass -File scripts\start-ollama.ps1
```
*What it does:* runs `D:\Ollama\app\ollama.exe serve` with your model folder, listening only on this
computer. The settings apply only to this window and are forgotten when you close it.
**Expected:** a line containing `Listening on 127.0.0.1:11434 (version 0.40.9)`, then something like
`inference compute … NVIDIA GeForce RTX 3050 Laptop GPU`.
**Leave this window open.** Press Ctrl+C in it to stop the AI server.

### Ollama diagnostic and recovery (if step 5 doesn't look right)
Your earlier session showed `Error: could not locate ollama app`. That message appears when you run
`ollama list` **without a server running**: the portable version has no tray app to auto-start.
With step 5's window open, test in your first window:
```powershell
$env:OLLAMA_MODELS = "D:\Ollama\models"
D:\Ollama\app\ollama.exe list
```
**Expected:** `llama3.2:3b … 2.0 GB`. If instead:
| You see | Meaning | Do this |
|---|---|---|
| `could not locate ollama app` | server not running | go back to step 5's window and check it is still open |
| list is empty | server is using the wrong model folder | stop it (Ctrl+C) and rerun `start-ollama.ps1` (it sets the folder) |
| "Something is already listening on port 11434" | another Ollama is running | fine if it's Ollama; otherwise close that program |
| lots of `GPU discovery watchdog timed out` | slow GPU probing (seen before) | harmless if chat still works; the script already sets `OLLAMA_VULKAN=0`. Updating the NVIDIA driver may help |
| `no compatible GPUs` / everything on CPU | GPU not detected | run `nvidia-smi`; if that fails, reinstall the NVIDIA driver (your decision, not automated) |
Quick model test (optional, uses the GPU for ~10 s):
```powershell
D:\Ollama\app\ollama.exe run llama3.2:3b "Say hello in five words."
```
**Do not** delete or re-download anything in `D:\Ollama`. Your model is intact (verified: 2,019,377,376
bytes, digest matches the manifest).

## Step 6 — Health check (read-only)
Back in the first window:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\doctor.ps1
```
**Expected:** `[ OK ]` for Python, Configuration, RAM, GPU, Models on disk, Ollama executable,
**Ollama server: running**, Ollama models: `llama3.2:3b`, Desktop UI (PySide6): installed.
`[INFO]` lines for optional parts are fine.

## Step 7 — Launch
```powershell
powershell -ExecutionPolicy Bypass -File scripts\launch.ps1
```
*Expected:* a welcome window, then the floating HUD with the glowing core. Type "hello" and press
Enter. The first reply takes a few seconds longer while the model loads into the GPU.
Text-only alternative in the terminal: `scripts\launch.ps1 -Chat`.
Safe mode (existing model only, no voice, no computer control): `scripts\launch.ps1 -SafeMode`.

**Stopping N.E.K.O.:** right-click the tray icon (near the clock) → Quit. Then close the Ollama window
or press Ctrl+C in it.

## Step 8 — Optional: voice
1. `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Apply -WithVoice`
2. Download the speech model once (MODEL_GUIDE §4).
3. Windows Settings → Privacy & security → Microphone: allow desktop apps (your decision).
4. In N.E.K.O. Settings tick "Speak replies aloud" and restart.
5. Hold the 🎙 button, speak, release.

## Step 9 — Optional: let N.E.K.O. use folders and apps
Command Center → Settings:
- *Folders N.E.K.O. may read*: e.g. `D:\PROJECT; D:\Notes`
- *Folders N.E.K.O. may change*: e.g. `D:\Notes` (changes still ask you first)
- *Computer control*: tick to allow opening Notepad/Calculator/Explorer.
Save, then restart N.E.K.O.

## Step 10 — Optional: more models
See MODEL_GUIDE. Nothing is downloaded without your command.

## Automatic start with Windows (optional, off)
Not enabled and not recommended until you've used N.E.K.O. for a while. If you want it later:
press Win+R, type `shell:startup`, Enter, and create a shortcut there whose target is
`powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File D:\PROJECT\N.E.K.O\scripts\launch.ps1`.
Ollama must also be started (add a second shortcut for `start-ollama.ps1`). To undo it, delete the
shortcuts from that folder.

## Where things are
| | Location |
|---|---|
| Program | `D:\PROJECT\N.E.K.O` |
| Your settings | `%LOCALAPPDATA%\NEKO\config.toml` |
| Your data (memory, history) | `%LOCALAPPDATA%\NEKO\neko.db` |
| Logs | `%LOCALAPPDATA%\NEKO\logs` |
| Backups | `%LOCALAPPDATA%\NEKO\backups` |
| AI models | `D:\Ollama\models` |

Uninstall: `scripts\uninstall.ps1` (dry run) then `-Apply`. Your data is kept unless you add
`-AlsoDeleteData`.
