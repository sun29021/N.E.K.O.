# Model guide

N.E.K.O. **never downloads a model by itself.** You decide what to add, check the space and the
licence, then run one command. Every size below is the Ollama download size checked on 2026-10-27.

## 1. What you already have (no download needed)
| Model | Size | Good for |
|---|---|---|
| `llama3.2:3b` (Q4_K_M) in `D:\Ollama\models` | 2.0 GB | everyday chat, simple questions, summaries. English best; Bangla weak |

The default profile `existing-only` uses just this model. **You can start with zero downloads.**

> **Installed on 2026-10-27:** qwen3:1.7b, qwen3:4b, qwen2.5-coder:1.5b, gemma3:4b, bge-m3
> (bge-m3 was chosen instead of nomic-embed-text because it also handles Bangla). Your config uses
> `laptop-lite`. Measured roles: greetings → qwen3:1.7b, chat/planning → llama3.2:3b, code →
> qwen2.5-coder:1.5b, "think carefully" → qwen3:4b, screenshots → gemma3:4b, memory search → bge-m3 (CPU).
> Note: Ollama's `qwen3:4b` always "thinks" before answering (~1–2 min on this GPU), so it's reserved
> for deep mode.

## 2. Recommended optional models for this laptop (`laptop-lite` profile)
| Add | Command (Ollama must be running) | Size | What you gain | Licence (read before sharing) |
|---|---|---|---|---|
| Fast replies | `D:\Ollama\app\ollama.exe pull qwen3:1.7b` | 1.4 GB | quicker small talk | Apache-2.0 |
| Better reasoning | `... pull qwen3:4b` | 2.5 GB | planning, harder questions; partly runs on CPU | Apache-2.0 |
| Coding | `... pull qwen2.5-coder:1.5b` | 1.0 GB | code help | Apache-2.0 (avoid the 3b size: research-only licence) |
| Screenshots | `... pull gemma3:4b` | 3.4 GB | "explain this error/dialog/chart" | Gemma Terms of Use |
| Semantic memory | `... pull nomic-embed-text` | ~0.3 GB | memory search by meaning | Apache-2.0 |
| Semantic memory incl. Bangla | `... pull bge-m3` | ~1.2 GB | multilingual memory search | MIT |

Everything together is about **8–10 GB on D:**. D: currently has ~108 GB free.

### Before each download
```powershell
Get-PSDrive D | Select-Object @{n='FreeGB';e={[math]::Round($_.Free/1GB,1)}}
```
Keep at least 10 GB free afterwards. Then, in a **second** PowerShell window (the first runs
`start-ollama.ps1`):
```powershell
$env:OLLAMA_MODELS = "D:\Ollama\models"
D:\Ollama\app\ollama.exe pull qwen3:4b
D:\Ollama\app\ollama.exe list
```
Then set `profile = "laptop-lite"` in `%LOCALAPPDATA%\NEKO\config.toml` (or in Settings) and restart
N.E.K.O.

### Check a model's licence
```powershell
D:\Ollama\app\ollama.exe show qwen3:4b --license
```
Also read the model card on ollama.com/library or the publisher's Hugging Face page.

## 3. Higher-quality profile (optional desktop with ~16 GB VRAM — unverified hardware)
`desktop-16gb`: `qwen3:8b` (5.2 GB), `qwen3:14b` (9.3 GB), `qwen2.5-coder:7b` (4.7 GB),
`gemma3:12b` (8.2 GB), `bge-m3`. Pull these **on the desktop**, not the laptop. On the laptop a 8B
model would mostly run on the CPU (estimated 4–8 tok/s, unmeasured).

## 4. Speech models (only if you installed voice)
Speech recognition (faster-whisper "small", ~0.5 GB, from Hugging Face `Systran/faster-whisper-small`).
One-time download, run by you:
```powershell
cd D:\PROJECT\N.E.K.O
.venv\Scripts\python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('ok')"
```
After that N.E.K.O. loads it offline (`local_files_only=True`). Use `tiny` or `base` for speed,
`medium` (~1.5 GB) for accuracy.

Speech output:
- **Kokoro** (default, natural, free, local; installed 2026-10-27): two files in `D:\NEKO-Data\voices\kokoro`
  from https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.1
  - `kokoro-v1.0.onnx` 310 MB, SHA-256 `beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a`
  - `voices-v1.0.bin` 27 MB, SHA-256 `bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d`
  Pick a voice with `voice.kokoro_voice`: `bm_george` (default), `bm_fable`, `bm_lewis`, `bm_daniel`
  (British male); `am_michael`, `am_adam`, `am_onyx` (US male); `af_heart`, `af_bella`, `bf_emma`, … (female).
  Samples: `D:\NEKO-Data\voices\samples`.
- **Windows SAPI**: nothing to download; used automatically if Kokoro is unavailable.
- **ElevenLabs** (cloud, optional, off): set `voice.tts_engine = "elevenlabs"`, `voice.elevenlabs_voice_id`,
  `privacy.allow_cloud_models = true`, and the key with `setx ELEVENLABS_API_KEY "<key>"`. Everything spoken
  is then sent to ElevenLabs.
- **Piper** (better voices, GPL-3.0, separate program): download a Windows release from
  https://github.com/OHF-Voice/piper1-gpl (or the archived rhasspy/piper releases), plus a voice
  (`.onnx` + `.onnx.json`, e.g. `en_US-lessac-medium`, ~60 MB). Then set `voice.tts_engine = "piper"`,
  `voice.piper_exe`, `voice.piper_voice`. There is no Bangla Piper voice.

Wake word (optional): `setup.ps1 -Apply -WithWakeWord`. openWakeWord downloads its pre-trained
models on first use. The `hey_jarvis` model is CC BY-NC-SA 4.0 (personal, non-commercial use).

## 5. Removing a model
Only if you choose to, and only with Ollama's own command:
```powershell
D:\Ollama\app\ollama.exe rm qwen3:1.7b
```
Never delete files inside `D:\Ollama\models\blobs` by hand.

## 6. Provenance and checksums
Ollama verifies each layer's SHA-256 digest during `pull` (the blob file name *is* its digest).
`python -m neko models` lists the digests N.E.K.O. sees. For sharing rules see
SHARING_AND_DISTRIBUTION §3. Never bundle model files in a public release; tell people to pull from
the official library.

## 7. Fine-tuning?
Not recommended on a 4 GB GPU (RESEARCH_LEDGER R9). Use memories ("remember that…"), answer-length
and personality settings, and approved lessons instead.
