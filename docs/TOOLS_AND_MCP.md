# Tools and MCP

## 1. Principle
Tools are small, typed, audited functions governed by the policy layer. MCP is an *optional plug-in
mechanism*, not the assistant's brain. N.E.K.O. is fully useful without any MCP server, and none is
installed or configured.

## 2. Tool declaration (`tools/base.py: ToolSpec`)
| Field | Meaning |
|---|---|
| `name`, `description` | shown to the model |
| `params` | input schema subset: type, required, default, enum, min/max, max_length (NUL bytes rejected) |
| `output` | description of the output (results are always returned to the model as UNTRUSTED text) |
| `risk`, `risk_fn` | base level and argument-dependent escalation |
| `category` | files, computer_control, scripts, diagnostics, network… (policy gates) |
| `side_effects`, `reversible` | shown in approval dialogs |
| `timeout_s` | hard limit for the executor |
| `needs_network` | denied unless `privacy.allow_network` |
| `prohibited` | always denied |
| `verifier` | **mandatory for state-changing Level ≥2 tools** (the registry refuses to register one without it) |

## 3. Built-in tools
| Tool | Level | Verification |
|---|---|---|
| list_dir | 0 | — |
| read_text_file (≤200 KB, text only) | 0 | — |
| search_files (name pattern + optional text, skips .git/node_modules/.venv) | 0 | — |
| system_status | 0 | — |
| list_models | 0 | — |
| write_note (.txt/.md; overwrite → L2, backup kept) | 1/2 | file exists and content matches |
| move_file | 2 | destination exists, source gone |
| open_app (allow-list, absolute paths) | 1 | process started (Store-app launchers may exit early; noted) |
| run_approved_script | 2 | exit code 0 |
| delete_files | prohibited | — |

Protocol with the model: **native function calling** (Ollama `/api/chat` `tools`). The model returns
structured `tool_calls`, and results go back as `role: tool` messages, fenced as UNTRUSTED. Bare-JSON calls
(`{"name": …, "parameters": …}`) are also accepted, because llama3.2 sometimes emits those. For runtimes
without function calling, the fallback is a text protocol: the reply must *start* with
`<tool_call>{"tool": …, "args": {…}}</tool_call>`. A guard detects replies that *pretend* to have used a
tool (seen live with llama3.2); it retries once, then labels the answer. Tools are only offered when
the request mentions files, folders, system status, apps and the like. At most 4 tool steps per request.

## 4. MCP: evaluation and policy
Candidate integrations (none installed; **versions/maintenance not re-verified this session**):

| Integration | Typical source | Permissions / network | Risk | Essential? | Safe alternative |
|---|---|---|---|---|---|
| Filesystem | official MCP reference servers (modelcontextprotocol GitHub org) | local files | high if broad roots | no | built-in file tools |
| Git | official reference server | repo read/write | medium | no | read tools + approved scripts |
| Browser automation (Playwright MCP) | Microsoft | full browser + network | high (prompt injection from web) | no | none in v0.1 |
| Docs search / fetch | various | network | medium | no | none (network off) |
| SQLite | reference server | local DB | medium | no | N.E.K.O.'s own DB API |
| Calendar/email | vendor servers | OAuth tokens, network, **sending** = Level 3 | high | no | — |

Rules, if MCP support is added (P2):
1. Opt-in per server via config. Nothing is auto-discovered from registries.
2. Pin exact versions and record the package hash. Review the source and declared tools before enabling.
3. Run each server as a separate restricted process with its own working dir and no inherited secrets.
4. Map every MCP tool to a `ToolSpec` with a risk level (default Level 2 if unknown) and route it
   through the same policy, approvals, taint rules and audit log.
5. Treat MCP tool output as UNTRUSTED.
6. Never pass N.E.K.O.'s memories or files to a server unless the user approves that call.
7. Show enabled integrations in the Command Center.

## 5. Adding a tool (developer checklist)
Schema → risk → category → side effects/reversibility → timeout → verifier → unit tests (allowed,
denied, approval, taint, timeout) → docs table above → STATUS.md.
