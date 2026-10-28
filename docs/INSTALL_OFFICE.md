# Installing N.E.K.O. on another PC (e.g. the office desktop)

Office PC: MSI with **one RTX 5060 Ti 16 GB**, Ryzen 7 7800X3D, 32 GB DDR5 RAM. The installer detects this
itself and picks the `desktop-16gb` plan: qwen3:14b, gemma3:12b, qwen2.5-coder:14b fully on the GPU.
(A PC with two cards, ~32 GB of GPU memory, would get `desktop-32gb` with 27-32B models.)

That PC gets its **own** assistant: its own name, voice, memory - and its own phone and Telegram bot.
Nothing personal is copied from the laptop (no memories, no keys, no paired phone).

## 0. Before you start (on the laptop)
Publish the newest version first, so the office PC's one-click updates start from it:
ask Claude "publish the update" (or run `scripts\publish-update.ps1`). If you forget, the installer keeps
the newer version it was given and tells you to run it again after publishing - it never downgrades.

## 1. Make the package (on the laptop)
```powershell
powershell -ExecutionPolicy Bypass -File D:\PROJECT\N.E.K.O\scripts\build-dist.ps1
```
This creates `D:\NEKO-Data\dist\NEKO-Setup.zip` (under 1 MB: code, tests, docs, installer). The build stops
if it finds a config, database, phone pairing file, shortcut, API key or Telegram bot key in it.

## 2. Copy it to the office PC
USB stick, OneDrive, Google Drive - any way. Unzip it anywhere (e.g. the Desktop).

## 3. Double-click `INSTALL.cmd` (that's it)
It checks the PC, shows what it found and what it will download, and asks once before installing.
What happens, in order:
1. **Check**: Windows, CPU, RAM, every NVIDIA GPU + total video memory, driver, free disk, internet.
   (Only want the check? `install.ps1 -CheckOnly`.)
2. **Driver**: RTX 50-series needs NVIDIA driver 572+. If older, it opens NVIDIA's page; install, run again.
3. **Installs** into `D:\NEKO`: Python (via uv, no admin), Neko's packages, GPU speech, Ollama portable
   (no startup entry), voices, Whisper `large-v3-turbo`, and the AI models:
   - 16 GB GPU: **full** (qwen3:14b, qwen3:4b, qwen2.5-coder:14b, gemma3:12b, bge-m3 - about 35 GB);
     `-Models light` for qwen3:14b, qwen3:4b, bge-m3 (about 18 GB).
4. **Profile questions** (answer for the person who will use THAT PC):
   - their name, the assistant's name (her wake word follows it - e.g. "Nova"), female or male voice,
     Bangla or not;
   - **"Control <name> from a phone through Telegram?"** - say yes, then on **that person's phone**:
     Telegram > **@BotFather** (blue tick) > `/newbot` > name > username ending in `bot` > paste the key.
     The installer checks the key with Telegram and shows the bot's @name. **Always a NEW bot** - never
     the laptop's (if two PCs share one bot, Neko notices and shows "bot key used by another PC");
   - free Groq / Gemini keys (optional; they can be separate free accounts too).
5. Shortcuts, start with Windows (asks), self-test, health check, start.

## 4. Pair the phone (on the office PC, 30 seconds)
When she starts, the orb shows: **"Pair your phone: in Telegram open @your_bot and send /pair 123456"**.
Send exactly that from the office phone. She answers "Paired!" and from then on only that phone's Telegram
account can talk to her. Then set an **approval PIN**: Command Center > Phone > 3. Approval PIN.
(Code expired? Command Center > Phone > Pair my phone.)

## 5. Optional extras on the office PC
- **Live calls from its phone**: install Tailscale on the office PC and on that phone (same Tailscale
  account), then Command Center > Phone > **Turn on calls** > Send call link to my phone.
- **Let the laptop use the office GPU**: see docs/UPDATES.md (`scripts\share-gpu.ps1` on the office PC).
  The laptop then automatically uses the office's best model (qwen3:14b) when the office PC is on.

## Updates
Office Neko checks every 6 hours. Tray icon > **Install update** when she says one is ready (backup,
new version, self-test, automatic rollback if anything fails). Her profile, memory, phone pairing and keys
are never touched by updates.

## Notes
- Re-running the installer is safe: finished steps are skipped; the profile and keys are kept unless you
  choose to replace them.
- Uninstall: delete `D:\NEKO`, `%LOCALAPPDATA%\NEKO` and the shortcuts; in @BotFather send `/deletebot`.
