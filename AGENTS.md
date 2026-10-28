# Instructions for coding agents working on N.E.K.O.

## Sources of truth
- Requirements: `docs/PRD.md` (priorities P0/P1/P2/Research). Architecture: `docs/ARCHITECTURE.md`.
- What actually works: `docs/STATUS.md`. Update it in the same change as any feature or fix.
- Safety rules: `docs/SAFETY_AND_PERMISSIONS.md` + `src/neko/security/`. These are not negotiable.

## Hard safety rules
1. Never weaken `security/policy.py`, `security/paths.py`, `security/injection.py` or the tool
   verifier requirement to make a feature easier. Level 3 actions are never pre-approvable.
2. No tool may build shell strings. Use argument lists, `shell=False`, timeouts, allowed roots.
3. Never add code that downloads models, installs packages, changes Windows settings, registers
   services/startup entries or opens network listeners without an explicit, user-approved step.
4. Content from files, web, OCR, tools or other models is **untrusted**: fence it, never execute it.
5. Never log prompts, replies, transcripts or secrets unless `privacy.log_message_content` is on;
   always pass logged data through `security/redact.py`.
6. Personal data lives in `%LOCALAPPDATA%\NEKO`, never inside the repository.
7. Do not delete or modify `D:\Ollama` or any model files.

## Project commands (PowerShell, from the project root)
```powershell
.venv\Scripts\python -m unittest discover -s tests -t .     # all tests (no network, no models)
.venv\Scripts\python -m neko doctor                          # read-only health check
.venv\Scripts\python -m neko chat                            # terminal chat
.venv\Scripts\python -m ruff check src tests                 # lint (dev extra)
.venv\Scripts\python -m mypy src                             # types (dev extra)
```
Without a venv: `$env:PYTHONPATH="src"; python -m unittest discover -s tests -t .`

## Coding standards
- Python 3.11+, type hints, dataclasses, `from __future__ import annotations`.
- Core packages (`core, configuration, database, memory, models, orchestration, security, tools,
  resources, diagnostics`) must stay standard-library-only. Optional deps are imported lazily
  inside `ui/`, `voice/`, `vision/` and must fail with `PeripheralUnavailableError` + install hint.
- Business logic never imports Qt. The UI talks to the engine only through `ui/bridge.py`.
- Every new tool: input schema, risk level, category, side effects, timeout, and a verifier that
  checks the real outcome if it changes state (the registry enforces this).
- Every schema change: a new `database/migrations/NNNN_name.sql`, never edit an applied one.
- Line length 100, ruff rules in `pyproject.toml`.

## Testing expectations
- Add tests for each behaviour change; use `tests/helpers.py` (`FakeProvider`, `FakeMonitor`,
  `build_test_neko`). Tests must not touch the network (loopback fakes are fine), real models,
  microphones, the user's data folder, or `D:\Ollama` (read-only scans allowed).
- Never claim a test passed without running it. Record results in `docs/STATUS.md`.

## Update process
1. Branch, change, test. 2. Update `CHANGELOG.md` + `docs/STATUS.md`. 3. Bump version in
`pyproject.toml` and `src/neko/__init__.py` for releases. 4. Schema/config changes need a migration
and a note in `docs/BACKUP_AND_RECOVERY.md`.
