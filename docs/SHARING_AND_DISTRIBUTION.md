# Sharing N.E.K.O. with someone else

Your personal data is never inside the project folder. It lives in *your* `%LOCALAPPDATA%\NEKO`.
So sharing the project shares only code, docs and templates.

## 1. Options compared
| Option | Size | Effort for you | Effort for them | Updates | Recommended |
|---|---|---|---|---|---|
| **Release zip + SHA-256** (`packaging\build-release.ps1`) | < 1 MB | low | run setup | send a new zip | **Yes, first** |
| Private/public Git repository (GitHub) | < 1 MB | low (needs a GitHub account; your decision) | `git clone`, setup | `git pull` + `update.ps1` | Yes, once you're comfortable |
| Packaged app (PyInstaller/Nuitka one-folder build) | 250–400 MB (PySide6 + Python) | medium; antivirus false positives are common | double-click | new build each time | Later (P2) |
| Installer with wizard (Inno Setup / MSIX) | same + installer | high; code-signing certificate costs money | easiest | installer updates | Later (P2) |
| Bundling models | +2–10 GB | — | — | — | **No.** Licences and size; have them pull from official sources |
| Portable (USB) copy | ~1.5 GB with .venv | low | none | manual | Works if the same Python path exists. venvs are not reliably relocatable, so re-run setup instead |

## 2. Make a clean release zip
```powershell
cd D:\PROJECT\N.E.K.O
powershell -ExecutionPolicy Bypass -File packaging\build-release.ps1          # dry run: lists files
powershell -ExecutionPolicy Bypass -File packaging\build-release.ps1 -Apply   # writes dist\neko-0.1.0.zip + .sha256
```
It includes only tracked project files (src, tests, docs, scripts, config templates, packaging, top-level
docs). It **refuses** to build if it finds a `.db`, `.env`, `config.toml`, log, backup, model or `.venv`
inside the folder list. Send the zip **and** the `.sha256` text. The recipient checks it with:
```powershell
Get-FileHash .\neko-0.1.0.zip -Algorithm SHA256
```

## 3. What the other person gets (clean install)
Their own config (created from `config\user.example.toml`), database, memories, logs, model inventory,
permission policy and secrets, all created fresh on *their* PC. Nothing of yours: no memories, history,
config, API keys, browser data, files or Ollama key.

Their steps: INSTALLATION_MANUAL from step 1. They need Ollama themselves
(https://ollama.com/download, or the portable zip) and a model (`ollama pull llama3.2:3b`, ~2 GB).
In their config they set `profile = "existing-only"` with their model, or edit the profile. **Note:**
`start-ollama.ps1` assumes `D:\Ollama`. On their PC they pass `-OllamaExe` and `-ModelsDir`, or use
the standard Ollama installer, which runs its own server (then they skip start-ollama.ps1).

## 4. Licences when sharing
- N.E.K.O. code: MIT. Keep the LICENSE file.
- Dependencies are installed by pip on their machine, not redistributed by you.
- Models: never include model files. Tell people which tag to pull. Each model has its own terms
  (Llama 3.2 Community License requires attribution and an acceptable-use policy; Gemma Terms of Use;
  Qwen 3B-size research licences are non-commercial). See MODEL_GUIDE.
- openWakeWord pre-trained models: CC BY-NC-SA 4.0, so no commercial use.
- Piper: GPL-3.0. It's a separate program they download themselves.

## 5. Updates
Bump the version in `pyproject.toml` + `src/neko/__init__.py`, update CHANGELOG, run the tests, build a new
zip. Recipients replace the project folder (their data is elsewhere) and run `scripts\update.ps1 -Apply`.
That backs up first, reinstalls the pinned dependencies, runs config checks and tests, and migrates the
database on next launch. **There is no auto-updater.** N.E.K.O. never downloads and runs code by
itself.

Before each release: review dependency changes (`pip list --outdated` in the venv), check advisories
for PySide6/faster-whisper, re-run the full test suite and `doctor`.

## 6. First-run experience for new users
Setup's dry run explains what it will do. `doctor` checks the computer. The first-run window explains
local processing, the mic/camera policy and approvals. The `existing-only` profile means *one* model
download (with its size shown in MODEL_GUIDE) gets a working text assistant. Voice is a separate opt-in
step.
