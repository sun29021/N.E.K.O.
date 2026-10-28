-- 0003: reminders and learned skills (0.8.0, 2026-10-28)
-- * reminders: "remind me at 6 to call Ammu" - spoken on the PC and sent to the paired phone when due.
-- * skills: a sequence of actions she did for you, saved under a name ("do the monthly sheet").
--   Replaying a skill runs every step through the normal permission policy again (approvals included).

CREATE TABLE reminders (
    id              TEXT PRIMARY KEY,
    due_at          REAL NOT NULL,
    text            TEXT NOT NULL,
    created_at      REAL NOT NULL,
    origin          TEXT NOT NULL DEFAULT '',
    done_at         REAL
);
CREATE INDEX idx_reminders_due ON reminders(done_at, due_at);

CREATE TABLE skills (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    steps_json      TEXT NOT NULL,       -- [{"tool": ..., "args": {...}, "say": "open Excel"}]
    created_at      REAL NOT NULL,
    last_used_at    REAL,
    uses            INTEGER NOT NULL DEFAULT 0
);
