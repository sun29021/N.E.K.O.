-- N.E.K.O. schema v1. See docs/DATABASE_SCHEMA.md for field meanings.
-- Timestamps are Unix epoch seconds (REAL). IDs are short random hex strings.

CREATE TABLE settings_kv (
    key         TEXT PRIMARY KEY,
    value_json  TEXT NOT NULL,
    updated_at  REAL NOT NULL
);

-- ---------------------------------------------------------------- conversations
CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    started_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    summary     TEXT NOT NULL DEFAULT '',
    archived    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('system','user','assistant','tool')),
    content         TEXT NOT NULL,
    created_at      REAL NOT NULL,
    model           TEXT,
    location        TEXT,              -- local | lan:<name> | cloud:<name>
    token_estimate  INTEGER
);
CREATE INDEX idx_messages_conv_time ON messages(conversation_id, created_at);

-- ---------------------------------------------------------------- memories
CREATE TABLE memories (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL CHECK (kind IN
                    ('preference','fact','project','episode','lesson','assumption','temporary')),
    content         TEXT NOT NULL,
    trust           TEXT NOT NULL CHECK (trust IN
                    ('user_stated','verified','observed','inferred','untrusted')),
    confidence      REAL NOT NULL DEFAULT 0.7 CHECK (confidence BETWEEN 0 AND 1),
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN
                    ('active','pending_approval','superseded','deleted','expired')),
    version         INTEGER NOT NULL DEFAULT 1,
    supersedes_id   TEXT REFERENCES memories(id) ON DELETE SET NULL,
    tags            TEXT NOT NULL DEFAULT '',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL,
    last_used_at    REAL,
    use_count       INTEGER NOT NULL DEFAULT 0,
    expires_at      REAL,
    sensitive       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_memories_status_kind ON memories(status, kind);
CREATE INDEX idx_memories_expires ON memories(expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE memory_provenance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id   TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,          -- user_message | tool_result | task_outcome | import | manual_edit
    source_ref  TEXT NOT NULL DEFAULT '',-- message id, task id, file path...
    note        TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);
CREATE INDEX idx_provenance_memory ON memory_provenance(memory_id);

CREATE TABLE memory_embeddings (
    memory_id   TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
    model       TEXT NOT NULL,
    dims        INTEGER NOT NULL,
    vector      BLOB NOT NULL,          -- float32 little-endian
    created_at  REAL NOT NULL
);

CREATE TABLE memory_contradictions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_a    TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    memory_b    TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    note        TEXT NOT NULL DEFAULT '',
    resolved    INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL
);

-- Full-text index over memory content (external content table).
CREATE VIRTUAL TABLE memories_fts USING fts5(
    content, tags, content='memories', content_rowid='rowid', tokenize='unicode61'
);
CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, tags) VALUES (new.rowid, new.content, new.tags);
END;
CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags) VALUES ('delete', old.rowid, old.content, old.tags);
END;
CREATE TRIGGER memories_au AFTER UPDATE OF content, tags ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags) VALUES ('delete', old.rowid, old.content, old.tags);
    INSERT INTO memories_fts(rowid, content, tags) VALUES (new.rowid, new.content, new.tags);
END;

CREATE TABLE memory_retrievals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id   TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    task_id     TEXT,
    score       REAL NOT NULL,
    reason      TEXT NOT NULL,
    created_at  REAL NOT NULL
);

-- ---------------------------------------------------------------- documents / projects
CREATE TABLE documents (
    id          TEXT PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL DEFAULT '',
    sha256      TEXT,
    size_bytes  INTEGER,
    project     TEXT NOT NULL DEFAULT '',
    indexed_at  REAL
);

-- ---------------------------------------------------------------- tasks & outcomes
CREATE TABLE tasks (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    goal            TEXT NOT NULL,
    kind            TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN
                    ('pending','planning','running','awaiting_approval','verifying',
                     'succeeded','failed','cancelled')),
    plan_json       TEXT NOT NULL DEFAULT '[]',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL,
    finished_at     REAL,
    error           TEXT
);
CREATE INDEX idx_tasks_status ON tasks(status, updated_at);

CREATE TABLE task_steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    description TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  REAL NOT NULL,
    UNIQUE (task_id, seq)
);

CREATE TABLE tool_invocations (
    id              TEXT PRIMARY KEY,
    task_id         TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    tool            TEXT NOT NULL,
    risk_level      INTEGER NOT NULL,
    args_redacted   TEXT NOT NULL,       -- JSON with secrets redacted
    status          TEXT NOT NULL CHECK (status IN
                    ('denied','awaiting_approval','running','succeeded','failed','cancelled','timeout')),
    result_summary  TEXT NOT NULL DEFAULT '',
    started_at      REAL NOT NULL,
    finished_at     REAL,
    approval_id     TEXT
);
CREATE INDEX idx_tool_invocations_task ON tool_invocations(task_id);

CREATE TABLE verification_evidence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    invocation_id   TEXT REFERENCES tool_invocations(id) ON DELETE SET NULL,
    method          TEXT NOT NULL,       -- file_exists | exit_code | api_status | user_confirmed | ...
    passed          INTEGER NOT NULL,
    detail          TEXT NOT NULL DEFAULT '',
    created_at      REAL NOT NULL
);

CREATE TABLE outcomes (
    task_id         TEXT PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    succeeded       INTEGER NOT NULL,
    failure_class   TEXT,                -- model_error | tool_error | permission | timeout | user_rejected | unknown
    failure_reason  TEXT,
    user_feedback   TEXT,
    lesson          TEXT,
    lesson_confidence REAL,
    lesson_status   TEXT CHECK (lesson_status IN ('none','proposed','approved','rejected')),
    created_at      REAL NOT NULL
);

CREATE TABLE incidents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    severity    TEXT NOT NULL CHECK (severity IN ('info','warning','error','critical')),
    component   TEXT NOT NULL,
    message     TEXT NOT NULL,
    created_at  REAL NOT NULL
);

-- ---------------------------------------------------------------- workflows
CREATE TABLE workflows (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    reliable    INTEGER NOT NULL DEFAULT 0,  -- set only after evidence of repeated success
    created_at  REAL NOT NULL
);

CREATE TABLE workflow_versions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id   TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    version       INTEGER NOT NULL,
    steps_json    TEXT NOT NULL,
    approved      INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    UNIQUE (workflow_id, version)
);

-- ---------------------------------------------------------------- models & resources
CREATE TABLE model_inventory (
    name            TEXT PRIMARY KEY,     -- e.g. llama3.2:3b
    runtime         TEXT NOT NULL,        -- ollama | llamacpp | faster-whisper | piper ...
    path            TEXT,
    size_bytes      INTEGER,
    quantization    TEXT,
    capabilities    TEXT NOT NULL DEFAULT '',
    license         TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT '',
    digest          TEXT,
    last_used_at    REAL,
    discovered_at   REAL NOT NULL,
    removable       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE routing_decisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT,
    task_kind   TEXT NOT NULL,
    chosen      TEXT,
    candidates  TEXT NOT NULL,            -- JSON list of {model, score, rejected_reason}
    reason      TEXT NOT NULL,
    latency_ms  REAL,
    succeeded   INTEGER,
    created_at  REAL NOT NULL
);
CREATE INDEX idx_routing_model ON routing_decisions(chosen, created_at);

CREATE TABLE resource_samples (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ram_free_mb     INTEGER,
    ram_total_mb    INTEGER,
    vram_free_mb    INTEGER,
    vram_total_mb   INTEGER,
    gpu_util_pct    REAL,
    gpu_temp_c      REAL,
    cpu_pct         REAL,
    on_battery      INTEGER,
    battery_pct     INTEGER,
    created_at      REAL NOT NULL
);

-- ---------------------------------------------------------------- permissions & audit
CREATE TABLE approvals (
    id          TEXT PRIMARY KEY,
    tool        TEXT NOT NULL,
    risk_level  INTEGER NOT NULL,
    summary     TEXT NOT NULL,
    decision    TEXT NOT NULL CHECK (decision IN ('pending','approved','denied','expired')),
    decided_by  TEXT NOT NULL DEFAULT '',  -- 'user' or 'standing_rule:<id>'
    created_at  REAL NOT NULL,
    decided_at  REAL
);

CREATE TABLE standing_permissions (
    id          TEXT PRIMARY KEY,
    tool        TEXT NOT NULL,
    scope_json  TEXT NOT NULL,            -- narrow constraints, e.g. {"path_prefix": "D:\\Notes"}
    max_risk    INTEGER NOT NULL CHECK (max_risk <= 2),   -- level 3 can never be pre-approved
    created_at  REAL NOT NULL,
    expires_at  REAL,
    enabled     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE audit_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL,            -- tool | permission | memory | model | config | security | system
    action      TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at  REAL NOT NULL
);
CREATE INDEX idx_audit_time ON audit_events(created_at);

CREATE TABLE backups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    size_bytes  INTEGER NOT NULL,
    schema_version INTEGER NOT NULL,
    created_at  REAL NOT NULL
);
