# Updates between your PCs, and using the office GPU from the laptop

## One-click updates (private GitHub repo)
**Laptop (where Neko is improved)** - publish a new version:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\publish-update.ps1 -Message "What's new"
```
It runs the full self-test, refuses to publish personal files (config, database, keys, shortcuts, .venv) or
anything that looks like an API key, then pushes to your private repo.

**Office PC** - Neko checks 2 minutes after starting and then every 6 hours. When there is an update, the
orb says so and the tray shows a message. Tray icon > **Install update** (or `scripts\update.ps1 -Apply`):
1. verified backup of her database, 2. new code (fast-forward only), 3. packages if they changed,
4. full self-test. **If anything fails it goes back to the version you had.** Then she restarts.
Your profile, memories and keys (`%LOCALAPPDATA%\NEKO`) are never touched.
Tested 2026-10-28 with a local copy of the repo: update 0.7.0 -> 0.7.1 applied; a deliberately broken update
was rolled back automatically.

### One-time setup
1. github.com -> New repository -> name `neko` -> **Private** -> no README -> Create.
2. Give the repo address to Claude (or run on the laptop):
   `git remote add origin https://github.com/<you>/neko.git` then `git push -u origin main`
   (a GitHub sign-in window opens the first time).
3. Rebuild the installer package (`scripts\build-dist.ps1`): it now records the repo, so the office install
   connects to it automatically (it signs in to GitHub once on that PC).

## Office GPU from the laptop (Tailscale)
1. Office PC: install Tailscale (https://tailscale.com/download), sign in with the **same account** as the laptop.
2. Office PC, after Neko is installed and running:
   `powershell -ExecutionPolicy Bypass -File scripts\share-gpu.ps1`
   (shares Ollama only inside your Tailscale network; `-Stop` undoes it). If Tailscale prints a link about
   enabling "Serve", open it once and allow it.
3. Laptop: `models.office_url = "auto"` (already set). When the office PC is online, chat, coding and vision
   use its bigger models (Command Center shows `processed: lan:office`); when it's off, the laptop's own GPU
   and the cloud brains answer. Hearing and the voice always run on the laptop.
Tested 2026-10-28 on the laptop itself through `tailscale serve`: models listed in 0.06 s, chat worked,
an offline office was detected in 2.5 s and skipped.

## Start with Windows
Settings > "Start with Windows" (or `scripts\autostart.ps1 -Enable` / `-Disable`): a shortcut in your
Startup folder starts Neko hidden; she appears when you say her name.
