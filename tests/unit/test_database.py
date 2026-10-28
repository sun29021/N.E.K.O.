import sqlite3
import unittest

from tests.helpers import temp_dir

from neko.core.errors import DatabaseError
from neko.database.db import Database, _split_sql


class DatabaseTests(unittest.TestCase):
    def test_migrate_in_memory(self):
        db = Database(":memory:")
        self.assertEqual(db.migrate(), [1, 2])  # 0002: conversation compaction + message search
        self.assertEqual(db.schema_version(), 2)
        self.assertEqual(db.migrate(), [])  # idempotent
        ok, msg = db.integrity_check()
        self.assertTrue(ok, msg)

    def test_foreign_keys_enforced(self):
        db = Database(":memory:")
        db.migrate()
        with self.assertRaises(DatabaseError):
            db.execute("INSERT INTO messages(id, conversation_id, role, content, created_at) VALUES ('m','nope','user','x',0)")

    def test_check_constraints(self):
        db = Database(":memory:")
        db.migrate()
        with self.assertRaises(DatabaseError):
            db.execute("INSERT INTO standing_permissions(id, tool, scope_json, max_risk, created_at) VALUES ('s','t','{}',3,0)")

    def test_transaction_rollback(self):
        db = Database(":memory:")
        db.migrate()
        with self.assertRaises(RuntimeError), db.transaction() as c:
            c.execute("INSERT INTO conversations(id, started_at, updated_at) VALUES ('c1',0,0)")
            raise RuntimeError("boom")
        self.assertIsNone(db.one("SELECT id FROM conversations WHERE id='c1'"))

    def test_split_sql_keeps_triggers(self):
        stmts = _split_sql("CREATE TABLE a(x);\nCREATE TRIGGER t AFTER INSERT ON a BEGIN\n  SELECT 1;\n  SELECT 2;\nEND;\n")
        self.assertEqual(len(stmts), 2)
        self.assertIn("SELECT 2", stmts[1])

    def test_backup_verify_restore(self):
        tmp = temp_dir()
        db = Database(tmp / "neko.db", backup_dir=tmp / "backups")
        db.migrate()
        db.execute("INSERT INTO conversations(id, title, started_at, updated_at) VALUES ('c1','before',0,0)")
        bpath = db.backup(reason="test")
        ok, msg = Database.verify_backup(bpath)
        self.assertTrue(ok, msg)
        db.execute("UPDATE conversations SET title='after' WHERE id='c1'")
        kept = db.restore_from(bpath)
        self.assertTrue(kept.exists())
        db2 = Database(tmp / "neko.db")
        self.assertEqual(db2.one("SELECT title FROM conversations WHERE id='c1'")["title"], "before")
        db2.close()

    def test_tampered_backup_rejected(self):
        tmp = temp_dir()
        db = Database(tmp / "neko.db", backup_dir=tmp / "b")
        db.migrate()
        bpath = db.backup()
        with bpath.open("r+b") as fh:
            fh.seek(200)
            fh.write(b"\xff\xff\xff")
        ok, _ = Database.verify_backup(bpath)
        self.assertFalse(ok)
        with self.assertRaises(DatabaseError):
            db.restore_from(bpath)
        db.close()

    def test_export_json_rejects_unknown_table(self):
        db = Database(":memory:")
        db.migrate()
        with self.assertRaises(DatabaseError):
            db.export_json(["sqlite_master; DROP TABLE memories"])
        self.assertIn("memories", db.export_json(["memories"]))

    def test_wal_mode_on_file(self):
        tmp = temp_dir()
        db = Database(tmp / "x.db")
        self.assertEqual(db.conn.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
        db.close()
        self.assertTrue(isinstance(sqlite3.sqlite_version, str))


if __name__ == "__main__":
    unittest.main()
