# Changelog

All notable changes. Versions follow semantic versioning; database schema and
config versions are tracked separately (see docs/DATABASE_SCHEMA.md).

## [0.7.1] - 2026-10-28 - start with Windows, office GPU from the laptop, one-click updates

### Added
- Start with Windows, hidden: `scripts/autostart.ps1`, Settings checkbox, installer question. Neko starts
  invisible at sign-in (`neko ui --background`) and appears when you say her name. On for the owner's laptop.
- Office GPU over Tailscale (`models/office.py`, `scripts/share-gpu.ps1`): the office PC shares Ollama only
  inside your tailnet via `tailscale serve` (no firewall change); the laptop (`models.office_url = "auto"`)
  finds it and prefers its bigger models, skipping it quickly when offline. Tested through tailscale serve.
- One-click updates from a private GitHub repo: `scripts/update.ps1` (check / backup / fast-forward /
  packages / self-test / automatic rollback), `scripts/publish-update.ps1` (tests + no personal files or keys),
  background check every 6 h + tray "Install update"; the installer connects new PCs to the repo.
  Simulated end to end: a good update applied, a broken one rolled back. The project is now a git repository.
## [0.7.0] - 2026-10-28 - natural voices, Bangla, word-by-word subtitles, brain map, office installer

### Added
- Natural voices (`voice/tts_edge.py`): Microsoft neural voices via the free `edge-tts` package - English
  (Ava female / Andrew male) and **native Bangla** (Nabanita female / Pradeep male), chosen per sentence by
  script. Online only (the spoken text goes to Microsoft); Kokoro takes over offline. `voice.tts_engine = "edge"`.
- Word-by-word subtitles (`voice/playback.py`): one gap-free player for all voices fires the words as they are
  heard (exact timings from Edge, estimated for Kokoro); the orb shows them instead of the whole reply.
- Voice commands: "use a male voice" / "switch to female voice"; "speak Bangla" / "bangla te kotha bolo" /
  "বাংলায় বলো" (answers in natural Bangla, hears Bangla); "speak English". Applied live and saved.
- Barge-in: say her name while she talks - "Neko, stop" silences her; "Neko, wait - <request>" switches to the
  new request. Her own voice can't trigger it (needs her name). Real-time simulation 3/3. `voice.barge_in`.
- Brain map (`memory/brain.py`, `ui/brain_view.py`): rotating 3D-style graph of memories, projects, documents,
  vocabulary, tools, brains and voice; inspector, search, filter legend, double-click opens files.
- Tool armory (`diagnostics/armory.py`, `ui/armory_view.py`): every ability with an honest status pill.
  Both open from the tray, the orb menu, or by voice ("show me your brain", "open your tool armory").
- Office installer: `scripts/install/install.ps1` (check PC -> install uv/Python, packages, portable Ollama,
  voice + speech models, GPU-sized AI models -> profile with name, assistant name, female/male voice,
  Bangla, optional keys -> shortcuts, self-test). `scripts/build-dist.ps1` builds `NEKO-Setup.zip` and refuses
  to package personal files or anything that looks like a key. Guide: docs/INSTALL_OFFICE.md.
- `desktop-16gb` profile updated for the office RTX 5060 Ti 16 GB (qwen3:14b, 16k context).
## [0.6.2] - 2026-10-28 - fixes from the first real cloud session

### Fixed (from the owner's log: "Dishab Manual from the download and summarize it" went wrong 6 times)
- The cloud brain never used tools and pretended ("I'm opening it... couldn't locate it"), twice replying
  empty: cloud brains now use real function calling. Live: "how much RAM is free?" -> system_status, 1.2 s.
- File requests with the verb after the name weren't recognised; near-miss names ("Dishab" ~ "Hisab") and
  spelled names ("H-I-S-A-B") now match; document names from Downloads/Desktop/Documents are in the speech
  vocabulary. Live: the exact sentence found Hisab-Manual.pdf and Gemini summarised it in 5 s.
- When a document can't be found she asks where it is, and your next short answer completes the request.
- Odd spaces in cloud replies (narrow no-break spaces) are normalised for the voice.
## [0.6.1] - 2026-10-28 - cloud brains live

### Fixed
- Cloud model choice is probed, not guessed: Groq's llama-3.3-70b is retired and Gemini's newest 3.8-flash
  timed out, so each candidate is test-asked once a day in the background and the first one that answers is
  used (cached in `cloud_models.json`). "Think briefly" (`reasoning_effort: low`) for speed; medium for deep work.

### Verified live with the owner's free keys
- Groq `openai/gpt-oss-120b`: first words 0.6-2.0 s, correct answers. Gemini `gemini-3.6-flash`: deep
  planning question answered in 6.8 s.
## [0.6.0] - 2026-10-28 - instant listening, PC control, free cloud brains, "upgrade yourself"

### Added
- Live listening (GPU): captions of what you're saying appear while you talk, and when what you said is
  already a complete request she stops waiting after 0.6-0.9 s of quiet. Simulated in real time with the
  real model: request ready 0.7-0.9 s after you stop (was 2.5 s + up to 6 s "unfinished" wait). If you keep
  talking right after an early end, the first answer is dropped and the whole sentence is used instead.
  Timings (never words) are logged per utterance.
- PC control (`tools/pc.py`): open any installed app (Start Menu, 196 found), website, file, folder or
  Settings page; volume/mute/media keys; focus/minimise/maximise/close windows; type text; lock, sleep,
  restart, shut down (30 s countdown, "cancel the shutdown"). Common commands run instantly without the
  model. Risk levels: sleep/typing ask (Level 2), restart/shutdown ask every time (Level 3). Live:
  "open calculator" 1.7 s, "close calculator" 0.6 s.
- Free cloud brains (`models/cloud.py`): Groq (fast, smart everyday brain) and Google Gemini (~1M-token
  context: whole PDFs, deep thinking, study notes in one go), used only after you paste a free key in
  Command Center > Settings. Local model takes over in the same turn when a free limit is hit or you're
  offline (that brain rests 10 min). Sensitive requests always stay local.
- "Upgrade yourself to ...": Claude Code changes N.E.K.O.'s own code following AGENTS.md, with tests and
  docs, after your approval. She never installs code she found on the internet by herself.

### Fixed
- "close calculator" made Neko quit herself.
- She claimed she could not shut down the PC or open apps; her capability list now matches reality.
## [0.5.5] - 2026-10-28 - 10x faster, more accurate hearing; auto-compacting memory

### Added
- Speech recognition on the GPU with the bigger `large-v3-turbo` model (owner approved the downloads:
  NVIDIA cuBLAS + cuDNN ~2.0 GB in the venv, model 1.5 GB in `D:\NEKO-Data\models\whisper`).
  Measured next to llama3.2:3b on the RTX 3050: 0.5 s per sentence (was 3.1 s on the CPU), 3.4 of 4 GB
  VRAM in use. Without the word list it hears Bangla words closer ("Operadhi Bangla" vs "operati-Bangla").
  Any GPU problem falls back to `small` on the CPU automatically. The model loads when listening starts.
- Auto-compaction like Claude Code: when a conversation grows past ~40 messages, the oldest are folded
  into a rolling summary in the background (no delay to the reply); the newest 30 stay word for word.
  Live: 70 messages -> 8 short notes in 3 s.
- Recall from all saved conversations: "what did I tell you about my sister earlier?" searches every past
  message (new full-text index) and shows her the matching lines with dates (fenced as untrusted).

### Changed
- Database schema 2 (`0002_conversation_compaction.sql`): `conversations.summary_upto` + `messages_fts`.
  A verified backup is made automatically before the upgrade.
- The old summary (rebuilt from the last 40 messages, which lost everything older, and ran before the
  reply) is gone.
## [0.5.4] - 2026-10-28 - hears your words right (personal vocabulary), better song picks

### Added
- Personal vocabulary (`voice/vocabulary.py`): names and words you use are given to speech recognition
  as a spelling hint. Measured with synthetic voices: "up a Radhi Bangla song" -> "Oporadhi, Bangla song",
  "HISSEP project" -> "Hisab project", "Nico" -> "Neko"; ordinary sentences unchanged. Sources:
  `voice.vocabulary` (owner's config seeded with Bangla words/artists), `vocabulary.txt` in the data
  folder, and project folder names.
- "Neko, learn the word Oporadhi" / "add Tahsan to your vocabulary" adds to it (no model involved).

### Fixed
- Song search picked a lecture ("...Opera: World Premiere"): results are now ranked for real songs
  (Music category, song-like titles, normal length; reactions/lectures/podcasts pushed down), and
  "song" is added to bare searches. Live: "oporadhi" -> Arman Alif - Oporadhi.
- "Could not open file": if a stream won't start, the next result is tried (up to 3).
## [0.5.3] - 2026-10-28 - "pause" works while music plays

### Fixed
- Saying "pause" during music did nothing: the speakers kept the microphone "loud", so the listener
  recorded one 60 s blob of song + voice and then ignored "pause" (no name). While music plays she now
  listens in 4 s windows, accepts short commands without her name ("pause", "stop", "resume", "louder",
  "quieter", "turn it up/down"), hints those words to the recogniser, and no longer treats lyrics as
  follow-up commands. Measured on synthetic speech over music-like sound: all three commands recognised
  when the voice is louder than the music; only "stop" when they're equally loud.

### Added
- Pause / resume / stop music in the orb's right-click menu and in the tray menu.
## [0.5.2] - 2026-10-28 - faster voice replies, finds files by name, honest about her settings

### Fixed
- **Settings never reached the real app.** Commands run from the Claude desktop app see a hidden copy of
  `%LOCALAPPDATA%` (Windows app virtualization), so earlier config edits (internet, folders, memory size,
  voice tuning) only changed that copy. The owner's real `config.toml` is now updated (old one backed up as
  `config.toml.bak-<time>`), and the Start Menu shortcut was recreated where Windows can see it.
- Two copies of Neko could run at once, both listening and answering: a per-user lock now allows one.
- Long spoken requests were dropped ("utterance handling failed: timeout" in the real log, 3 times
  tonight): the transcription time limit now grows with the recording.
- "Read hisab manual pdf": she searches the allowed folders by name (your own folders first, "in
  downloads" narrows it, identical copies count once) and reads it herself, instead of the model guessing a
  path and then claiming PDFs need internet. With a document loaded she answers from it (no tool hunting).
- She invented menus ("Tools > Allowed Apps") when asked how to enable internet: questions about her
  settings are now answered from the real settings, and her prompt states the facts about herself.

### Added
- Spoken replies start after the first sentence instead of after the whole answer (`ui/live_speech.py`,
  `voice.base.TextStream`, Kokoro streaming): measured first sentence after ~1.0 s on a short question
  and ~2.7 s on a PDF summary (whole answer 7.1 s). Code is never read aloud; long answers stop after
  ~650 characters (the rest stays on screen).
- Instant feedback: the orb shows "got it..." the moment you stop talking, the caption shows what she
  heard, slow jobs get a short "Mm, one sec.", and her colour changes as soon as she starts answering.
- Command Center > Settings: "Allow internet" checkbox (asks to confirm, applies immediately).
- `scripts/restart-neko.ps1`.
## [0.5.1] - 2026-10-28 - music from YouTube

### Added
- "Neko, play <song>": finds the song on YouTube (optional `yt-dlp`, search only - nothing is saved
  to disk) and streams its audio in the background with Qt Multimedia (`neko/media`,
  `ui/music_player.py`). "Pause / resume / stop the music", "louder / quieter". Handled without the
  language model; `play_music` is verified by the player actually reporting "playing".
- Music ducks to 25% while she listens or speaks, and comes back afterwards. Emergency stop stops it.
- Setting `ui.music_volume` (default 0.6). Needs `privacy.allow_network`.

### Changed
- Owner's choice: `tools.cloud_documents = false` - documents stay on this PC.
- Longer listening, now in `[voice]` settings: `pause_seconds` 1.6 (was 1.3), `addressed_pause_seconds`
  2.5 (was 1.8), `wait_rest_seconds` 6 (was 4), `max_speech_seconds` 60 (was 30). Owner's config:
  `follow_up_seconds` 15 (was 8).
## [0.5.0] - 2026-10-28 - "show me" panel, documents & study notes, multitasking, orb presence

### Added
- "Show me ..." side panel (`ui/visual_panel.py`): a teal/gold holographic card beside the orb with
  the answer as Markdown plus a Wikipedia picture when internet is on (`tools/web.wiki_picture`).
  Slides in, closes itself after `ui.visual_panel_seconds` (not while the mouse is over it);
  "show me again" reopens the last one without asking the model (`ev.VISUAL`, `Coordinator.last_visual`).
- Documents (`neko/documents`): `read_document` (PDF via optional `pypdf`, Word .docx and PowerPoint
  .pptx with the standard library, text files), `explorer_selection` ("what's this file?" = the file
  selected in File Explorer) and `make_pdf` (Markdown -> PDF, verified; Qt renderer in `ui/pdf_render.py`).
- Study notes: "I have an exam, make simpler notes and a cheat sheet from this PDF" -> a 3-4 page
  easy-read notes PDF + a one-page cheat sheet in `tools.study_folder`, shown on the panel with
  "Open PDF" buttons. Claude Code reads the document when `tools.cloud_documents = true`, otherwise
  the local model studies it part by part. Never overwrites earlier notes.
- Multitasking (`ui/bridge.py`): two lanes - a long job (Claude Code project work, study notes) runs
  in the background while normal chat continues; further requests queue as "next up". A finished
  background job is announced after the current reply instead of interrupting it.
- Orb presence: dissolves after `ui.idle_hide_seconds` idle (default 4 min) and re-materialises with
  a cyberpunk entrance (rings draw in, glitch scan lines, sweep) on her name, a reply or typing.
- Desktop + Start Menu shortcuts use the new orb icon (`packaging/neko.ico`, also the tray icon).

### Fixed
- "Shows listening but doesn't answer": the orb only lights up for speech addressed to her
  (after her name / in the follow-up window), not for background talk.
- Requests spoken while she was busy were dropped ("say it again"); they now run or queue.
- Visual answers no longer start with filler ("Okay, I'll try to explain...").

### Changed
- User config: `models.num_ctx` 8192 (more conversation fits), read access to D:\, E:\, F:\ and the
  user's Desktop/Documents/Downloads/OneDrive/Pictures (credential folders stay blocked by
  `security/paths.py`). New settings: `ui.idle_hide_seconds`, `ui.visual_panel_seconds`,
  `tools.cloud_documents`, `tools.study_folder`. No database schema change.
## [0.4.0] - 2026-10-27 - orb-only holographic UI, internet, Claude Code, smarter + smoother

### Added
- Orb-only window (`ui.style = "orb"`): just the floating HoloCore + fading subtitles; drag, click
  (stop), double-click (Command Center), right-click menu, type-to-chat (`ui/orb_window.py`).
- HoloCore (`ui/holo.py`): teal/gold ring HUD after the owner's reference; distinct motion for idle
  (breathing), listening (inward ripples), thinking (fast counter-spin), coding (gear steps + radar
  sweep + filling bars), speaking (outward ripples + waveform); colour follows her emotion.
- Internet: `web_search` (DuckDuckGo form POST) and `read_web_page`, with private/local address
  blocking (SSRF guard) and untrusted fencing (`tools/web.py`).
- Coding like Claude Code: project questions/tasks go to the installed Claude Code CLI (read-only by
  default; file edits need approval each run); local `analyze_project` fallback (`tools/dev.py`).
- Smarter references (`orchestration/smart.py`): "this thing" -> looks at the screen; "D drive project
  folder ... HISAB" -> D:\PROJECT\HISAB; ambiguous -> asks which project.
- "Close yourself" / "go to sleep" closes N.E.K.O. (answered without a model); PC shutdown is refused honestly.
- ElevenLabs cloud voice now falls back to Kokoro automatically when credits run out.
- 17 tests (152 total).

### Changed / fixed
- Voice: gap-free continuous playback (next sentence synthesised while one plays), 8 ms fades,
  natural pauses, high-latency buffer (fixes the short "cracks"), speed 0.92, laughter words no longer
  read aloud ("haha" -> playful tone).
- Emergency stop no longer makes every later message reply "Stopped." - chat continues, actions stay
  blocked until Resume (right-click the orb).
- Fabrication guard also catches "(checking system status)" style claims; capability list in the
  prompt now follows the real settings (internet on/off).
- Emotion tags in the middle of a reply are removed.

## [0.3.0] - 2026-10-27 - always listening + expressive female voice

### Added
- Always-on listening with the name as wake word ("Neko, …"), follow-up window, tray toggle;
  emergency stop turns the mic off (`voice/listener.py`).
- Expressive female persona (Kokoro `af_heart`), per-reply emotion (tag parsing + inference from the
  reply) shaping speed and voice blend; emotion tags never shown (`core/emotion.py`).
- 12 tests (136 total): wake-name parsing, VAD, listener flow, emotion parsing/streaming, BOM tolerance.

### Fixed
- Speech recognition crashed when "auto" picked CUDA without cuBLAS: now falls back to the CPU.
- Config loader tolerates a UTF-8 byte-order mark (Notepad / PowerShell 5.1). Removed BOMs that a
  PowerShell edit had added to `defaults.toml`, `pyproject.toml`, `__init__.py` and `theme.py`.
- Default personality is warm and playful instead of "calm, precise" (greetings sounded robotic).

## [0.2.0] - 2026-10-27 - natural voice + golden neural hologram

### Added
- Kokoro-82M natural local voice (default) with sentence streaming and live loudness; automatic
  SAPI fallback; optional ElevenLabs cloud adapter (off; needs cloud permission + env-var key).
- "Aurum" golden holographic theme (default) and a live neural-network core: signals travel along
  axons and cascade through neurons, driven by tokens, tool calls, thinking, listening and speaking.
- Adaptive animation frame rate (12/24 fps) and batched drawing.
- Research ledger R10 (AirLLM and other large-model-on-small-GPU projects) and R11 (voices).
- 7 tests (124 total).

### Fixed
- Workaround for kokoro-onnx 0.4.9 passing `speed` as int32 to v1.0 models.

## [0.1.1] - 2026-10-27 - installed and tested with real models

### Fixed (found in live testing; details in docs/STATUS.md §3)
- Native Ollama function calling replaces the text tool protocol (llama3.2 invented tool results);
  bare-JSON tool calls accepted; fabricated-tool-result guard.
- Tools only offered when relevant; explicit capability list in the system prompt.
- CPU-only embedder + `OLLAMA_MAX_LOADED_MODELS=2` (stopped per-message model reloads).
- Live loaded-model state in the router; freed VRAM counted; role-dependent loaded bonus.
- qwen3 thinking handled (`think` flag, leaked `</think>` stripped, deep-think mode); planning on llama3.2.
- Automatic embedding of new memories; correct tokens/s from `eval_duration`.
- setup.ps1 Python discovery; start-ollama.ps1 under PowerShell 5.1; approval detail formatting;
  Windows 11 detection; progress bar legibility.

### Added
- `scripts\start-neko.ps1` (one-click start, used by the Desktop shortcut) and `scripts\stop-neko.ps1`.
- 7 new tests (117 total).

## [0.1.0] - 2026-10-27 - first developer preview (not yet run on real models)

### Added
- Dependency-free core engine: validated TOML config, SQLite schema v1 with migrations,
  backup/verify/restore, memory with provenance/versioning/expiry, FTS5 + optional
  embedding retrieval, context budgeting.
- Model gateway with Ollama and OpenAI-compatible adapters, resource-aware router with
  logged reasons, model lifecycle (one resident model on 4 GB GPUs), read-only Ollama
  disk inventory.
- Permission engine (risk levels 0-3, prohibited tools, narrow standing rules,
  emergency stop, untrusted-content escalation), path policy, secret redaction,
  prompt-injection fencing.
- Tool gateway with schemas, timeouts, verification and audit; 8 built-in tools.
- Coordinator loop with streaming, tool calls, memory commands, honest failure messages.
- PySide6 HUD with animated core, Command Center, approval dialogs, tray, first-run screen.
- Voice adapters (faster-whisper push-to-talk, Windows SAPI / Piper TTS, optional openWakeWord).
- PowerShell setup (dry-run default), doctor, launch, start-ollama, backup, restore, update, uninstall.
- Full documentation set and 110 automated tests (all passing on Python 3.11 and 3.14).

### Known limitations
- The desktop UI, voice and real-model paths have not been executed yet (PySide6 and voice
  packages are not installed on the development machine; no model server was started).
