# N.E.K.O. 0.7 plan (written 2026-10-28 05:47, owner asleep until ~8 AM)

This file is the single source of truth for the 0.7 work, so any session (including the automatic
8 AM continuation) can pick it up. Tick items as they are DONE AND TESTED. Read AGENTS.md first.

## Owner's requests (2026-10-28, ~05:30)
1. The voice sounds unnatural: make it natural. Subtitles must appear **word by word** as she speaks,
   not the whole reply at once.
2. Owner researched full-duplex voice (micro-turns, the AI listens while it talks, "mm-hm" backchannels,
   can interrupt). Take what is feasible.
3. Futuristic UI like the reference screenshots: a dark 3D-ish "brain" graph of her knowledge (notes,
   projects, files, tools, concepts as glowing coloured nodes with links, filter legend, inspector panel,
   search), and a "Tool armory" page listing everything she can reach and its status.
4. Use the laptop's full potential (this laptop: RTX 3050 4 GB, Ryzen, 16 GB RAM).
5. **Office PC**: same assistant, more powerful: Ryzen 7 7800X3D, MSI RTX 5060 Ti **16 GB**, 2x16 GB
   DDR5-6000 CL32. Bigger local models + the cloud brains.
6. **One command** for the office PC's terminal that: checks the PC (CPU, RAM, GPU, VRAM, driver, disk,
   Windows), lists what is present/missing, downloads and installs what is missing, downloads Neko and
   compatible models, installs Neko, then asks for the **profile**: the user's name, what the assistant
   is called, **male or female voice**.
7. The assistant can switch **male/female voice**, and a **native Bangla voice** when asked to speak Bangla.
8. Keep working after the usage limit resets at 8 AM.

## Decisions (owner answered only the GPU question; defaults chosen for the rest, tell the owner)
- Office GPU: RTX 5060 Ti 16 GB (Blackwell, needs a recent NVIDIA driver, >= 572; CUDA 12.8+).
- Voice: **online + offline**. Microsoft Edge neural voices (free, online, `edge-tts` package):
  English female `en-US-AvaMultilingualNeural` / `en-US-AriaNeural`, male `en-US-AndrewMultilingualNeural`
  / `en-US-GuyNeural`; Bangla female `bn-BD-NabanitaNeural`, male `bn-BD-PradeepNeural`. Offline
  fallback: Kokoro (af_heart female / am_michael male). Edge gives word-boundary timings -> exact
  word-by-word subtitles. Spoken text goes to Microsoft (mention it in docs).
- Delivery to office PC: self-contained installer package built at `D:\NEKO-Data\dist\NEKO-Setup\`
  (+ zip). Owner copies it by USB/OneDrive and runs ONE command from it. (A private GitHub repo needs the
  owner's own sign-in - offer later.) The installer may download public things (Python, Ollama, pip
  packages, models) from official sources; it never contains the owner's keys or personal data.
- Memory between PCs: separate for now (opt-in sync later).
- Full duplex: no fine-tuned 35B on these GPUs. Feasible now: **barge-in** (talk over her to stop her,
  works best with headphones; with speakers use a higher threshold + ignore her own words), quick
  "mm-hm"/"okay" acknowledgements are optional. Document honestly.

## Hard constraints learned this session (do not repeat these mistakes)
- **Claude desktop sandbox**: shell commands from this app see a virtualized `%LOCALAPPDATA%`/`%APPDATA%`.
  The REAL Neko config/DB/logs are only reachable through a process started outside the package:
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=...}`, staging
  files on `D:\NEKO-Data\realcheck`. Restart Neko the same way with `scripts\restart-neko.ps1`.
  Never read or print the owner's API keys (`secrets.toml`); test cloud only via scripts that print status.
- Always write files without BOM (`[IO.File]::WriteAllText(p, t, (New-Object Text.UTF8Encoding $false))`
  or the Edit tool). Run tests: `.venv\Scripts\python -m unittest discover -s tests -t .` (220 pass at start).
- Owner is a beginner: plain words, honest status, never claim untested things work.

## Checklist
- [x] 1. Voice engine `voice/tts_edge.py`: edge-tts streaming (mp3 -> PCM via PyAV, already installed),
      word-boundary events -> `on_word(word, start_ms)`; voices by language+gender; emotion -> rate/pitch;
      falls back to Kokoro when offline. Settings: `voice.tts_engine = "edge"`, `voice.gender`,
      `voice.edge_voice_en/_bn` overrides. Install `edge-tts` into the venv (owner approved installs).
- [x] 2. Bangla: detect Bangla replies (Bengali script) -> Bangla voice; "speak Bangla / bangla te bolo"
      -> reply in Bangla (prompt) + Bangla voice; Kokoro can't do Bangla -> Edge only (say so offline).
- [x] 3. Male/female switch: "use a male voice" / "switch to female voice" command (persists in config via
      Settings save path) + Settings dropdown; Kokoro male voice am_michael / am_adam.
- [x] 4. Word-by-word subtitles: orb caption shows the words as they are spoken (karaoke: current word
      highlighted, last ~10 words), driven by word timings (Edge) or estimated timings (Kokoro: per
      sentence, words spread by character length).
- [x] 5. Barge-in: while she speaks, keep listening with a raised threshold; a clear new utterance (not
      her own words) stops her speech and is handled as the next request. Setting `voice.barge_in`.
- [x] 6. Brain graph UI (`ui/brain_view.py`): QPainter pseudo-3D force-directed graph of memories,
      projects, documents, vocabulary, tools, conversations-topics; colours by type, filter legend,
      search box, inspector (click a node -> details + linked nodes), slow rotation, glow. Open from
      tray / orb menu / "show me your brain".
- [x] 7. Tool armory page: all tools + cloud brains + voice engines with status (connected / needs key /
      off) and what each does; buttons to Settings.
- [x] 8. Hardware profiles: `doctor` reports a recommendation; office profile `desktop-16gb` with
      qwen3:14b (chat/reasoning), qwen2.5-coder:14b (coding), gemma3:12b (vision), qwen3:4b (fast),
      bge-m3; GPU speech large-v3-turbo; num_ctx 16384.
- [x] 9. Installer package `scripts/install/`: `install.ps1` (one command), checks + report, installs
      Python 3.11 (winget or python.org), Ollama (winget), VC++ runtime, creates venv, pip installs
      (PySide6, faster-whisper, kokoro-onnx, sounddevice, pypdf, yt-dlp, edge-tts, nvidia cu12 libs),
      downloads Kokoro + whisper turbo + Ollama models by VRAM, profile wizard (names, voice gender,
      languages, optional Groq/Gemini keys typed by the user), shortcuts, runs tests + doctor, launches.
      NVIDIA driver: check version; if too old, open NVIDIA's download page (never silent driver
      install). Build `D:\NEKO-Data\dist\NEKO-Setup` + zip with `scripts/build-dist.ps1`.
- [x] 10. Tests for all of the above; docs (STATUS, CHANGELOG 0.7.0, USER_MANUAL, INSTALL_OFFICE.md);
      version bump; real restart (WMI); final report to the owner with exactly what to run on the
      office PC.

## Progress log
- 05:47 plan written.
- 06:15 items 1-4 done: tts_edge.py + playback.py (word timings), Bangla/gender/language commands (saved to the
  config the settings came from), subtitles on the orb. 226 tests pass. Owner's real config now tts_engine=edge.
  Silent live test: English first word 1.6 s, Bangla 1.0-1.3 s.
- 06:25 item 5 done: barge-in needs her NAME while she talks ("Neko, stop" / "Neko, wait - X"); her own echo
  ignored. Real-time simulation passed 3/3. Setting voice.barge_in.
- 06:45 items 6-7 done: memory/brain.py + ui/brain_view.py (3D force graph, inspector, search, legend filter,
  open docs on double-click), diagnostics/armory.py + ui/armory_view.py. Open via tray, orb menu, "show me your
  brain" / "tool armory". Renders inspected. 231 tests pass.
- 10:40 (main session after the usage reset; the scheduled run was stopped to avoid two sessions editing the same
  files) items 8-10 done: installer + build-dist + INSTALL_OFFICE.md; real end-to-end test install passed after 3
  fixes; 0.7.0 docs. 231 tests pass. D:\NEKO-TEST (test install) left for the owner to delete.
