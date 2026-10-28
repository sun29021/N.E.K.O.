# Performance plan

**Measured on 2026-10-27 through N.E.K.O.:** see STATUS.md §2. Highlights: llama3.2:3b 44–55 tok/s,
qwen3:1.7b ~87 tok/s, qwen2.5-coder:1.5b ~110 tok/s, qwen3:4b ~22–25 tok/s (partly on CPU), gemma3:4b
~18 tok/s (48 s per screenshot), whisper-small 2 s per 5 s of speech, model loads 3–6 s.
P1, P2, P4 and P5 are done; P3 and P6–P12 are still to do. The older log figure (~30 tok/s for llama3.2)
was lower than today's measurement.

## 1. Expected bottlenecks (in order)
1. **VRAM (4 GB).** Models above ~2.5 GB of weights spill layers to the CPU; speed drops sharply.
2. **Model switching.** Loading a model takes ~2–10 s (estimate). Switching roles (chat → vision)
   on one GPU means unloading and reloading.
3. **Vision prompts.** Image encoding plus thousands of image tokens on a partially offloaded 4B model.
   Expect 10–30 s per screenshot (estimate).
4. **STT on CPU.** faster-whisper small int8 on the Ryzen 4800H: ~1–3 s per 5 s utterance (estimate).
5. **Battery mode.** GPU/CPU clocks drop; expect 30–60 % slower (estimate).
6. **Context length.** Prompt processing grows with history; 4096 ctx keeps it under ~1–2 s.

## 2. Benchmarks to run (record results in STATUS.md)
| ID | Measure | How | Target |
|---|---|---|---|
| P1 | load time, first-token latency, tok/s, VRAM split for each installed model | `ollama run <m> --verbose "Explain photosynthesis in 100 words"`; `ollama ps` for the GPU/CPU split | llama3.2:3b ≥ 25 tok/s; qwen3:4b ≥ 10 tok/s |
| P2 | same through N.E.K.O. | `python -m neko chat`; read the meta line (tok/s, first token) | overhead < 150 ms vs P1 |
| P3 | peak RAM / VRAM | Task Manager → Performance + `nvidia-smi -l 1` during P1 | ≥ 2 GB RAM free throughout |
| P4 | screenshot analysis latency (gemma3:4b) | capture a 1920×1080 error dialog, ask "what's the error?" | < 30 s, correct text |
| P5 | STT latency | 5 s English utterance, small/int8/CPU | < 3 s |
| P6 | TTS start latency | SAPI, 1-sentence reply | < 1 s |
| P7 | DB retrieval time | 5,000 synthetic memories, `MemoryRetriever.retrieve` | < 50 ms lexical; < 200 ms with embeddings |
| P8 | app startup | launch → HUD visible | < 3 s (model load excluded) |
| P9 | idle footprint | HUD visible, idle 5 min | < 3 % CPU, < 250 MB RAM (N.E.K.O. process) |
| P10 | HUD responsiveness | type during streaming | no input lag > 100 ms |
| P11 | thermal | 15 min continuous chat on AC | GPU < 85 °C; no throttling warnings |
| P12 | KV-cache q8 effect | `start-ollama.ps1 -KvCacheQ8`, repeat P1/P3 for qwen3:4b | lower VRAM, same quality |

## 3. Tuning levers (in order of safety)
`num_ctx` 4096 → 2048 · smaller model for the `fast` role · `-KvCacheQ8` · keep one model resident
(default) · CPU STT (default) · reduced motion (saves a little GPU on the iGPU/dGPU compositor) ·
plug in the charger. Speculative decoding via llama.cpp `llama-server` with a small draft model is a
P2 experiment.
