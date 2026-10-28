# Troubleshooting

Start with the read-only health check: `powershell -ExecutionPolicy Bypass -File scripts\doctor.ps1`.
Logs: `%LOCALAPPDATA%\NEKO\logs\neko.log.jsonl` (secrets redacted; your messages aren't logged).

| Symptom | Likely cause | Safe check | Fix |
|---|---|---|---|
| **Runtime not found** — "I can't reach the Ollama model server", HUD grey/offline | Ollama not running | `Get-NetTCPConnection -LocalPort 11434 -State Listen` | run `scripts\start-ollama.ps1` and keep its window open |
| `Error: could not locate ollama app` | ran `ollama list` without a server (portable install has no tray app) | — | start the server first (above), then `ollama list` in another window |
| **Model not found** — "That model isn't installed in Ollama" | profile wants a model you didn't pull | `D:\Ollama\app\ollama.exe list` | use profile `existing-only`, or pull the model (MODEL_GUIDE) |
| `ollama list` shows nothing but files exist | server started without `OLLAMA_MODELS` | look for `OLLAMA_MODELS:` in the server window's first lines | restart via `start-ollama.ps1` |
| **Insufficient RAM/VRAM** — "needs ~X MB but only Y MB is safely free" | other apps using memory, or model too big | Task Manager → Performance | close browsers/games; use a smaller model; lower `num_ctx` to 2048; or reduce `resources.ram_safety_margin_mb` carefully (not below 1024) |
| **Low disk space** | C: has ~18 GB free | `Get-PSDrive C,D` | keep models on D: (default); clear `%TEMP%`; N.E.K.O. never deletes files for you |
| **GPU initialisation failure** / everything on CPU | driver problem, discovery timeout | `nvidia-smi`; server window shows `inference compute … CUDA` | reboot; update NVIDIA driver (your choice); `start-ollama.ps1` already disables Vulkan probing |
| repeated "GPU discovery watchdog timed out" | slow device probing (seen in your old log) | does chat work? | harmless if chat works; otherwise as above |
| **Slow responses** | model partly on CPU, battery mode, long context, first load | Models tab → last routing "GPU fit" | plug in the charger; use `llama3.2:3b`/`qwen3:1.7b`; lower `num_ctx`; try `start-ollama.ps1 -KvCacheQ8`; wait for the first load (~5–15 s) |
| First reply slow, next ones fast | model loading into VRAM | — | normal. `keep_alive` keeps it loaded for 5 min |
| **Microphone failure** — "couldn't open the microphone" | Windows privacy block, wrong device, other app using it | Settings → Privacy → Microphone; Sound settings → Input | allow desktop apps; set `voice.input_device`; close other recording apps |
| "Voice input isn't ready: sounddevice is not installed" | voice extras not installed | — | `scripts\setup.ps1 -Apply -WithVoice` |
| **Speech recognition failure** — "speech model isn't downloaded yet" | faster-whisper model missing | — | MODEL_GUIDE §4 one-time download |
| wrong/garbled transcripts | noisy room, Bangla, small model | — | speak closer; set `stt_language`; try `stt_model = "medium"` (slower) |
| **Speech synthesis failure** / silence | muted, `tts_engine = "none"`, Piper paths wrong | Settings → Voice | use `sapi`; check `piper_exe`/`piper_voice` paths |
| N.E.K.O. hears itself | echo from speakers | — | use headphones; lower volume |
| **Database errors** — "local database reported an error" | file locked by a second instance, disk full, corruption | `python -m neko doctor` → Database line | close other N.E.K.O. windows; free space; see BACKUP_AND_RECOVERY §6 |
| "Database upgrade … failed and was rolled back" | migration error | log file | data unchanged; restore the pre-migration backup if needed; report the bug |
| **HUD rendering issues** — black box instead of transparent panel, flicker | GPU driver / remote desktop / transparency effects off | — | Settings → HUD opacity 1.0; turn on Reduce motion; Windows Settings → Personalisation → Colours → Transparency effects |
| HUD disappeared | hidden with Esc or off-screen | tray icon | tray → Show HUD; delete nothing |
| **Wake-word problems** | not wired into UI in v0.1 | — | use push-to-talk (wake word is P2) |
| **Permission denials** — "Not permitted: …" | folder not allowed, computer control off, emergency stop active, prohibited tool | message text says which | Settings → folders / Computer control; press RESUME after an emergency stop; deletion is always blocked |
| "You did not approve this action" but you didn't see a dialog | dialog hidden behind another window, or timed out (5 min) | taskbar | try again and watch for the dialog; it isn't always-on-top by design |
| **Remote inference disconnection** | (optional feature) desktop off / token unset | doctor | laptop keeps working locally; set the token env var; see ARCHITECTURE §7 |
| **Interrupted tasks** (crash, power loss) | — | Activity tab shows "running" forever | harmless; tasks are re-created per request. Check Activity → tool invocations for anything half-done (e.g. a move) |
| **Failed update** | dependency install error or migration error | `scripts\update.ps1` output | restore with `scripts\restore.ps1 <pre-update backup>` and go back to the previous project copy |
| `config-check` errors | typo in config.toml | `python -m neko config-check` lists exact keys | fix the listed keys; `config.toml.bak` is the previous version |
| **PC restarts by itself / blue screen** (seen 2026-10-27: bugchecks 0xA at 11:07 and 0x1E at 17:14) | a faulty kernel **driver** (both codes); heavy GPU/CPU use can expose it | Event Viewer → System → Kernel-Power 41 / BugCheck 1001; dumps in `C:\Windows\Minidump` (admin) | see STATUS.md §7: remove Baidu Cleaner (`BprotectEx.sys`, 2015), don't keep LDPlayer + BlueStacks both installed, clean-install the NVIDIA driver, update ASUS/AMD software; then Windows Memory Diagnostic |
| PowerShell says "running scripts is disabled" | Windows execution policy | — | always use `powershell -ExecutionPolicy Bypass -File …` as shown (affects only that command) |

Still stuck? Run `doctor`, copy its output plus the last 50 lines of the log (secrets are already
redacted; skim it for anything private anyway) and ask for help.
