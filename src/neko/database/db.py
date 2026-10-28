"""SQLite access: connection management, versioned migrations, backup/restore.

* WAL journal mode for safe concurrent readers + one writer.
* Foreign keys enforced on every connection.
* A connection per thread (sqlite3 objects are not shared across threads).
* Every migration runs inside a transaction; on failure nothing is applied.
* Before applying migrations to an existing database a verified backup is made.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..core.errors import DatabaseError

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
_MIGRATION_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


def _discover_migrations() -> list[tuple[int, Path]]:
    out = []
    for p in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = _MIGRATION_RE.match(p.name)
        if m:
            out.append((int(m.group(1)), p))
    return out


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Database:
    def __init__(self, path: Path | str, *, backup_dir: Path | None = None) -> None:
        self.path = Path(path)
        self.backup_dir = backup_dir
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self._all_conns: list[sqlite3.Connection] = []
        self.in_memory = str(path) == ":memory:"
        if self.in_memory:
            # one shared connection for tests; guarded by the write lock
            self._shared = self._connect()
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ connections
    def _connect(self) -> sqlite3.Connection:
        # Each thread uses only its own connection; check_same_thread=False just lets
        # close() release worker-thread connections at shutdown.
        conn = sqlite3.connect(str(self.path), timeout=10, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        if not self.in_memory:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        if self.in_memory:
            return self._shared
        c = getattr(self._local, "conn", None)
        if c is None:
            c = self._connect()
            self._local.conn = c
            with self._write_lock:
                self._all_conns.append(c)
        return c

    def close(self) -> None:
        """Close every connection opened by any thread (call at shutdown)."""
        if self.in_memory:
            self._shared.close()
            return
        with self._write_lock:
            conns, self._all_conns = self._all_conns, []
        for c in conns:
            try:
                c.close()
            except sqlite3.ProgrammingError:
                pass  # sqlite refuses cross-thread close on some builds; process exit releases it
        self._local = threading.local()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._write_lock:
            c = self.conn
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
            except BaseException:
                c.execute("ROLLBACK")
                raise
            else:
                c.execute("COMMIT")

    def execute(self, sql: str, params: tuple[Any, ...] | dict[str, Any] = ()) -> sqlite3.Cursor:
        try:
            if sql.lstrip().upper().startswith("SELECT"):
                return self.conn.execute(sql, params)
            with self._write_lock:
                return self.conn.execute(sql, params)
        except sqlite3.Error as exc:
            raise DatabaseError(str(exc)) from exc

    def query(self, sql: str, params: tuple[Any, ...] | dict[str, Any] = ()) -> list[sqlite3.Row]:
        return self.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple[Any, ...] | dict[str, Any] = ()) -> sqlite3.Row | None:
        return self.execute(sql, params).fetchone()

    # ------------------------------------------------------------------ migrations
    def schema_version(self) -> int:
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    def migrate(self) -> list[int]:
        """Apply pending migrations. Returns the versions applied."""
        current = self.schema_version()
        pending = [(v, p) for v, p in _discover_migrations() if v > current]
        if not pending:
            return []
        if current > 0 and not self.in_memory and self.backup_dir is not None:
            self.backup(reason=f"pre-migration-v{current}")
        applied = []
        for version, path in pending:
            sql = path.read_text(encoding="utf-8")
            with self._write_lock:
                c = self.conn
                try:
                    c.execute("BEGIN IMMEDIATE")
                    for statement in _split_sql(sql):
                        c.execute(statement)
                    c.execute(f"PRAGMA user_version = {version:d}")
                    c.execute("COMMIT")
                except sqlite3.Error as exc:
                    c.execute("ROLLBACK")
                    raise DatabaseError(
                        f"migration {path.name} failed: {exc}",
                        user_message=(
                            f"Database upgrade {path.name} failed and was rolled back. "
                            "Your data is unchanged. See docs/BACKUP_AND_RECOVERY.md."
                        ),
                    ) from exc
            applied.append(version)
        return applied

    # ------------------------------------------------------------------ integrity / backup
    def integrity_check(self) -> tuple[bool, str]:
        rows = self.conn.execute("PRAGMA integrity_check").fetchall()
        msg = "; ".join(str(r[0]) for r in rows)
        fk = self.conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            msg += f"; {len(fk)} foreign key violation(s)"
        return (msg == "ok" and not fk), msg

    def backup(self, dest: Path | None = None, *, reason: str = "manual") -> Path:
        """Online, consistent backup using the SQLite backup API."""
        if self.in_memory:
            raise DatabaseError("cannot back up an in-memory database")
        target_dir = dest.parent if dest else (self.backup_dir or self.path.parent / "backups")
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = dest or target_dir / f"neko-{stamp}-{reason}.db"
        bconn = sqlite3.connect(str(dest))
        try:
            with self._write_lock:
                self.conn.backup(bconn)
        finally:
            bconn.close()
        check = sqlite3.connect(str(dest))
        try:
            ok = check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            check.close()
        if not ok:
            dest.unlink(missing_ok=True)
            raise DatabaseError("backup failed its integrity check and was discarded")
        digest = file_sha256(dest)
        dest.with_suffix(".db.sha256").write_text(f"{digest}  {dest.name}\n", encoding="ascii")
        try:
            self.execute(
                "INSERT INTO backups(path, sha256, size_bytes, schema_version, created_at) VALUES (?,?,?,?,?)",
                (str(dest), digest, dest.stat().st_size, self.schema_version(), time.time()),
            )
        except DatabaseError:
            pass  # schema may not exist yet (pre-migration backup of an old file)
        return dest

    @staticmethod
    def verify_backup(path: Path) -> tuple[bool, str]:
        sidecar = path.with_suffix(".db.sha256")
        if not path.exists():
            return False, "backup file missing"
        if sidecar.exists():
            expected = sidecar.read_text(encoding="ascii").split()[0]
            if file_sha256(path) != expected:
                return False, "checksum mismatch: the backup file was modified or corrupted"
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            res = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
        return res == "ok", res

    def restore_from(self, backup_path: Path) -> Path:
        """Replace the live database with a verified backup.

        The current file is kept as ``neko.db.before-restore`` so a restore can
        itself be undone. Callers must make sure the app is otherwise idle.
        """
        ok, msg = self.verify_backup(backup_path)
        if not ok:
            raise DatabaseError(f"refusing to restore: {msg}")
        self.close()
        keep = self.path.with_suffix(".db.before-restore")
        if self.path.exists():
            shutil.copy2(self.path, keep)
        for suffix in ("-wal", "-shm"):
            Path(str(self.path) + suffix).unlink(missing_ok=True)
        shutil.copy2(backup_path, self.path)
        return keep

    # ------------------------------------------------------------------ export
    def export_json(self, tables: list[str]) -> dict[str, list[dict[str, Any]]]:
        allowed = {r["name"] for r in self.query("SELECT name FROM sqlite_master WHERE type='table'")}
        out: dict[str, list[dict[str, Any]]] = {}
        for t in tables:
            if t not in allowed:
                raise DatabaseError(f"unknown table {t}")
            rows = self.query(f'SELECT * FROM "{t}"')  # noqa: S608 - name validated above
            out[t] = [
                {k: (r[k].hex() if isinstance(r[k], bytes) else r[k]) for k in r.keys()} for r in rows
            ]
        return out

    def audit(self, category: str, action: str, **detail: Any) -> None:
        self.execute(
            "INSERT INTO audit_events(category, action, detail_json, created_at) VALUES (?,?,?,?)",
            (category, action, json.dumps(detail, default=str), time.time()),
        )


def _split_sql(sql: str) -> list[str]:
    """Split a migration into statements, keeping trigger bodies intact."""
    statements: list[str] = []
    buf: list[str] = []
    in_trigger = False
    for line in sql.splitlines():
        stripped = line.strip()
        if not buf and (not stripped or stripped.startswith("--")):
            continue
        buf.append(line)
        upper = stripped.upper()
        if upper.startswith("CREATE TRIGGER"):
            in_trigger = True
        if in_trigger:
            if upper == "END;":
                statements.append("\n".join(buf))
                buf, in_trigger = [], False
        elif stripped.endswith(";"):
            statements.append("\n".join(buf))
            buf = []
    if "".join(buf).strip():
        statements.append("\n".join(buf))
    return statements
