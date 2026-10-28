"""JSON-lines logging with mandatory redaction and size-based rotation.

Log files live in ``%LOCALAPPDATA%\\NEKO\\logs`` (never in the repo). Message
content (prompts, replies, transcripts) is not logged unless the user enables
``privacy.log_message_content``; even then secrets are redacted.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import time
from pathlib import Path

from ..security.redact import redact_text


class RedactingJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact_text(record.getMessage()),
        }
        extra = getattr(record, "neko", None)
        if isinstance(extra, dict):
            entry["data"] = json.loads(redact_text(json.dumps(extra, default=str)))
        if record.exc_info:
            entry["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(log_dir: Path, level: str = "INFO", max_mb: int = 20, console: bool = False) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "neko.log.jsonl"
    root = logging.getLogger("neko")
    root.setLevel(level.upper())
    for h in list(root.handlers):
        root.removeHandler(h)
    fh = logging.handlers.RotatingFileHandler(path, maxBytes=max_mb * 1_048_576 // 4, backupCount=3, encoding="utf-8")
    fh.setFormatter(RedactingJsonFormatter())
    root.addHandler(fh)
    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        ch.setLevel(logging.WARNING)
        root.addHandler(ch)
    root.propagate = False
    return path
