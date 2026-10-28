# Resource management

The laptop is shared with you, Windows and your other apps. N.E.K.O. is a guest on it, not an AI server.

## 1. What is measured, and how

| Metric | API | Measurable here? |
|---|---|---|
| RAM total/free | `GlobalMemoryStatusEx` | ✅ (verified: 9835 MB free of 15789 MB during doctor run) |
| CPU load | `GetSystemTimes` deltas | ✅ (needs two samples) |
| VRAM total/used, GPU util, GPU temp | `nvidia-smi --query-gpu` | ✅ (verified: 4096 MB, 58 °C) |
| CPU temperature | — | ❌ no reliable documented API; shown as "not measured" |
| Battery / AC | `GetSystemPowerStatus` | ✅ |
| Disk free | `shutil.disk_usage` | ✅ |
| Model disk usage | Ollama manifests (read-only scan) | ✅ |
| Loaded models + VRAM share | Ollama `/api/ps` | ✅ when server runs |

Snapshots are cached for 3 s. The UI polls every `resources.poll_interval_s` (5 s) on a background
thread. If `nvidia-smi` is missing it is disabled for the session (no repeated failing calls).

## 2. Feasibility (`resources.assess`)
Ollama splits model layers between VRAM and RAM, so the check uses *combined* usable memory:

```
usable_vram = vram_free - vram_safety_margin (400 MB)
usable_ram  = ram_free  - ram_safety_margin  (2048 MB)
need        = weights (file size) + KV cache (~450 MB per 4k ctx for a 3B model, scaled) + 150 MB buffers
need <= usable_vram               -> "full GPU"
need <= usable_vram + usable_ram  -> "CPU/GPU split - slower"  (user is told)
otherwise                         -> rejected, reason logged, fallback role tried
```

The estimate for `llama3.2:3b` is ~2.5 GB. Ollama's own log measured 1742 + 484 MiB of weights,
448 MiB of KV cache and ~125 MiB of compute buffers ≈ 2.8 GB, so the estimate is slightly low.
A test keeps it within 2.4–3.2 GB. Treat all estimates as ±25 %.

| Model | File size | Est. peak (4k ctx) | Expected on RTX 3050 4 GB |
|---|---|---|---|
| llama3.2:3b Q4_K_M | 2.0 GB | ~2.5–2.8 GB | mostly GPU (measured 26/29 layers, ~30 tok/s) |
| qwen3:1.7b | 1.4 GB | ~2.0 GB | fully GPU (estimate) |
| qwen3:4b | 2.5 GB | ~3.1 GB | GPU + some CPU — **estimate 12–25 tok/s, unmeasured** |
| gemma3:4b (vision) | 3.4 GB | ~4.0 GB + image tokens | split; vision prompts slow (several seconds per image) — **unmeasured** |
| qwen3:8b | 5.2 GB | ~6.2 GB | mostly CPU; **estimate 4–8 tok/s, unmeasured** |

## 3. Concurrency and lifecycle
- One inference at a time (`ModelLifecycle.lock`; the UI refuses a second send).
- `models.max_loaded_models = 1`: before using a different chat model, others are unloaded
  (`keep_alive: 0`). The memory embedder (bge-m3) is the exception: it runs **on the CPU**
  (`num_gpu: 0`) and stays loaded, so Ollama is started with `OLLAMA_MAX_LOADED_MODELS=2`. Measured
  impact: removed a 4 s reload on every message and restored the coder model from 9 to ~110 tok/s.
- Idle unload: Ollama's `keep_alive` (5 min) frees VRAM when you stop chatting.
- Loaded models are preferred (+0.15 score), avoiding a 2–10 s reload.
- STT runs on the CPU by default so it doesn't fight the LLM for VRAM. "auto" uses CUDA only when
  >1.5 GB of VRAM is free.

## 4. Thermal and power policy
- Background work (conversation summaries) is skipped on battery below 35 %.
- No GPU clocks, power limits or Windows power plans are changed, ever.
- GPU temperature is shown. `gpu_temp_soft_limit_c` (85 °C) is reserved for a P1 rule that pauses
  optional work. It is *not* enforced in v0.1.
- Sensors are polled every 5 s at most.

## 5. Storage budgets
| Item | Budget / expected size |
|---|---|
| Model weights | `storage.model_budget_gb` = 25 GB (on D:) — laptop-lite optional set ≈ 6–8 GB |
| Database | a few MB per year of normal chatting (estimate) |
| Logs | `storage.log_max_mb` = 20 MB (4 rotating files) |
| Backups | ~DB size each; `backup_keep` = 10 (advisory; not auto-deleted in v0.1) |
| Speech models | faster-whisper small ≈ 0.5 GB, Piper voice ≈ 60 MB |
| Python env | ~1.2 GB with PySide6, +~1 GB with voice |
| Safety margin | `resources.disk_min_free_gb` = 10 GB on any drive N.E.K.O. writes to |

Before any model download (always manual), MODEL_GUIDE shows how to check space first. N.E.K.O.
never deletes files to make room.

## 6. Model inventory
`python -m neko models` (or Command Center → Models) lists name, quantisation, size, licence note,
capabilities and whether a model is loaded. "Safe to remove" is for you to decide. N.E.K.O. marks
nothing as removable automatically (`model_inventory.removable` = 0).

## 7. Safe mode
`scripts\launch.ps1 -SafeMode` runs with the `existing-only` profile, voice off, computer control off
and reduced motion.
