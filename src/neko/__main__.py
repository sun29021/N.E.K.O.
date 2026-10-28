"""Command-line entry point.

    python -m neko doctor            read-only health check
    python -m neko chat              text chat in the terminal (approvals asked in the terminal)
    python -m neko ask "question"    one-shot question
    python -m neko ui                desktop HUD (needs PySide6)
    python -m neko models            list installed models (disk + server)
    python -m neko memory list|add|delete|export|import|pending|approve
    python -m neko backup | restore <file> | verify-backup <file>
    python -m neko config-check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import APP_FULL_NAME, APP_NAME, __version__


def _approval_prompt(req: object) -> None:
    r = req  # ApprovalRequest
    print("\n" + "=" * 70)
    print(f"APPROVAL NEEDED (risk level {int(r.risk)}): {r.summary}")  # type: ignore[attr-defined]
    print(f"Side effects: {r.side_effects}. Reversible: {'yes' if r.reversible else 'NO'}")  # type: ignore[attr-defined]
    answer = input("Type 'yes' to allow, anything else to refuse: ").strip().lower()
    r.resolve(answer == "yes")  # type: ignore[attr-defined]


def cmd_chat(args: argparse.Namespace) -> int:
    from .app.bootstrap import build
    from .core.cancel import CancelToken

    neko = build()
    neko.policy.set_approval_handler(_approval_prompt)
    print(f"{APP_NAME} {__version__} - {APP_FULL_NAME}. Type /quit to exit, Ctrl+C to stop a reply.")
    health = neko.providers[0].health()
    if not health.ok:
        print("Warning: the Ollama server is not reachable. Start it with scripts\\start-ollama.ps1")
    conv = neko.conversations.create("terminal chat")
    try:
        while True:
            try:
                text = input("\nyou > ").strip()
            except EOFError:
                break
            if not text:
                continue
            if text in ("/quit", "/exit"):
                break
            token = CancelToken()
            streamed: list[str] = []

            def show(t: str) -> None:
                streamed.append(t)
                print(t, end="", flush=True)

            print("neko > ", end="", flush=True)
            try:
                reply = neko.coordinator.handle(text, conversation_id=conv, token=token, on_token=show)
            except KeyboardInterrupt:
                token.cancel("user interrupted")
                print("\n[stopped]")
                continue
            if not streamed:
                print(reply.text, end="")  # memory commands, errors and tool-only turns are not streamed
            elif "".join(streamed).strip() != reply.text.strip():
                print("\n" + reply.text, end="")  # final answer after tool calls
            print()
            meta = [f"model: {reply.model or '-'} ({reply.location})"]
            if reply.timings.get("tokens_per_s"):
                meta.append(f"{reply.timings['tokens_per_s']:.1f} tok/s")
            meta += reply.notes
            print("   [" + " | ".join(meta) + "]")
    finally:
        neko.shutdown()
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    from .app.bootstrap import build

    neko = build()
    neko.policy.set_approval_handler(_approval_prompt)
    try:
        reply = neko.coordinator.handle(" ".join(args.text))
        print(reply.text)
        return 0 if reply.succeeded else 2
    finally:
        neko.shutdown()


def cmd_doctor(args: argparse.Namespace) -> int:
    from .configuration.settings import load_settings
    from .diagnostics.doctor import doctor_main

    return doctor_main(load_settings)


def cmd_config_check(args: argparse.Namespace) -> int:
    from .configuration.settings import as_dict, load_settings
    from .core.errors import ConfigError

    try:
        s = load_settings()
    except ConfigError as exc:
        print(exc.user_message)
        return 1
    print("Configuration is valid. Sources:", ", ".join(s.source_files))
    if args.show:
        print(json.dumps(as_dict(s), indent=2, default=str))
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    import os

    from .configuration.settings import load_settings
    from .models.inventory import scan_ollama_store
    from .models.ollama import OllamaProvider

    s = load_settings()
    models_dir = Path(os.environ.get("OLLAMA_MODELS") or r"D:\Ollama\models")
    print(f"On disk in {models_dir} (read-only scan):")
    for e in scan_ollama_store(models_dir):
        print(f"  {e.name:28} {e.quantization:8} {e.size_bytes / 1e9:6.2f} GB  licence: {e.license_note}")
    p = OllamaProvider(s.models.ollama_url)
    h = p.health()
    if not h.ok:
        print("Ollama server: not running (start with scripts\\start-ollama.ps1)")
        return 0
    print(f"Ollama server {h.version}:")
    for m in p.list_models():
        caps = ",".join(sorted(c.value for c in m.capabilities))
        print(f"  {m.name:28} {m.parameter_size:6} {m.quantization:8} [{caps}]{' LOADED' if m.loaded else ''}")
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    from .app.bootstrap import build

    neko = build()
    try:
        store = neko.memory
        if args.action == "list":
            for m in store.list(status=None if args.all else "active"):
                print(f"[{m.id}] ({m.kind}/{m.trust.value}/{m.status} conf {m.confidence:.2f}) {m.content}")
        elif args.action == "pending":
            for m in store.list(status="pending_approval"):
                print(f"[{m.id}] ({m.kind}/{m.trust.value}) {m.content}")
        elif args.action == "approve":
            store.approve(args.value)
            print("approved")
        elif args.action == "add":
            m = store.add(args.value, kind=args.kind)
            print(f"added {m.id} ({m.status})")
        elif args.action == "delete":
            print("deleted" if store.delete(args.value) else "not found")
        elif args.action == "export":
            out = Path(args.value or "neko-memory-export.json")
            out.write_text(json.dumps(store.export(include_sensitive=args.all), indent=2, default=str), encoding="utf-8")
            print(f"exported to {out.resolve()}")
        elif args.action == "import":
            n = store.import_export(json.loads(Path(args.value).read_text(encoding="utf-8")))
            print(f"imported {n} memories (non user-stated ones wait in 'pending')")
    finally:
        neko.shutdown()
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    from .configuration.settings import load_settings
    from .database.db import Database

    s = load_settings()
    db = Database(s.db_path, backup_dir=s.backup_dir)
    if args.action == "backup":
        db.migrate()
        p = db.backup(reason="manual")
        print(f"backup written and verified: {p}")
        backups = sorted(s.backup_dir.glob("neko-*.db"))
        print(f"{len(backups)} backup(s) in {s.backup_dir} (keep setting: {s.storage.backup_keep}; old ones are not auto-deleted)")
    elif args.action == "verify-backup":
        ok, msg = Database.verify_backup(Path(args.file))
        print(("OK: " if ok else "FAILED: ") + msg)
        return 0 if ok else 1
    elif args.action == "restore":
        kept = db.restore_from(Path(args.file))
        print(f"restored. The previous database was kept at {kept}")
    db.close()
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    try:
        from .ui.app import run_ui
    except ImportError as exc:
        print(f"The desktop UI needs PySide6 ({exc}). Install it with scripts\\setup.ps1 (it is included by default).")
        return 1
    return run_ui(background=bool(getattr(args, "background", False)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="neko", description=f"{APP_NAME} - {APP_FULL_NAME}")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("doctor", help="read-only health check").set_defaults(fn=cmd_doctor)
    cc = sub.add_parser("config-check", help="validate configuration")
    cc.add_argument("--show", action="store_true")
    cc.set_defaults(fn=cmd_config_check)
    sub.add_parser("chat", help="terminal chat").set_defaults(fn=cmd_chat)
    a = sub.add_parser("ask", help="one-shot question")
    a.add_argument("text", nargs="+")
    a.set_defaults(fn=cmd_ask)
    ui = sub.add_parser("ui", help="desktop HUD")
    ui.add_argument("--background", action="store_true", help="start hidden; appear when she hears her name")
    ui.set_defaults(fn=cmd_ui)
    sub.add_parser("models", help="list models").set_defaults(fn=cmd_models)
    m = sub.add_parser("memory", help="inspect and manage memory")
    m.add_argument("action", choices=["list", "pending", "approve", "add", "delete", "export", "import"])
    m.add_argument("value", nargs="?", default="")
    m.add_argument("--kind", default="fact")
    m.add_argument("--all", action="store_true", help="include non-active / sensitive")
    m.set_defaults(fn=cmd_memory)
    b = sub.add_parser("backup", help="back up the database")
    b.set_defaults(fn=cmd_backup, action="backup")
    r = sub.add_parser("restore", help="restore the database from a backup")
    r.add_argument("file")
    r.set_defaults(fn=cmd_backup, action="restore")
    v = sub.add_parser("verify-backup", help="check a backup file")
    v.add_argument("file")
    v.set_defaults(fn=cmd_backup, action="verify-backup")
    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        args = ap.parse_args(["ui"] if argv is None and len(sys.argv) == 1 else ["--help"])
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
