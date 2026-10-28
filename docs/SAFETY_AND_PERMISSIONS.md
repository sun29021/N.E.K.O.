# Safety and permissions

N.E.K.O. separates **observe → suggest → prepare → execute**. The model can only *ask* for a
tool. Whether anything happens is decided by code in `security/policy.py`, plus you.

## 1. Risk levels

| Level | Meaning | Examples (built-in) | Rule |
|---|---|---|---|
| 0 Read-only | looks, doesn't change | list_dir, read_text_file, search_files, system_status, list_models | allowed inside allowed folders |
| 1 Low, reversible | small, undoable | write_note (new file), open_app (allow-list) | allowed and logged; **approval if untrusted content is in context** |
| 2 Material | changes things | move_file, write_note overwrite (backup kept), run_approved_script | approval each time, unless a narrow standing rule matches |
| 3 High impact | hard to undo / external | (none built in; reserved for e.g. sending email, elevated commands) | fresh, informed approval every time; **cannot be pre-approved** (enforced in code and by a DB CHECK) |
| Prohibited | never | delete_files | denied even if you click approve |

A tool can raise its own level based on its arguments (`risk_fn`). For example, `write_note` with
`overwrite=true` becomes Level 2.

## 2. Decision order (`PermissionPolicy.evaluate`)
1. Prohibited → deny.
2. Emergency stop active and level ≥1 → deny.
3. Category `computer_control` while `tools.computer_control_enabled = false` → deny.
4. Needs network while `privacy.allow_network = false` → deny.
5. Level 0/1 → allow. Level 2 → standing rule or ask. Level 3 → ask.
6. **Taint escalation** (`ToolExecutor`): if untrusted content has entered the conversation in this
   turn or the previous 3 turns (tool output, files, screenshots), every level ≥1 call needs approval.

## 3. Standing rules
`policy.add_standing_rule(tool, scope, risk=2, days=30)`. The scope must be non-empty, and only
`path_prefix` and `equals` are supported; unknown keys fail closed. Every path argument must sit under
the prefix. Rules expire and are audited. There is no UI for creating them yet (deliberately).

## 4. Approval dialog
It shows the risk level and colour, a plain-language summary, the side effects, whether the action can
be undone, and the redacted arguments. **Deny is the default button.** Level 3 also needs an "I understand"
tick. It is a normal modal window, not always-on-top, so it can't hide UAC, the sign-in screen or other
security prompts. UAC runs on the secure desktop anyway. Unanswered requests expire after about
280–300 s and count as denied. Gestures and voice can never approve.

## 5. Prompt-injection defence
- Untrusted content is wrapped in `BEGIN UNTRUSTED <random tag> … END UNTRUSTED <tag>`. Look-alike
  markers inside the content are neutralised, and the system prompt tells the model it is data.
- Common injection phrases are detected, and the reply carries a note when one is found.
- **Structural defence (the one that matters):** approval cannot be produced by text, and taint forces
  approval for any action after untrusted input.
- Memories from untrusted sources need approval before they can influence later prompts.
- Tool calls are only accepted when the model's reply *starts* with `<tool_call>`. Tool-call text
  inside a quoted document is ignored.

## 6. Files and paths (`security/paths.py`)
- Read only inside `tools.allowed_roots` (and writable roots). Write only inside `tools.writable_roots`.
- Paths are resolved (symlinks, `..`) **before** checking.
- Always denied: `.ssh`, `.gnupg`, `.aws`, `.azure`, `.kube`, `.docker`, `.env`, `.netrc`, `.git-credentials`,
  browser credential stores (`Login Data`, `Cookies`, `Local State`, `Web Data`), `Credentials`,
  `Protect`, `Vault`, `ntuser.dat`, `%SystemRoot%\System32\config`.
- Never writable: `%SystemRoot%`, Program Files, ProgramData, N.E.K.O.'s own data folder and source tree.

## 7. Processes and scripts
- No tool builds a command string. Processes get argument lists with `shell=False`.
- `open_app`: only entries in `tools.allowed_apps`, given as absolute paths to existing `.exe` files
  (protects against PATH hijacking).
- `run_approved_script`: only `.py`/`.ps1` files inside `tools.approved_scripts_dir`. Python runs in
  isolated mode (`-I`). PowerShell gets `-NoProfile -NonInteractive -ExecutionPolicy Bypass -File`;
  the bypass is process-scoped, because **you** are vouching for scripts you placed in that folder.
  Arguments must be short strings. Working directory = the scripts folder. Timeout = 120 s. Exit code
  and the last 4 KB of output are recorded.
- There is no general shell tool, and no elevation (UAC) is ever requested.

## 8. Emergency stop
The red button (Command Center), Shift+click on the HUD stop button, the tray menu, or **Ctrl+Shift+F12**
while a N.E.K.O. window has focus. It:
- cancels every registered task token (model streams stop, tools see cancellation),
- denies all pending approvals,
- stops speech,
- blocks every level ≥1 action until you press **Resume**.

Limits: an action that has already happened is not undone. A tool handler that is mid-way through a
blocking OS call finishes that call (its result is discarded). The emergency-stop key is an in-app
shortcut, **not a global hotkey**. If N.E.K.O. is frozen, close it from Task Manager.

## 9. Privacy defaults
| Setting | Default |
|---|---|
| Network tools | off |
| Cloud models | off |
| Remote computer | off |
| Microphone | only while the mic button is held |
| Wake word | off |
| Screenshots | only on capture button; kept in memory; not saved |
| Message content in logs | off |
| Model downloads | never automatic |

## 10. Things N.E.K.O. will never do (v0.1)
Delete files · request admin rights · change Windows settings, registry, firewall or startup entries ·
send messages/emails · buy anything · enter passwords · open network listeners · install
packages or models by itself.
