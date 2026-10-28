# Security and quality audit — v0.1.0 (2026-10-27)

Performed as a separate review pass over the code after implementation. Scope: all of `src/neko`,
`scripts/`, `packaging/`, config templates. Method: manual code reading against the threat model
below, plus targeted tests (security tests are in `tests/security` and `tests/integration`).
Nothing was penetration-tested against a live model.

## 1. Threat model
Assets: personal memories and history, files in allowed folders, the user's apps, credentials on the
PC, system stability. Adversaries: malicious content the assistant reads (documents, web pages,
screenshots, tool output), a mistaken or "jailbroken" model, other local software, and anyone who
gets hold of a shared zip or backup. Out of scope: an attacker with admin access to the PC.

## 2. Findings fixed during the audit
| # | Severity | Finding | Fix | Test |
|---|---|---|---|---|
| F1 | **High** | Untrusted content summarised in one turn could steer a *later* turn, where low-risk actions (write_note, open_app) ran without approval | Conversation taint lasts 3 turns; images taint too | `test_taint_persists_into_next_turn` |
| F2 | Medium | `allowed_apps` used bare names (`notepad.exe`), so PATH hijacking could start a planted binary | Absolute paths required; `%VARS%` expanded; file must exist | defaults + tool check |
| F3 | Medium | Emergency-stop hotkey was Ctrl+Shift+Esc (Windows Task Manager) — conflict / unreliable | Changed to Ctrl+Shift+F12 | — |
| F4 | Low | Path deny-list contained generic names (`system`, `security`), blocking legitimate folders | Replaced with specific credential stores + registry hive path | path tests |
| F5 | Low | Router never recorded failures, so the unreliable-model penalty couldn't trigger | Failure recorded on model errors | `test_model_failure_recorded_for_routing_stats` |
| F6 | Low | Worker-thread SQLite connections never closed at shutdown | All connections tracked and closed | suite |
| F7 | Low | SAPI rate/volume were passed as `-Command` args, which PowerShell doesn't bind to `$args` reliably | Integers formatted into the script; text via stdin only | — |
| F8 | Low | Settings save would crash on `[[remote.endpoints]]` arrays | TOML writer supports arrays of tables | — |

## 3. Controls verified by tests
Risk levels enforced in code · Level 3 can't be pre-approved (code + DB CHECK) · prohibited tools denied
even when approved · untrusted fencing with random tags and escaped look-alike markers · injection
phrase detection · taint escalation · path resolution before checks · credential-store denial · system
dirs never writable · N.E.K.O.'s own data/source not writable by tools · no shell strings (argument
lists, `shell=False`) · tool timeouts · verification required for state-changing tools · approval
denied when no UI is present · emergency stop cancels and blocks · secret redaction in logs/audit ·
FTS query sanitising · export table-name validation · config rejects public model URLs and non-HTTPS/
non-private remote endpoints · backups verified by SHA-256 and integrity check · tampered backups refused.

## 4. Open risks (not fixed in v0.1)
| # | Severity | Risk | Mitigation now | Recommended |
|---|---|---|---|---|
| O1 | Medium | **Ollama has no authentication.** Any local program can use it, and a website could try DNS rebinding | bound to 127.0.0.1; default Ollama origin list is localhost-only | keep `OLLAMA_HOST=127.0.0.1`; never set `OLLAMA_ORIGINS=*` |
| O2 | Medium | **Dependencies pinned by version but not hash**, so a compromised PyPI release could be installed | pins in pyproject; dry-run setup | generate a hash-locked requirements file (`pip-compile --generate-hashes` / `uv pip compile`) on first setup and install with `--require-hashes` |
| O3 | Medium | Small models may *misreport* tool results or invent facts in prose | tool summaries come from code; UI shows verification status | show verified ✓ / ✗ badges per tool step in Chat (P1) |
| O4 | Medium | Tool handlers that time out keep running in their thread until their OS call returns | cooperative cancel; result discarded; "may have partially completed" message | run risky tools in a subprocess that can be killed (P1) |
| O5 | Low | Injection detection is heuristic and easy to evade | it's only a warning; the structural controls (taint + approvals) do the real work | — |
| O6 | Low | Approval summaries include model-supplied paths/strings; a crafted path could look misleading | raw JSON args are shown below the summary; NUL bytes rejected | sanitise control characters/RTL overrides in summaries (P1) |
| O7 | Low | DB and backups are unencrypted at rest | protected by the Windows profile ACL; documented | optional DPAPI-encrypted backups (P2) |
| O8 | Low | `run_approved_script` trusts every script in the approved folder; PowerShell runs with process-scoped `-ExecutionPolicy Bypass` | folder is opt-in, empty by default; Level 2 approval each run | per-script hash allow-list (P1) |
| O9 | Low | Emergency-stop key is in-app only (not global) | tray menu + red button | optional global hotkey via `RegisterHotKey` (P1) |
| O10 | Info | Remote endpoint TLS: self-signed certificates need `ca_file`, which config doesn't expose yet | remote is off | expose `ca_file` + certificate pinning before enabling remote (P2) |
| O11 | Info | openWakeWord pre-trained model licence is non-commercial | off by default; documented | train own model for commercial redistribution |
| O12 | Info | `C:\Users\sun29\.ollama\id_ed25519` is Ollama's private key | never read or copied by N.E.K.O. | don't include it in backups you share |

## 5. Privacy review
Local-only by default. No telemetry. No message content in logs by default. Screenshots and audio
are memory-only. Memory export excludes sensitive items by default. The release builder refuses to
package databases, configs, logs, backups, models or environments. The data directory lives outside
the repository.

## 6. Licence compliance
N.E.K.O. code is MIT. Nothing third-party is bundled. Licence notes for every recommended model are in
MODEL_GUIDE. Licences marked "verify" (Qwen 3B sizes, Gemma terms) must be checked on the model card
before any redistribution or commercial use.

## 7. Code quality notes
- Core is stdlib-only and type-hinted. ruff/mypy are configured but **not run** (not installed; no
  packages were installed in this phase). Run them after setup with the `dev` extra.
- The UI code (`src/neko/ui`) compiles but has **never been executed**. Expect small API fixes on
  first run (TEST_PLAN U1–U12).
- Some test DB connections aren't closed; harmless ResourceWarnings appear when running tests
  without `-W ignore::ResourceWarning`.
