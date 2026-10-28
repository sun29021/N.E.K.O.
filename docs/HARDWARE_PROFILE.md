# Hardware profile (verified by read-only inspection, 2026-10-27)

## Primary laptop: verified facts

| Item | Value | How it was checked |
|---|---|---|
| Model | ASUS TUF Gaming A15 FA506ICB | `Win32_ComputerSystem` |
| CPU | AMD Ryzen 7 4800H, 8 cores / 16 threads (AVX2, no AVX-512) | `Win32_Processor` |
| RAM | 16 GB (2 × 8 GB Micron DDR4-3200); 15.4 GiB visible; 5.5–9.8 GB free when checked | `Win32_PhysicalMemory`, `GlobalMemoryStatusEx` |
| Discrete GPU | NVIDIA GeForce RTX 3050 Laptop, 4096 MiB, compute 8.6, driver 610.62 (CUDA driver 13.3 per Ollama log) | `nvidia-smi` |
| Integrated GPU | AMD Radeon (Vega, 512 MB shared) | `Win32_VideoController` |
| OS | Windows 11 Home 10.0.26200 | `Win32_OperatingSystem` |
| Disks | C: 138 GB (18.2 GB free) · D: "SOFTWARE" 167 GB (108.7 GB free) · E: "GAMES" 168 GB (102 GB free) · F: 525 GB (211 GB free) | `Win32_LogicalDisk` |
| Battery | A32-K55, 84–99 % when checked; AC status readable | `Win32_Battery`, `GetSystemPowerStatus` |
| GPU temperature | 58–59 °C idle | `nvidia-smi` |
| CPU temperature | **Not measured** — no reliable documented API on this laptop | — |
| Python | 3.14.6 (`C:\Python314`); uv-managed 3.11.17 also present | `python --version`, `py -0p` |
| Node / Git | Node 24.17.0, Git 2.54.0 (not needed by N.E.K.O.) | `--version` |
| uv | Python package `uv 0.13.3` in system Python (no `uv.exe` on PATH) | `pip list` |

## Existing Ollama installation (left untouched)

| Item | Value |
|---|---|
| Executable | `D:\Ollama\app\ollama.exe` (37.8 MB), portable zip install, **not on PATH** |
| Version | 0.40.9 (log: "Listening on 127.0.0.1:11434 (version 0.40.9)") |
| Backends present | CPU (many ISA variants), `cuda_v12`, `cuda_v13`, `vulkan` |
| Models dir | `D:\Ollama\models` (was set via `OLLAMA_MODELS` in the shell that started it; **not set** in the current environment) |
| Models | `llama3.2:3b` — Llama 3.2 3B Instruct, Q4_K_M, 3.21 B params, blob 2,019,377,376 bytes, present |
| Download cache | `D:\Ollama\dl\ollama-windows-amd64.zip` (1.59 GB) + `sha256sum.txt` — the installer zip; can be removed by you later to free 1.6 GB (N.E.K.O. will never remove it) |
| Key file | `C:\Users\sun29\.ollama\id_ed25519` (Ollama's identity key; treat as a secret; never shared) |

### What the old log proves (and what it doesn't)

From `D:\Ollama\serve.log` (2026-10-23):
- **Did work:** the model downloaded (3 min 10 s), loaded with 26/29 layers on the GPU, and answered
  chat requests at about 30 tokens/s.
- **Warnings:** "GPU discovery watchdog timed out" (repeated) and "unable to refresh free memory,
  using old values". Inference continued on CUDA anyway.
- **Not proven:** that the server starts today with the current driver (610.62). The startup and
  `ollama list` steps in the Installation Manual check this.

## Optional desktop — unverified
Ryzen 7 7700X, RTX 5060 Ti (possibly 16 GB), 32 GB DDR5 and an MSI B850M board have been discussed.
**None of this was observed.** N.E.K.O. doesn't need it. If it becomes available, use the
`desktop-16gb` profile and the remote-endpoint design in ARCHITECTURE §7. That pairing is not
built yet.

## What this means for N.E.K.O.
- One ~2–3 GB model resident at a time. 4B models will spill partly to the CPU; 7–8B models
  mostly will (slow, though usable for non-voice tasks).
- Keep ≥2 GB RAM free for Windows (default `ram_safety_margin_mb = 2048`).
- C: is tight (18 GB free). N.E.K.O.'s data is small (MBs), but **new models should go on D:**
  (Ollama already uses `D:\Ollama\models`).
