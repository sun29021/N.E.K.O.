# Product requirements — N.E.K.O. 0.x

**Product:** a private, local-first AI companion and Windows command center for one person, which
others can install as their own clean copy.
**Primary user:** a beginner on an ASUS TUF A15 (RTX 3050 4 GB, 16 GB RAM) who wants a capable,
honest assistant without subscriptions.
**Priorities:** P0 = first usable version · P1 = next · P2 = advanced/optional · R = needs a
feasibility experiment first.
**Status column:** ✅ implemented + automated tests · 🟡 implemented, not yet run for real ·
⬜ not built.

## 1. Conversation

| ID | Requirement / user story | Acceptance criteria | Pri | Status |
|---|---|---|---|---|
| C1 | As a user I can type a message and get a streamed reply from a local model. | Tokens appear as generated; reply is stored; model + "local" are shown. | P0 | ✅ (fake model) / 🟡 real |
| C2 | I can stop a reply at any time. | Stop/Ctrl+. ends streaming within ~0.5 s; task is marked cancelled. | P0 | ✅ |
| C3 | When the model server or model is missing, I get a plain explanation and a next step. | No stack traces; message names the fix (start-ollama, MODEL_GUIDE). | P0 | ✅ |
| C4 | Conversation history persists between sessions and can be cleared. | History reloads; "Clear conversation history" deletes it. | P0 | ✅ |
| C5 | I can choose personality and answer length. | Settings change the system prompt. | P0 | ✅ |
| C6 | It shows where processing happens (local / LAN / cloud). | Pill in HUD, metadata line in chat. | P0 | ✅ / 🟡 UI |
| C7 | Push-to-talk voice input. | Hold mic → speak → text appears and is sent. | P1 | 🟡 |
| C8 | Spoken replies, interruptible. | SAPI speaks; Stop ends speech immediately. | P1 | 🟡 |
| C9 | Configurable wake word ("Hey Jarvis"). | Off by default; visible indicator when on. | P2 | 🟡 detector only, not wired to UI |
| C10 | Long conversations stay within the model's context. | Older turns are summarised or dropped, and the user is told. | P0 | ✅ |

## 2. Memory

| ID | Requirement | Acceptance | Pri | Status |
|---|---|---|---|---|
| M1 | "Remember that …" saves a memory; "forget …" removes one. | Saved with provenance; forget deletes a single match, or lists several and asks. | P0 | ✅ |
| M2 | Relevant memories are used in answers, and I can see why. | Retrieval reason + score recorded per use; visible in Memory tab. | P0 | ✅ |
| M3 | Model-inferred or document-derived facts never become memories silently. | Stored as `pending_approval`; excluded from retrieval until approved. | P0 | ✅ |
| M4 | I can view, search, edit (versioned), delete, export and import memories. | All operations available in UI and CLI. | P0 | ✅ engine / 🟡 UI |
| M5 | Temporary memories expire. | `temporary` kind expires after TTL. | P1 | ✅ |
| M6 | Semantic search when an embedding model is installed. | Falls back to keyword search if not. | P1 | ✅ |
| M7 | Verified lessons from completed tasks (with approval). | Lesson proposed only with verification evidence; needs approval. | P1 | ✅ engine; no UI prompt yet |

## 3. Models and resources

| ID | Requirement | Acceptance | Pri | Status |
|---|---|---|---|---|
| R1 | Picks a suitable installed model per task, with a logged reason. | Routing decision table + reasons. | P0 | ✅ |
| R2 | Never downloads models automatically. | No pull calls anywhere; missing model → instructions. | P0 | ✅ |
| R3 | Won't load a model that would starve Windows of memory. | Safety margins enforced; rejection explained. | P0 | ✅ |
| R4 | Only one model resident on 4 GB GPUs. | Others unloaded before switching. | P0 | ✅ |
| R5 | Shows RAM, VRAM, GPU temperature, battery, disk. | Models & Resources tab; unknown values shown as unknown. | P0 | ✅ engine / 🟡 UI |
| R6 | Optional second computer for inference. | Paired, HTTPS, token, LAN-only, off by default. | P2 | 🟡 adapter only; pairing/proxy not built |
| R7 | Optional cloud models. | Disabled by default; clear indicator. | P2 | ⬜ (adapter reusable) |

## 4. Tools and computer assistance

| ID | Requirement | Acceptance | Pri | Status |
|---|---|---|---|---|
| T1 | Read/search files in folders I allow. | Outside allowed folders → refused with explanation. | P0 | ✅ |
| T2 | Create notes; move files with approval; verify the result on disk. | Verification recorded. | P0 | ✅ |
| T3 | Open apps from my allow-list. | Only absolute-path entries; computer control setting must be on. | P1 | ✅ |
| T4 | Run scripts only from an approved folder, with approval. | No shell strings; timeout; exit code recorded. | P1 | ✅ |
| T5 | Windows UI Automation (navigate/type into apps). | Verify state after each step; stop when unsure. | P2 | ⬜ |
| T6 | Web research with citations. | Network permission; sources preserved. | P2 | ⬜ |
| T7 | MCP integrations. | Pinned, reviewed, opt-in. | P2 | ⬜ (design only) |

## 5. Vision

| ID | Requirement | Acceptance | Pri | Status |
|---|---|---|---|---|
| V1 | Capture my screen on request and ask about it. | HUD hides, captures, image kept in memory only, sent to local vision model. | P1 | 🟡 |
| V2 | If no vision model is installed, say so and how to add one. | Clear message. | P0 | ✅ |
| V3 | OCR-specialised pipeline / tiling for dense screens. | | P2 | ⬜ (tiling helper only) |
| V4 | Hand-gesture control (MediaPipe). | Never approves actions. | R | ⬜ |

## 6. Safety

| ID | Requirement | Acceptance | Pri | Status |
|---|---|---|---|---|
| S1 | Risk levels 0–3 enforced in code; Level 3 never pre-approved; prohibited actions blocked. | Tests. | P0 | ✅ |
| S2 | Untrusted content can't trigger actions without my approval. | Taint escalation; injection tests. | P0 | ✅ |
| S3 | Emergency stop cancels everything and blocks actions until resumed. | Tests. | P0 | ✅ |
| S4 | Logs never contain secrets or (by default) message content. | Redaction tests. | P0 | ✅ |
| S5 | Audit trail of tool calls, approvals and memory changes. | Activity tab. | P0 | ✅ |

## 7. Desktop experience

| ID | Requirement | Pri | Status |
|---|---|---|---|
| D1 | Floating HUD with animated core and 10 states; compact ↔ Command Center | P0 | 🟡 |
| D2 | Approval dialogs that default to Deny and never cover Windows security prompts | P0 | 🟡 |
| D3 | Tray icon; HUD can be hidden/disabled | P0 | 🟡 |
| D4 | Reduced motion, keyboard access, high-DPI | P1 | 🟡 |
| D5 | First-run screen | P0 | 🟡 (basic) |

## 8. Install, share, maintain

| ID | Requirement | Pri | Status |
|---|---|---|---|
| I1 | Dry-run-by-default setup script; never touches models/drivers/settings | P0 | 🟡 (parsed, not run) |
| I2 | Read-only doctor | P0 | ✅ (run for real, see STATUS) |
| I3 | Verified backup/restore | P0 | ✅ |
| I4 | Clean install for another person without my data | P0 | 🟡 (by design: data outside repo) |
| I5 | Packaged installer | P2 | ⬜ |

## Known limitations (by design)
- Small local models are much weaker than frontier cloud models. Expect mistakes, especially
  with multi-step tool use and Bangla.
- No real-time "barge-in" voice interruption (the mic is gated while speaking).
- Not sentient, doesn't self-improve its neural network, and has no perfect recall.
