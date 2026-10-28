# Roadmap

## Now: make v0.1 real (you, guided by INSTALLATION_MANUAL)
1. Setup + start Ollama + doctor (O1–O3).
2. First real chat (O4), first UI run (U1–U12), fix whatever small UI issues appear.
3. Run benchmarks P1–P3 and record them in STATUS.md.

## v0.2 (P1)
- Hash-locked dependencies (`--require-hashes`) in setup (audit O2).
- Verified ✓/✗ badges per tool step in Chat (O3); approval-summary sanitising (O6).
- Kill-able subprocess sandbox for state-changing tools (O4).
- Lesson approval prompt in the UI after verified tasks; feedback buttons (👍/👎 → `add_feedback`).
- Document search: index allowed folders into `documents` + FTS (txt/md/pdf text).
- Selected-window and region screen capture; HUD position memory per monitor.
- Optional global hotkeys (push-to-talk, emergency stop) via `RegisterHotKey`.
- GPU temperature soft limit pauses background work.
- Kokoro TTS adapter (better English voices, Apache-2.0).
- Backup rotation honouring `backup_keep`.

## v0.3 (P2)
- Wake word wired into the UI with an always-visible indicator ("Hey Jarvis"; custom phrase training guide).
- Windows UI Automation agent (pywinauto/uiautomation) with step verification.
- Optional web research tool (network permission, citations, untrusted fencing).
- Paired desktop: setup guide for TLS reverse proxy + token, `ca_file` pinning, health/capability
  checks, routing by observed speed.
- MCP client with pinned, reviewed servers mapped onto ToolSpecs.
- OCR-first screenshot pipeline (Windows.Media.Ocr) + tiling.
- Packaged one-folder build + installer; code signing.

## Research (needs a feasibility experiment first)
- Hand gestures with MediaPipe (CPU load alongside the LLM; never for approvals).
- Bangla STT fine-tuned model (BanglaASR / Whisper-small fine-tune) and Bangla TTS options.
- Speculative decoding with llama.cpp server for faster 4B models.
- PowerInfer with a ReLU-sparse model under `--vram-budget`.
- LoRA personalisation on the 16 GB desktop (only with a held-out evaluation set).
