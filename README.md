# N.E.K.O. — Neuro Electric Knowledge Operator

A private, local-first AI companion and Windows command center. It talks with you
(text now, voice optionally), remembers what you tell it to, can look at screenshots you
choose to share, and can do small jobs on your computer — **only after asking you**.
Everything runs on your own laptop by default. No account, subscription or API key needed.

> **Status: 0.1.1 — installed and working on this laptop (2026-10-27).** Six local models,
> speech recognition and the desktop app are set up, and live tests passed with real models
> (chat, tools, memory, screenshots, speech-to-text, prompt-injection resistance; 117 automated tests).
> **Start it with the "N.E.K.O." shortcut on your Desktop.** Measured speeds and what still needs a
> human check are in [docs/STATUS.md](docs/STATUS.md).

## What it can do (v0.1)

| Capability | State |
|---|---|
| Text chat with a local model (Ollama, your existing `llama3.2:3b`) | Implemented, tested with a fake model |
| Floating animated HUD + Command Center (chat, activity, memory, models, diagnostics, settings) | Implemented, **not yet run** |
| Persistent memory you can inspect, edit, delete, export ("remember that…", "forget…") | Implemented, tested |
| Resource-aware model choice with explained reasons (RAM/VRAM/battery) | Implemented, tested |
| Safe tools: read/search files in folders you allow, write notes, move files, open allow-listed apps, run approved scripts | Implemented, tested |
| Approval prompts, emergency stop, prompt-injection protection, audit log | Implemented, tested |
| Screenshot questions ("explain this error") | Implemented; needs an optional vision model (~3.4 GB) |
| Push-to-talk voice + spoken replies | Implemented; needs optional voice packages, **not yet run** |
| "Hey Jarvis" wake word | Optional; personal use only (model licence is non-commercial) |
| Second computer as extra brain, web research, hand gestures | Designed, not built (see [ROADMAP](docs/ROADMAP.md)) |

## Your computer (inspected 2026-10-27)

ASUS TUF Gaming A15 · Ryzen 7 4800H (8 cores) · **16 GB RAM** · RTX 3050 Laptop **4 GB** (driver 610.62) ·
Windows 11 Home 26200 · C: 18 GB free, D: 108 GB free · Ollama 0.40.9 portable in `D:\Ollama` with
`llama3.2:3b` (2.02 GB, Q4_K_M). Ollama's own log shows that model ran at **~30 tokens/s** on the GPU.
Details: [docs/HARDWARE_PROFILE.md](docs/HARDWARE_PROFILE.md).

## Get started

Follow **[docs/INSTALLATION_MANUAL.md](docs/INSTALLATION_MANUAL.md)**, a step-by-step guide written
for beginners. In short:

```powershell
cd D:\PROJECT\N.E.K.O
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1          # dry run: shows what it would do
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Apply   # installs into .venv only
powershell -File scripts\start-ollama.ps1                           # in its own window
powershell -File scripts\doctor.ps1                                 # read-only health check
powershell -File scripts\launch.ps1                                 # opens the HUD
```

## How it is built

```
 HUD / Command Center (PySide6)  ──signals──  UiBridge
                                               │
 Coordinator ── intent ── router ── model gateway ── Ollama (localhost)
      │            │
      │        memory (SQLite + FTS5 + optional embeddings)
      │
 tool gateway ── permission policy ── approvals (you) ── audit log
```

Python 3.11–3.13, PySide6 for the desktop, SQLite for storage, Ollama for models. The core
engine uses **only the Python standard library**, so it stays small and easy to audit.
Full design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Privacy and safety in one paragraph

Requests are processed on this computer. Network research, cloud models and the remote
computer are **off** and can only be turned on by editing the config file. The microphone is used only
while you hold the mic button, and screenshots only when you press capture; neither is saved. Anything that
changes your files or opens programs is checked by a policy written in code, not by the AI. Text from
files, web pages or screenshots is treated as data and can never approve an action. Deleting files is
blocked completely. Your data lives in `%LOCALAPPDATA%\NEKO`, outside this project folder, so sharing the
project never shares your memories.
Details: [docs/SAFETY_AND_PERMISSIONS.md](docs/SAFETY_AND_PERMISSIONS.md).

## Documentation

| Read first | For developers |
|---|---|
| [Installation manual](docs/INSTALLATION_MANUAL.md) | [Architecture](docs/ARCHITECTURE.md) · [PRD](docs/PRD.md) |
| [User manual](docs/USER_MANUAL.md) | [Research ledger](docs/RESEARCH_LEDGER.md) |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | [Memory design](docs/MEMORY_DESIGN.md) · [Database schema](docs/DATABASE_SCHEMA.md) |
| [Model guide](docs/MODEL_GUIDE.md) | [Voice](docs/VOICE_DESIGN.md) · [Vision & gestures](docs/VISION_AND_GESTURES.md) |
| [Backup & recovery](docs/BACKUP_AND_RECOVERY.md) | [UI/UX spec](docs/UI_UX_SPEC.md) · [Tools & MCP](docs/TOOLS_AND_MCP.md) |
| [Sharing N.E.K.O.](docs/SHARING_AND_DISTRIBUTION.md) | [Resource management](docs/RESOURCE_MANAGEMENT.md) · [Performance plan](docs/PERFORMANCE_PLAN.md) |
| [Status](docs/STATUS.md) · [Roadmap](docs/ROADMAP.md) | [Test plan](docs/TEST_PLAN.md) · [Security audit](docs/SECURITY_AUDIT.md) |

## Licence

N.E.K.O.'s own code is MIT. PySide6, the voice tools and every AI model keep their own licences and are
**not bundled**; see [LICENSE](LICENSE) and [docs/MODEL_GUIDE.md](docs/MODEL_GUIDE.md).
N.E.K.O. is an original project. It is not affiliated with any film, studio or other assistant product.
