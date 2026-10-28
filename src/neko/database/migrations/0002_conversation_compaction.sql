-- 0002: auto-compacting conversations + searchable message history (0.5.5, 2026-10-28)
-- * conversations.summary_upto: messages up to this time are folded into conversations.summary,
--   so the summary grows step by step instead of being rebuilt from the last 40 messages.
-- * messages_fts: full-text index so she can recall what was said long ago (only when
--   privacy.store_conversations is on - otherwise messages are never stored at all).

ALTER TABLE conversations ADD COLUMN summary_upto REAL NOT NULL DEFAULT 0;

CREATE VIRTUAL TABLE messages_fts USING fts5(
    content, content='messages', content_rowid='rowid', tokenize='unicode61'
);
CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
END;
CREATE TRIGGER messages_au AFTER UPDATE OF content ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
    INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
END;
INSERT INTO messages_fts(messages_fts) VALUES ('rebuild');
