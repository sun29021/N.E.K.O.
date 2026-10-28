# User manual

## 0. Starting and stopping (the easy way)
- **Start:** double-click **N.E.K.O.** (the glowing orb icon) on your Desktop, or press the Windows key
  and type "N.E.K.O.". It starts the model server hidden in the background if needed and opens the orb.
- **Stop:** say "Neko, shut down", or tray icon → Quit. Run `scripts\stop-neko.ps1` to also stop the
  model server and free GPU memory (or just restart the PC). To start again, use the Desktop icon.
- **She vanished?** After 4 quiet minutes the orb fades away, but she is still listening. Say "Neko"
  (or a request) and she reappears. Change the delay with `ui.idle_hide_seconds` (0 = never hide).

## 000. New in 0.8 - Neko on your phone
- **Telegram chat** (text, voice notes, photos, files) and **live calls** from your phone - set up in
  Command Center > Phone, step by step in docs/PHONE.md. Risky actions ask you on the phone.
- **Reminders**: "remind me at 6 to call Ammu", "remind me in 20 minutes to check the rice",
  "what are my reminders?", "cancel my reminders". She says it on the PC and messages your phone.
- **Learned skills**: let her do a few steps ("open Excel", "click Blank workbook"...), then say
  **"save that as monthly sheet"**. Next time: **"do the monthly sheet"**. "What skills do you know?",
  "forget the skill monthly sheet". Each step still asks for approval when it needs it.
- From the phone: "send me my screen", "is my laptop on?", "lock my PC", "play music on the PC".

## 00. New in 0.7
- **Natural voice** with subtitles that appear word by word as she speaks.
- **"Use a male voice" / "switch to female voice"**, **"speak Bangla"** (native Bangla voice) / **"speak English"**.
- **Interrupt her**: say "Neko, stop" while she talks, or "Neko, wait - play Believer" to change the request.
- **"Show me your brain"** - a 3D map of everything she knows; **"open your tool armory"** - all her abilities.
  (Also in the tray menu and the orb's right-click menu.)
- **Office PC**: see docs/INSTALL_OFFICE.md - one command installs everything.

## 0a. New in 0.6
- **She shows what she hears while you talk**, and answers ~1 s after you finish a complete sentence.
- **PC control:** "open Chrome / YouTube / my Downloads / bluetooth settings", "volume up", "mute", "next song",
  "close Discord", "minimise Word", "switch to WhatsApp", "search Google for ...", "type "hello"", "lock my PC",
  "put my PC to sleep", "restart / shut down my PC" (asks first, 30 s countdown; "cancel the shutdown").
- **Buttons and menus inside apps:** "in Calculator click Seven", "in Notepad open File > Save as",
  "what buttons are in this window?", "turn on dark mode in Settings". Anything like delete / send / pay /
  uninstall / sign out always asks you first; she never types passwords or clicks in security windows.
- **Free cloud brains:** Command Center > Settings > "Get a free key" next to Groq and Gemini. Sign up yourself,
  copy the key, paste it in the field, Save. From then on she uses the cloud brain (smarter, very fast) and falls
  back to the local one automatically. Free tiers have daily limits and may use what you send to improve their
  products; passwords and other sensitive requests always stay on your PC.
- **"Upgrade yourself to ..."** - Claude Code adds the feature to her code (you approve it first), then restart her.

## 0b. New in 0.5
- **Long conversations:** she keeps the last ~30 messages word for word and folds older ones into a running
  summary automatically (like Claude's auto-compact). Ask "what did I tell you about ... earlier?" and she searches
  all your saved conversations. Her working window is 8,192 tokens - the most this laptop's GPU can hold next to
  her voice; 500k-1M tokens would need a data-centre GPU.
- **She mishears a name?** Say or type "Neko, learn the word Oporadhi" (or "add Arman Alif to your vocabulary").
  She then spells it right when you speak. The list lives in `%LOCALAPPDATA%\NEKO\vocabulary.txt` and in
  `voice.vocabulary` in the config - edit freely. Typing always works perfectly if she keeps mishearing.
- **Internet on/off:** double-click the orb -> Settings -> tick **Allow internet** -> Save settings. Works at once.
- **Restart her:** run `scripts\restart-neko.ps1`, or quit from the tray and double-click the Desktop icon. Only one
  copy of Neko can run at a time.
- **Files by name:** "read hisab manual pdf" - she looks in your allowed folders (Downloads, Desktop, Documents,
  OneDrive, D:, E:, F:) and asks if there's more than one.
- **Listening time:** she waits 2.5 s of silence before deciding you've finished (1.6 s for background
  talk), and after she answers you have 15 s to keep talking without her name. Tune these in the
  `[voice]` part of `%LOCALAPPDATA%\NEKO\config.toml`: `addressed_pause_seconds`, `follow_up_seconds`.
  Longer pauses mean she starts answering a little later.
- **Music:** "Neko, play Believer by Imagine Dragons" finds it on YouTube and plays the sound in the
  background (no window, nothing saved). Then: "pause the music", "resume the music", "stop the music",
  "louder", "quieter". While music plays you can just say **"pause"**, **"stop"**, **"resume"** or **"turn it up"**
  without her name, or right-click the orb > Pause music. The music gets quieter while she listens or talks. With loud music, say her name
  clearly (or click the orb). Note: YouTube's terms only allow playback in their own apps, and this can
  stop working when YouTube changes its site.
- **"Show me ..."** ("show me how a jet engine works", "what does a black hole look like"): a panel opens
  beside her with the answer and a picture (from Wikipedia, when internet is on). It closes by itself
  after 90 s, or click ×. **"Show me again"** brings the last one back.
- **"What's this file?"**: open the folder in File Explorer, click the file, then ask. She reads PDF,
  Word (.docx), PowerPoint (.pptx) and text files. If several files are possible she asks which one.
- **Study help:** "I have an exam tomorrow - make simpler notes and a cheat sheet from this PDF." She
  makes a 3-4 page easy-read notes PDF and a one-page cheat sheet in `D:\NEKO-Notes\Study`. The panel
  shows the cheat sheet and has **Open PDF** buttons. With `tools.cloud_documents = true` (currently **off**: your documents stay on this PC)
  Claude reads the document, which is much better quality but sends that document to Anthropic. Set it to
  `false` to keep documents on this PC (the local model is slower and simpler). Always check important
  facts against your original material.
- **Two things at once:** while she works on a long job (a project with Claude Code, study notes) you can
  keep chatting. Anything else you ask is queued as "next up". **Stop** cancels the newest job.

## 1. First launch
`scripts\launch.ps1` (or the Desktop shortcut) opens a welcome window on a brand-new install. It tells you whether the model server is running
and which models were found, and explains the microphone, camera and approval policy. Click
**Let's go**. The **HUD** appears: a floating dark panel with a glowing core.

If the core is **grey** ("Model server offline"), start `scripts\start-ollama.ps1` in another window.
It turns cyan within ~15 s.

## 2. Talking by text
Type in the HUD box and press **Enter**. The core turns violet while it thinks, and the reply streams in.
For a bigger view, press **□** (or Ctrl+E) to open the **Command Center → Chat**. Under each reply
you'll see which model answered, *where* it ran (LOCAL), speed, and notes such as "Part of this
model runs on the CPU, so replies will be slower."

**Stop a reply:** ■ button or **Ctrl+.**

Useful things to say:
| Say | What happens |
|---|---|
| "Remember that I prefer short answers" | saved as a preference (no model needed) |
| "Remember that my project folder is D:\PROJECT" | saved as a fact |
| "What do you remember about my projects?" | answers using saved memories |
| "Forget my old address" | deletes the one matching memory, or lists several so you can choose |
| "Make a step-by-step plan for …" | everyday planning (llama3.2, ~30 s for a long plan) |
| "Think carefully about …" / "… in depth" | deep mode: qwen3:4b thinks silently first (~1–2 min, more careful) |
| "Fix this Python error: …" | uses the coding model if installed |
| "How much RAM is free?" | uses the read-only system_status tool |
| "List the files in D:\NEKO-Notes" | already allowed (also D:\PROJECT) |
| "Write a note in D:\NEKO-Notes called ideas.md saying …" | creates the note (replacing one asks you first) |
| "Open notepad" | allowed apps: Notepad, Calculator, Explorer |

## 3. Voice (optional, after installing voice)
**Hold** the 🎙 button, speak, **release**. The core turns green while listening, then "Transcribing…".
The text appears in the box and is sent. If "Speak replies aloud" is on, N.E.K.O. answers
with Windows' built-in voice. Press ■ to stop it talking.
The microphone is only on while you hold the button. No audio is saved.
Tips: speak after the core turns green; use headphones to avoid echo. Bangla recognition is
experimental (set Speech recognition language to `bn`).

## 4. Screenshots
Press **⧉**. The HUD hides for a moment, captures the screen under your mouse, then says
"Screenshot attached". Type your question, e.g. "What does this error mean?". This needs a vision model
(e.g. `gemma3:4b`, see MODEL_GUIDE). Without one, N.E.K.O. tells you so. Screenshots are never saved.

## 5. The HUD
| Control | Action |
|---|---|
| drag anywhere | move the HUD |
| □ / Ctrl+E | open the Command Center |
| – / Esc | hide (bring back from the tray icon) |
| ■ / Ctrl+. | stop the current reply/speech |
| Shift + ■, or Ctrl+Shift+F12 | **EMERGENCY STOP** |
| pills | where it runs (LOCAL), current model, mic state |

Core colours: cyan = ready · green = listening · violet = thinking · blue = using a tool · amber =
waiting for your approval · rose = error · grey = model server offline.

## 6. Approvals
When N.E.K.O. wants to change something, for example moving a file, an **approval window** shows what
will happen, the risk level, and whether it can be undone. **Deny** is the default button; you must
click **Approve** on purpose. High-impact actions also need the "I understand" box ticked.
If you don't answer within about 5 minutes, it counts as **Deny**.

Only approve things *you* asked for. If a document or web page "asks" N.E.K.O. to do something, it will
ask you first, and the reply will mention that the content contained instructions.

## 7. Emergency stop
The red **EMERGENCY STOP** in the Command Center (or Shift+■, Ctrl+Shift+F12, or tray → EMERGENCY
STOP) cancels everything, denies pending approvals, stops speech and blocks all actions until you press
**RESUME**. It can't undo an action that has already finished.

## 8. Memory
Command Center → **Memory**:
- search, and filter by status (active / pending_approval / superseded / expired / all)
- select a memory to see **where it came from** and **why it was used**
- **Approve** pending memories (things N.E.K.O. noticed but you didn't state), **Edit** (keeps the old
  version for audit), **Delete**, **Export**, **Clear conversation history**
- Turn learning off in Settings if you don't want N.E.K.O. to save anything.
Deleted memories may still exist in **older backups** until you delete those backup files.

## 9. Models and resources
Command Center → **Models & Resources** shows RAM/GPU memory bars, GPU temperature, power and disk,
installed models, and the **last routing decision**: which model was chosen and why the others were
skipped (not installed / not enough memory / remote disabled …).
**Model selection:** "Automatic (recommended)" or pin one model.
**Profiles** (Settings → Model profile): `existing-only` (no downloads) · `laptop-lite` (after adding
models) · `desktop-16gb` (only with a paired desktop).

## 10. Privacy settings
Local-only is the default. Network research, cloud models and remote computers aren't in the Settings
screen on purpose; they need a config-file edit (`privacy.allow_network`, `privacy.allow_cloud_models`,
`remote.enabled`). The Command Center header shows **local only** while all are off.
Other privacy controls: keep history on/off, learning on/off, message retention days, and
`privacy.log_message_content` (off: logs never contain what you say).

## 11. Offline mode
After setup, N.E.K.O. needs no internet at all. Chat, memory, tools, speech recognition (once its
model is downloaded), SAPI speech and screenshot analysis (with a local vision model) all work
offline. Downloading models and packages needs internet.

## 12. Terminal mode
`scripts\launch.ps1 -Chat` gives a text chat in PowerShell. Approvals are asked in the terminal
(type `yes`). Other commands (`.venv\Scripts\python -m neko …`): `doctor`, `models`,
`memory list|pending|approve|add|delete|export|import`, `backup`, `verify-backup <file>`,
`restore <file>`, `config-check --show`.

## 13. Daily routine
1. Start `scripts\start-ollama.ps1` (leave it open).
2. Start `scripts\launch.ps1`.
3. Chat. Approve or deny as needed.
4. Weekly: Command Center → Diagnostics → **Back up now** (or `scripts\backup.ps1`).
5. Quit from the tray icon, then Ctrl+C in the Ollama window.

Problems? See TROUBLESHOOTING.md.
