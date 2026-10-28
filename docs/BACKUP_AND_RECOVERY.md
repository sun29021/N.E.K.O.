# Backup and recovery

All personal data is in `%LOCALAPPDATA%\NEKO`: `neko.db` (memories, history, tasks, audit),
`config.toml`, `logs\`, `backups\`. No cloud service is involved.

## 1. Making a backup
- **UI:** Command Center → Diagnostics → **Back up now**
- **Script:** `scripts\backup.ps1` (optionally `-Destination E:\NEKO-backups` for an external drive)
- **CLI:** `.venv\Scripts\python -m neko backup`

How it works: SQLite's online backup API copies a consistent snapshot even while N.E.K.O. runs. The
copy is integrity-checked (`PRAGMA integrity_check`), a SHA-256 sidecar file
`neko-<date>-<reason>.db.sha256` is written, and the backup is recorded in the `backups` table.
`backup.ps1` also copies `config.toml`. Automatic backups are taken **before every database migration**.

What isn't backed up: model files (big, and re-downloadable; your one model is in `D:\Ollama\models`.
If you want to protect it, copy the whole `D:\Ollama\models` folder while Ollama is stopped), logs,
and the Python environment (re-create it with setup).

## 2. Model inventory export
`.venv\Scripts\python -m neko models > my-models.txt` lists every model with size and digest, so you can
re-pull the same ones later.

## 3. Memory export (portable JSON)
`python -m neko memory export my-memories.json` (sensitive memories are excluded unless you add
`--all`). Import on another install with `memory import my-memories.json`. Non-user-stated memories
re-enter as *pending*.

## 4. Verifying a backup
`python -m neko verify-backup <file.db>` checks the SHA-256 against the sidecar file and runs an
integrity check, opening the file read-only.

## 5. Restoring
1. Quit N.E.K.O. (tray → Quit).
2. `powershell -ExecutionPolicy Bypass -File scripts\restore.ps1 -BackupFile <path\neko-….db>`
3. It verifies the backup first, asks you to type YES, keeps your current file as
   `neko.db.before-restore`, removes stale `-wal`/`-shm` files and copies the backup in.
4. Start N.E.K.O. If the backup has an older schema, it is migrated forward automatically (with
   another pre-migration backup).
**Undo a restore:** quit, then restore from `neko.db.before-restore` the same way. Rename it to
`.db` first, because restore expects a backup file plus its optional sidecar.

## 6. Corruption response
Symptoms: "database disk image is malformed", or doctor shows `Database … FAIL`.
1. Quit N.E.K.O. Don't delete anything.
2. Copy `neko.db`, `neko.db-wal` and `neko.db-shm` to a safe folder (this keeps the evidence).
3. Restore the newest backup that passes `verify-backup`.
4. Optional salvage (advanced): with the SQLite CLI, `sqlite3 neko.db ".recover" > dump.sql`, then
   rebuild. Ask for help before doing this.

## 7. Schema migration recovery
A failed migration is rolled back automatically; your data stays at the old version. Restore the
`…pre-migration-vN.db` backup only if something still looks wrong, and run the previous N.E.K.O.
version until the problem is fixed.

## 8. Incomplete update
`scripts\update.ps1 -Apply` backs up first. If it fails half-way: restore that backup, put the previous
project files back (git checkout of the previous tag, or your previous release zip), and re-run
`setup.ps1 -Apply`.

## 9. After a crash
SQLite's WAL journal makes committed data durable. On the next start N.E.K.O. recovers
automatically. Tasks that were "running" stay in the log as running. Check Activity → tool
invocations for any half-done action.

## 10. Configuration migration
`config_version = 1`. If a future version changes the format, N.E.K.O. refuses to load the old file
with a clear message, and the release notes give the conversion steps. Saving from Settings keeps
the previous file as `config.toml.bak`.

**0.5.0 (2026-10-28):** no format change (`config_version` stays 1), only new optional keys:
`ui.idle_hide_seconds`, `ui.visual_panel_seconds`, `tools.cloud_documents`, `tools.study_folder`.
The owner's file was edited in place (`models.num_ctx` 8192, wider `tools.allowed_roots`) after a
copy was saved as `config.toml.bak-<timestamp>` next to it. Study PDFs in `D:\NEKO-Notes\Study` are
ordinary files: back them up like any document. No database migration.

## 11. Retention and deletion
- History older than `privacy.message_retention_days` (90) is deleted at startup.
- Deleting memories or history removes rows immediately, but **older backups keep their copies**.
  Delete old backup files in `%LOCALAPPDATA%\NEKO\backups` if you want data gone everywhere.
- To shrink the file after big deletions (frees disk pages): with N.E.K.O. closed, run
  `.venv\Scripts\python -c "import sqlite3,os;c=sqlite3.connect(os.path.expandvars(r'%LOCALAPPDATA%\NEKO\neko.db'));c.execute('VACUUM');c.close()"`.
- Wipe everything: `scripts\uninstall.ps1 -Apply -AlsoDeleteData`.

## 12. Encryption
Backups and the database are **not encrypted** by N.E.K.O. They're protected by your Windows account
(files under your profile). For external drives, use BitLocker To Go (Windows Pro) or an encrypted
7-Zip archive (AES-256) with a strong password. Never put a backup in a public place, because it
contains your memories and conversations. Credentials are never stored in N.E.K.O.'s database.

## 13. Schema 2 (0.5.5, 2026-10-28)
Migration `0002_conversation_compaction.sql` adds `conversations.summary_upto` and the `messages_fts` search
index (rebuilt from existing messages). Before applying it N.E.K.O. writes a verified backup
(`backups\neko-...-pre-migration-v1.db`). To go back: quit N.E.K.O., restore that backup (section 5) and run 0.5.4.
