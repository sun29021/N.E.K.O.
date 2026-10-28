# Voice design

> **Update 2026-10-27 (0.3.0): always listening + expressive female voice.**
> - `voice.always_listen = true`: the mic streams continuously; an energy VAD finds utterances, which
>   faster-whisper (CPU) transcribes. She answers when she hears her name (`voice.wake_names`: neko,
>   nico, niko, neeko, necko, nekko). The name can be at the start ("Neko, …") or the end ("…, Neko?").
>   "Neko" alone → "Yes?" and the next sentence is the command. After each answer you have
>   `follow_up_seconds` (8 s) to continue without the name. Tray menu → "Always listen" toggles it;
>   EMERGENCY STOP turns the mic off. Audio stays in memory only. While she speaks, the mic is ignored
>   (no voice barge-in). File: `voice/listener.py`.
> - Measured: synthetic-voice tests 6/6 correct (name at start, at end, alone, absent, follow-up),
>   ~2 s to recognise each utterance on the CPU. Whisper's `hotwords` option was tested and made it
>   *drop* the name, so it isn't used. A real human voice in your room isn't tested yet.
> - Voice `af_heart` (Kokoro, female). `voice.expressive = true`: warm persona, natural "hmm/oh!/aww",
>   and an emotion per reply (`core/emotion.py`). The model's tag (`[happy]`, or bare "happy!", "Calm
>   Mm-hm" as llama3.2 actually writes it) is hidden and sets speed + a voice blend (af_bella brighter,
>   af_nicole softer). If the tag is missing or contradicts the words, the emotion is inferred from the
>   reply text. Samples: `D:\NEKO-Data\voices\samples\neko_voice_*.wav`.
> - Not possible on this laptop: real humming/singing or cloned voices. Those need expressive TTS models
>   (Chatterbox, Orpheus, Dia) that want their own GPU; candidates for the optional 16 GB desktop.

> **Update 2026-10-27:** default speech output is now **Kokoro-82M** (natural, free, local, CPU):
> `voice/tts_kokoro.py`, voice `bm_george`. Measured: 3× faster than real time on the Ryzen 4800H.
> Speech starts after the first sentence (sentence-by-sentence synthesis), and loudness is reported 20×/s
> to the HUD core. Falls back to Windows SAPI automatically. ElevenLabs is an optional cloud adapter
> (`voice/tts_elevenlabs.py`), off by default and gated by `privacy.allow_cloud_models` + an API key in an
> environment variable. See RESEARCH_LEDGER R11.

## 1. Scope in v0.1
| Capability | State |
|---|---|
| Push-to-talk (hold mic button) | implemented (`voice/audio.py`, `ui/voice_controller.py`), **not run yet** |
| Local speech recognition (faster-whisper) | implemented, needs `-WithVoice` + a one-time model download |
| Spoken replies (Windows SAPI) | implemented, zero downloads, **not run yet** |
| Piper voices | adapter implemented; you install Piper and a voice yourself |
| Interrupt speech | Stop button / Ctrl+. cancels playback |
| Wake word "Hey Jarvis" | detector implemented (`voice/wakeword.py`); **not wired into the UI yet** (P2) |
| Streaming (word-by-word) transcription | not implemented — whole utterance is transcribed on release |
| Voice "barge-in" (talk over N.E.K.O.) | not supported (mic gated while speaking) |

## 2. Pipeline
```
[hold mic] -> PushToTalkRecorder (16 kHz mono int16, in memory, max 60 s)
[release]  -> (<0.3 s ignored) -> faster-whisper (VAD filter, beam 1, CPU int8)
           -> text shown in HUD input -> normal request path
reply      -> clean_for_speech (drops code blocks, links, markdown) -> SAPI/Piper
             SpeechGate.speaking = True  (mic + wake word ignore input) ... +0.3 s tail
```
Each stage is separate: capture (`PushToTalkRecorder`), VAD (inside faster-whisper's
`vad_filter`), STT (`FasterWhisperRecognizer`), orchestration (Coordinator), TTS
(`SapiSynthesizer`/`PiperSynthesizer`), playback (PowerShell SAPI process / `winsound`), and
cancellation (`CancelToken` kills the TTS process).

## 3. Echo control
Strategy: **half-duplex gating**. Capture can't start while N.E.K.O. speaks (pressing the mic stops
speech first), and the wake-word loop skips frames while `SpeechGate.speaking` is set, plus a 0.3 s
tail. Limitation: you can't interrupt by voice, only with the button or hotkey. With laptop speakers at
high volume, the 0.3 s tail may be too short for room echo. Headphones remove the problem entirely.

## 4. Models and resources
| Engine | Model | Size | Runs on | Notes |
|---|---|---|---|---|
| faster-whisper | tiny / base / **small** / medium | ~75 MB / 145 MB / 490 MB / 1.5 GB (int8, approximate) | CPU int8 by default | `local_files_only=True`: never downloads silently |
| SAPI | built-in Windows voices | 0 | CPU | English voices preinstalled; quality basic |
| Piper | e.g. `en_US-lessac-medium` | ~60 MB | CPU | GPL-3.0, separate exe; archived old repo → use OHF-Voice/piper1-gpl |

Expected latency (estimates, **benchmark needed**): small int8 on the Ryzen 4800H ≈ 1–3 s for a
5-second utterance. SAPI starts speaking in under 1 s.

## 5. Wake word feasibility
openWakeWord ships a pre-trained **`hey_jarvis`** model, so "Hey Jarvis" works without training.
Its **pre-trained models are CC BY-NC-SA 4.0**: fine for you personally, but not for commercial
redistribution. A custom phrase ("Hey Neko") needs training with the project's notebook (thousands of
synthetic clips, a GPU, about an hour). The training dependencies are dated (2022-era PyTorch/TF pins).
Wiring into the UI is planned (P2): a persistent "wake word listening" pill, an off switch, and no audio
retained.

## 6. Languages
| | English | Bangla (bn) |
|---|---|---|
| Recognition (faster-whisper multilingual) | good | **untested; expect poor accuracy**, especially with dialects. Published studies show generic Whisper struggles on Bangla; fine-tuned models (e.g. BanglaASR, Whisper-small fine-tune) do much better but aren't integrated |
| Speech output | SAPI/Piper OK | **no Piper Bengali voice exists**; SAPI has no Bangla voice by default (Windows may offer one as an optional language feature — unverified). Kokoro: Bangla not confirmed |
| Chat model | llama3.2 good | llama3.2 does not officially support Bangla; qwen3 is broadly multilingual — **untested** |

Setting `voice.stt_language = "bn"` forces Bangla recognition. Blank means auto-detect.

## 7. Privacy
- The microphone opens only while the button is held, or while the wake word is explicitly enabled.
- Audio stays in RAM and is discarded after transcription. (`voice.keep_recordings` exists in the
  config but **saving is not implemented**, deliberately.)
- Transcripts are treated like typed messages: stored only if conversation history is on.
- The HUD shows mic state ("mic ready", "Listening…").

## 8. Setup (later, manual)
See INSTALLATION_MANUAL §8: `setup.ps1 -Apply -WithVoice`, then a one-time
`faster-whisper` model fetch that you run and approve yourself (MODEL_GUIDE §4).
