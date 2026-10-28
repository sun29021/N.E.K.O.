# Research ledger

All checks were made on **2026-10-27** unless noted. "Confidence" is about the *fact*, not the
technology. Nothing listed here was installed or downloaded. Items marked **Benchmark needed**
must be measured on the laptop before they are relied on.

Where a page could not be read directly, the entry says so (secondhand = search-result summary,
not the primary page).

---

## R1. Local inference runtime

**Question:** Which runtime should N.E.K.O. use on an RTX 3050 4 GB + 16 GB RAM Windows laptop?

| Candidate | Source | Findings | Decision |
|---|---|---|---|
| **Ollama** | https://docs.ollama.com/windows, https://docs.ollama.com/api, local install `D:\Ollama` | v0.40.9 already installed (portable zip). Bundles a llama.cpp `llama-server`, with CUDA 12/13 and Vulkan backends (seen in `D:\Ollama\app\lib\ollama`). REST API on 127.0.0.1:11434, `keep_alive` unload, `/api/ps`. The docs say the standalone zip "contains only the Ollama CLI and GPU library dependencies" and is meant to be run via `ollama serve`. | **Primary runtime.** It's already installed, the model is already downloaded, and its log proves it worked on this GPU. |
| **llama.cpp** (`llama-server`) | https://github.com/ggml-org/llama.cpp/releases | Latest pre-release tag **b11925**, published 27 Oct. Windows builds: CPU, CUDA 12.4, CUDA 13.4, Vulkan, OpenVINO, SYCL, ROCm. GGUF, partial GPU offload (`-ngl`), mmap, quantized KV cache, speculative decoding (draft models) — the release page itself didn't mention these features; they are documented in the repo. | **Secondary option** through the OpenAI-compatible adapter (`models/openai_compat.py`). Useful later for speculative decoding or finer control. Not needed for v0.1. |
| llama-cpp-python | (not re-checked) | Python bindings. Building with CUDA on Windows needs Visual Studio Build Tools and the CUDA toolkit. | **Rejected for v0.1.** Heavy Windows build chain, and it duplicates what Ollama already provides. |
| Hugging Face Transformers + bitsandbytes/AWQ/GPTQ | (general knowledge, not re-checked) | Full PyTorch stack (several GB). 4-bit loading works but is slower and more memory-hungry than GGUF on 4 GB. | **Rejected** for inference. Only relevant to optional fine-tuning (R9). |
| EXL2 / ExLlamaV2 | (not re-checked) | Fast on NVIDIA, but GPU-only. The model must fit fully in VRAM, which at 4 GB rules out most useful models. | **Rejected** for this GPU. |
| **KTransformers** | https://github.com/kvcache-ai/ktransformers | Apache-2.0, active (updates 15 Oct 2026). CPU/GPU hybrid aimed at huge MoE models. Its examples use a 24 GB GPU plus hundreds of GB of DRAM (DeepSeek-R1/V3: 382 GB). An AVX2-only CPU backend was added in March 2026. Native Windows support was added in Aug 2024; its current state is not described. | **Rejected.** Built for server-class RAM. Gives no benefit at 16 GB. |
| **PowerInfer** | https://github.com/SJTU-IPADS/PowerInfer | MIT. Keeps "hot neurons" on the GPU and the rest on the CPU. **Only supports ReLU/ReGLU-sparse models** (Falcon-40B, Llama-2 ReLU variants, ProSparse, Bamboo-7B). The FAQ says Qwen and Mistral are not supported. Windows with AVX2 is tested. Latest news item is 2026-01-05. Benchmarks use 11–24 GB GPUs. | **Rejected for default.** Model choice is too narrow and old. Possible research experiment later with `--vram-budget`. |

**What makes bigger models usable on modest hardware (verified mechanisms):** GGUF k-quant 4-bit
weights (Q4_K_M ≈ 0.6 bytes/param), partial layer offload (llama.cpp `-ngl`, done automatically by
Ollama), memory-mapped loading, quantized KV cache (`OLLAMA_KV_CACHE_TYPE=q8_0`, which needs flash
attention), and MoE models whose active parameters are small. **None of these make a model fast
once most layers run on the CPU.**

**Evidence from this laptop** (`D:\Ollama\serve.log`, 2026-10-23, produced by the earlier Ollama run,
not by me):
- `llama3.2:3b` Q4_K_M, 3.21 B params, `-c 4096`: **26 of 29 layers offloaded to GPU**.
  CUDA0 model buffer 1742 MiB + CPU 484 MiB, KV cache 400 MiB GPU + 48 MiB CPU, compute ≈ 125 MiB.
- Generation **~30 tokens/s**. Prompt processing **~1334 tokens/s** (429-token prompt).
- `mmap` disabled by Ollama on Windows+CUDA ("reason=windows_cuda").
- Repeated `llama-server GPU discovery watchdog timed out` warnings. Inference still used CUDA.
  `OLLAMA_VULKAN=true` was set in that shell, and Vulkan probing of the AMD iGPU is a plausible cause
  of the slow discovery. That is unconfirmed; `start-ollama.ps1` sets `OLLAMA_VULKAN=0` to test it.
- Cause of `Error: could not locate ollama app`: when no server is running, the CLI tries to start
  the tray app, which the portable zip doesn't include. Fix: run `ollama serve`. Confidence:
  medium-high. This is consistent with the docs plus a forum reading of the source code
  ([forum](https://forum.langchain.com/t/llama-server-process-has-terminated-invalid-argument-load-mode-with-ollama-client-0-32-6-and-langchain-ollama-1-1-0/4320)).

Confidence: high for the runtime choice. **Benchmark needed:** qwen3:4b and gemma3:4b
speeds with partial offload.

---

## R2. Language models

Ollama library pages read directly: https://ollama.com/library/qwen3, /gemma3, /qwen2.5vl, /qwen2.5-coder.

| Model (Ollama tag) | Download | Context | Use in N.E.K.O. | Licence (verify on model card) | Notes |
|---|---|---|---|---|---|
| `llama3.2:3b` | 2.0 GB (on disk) | 128K native; Ollama default 4096 on 4 GB VRAM | **Default chat** (existing) | Llama 3.2 Community License (custom; attribution + acceptable-use policy) | Measured ~30 tok/s here. Officially lists en, de, fr, it, pt, hi, es, th — **Bangla not officially supported**. |
| `qwen3:1.7b` | 1.4 GB | 40K | fast role | Apache-2.0 (ggml-org GGUF repo lists apache-2.0; secondhand for official) | Has a thinking mode; multilingual. |
| `qwen3:4b` | 2.5 GB | 256K | reasoning / planning | Apache-2.0 (secondhand) | Will partly spill to CPU at 4 GB. **Benchmark needed.** |
| `qwen3:8b`/`14b` | 5.2 / 9.3 GB | 40K | desktop profile | Apache-2.0 | Too big for this laptop's GPU. |
| `qwen2.5-coder:1.5b` | 986 MB | 32K | coding | Apache-2.0 (**3B size uses the Qwen Research Licence, non-commercial** — hence 1.5b) | |
| `gemma3:4b` | 3.4 GB | 128K | **vision** | Gemma Terms of Use (custom, use restrictions) | The 1b/270m sizes are text-only. |
| `qwen2.5vl:3b` | 3.2 GB | 125K | vision alternative | Qwen licence for 3B is research/non-commercial (verify) | |

The Ollama "vision" search page also listed unfamiliar 2026 models (e.g. "d3", "bonsai-2",
"nemotron-3.5-bolt"). **I did not verify them**, so they are not recommended.
Confidence: high for sizes (read directly), medium for licences (open each model card before sharing).

---

## R3. Embeddings and vector search

| Option | Source | Finding | Decision |
|---|---|---|---|
| `nomic-embed-text` (Ollama) | https://ollama.com/search?c=embedding | English-focused, small (~274 MB, size from general knowledge) | **Default** optional embedder |
| `bge-m3` (Ollama, 567M params) | same | Described as multilingual | Recommended if you store **Bangla** memories |
| `embeddinggemma` 300m, `qwen3-embedding` 0.6b, `granite-embedding` 278m (multilingual) | same | Available | Alternatives |
| **sqlite-vec** | https://github.com/asg017/sqlite-vec | Apache-2.0/MIT, Windows + Python supported, **"pre-v1, expect breaking changes"** | **Not used in v0.1.** A brute-force cosine in Python over ≤10k memories is fast enough and adds no dependency. Revisit if memories grow past ~20k. |
| SQLite **FTS5** | Verified locally: available in Python 3.14.6 (SQLite 3.50.4) and 3.11.17 (SQLite 3.53.1) | Built in | **Used** for lexical search |

Decision: hybrid FTS5 + optional embeddings stored as float32 BLOBs. Confidence: high.

---

## R4. Speech recognition

| Option | Source | Finding | Decision |
|---|---|---|---|
| **faster-whisper** (CTranslate2) | https://pypi.org/project/faster-whisper/ (search summary, secondhand) | Current builds target CUDA 12 + cuDNN 9. Python ≥3.9. Version 1.2.1 seen in package metadata. MIT. | **Default STT** (push-to-talk), CPU int8 by default so the GPU stays free for the LLM |
| whisper.cpp | (not re-checked) | Fast C++, Vulkan/CUDA builds | Alternative if Python wheels are a problem |
| Bangla ASR | https://arxiv.org/abs/2507.01931 ; https://huggingface.co/bangla-speech-processing/BanglaASR | Generic Whisper is weak on Bangla and very weak on dialects. A Whisper-small fine-tune reports 4.58 % WER on Common Voice (self-reported). Wav2Vec-BERT beat Whisper in a 2025 study. | **Bangla voice input is "experimental / untested".** A fine-tuned model is a P2 research item. |

## R5. Text-to-speech

| Option | Source | Finding | Decision |
|---|---|---|---|
| Windows SAPI (System.Speech) | Built into Windows | Offline, zero download, robotic but reliable | **Default** |
| **Piper** | https://github.com/OHF-Voice/piper1-gpl ; https://github.com/rhasspy/piper/blob/master/VOICES.md | Development moved to `OHF-Voice/piper1-gpl`, **GPL-3.0**, "looking for maintainers". The old rhasspy/piper repo was **archived Oct 6 2025**. Voice list has en_US lessac/amy/ryan (low/medium/high). **No Bengali voice**; Hindi and Nepali exist. | Optional. Run as a **separate executable** (not imported, not bundled) so N.E.K.O.'s MIT code isn't affected by the GPL |
| **Kokoro-82M** | https://huggingface.co/hexgrad/Kokoro-82M | Apache-licensed weights. v1.0 covers 8 languages / 54 voices; **Bangla not confirmed**. Needs the `kokoro` + `misaki` packages and espeak-ng. | P1 candidate (better quality), not in v0.1 |

## R6. Wake word

| Option | Source | Finding | Decision |
|---|---|---|---|
| **openWakeWord** | https://github.com/dscripka/openWakeWord | Code Apache-2.0. **Pre-trained models (incl. `hey_jarvis`) CC BY-NC-SA 4.0.** On Windows only onnxruntime is used. Last release mentioned: v0.6.0 (2024-02-11). Custom phrases need training (Colab notebook, thousands of synthetic clips). | **Optional, off by default.** "Hey Jarvis" is feasible for **personal, non-commercial** use. A custom "Hey Neko" needs training. Don't bundle the model in a commercial release. |
| Community Windows training (hawake-wakeword) | https://github.com/IT-BAER/hawake-wakeword | Windows install script + web UI. Upstream training pins 2022-era PyTorch/TensorFlow | Pointer only |

## R7. Desktop UI

| Option | Source | Finding | Decision |
|---|---|---|---|
| **PySide6** | https://pypi.org/project/PySide6/ | 6.12.0 (8 Oct 2026). Requires Python ≥3.10, <3.16 — **supports 3.14**. LGPL-3.0/GPL. | **Chosen.** One language (Python), native frameless/translucent/always-on-top windows, QPainter animation, high-DPI, accessibility |
| Electron/Tauri + web | — | Adds Node/Rust and a second process, 100–300 MB RAM overhead | Rejected: overhead not justified on 16 GB |

LGPL note: N.E.K.O. uses PySide6 as an unmodified, dynamically linked library installed by pip,
which LGPL allows. Don't statically bundle it in a closed fork.

## R8. Agent frameworks and MCP

| Option | Finding | Decision |
|---|---|---|
| LangGraph / AutoGen / CrewAI (not re-checked in this session) | Large dependency trees, designed for cloud LLMs with reliable tool calling. Small local models call tools poorly | **Not used.** A ~400-line custom coordinator with explicit policy is easier to audit |
| MCP (Model Context Protocol) | An integration standard, not a brain. Servers run arbitrary code | **Not used in v0.1.** Design for optional, pinned, reviewed servers in `TOOLS_AND_MCP.md` |

## R9. Fine-tuning (LoRA/QLoRA)

General knowledge, not re-checked: QLoRA on a 3–4B model needs about 6–10 GB VRAM for useful batch
sizes. 4 GB is marginal even with Unsloth-style optimisations, the run takes hours, and there is a
real risk of overfitting a few hundred personal examples. **Decision:** no fine-tuning in v0.1. Use
retrieval, preferences, prompt profiles and verified-outcome learning instead. Revisit on the optional
16 GB desktop (P2 research).

---

---

## R10. "Run huge models on small GPUs": AirLLM and similar (checked 2026-10-27)

| Project | Source | What it really does | Speed on hardware like yours | Verdict for N.E.K.O. |
|---|---|---|---|---|
| **AirLLM** | https://github.com/lyogavin/airllm (Apache-2.0, active: v3.0 2026/06, training support 2026/09) | Loads **one transformer layer at a time** from disk into the GPU, runs it, discards it, repeats for every layer, **for every token**. VRAM ≈ one layer (claims 70B in ~4 GB, 405B in ~8 GB). | No official tok/s figures. Community reports: ~0.7 tok/s best case on fast NVMe, down to minutes per token. Theoretical floor for FP16 70B ≈ 140 GB ÷ disk speed ≈ **20 s/token on Gen4 NVMe** ([analysis](https://dev.to/umesh_malik/run-70b-llm-on-4gb-gpu-airllms-real-tradeoff-19oh), [guide](https://tutorials.technology/tutorials/run-large-llm-small-gpu-airllm-2026.html)). Also needs ~140+ GB free disk for the split layers, PyTorch + transformers (~5 GB), and Windows isn't mentioned. | **Not for conversation or voice.** A one-sentence reply would take minutes to hours. Possible as an overnight "batch question" tool on the 16 GB desktop. Research only. |
| **llama.cpp RPC** | https://github.com/ggml-org/llama.cpp (`rpc-server`) | Splits one model's layers across several computers over the LAN | Network-bound; usable over gigabit Ethernet | **Best fit for laptop + desktop** later: the desktop holds most layers. P2, together with R6 of the ROADMAP |
| **prima.cpp** | https://huggingface.co/papers/2504.08791 | Research fork of llama.cpp for home clusters (mixed CPU/GPU, low RAM/VRAM, Wi-Fi) | Paper claims 70B-scale on home devices | Watch; research |
| **distributed-llama** | https://github.com/b4rtaz/distributed-llama | Tensor parallelism across devices over Ethernet | Scales with devices | Alternative to llama.cpp RPC; research |
| **bitnet.cpp** | https://github.com/microsoft/BitNet (MIT, active July 2026) | Inference for 1.58-bit ("ternary") models on CPU; claims 2.4–6.2× x86 speed-ups, "100B at 5–7 tok/s on one CPU" (vendor claim) | Plausible for the 2.4B BitNet model on 16 GB RAM; needs a Visual Studio + Clang source build | Interesting for a CPU-only "fast brain"; models are still small/weak. Research |
| **KTransformers** | (R1) | CPU/GPU hybrid for huge MoE models | Needs 24 GB GPU + hundreds of GB RAM | Rejected (R1) |
| **PowerInfer** | (R1) | Hot/cold neuron split | ReLU-sparse models only | Rejected for default (R1) |
| **Ollama / llama.cpp partial offload** | in use | Q4 GGUF + layers split GPU/CPU | Measured: 3–4B models 22–115 tok/s on your RTX 3050 | **What N.E.K.O. uses.** The practical way to get the most model per GB today |

**Bottom line:** no software can make a 70B model *fast* on a 4 GB GPU. Speed is limited by how
many bytes must be read per token. AirLLM trades speed for size, and the trade is extreme.
For a smarter N.E.K.O. on this laptop, the realistic paths are: better small models as they
appear (Qwen/Gemma/Llama 3–8B Q4), the deep-think mode, and later the desktop over LAN
(llama.cpp RPC or a remote Ollama).

## R11. Natural voice: ElevenLabs vs free local voices (checked 2026-10-27)

| Option | Licence / cost | Runs | Quality | Decision |
|---|---|---|---|---|
| **ElevenLabs** | Cloud. Free plan: 10,000 credits/month, commercial use apparently not included; Starter ~$6/month ([pricing](https://elevenlabs.io/pricing)) | Internet only; your text goes to their servers | Excellent | **Optional adapter, off by default** (`voice/tts_elevenlabs.py`); needs `privacy.allow_cloud_models = true` + an API key in an environment variable |
| **Kokoro-82M** via kokoro-onnx | Weights Apache-2.0, wrapper MIT; free | **Local CPU** (onnxruntime), espeak-ng bundled | Very natural; 54 voices (28 English, US/UK) | **Default.** Measured here: 2 s to make 7 s of speech (3× faster than real time); whisper transcribed all 4 tested voices perfectly |
| Chatterbox (Resemble AI) | MIT | GPU preferred | Excellent, voice cloning | Too heavy alongside the LLM on 4 GB; P2 for the desktop |
| Dia / Sesame CSM / Orpheus | Apache-2.0 / Llama licence | GPU, slow | Very expressive | Desktop-only candidates |
| Piper | GPL-3.0 | CPU | Good, a bit robotic | Optional (kept) |
| Windows SAPI | built-in | CPU | Robotic | Automatic fallback |

Source for the open-model overview: [tts.ai 2026 guide](https://tts.ai/blog/open-source-text-to-speech-guide-2026/) (a vendor page,
not an independent benchmark). Bug found: kokoro-onnx 0.4.9 passes `speed` as int32 to v1.0 models
that expect float (ONNX Runtime error). N.E.K.O. overrides that one method (`voice/tts_kokoro.py`).

## R12. Free "big brains" and ElevenLabs details (checked 2026-10-27)
| Option | Free? | Notes | Use in N.E.K.O. |
|---|---|---|---|
| **Claude Code CLI** (installed, v2.1.302) | uses the owner's Claude subscription | real coding agent; `claude -p` works non-interactively (live test: 15 s) | **coding + project analysis** (`ask_claude_code`) |
| Groq API | free tier, needs an account + API key; e.g. llama-3.3-70b 30 RPM / 1,000 req/day; gpt-oss-120b 1,000 req/day (third-party tables) ([eesel](https://eesel.ai/blog/groq-pricing), [benchlm](https://benchlm.ai/md/free-tier/groq.md)) | OpenAI-compatible | optional future "smart brain" (owner creates the key) |
| Gemini API | free Flash tier, limits changed in 2026 (5–10 RPM reported) ([agentdeals](https://agentdeals.dev/gemini-api-pricing-changes)) | OpenAI-compatible endpoint `generativelanguage.googleapis.com/v1beta/openai/` | optional |
| **ElevenLabs** | free plan ≈ 10,000 credits/month ≈ ~10 minutes of speech; no commercial use; API "limited" on free; Starter ~$5–6/month ([bigvu](https://bigvu.tv/blog/elevenlabs-pricing-2026-plans-credits-commercial-rights-api-costs/), [smallest.ai](https://smallest.ai/blog/elevenlabs-pricing-plans-cost-what-you-get-in-2026)) | best quality, cloud, needs account + key | optional; auto-falls back to Kokoro when credits run out |
| Google Cloud storage | paid | not needed: N.E.K.O.'s whole database is a few MB locally | not used |

## Still to verify (before first use)
1. qwen3:4b / gemma3:4b tokens/s and VRAM split on this laptop (PERFORMANCE_PLAN tests P1–P4).
2. Whether `OLLAMA_VULKAN=0` removes the GPU-discovery watchdog warnings.
3. Exact current licence text for every model you download (open the model card).
4. Pinned package versions in `pyproject.toml` resolve on Python 3.12 (`sounddevice==0.5.2` was not
   checked against PyPI in this session).
