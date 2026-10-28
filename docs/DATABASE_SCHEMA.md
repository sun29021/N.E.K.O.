# Database schema (version 1)

File: `%LOCALAPPDATA%\NEKO\neko.db` · SQLite ≥3.45 · WAL journal · `foreign_keys=ON` ·
version stored in `PRAGMA user_version`. Source: `src/neko/database/migrations/0001_initial.sql`.

## Tables

| Table | Purpose | Key columns / constraints |
|---|---|---|
| `settings_kv` | small app state (reserved) | `key` PK |
| `conversations` | one row per conversation | `summary`, `archived` |
| `messages` | chat messages | FK → conversations **CASCADE**; role CHECK; index (conversation_id, created_at) |
| `memories` | long-term memory | kind CHECK (7 kinds); trust CHECK (5); status CHECK (active, pending_approval, superseded, deleted, expired); confidence 0–1; `supersedes_id` self-FK; `expires_at`; `sensitive` |
| `memory_provenance` | where each memory came from | FK → memories CASCADE |
| `memory_embeddings` | optional vectors (float32 LE BLOB) | PK memory_id, FK CASCADE |
| `memory_contradictions` | flagged conflicts | FKs CASCADE |
| `memories_fts` | FTS5 external-content index | kept in sync by 3 triggers |
| `memory_retrievals` | why/when a memory was used | FK CASCADE |
| `documents` | indexed document metadata (reserved for P1 document search) | `path` UNIQUE |
| `tasks` | one row per request | status CHECK (8 states) |
| `task_steps` | ordered steps | UNIQUE (task_id, seq) |
| `tool_invocations` | every tool call, args **redacted** | status CHECK; risk level |
| `verification_evidence` | proof a tool/task really worked | method, passed |
| `outcomes` | task result + lesson | lesson_status CHECK |
| `incidents` | notable errors | severity CHECK |
| `workflows`, `workflow_versions` | reusable procedures (reserved, P1) | `reliable` set only from evidence |
| `model_inventory` | models seen on disk / in runtime | licence, source, digest, removable |
| `routing_decisions` | every routing choice + candidates JSON + outcome | index (chosen, created_at) |
| `resource_samples` | optional resource history (reserved) | |
| `approvals` | every approval request and decision | decision CHECK |
| `standing_permissions` | narrow pre-approvals | **CHECK max_risk ≤ 2** (Level 3 can never be stored) |
| `audit_events` | append-only audit trail | category, action, detail_json |
| `backups` | backup registry | path, sha256, schema_version |

## Task status machine
`pending → planning | running`, `running → awaiting_approval | verifying | succeeded | failed | cancelled`,
`awaiting_approval → running | cancelled | failed`, `verifying → succeeded | failed | cancelled`.
Terminal states: succeeded, failed, cancelled (`orchestration/tasks.py`; invalid transitions raise).

## Migrations
- Files `NNNN_snake_name.sql` in `src/neko/database/migrations/`, applied in order on startup.
- Each runs in one transaction (`BEGIN IMMEDIATE … COMMIT`). On error everything rolls back and the
  app shows a recovery message.
- Before migrating an **existing** database, a verified backup (`neko-<time>-pre-migration-vN.db`)
  is written.
- Never edit an applied migration; add a new one. Rollback = restore the pre-migration backup
  (BACKUP_AND_RECOVERY §5).

## Concurrency
One connection per thread; writes are serialised by an in-process lock; `busy_timeout` is 10 s.
Only one N.E.K.O. process should use a database at a time. A second instance would mostly wait on
busy timeouts, though SQLite would keep the data consistent.

## Retention
Messages older than `message_retention_days` are deleted at startup (`Neko.maintenance()`).
Expired/superseded memories are purged 7 days after they expire. Audit events are kept (they're
small); export or prune them manually if you want.
