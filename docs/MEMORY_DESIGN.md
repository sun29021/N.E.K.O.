# Memory design

## 1. What is stored, and where

| Kind | Example | Source | Default status | Expires |
|---|---|---|---|---|
| Conversation messages | your messages + replies | chat | stored (can be turned off) | `privacy.message_retention_days` (90) |
| Session summary | rolling 120-word summary | the model, every 12 messages after 24 | stored on the conversation | with the conversation |
| `preference` | "I prefer short answers" | "remember that…" | active | no |
| `fact` | "My cat is called Mochi" | "remember that…" / manual add | active | no |
| `project` | "N.E.K.O. lives in D:\PROJECT" | manual | active | no |
| `episode` | "Organised Downloads on 3 Nov" | task outcomes (future) | pending | no |
| `lesson` | "Notes folder is D:\Notes" | verified task outcome | **pending approval** | no |
| `assumption` | inferred by the model | model | **pending approval** | yes |
| `temporary` | "meeting room is B2 today" | user | active | 24 h default |
| Tool results / evidence | file existed, exit code 0 | tools | `tool_invocations`, `verification_evidence` | with task |
| Failed attempts | failure class + reason | coordinator | `outcomes` | with task |

Every memory has a **trust label** (`user_stated`, `verified`, `observed`, `inferred`,
`untrusted`), a confidence (0–1), a version, and one or more **provenance** rows: where it came from,
when, and what changed.

## 2. Rules that stop self-reinforcing errors
1. Only `user_stated` and `verified` content can become active without approval. Everything else
   (model inferences, tool output, documents, web) waits in `pending_approval` and is **excluded
   from retrieval** until you approve it.
2. Sensitive-looking content (passwords, bank, medical, …) always waits for approval, even when you
   said it yourself.
3. A lesson is only *proposed* when the task has passing verification evidence. "The model said it
   worked" never counts.
4. Duplicates don't pile up. Restating something raises its confidence by 0.05 and adds a
   provenance row.
5. Possible contradictions (high word overlap with opposite polarity) are flagged in the retrieval
   reasons and shown to the model ("may contradict m_…"), not silently merged.
6. Editing creates a new version that supersedes the old one. The old one is kept as `superseded` for
   audit and purged after 7 days.
7. Memories can never change policy. Permissions live in code and in `standing_permissions`, which
   only you can create.

## 3. Search
- **Lexical:** SQLite FTS5 over content + tags (BM25), using `unicode61` tokenisation, which works for
  Bangla script. Query terms are reduced to word characters and quoted, so user text can't inject
  FTS syntax.
- **Semantic (optional):** when an embedding model is installed (`nomic-embed-text`, or `bge-m3`
  for Bangla), memory vectors are stored as float32 BLOBs and compared by cosine similarity in
  Python. That is fine up to roughly 10k memories (~5 ms per 1k vectors of 768 dims — estimate,
  not measured).
- Not every memory needs an embedding: they are created in batches by `Coordinator.index_embeddings()`
  and only for active memories.

## 4. Retrieval pipeline (`memory/retrieval.py`)
1. Normalise the query.
2. Current conversation: the last 30 messages come from `ConversationStore`, plus the summary.
3. Keyword candidates (FTS5, 3× the limit).
4. Semantic candidates (cosine ≥ 0.45) when available; a memory found both ways gets a +0.15 bonus.
5. Standing preferences are always considered (base score 0.35).
6. Score = relevance × trust weight × (0.5 + 0.5 × confidence) + recency bonus (0.1, decaying over
   ~30 days) + preference bonus (0.1).
7. Deduplicate (normalised equality or Jaccard > 0.85).
8. Flag contradictions.
9. Fit within the token budget (default 500 tokens of memories).
10. Each memory is shown to the model with its kind and trust label.
11. Each use is logged in `memory_retrievals` with score and reasons.
12. **Why was this retrieved?** Command Center → Memory → select a row → provenance and latest
    retrieval reasons.

## 5. Context-window management (`memory/context.py`)
Priority, highest first: system policy (never truncated) → your current message → memories →
untrusted tool/document data (capped at 900 tokens, truncated with a marker) → summary → recent
history (newest first until the budget runs out).
`prompt budget = num_ctx − response reserve (num_ctx/4, max 1024) − tool reserve (256)`.
Token counts are estimates (≈4 chars/token for Latin script, ≈1.6 for Bangla and other scripts).
When anything is dropped, the reply notes say so, e.g. "12 older message(s) were left out of context".

## 6. Verified learning loop
For each task: goal → plan steps (`task_steps`) → tool invocations (redacted args) → actual results →
verification evidence (file exists and content matches; exit code; process running; or your
confirmation via `TaskManager.add_feedback`) → outcome (succeeded, failure class/reason) → optional
lesson (`pending_approval`, confidence) → your approval.
Routing statistics: each routing decision records later success/latency. Models that succeed less than
60 % of the time over their last ≥5 uses are down-ranked.

## 7. Your controls
| Action | UI | CLI |
|---|---|---|
| View / search | Command Center → Memory | `python -m neko memory list [--all]` |
| Approve pending | Memory → filter "pending_approval" → Approve | `memory pending`, `memory approve <id>` |
| Edit | Memory → Edit… | — |
| Delete | Memory → Delete, or say "forget …" | `memory delete <id>` |
| Export / import | Memory → Export… | `memory export file.json`, `memory import file.json` |
| Clear history | Memory → Clear conversation history… | — |
| Retention | config `privacy.message_retention_days`, `temporary_memory_hours` | |
| Turn learning off | Settings → Learning | `privacy.learning_enabled = false` |

**What deletion means:** the memory row, its provenance, embedding, FTS entry and retrieval log
rows are removed from `neko.db` immediately (foreign-key cascade + FTS trigger). Copies in
**backups made earlier** remain until you delete those backup files. SQLite may keep freed pages in
the file until a `VACUUM`. The Backup manual explains how to run one.
