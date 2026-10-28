"""Expanded Command Center (docs/UI_UX_SPEC.md section 5).

Tabs: Chat, Activity, Memory, Models & Resources, Diagnostics, Settings.
A red EMERGENCY STOP button is always visible in the header.
"""

from __future__ import annotations

import html
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..app.bootstrap import Neko
from ..configuration.settings import save_user_overrides
from ..core.errors import ConfigError
from .theme import COLORS


def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.horizontalHeader().setStretchLastSection(True)
    t.verticalHeader().setVisible(False)
    return t


def _fill(t: QTableWidget, rows: list[list[Any]]) -> None:
    t.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            t.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))
    t.resizeColumnsToContents()


class CommandCenter(QMainWindow):
    send_requested = Signal(str)
    stop_requested = Signal()
    emergency_requested = Signal()
    resume_requested = Signal()
    doctor_done = Signal(str)

    def __init__(self, neko: Neko) -> None:
        super().__init__()
        self.neko = neko
        self.setWindowTitle("N.E.K.O. Command Center")
        self.resize(1040, 720)
        central = QWidget()
        central.setObjectName("Surface")
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(16, 12, 16, 12)

        header = QHBoxLayout()
        title = QLabel("N.E.K.O.  \u00b7  Neuro Electric Knowledge Operator")
        title.setObjectName("Title")
        header.addWidget(title)
        header.addStretch(1)
        self.privacy_pill = QLabel()
        self.privacy_pill.setObjectName("Pill")
        header.addWidget(self.privacy_pill)
        self.estop_btn = QPushButton("EMERGENCY STOP")
        self.estop_btn.setObjectName("Danger")
        self.estop_btn.setToolTip("Stops everything, cancels pending approvals, blocks all actions until you resume.")
        self.estop_btn.clicked.connect(self._estop_clicked)
        header.addWidget(self.estop_btn)
        lay.addLayout(header)

        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self._build_chat()
        self._build_activity()
        self._build_memory()
        self._build_models()
        self._build_diagnostics()
        self._build_settings()
        self.doctor_done.connect(self.doctor_out.setPlainText)
        self._update_privacy_pill()

    # ------------------------------------------------------------------ chat
    def _build_chat(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        self.chat = QTextBrowser()
        self.chat.setAccessibleName("Conversation")
        v.addWidget(self.chat, 1)
        self.chat_meta = QLabel("")
        self.chat_meta.setObjectName("Dim")
        v.addWidget(self.chat_meta)
        row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Message N.E.K.O.  -  try: remember that I prefer short answers")
        self.chat_input.returnPressed.connect(self._send)
        row.addWidget(self.chat_input, 1)
        send = QPushButton("Send")
        send.setObjectName("Primary")
        send.clicked.connect(self._send)
        row.addWidget(send)
        stop = QPushButton("Stop")
        stop.clicked.connect(self.stop_requested.emit)
        row.addWidget(stop)
        v.addLayout(row)
        self.tabs.addTab(w, "Chat")
        self._streaming = False

    def _send(self) -> None:
        text = self.chat_input.text().strip()
        if not text:
            return
        self.chat_input.clear()
        self.add_user(text)
        self.send_requested.emit(text)

    def add_user(self, text: str) -> None:
        self.chat.append(f"<p style='color:{COLORS['accent']}'><b>You</b></p><p>{html.escape(text)}</p>")
        self.chat.append(f"<p style='color:{COLORS['accent_2']}'><b>N.E.K.O.</b></p>")
        self._streaming = True

    def append_token(self, text: str) -> None:
        if self._streaming:
            cur = self.chat.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(text)
            self.chat.setTextCursor(cur)
            self.chat.ensureCursorVisible()

    def finish_reply(self, reply: Any, streamed_text: str) -> None:
        if not streamed_text.strip() or streamed_text.strip() != reply.text.strip():
            self.chat.append(html.escape(reply.text).replace("\n", "<br>"))
        meta = [f"model: {reply.model or '-'}", f"processed: {reply.location}"]
        if reply.timings.get("tokens_per_s"):
            meta.append(f"{reply.timings['tokens_per_s']:.1f} tok/s")
        if reply.timings.get("first_token_ms"):
            meta.append(f"first token {reply.timings['first_token_ms'] / 1000:.1f}s")
        if reply.memories_used:
            meta.append(f"{len(reply.memories_used)} memories used")
        meta += reply.notes
        self.chat_meta.setText("  \u00b7  ".join(meta))
        self._streaming = False
        self.refresh_activity()

    # ------------------------------------------------------------------ activity
    def _build_activity(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Tasks"))
        self.tasks_table = _table(["When", "Status", "Kind", "Goal"])
        v.addWidget(self.tasks_table, 2)
        v.addWidget(QLabel("Tool activity (arguments redacted)"))
        self.tools_table = _table(["When", "Tool", "Risk", "Status", "Result"])
        v.addWidget(self.tools_table, 2)
        v.addWidget(QLabel("Audit log"))
        self.audit_table = _table(["When", "Category", "Action", "Detail"])
        v.addWidget(self.audit_table, 2)
        b = QPushButton("Refresh")
        b.clicked.connect(self.refresh_activity)
        v.addWidget(b, 0, Qt.AlignmentFlag.AlignRight)
        self.tabs.addTab(w, "Activity")

    def refresh_activity(self) -> None:
        db = self.neko.db
        ts = lambda x: time.strftime("%d %b %H:%M:%S", time.localtime(x)) if x else ""  # noqa: E731
        _fill(self.tasks_table, [[ts(r["created_at"]), r["status"], r["kind"], r["goal"][:120]]
                                 for r in self.neko.tasks.recent(50)])
        _fill(self.tools_table, [[ts(r["started_at"]), r["tool"], r["risk_level"], r["status"], r["result_summary"][:140]]
                                 for r in db.query("SELECT * FROM tool_invocations ORDER BY started_at DESC LIMIT 50")])
        _fill(self.audit_table, [[ts(r["created_at"]), r["category"], r["action"], r["detail_json"][:160]]
                                 for r in db.query("SELECT * FROM audit_events ORDER BY id DESC LIMIT 80")])

    # ------------------------------------------------------------------ memory
    def _build_memory(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        self.mem_search = QLineEdit()
        self.mem_search.setPlaceholderText("Search memories")
        self.mem_search.returnPressed.connect(self.refresh_memory)
        row.addWidget(self.mem_search, 1)
        self.mem_filter = QComboBox()
        self.mem_filter.addItems(["active", "pending_approval", "superseded", "expired", "all"])
        self.mem_filter.currentIndexChanged.connect(self.refresh_memory)
        row.addWidget(self.mem_filter)
        v.addLayout(row)
        self.mem_table = _table(["ID", "Kind", "Trust", "Status", "Conf.", "Used", "Content"])
        self.mem_table.itemSelectionChanged.connect(self._show_provenance)
        v.addWidget(self.mem_table, 3)
        self.mem_detail = QPlainTextEdit()
        self.mem_detail.setReadOnly(True)
        self.mem_detail.setMaximumHeight(130)
        self.mem_detail.setAccessibleName("Memory provenance")
        v.addWidget(self.mem_detail)
        btns = QHBoxLayout()
        for label, fn in (("Add...", self._mem_add), ("Approve", self._mem_approve), ("Edit...", self._mem_edit),
                          ("Delete", self._mem_delete), ("Export...", self._mem_export),
                          ("Clear conversation history...", self._clear_history)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            btns.addWidget(b)
        btns.addStretch(1)
        v.addLayout(btns)
        note = QLabel("Deleting removes the memory, its search index entry and embedding. Backups made earlier "
                      "still contain it until they are deleted (see Backup & Recovery manual).")
        note.setObjectName("Dim")
        note.setWordWrap(True)
        v.addWidget(note)
        self.tabs.addTab(w, "Memory")
        self.refresh_memory()

    def _selected_memory_id(self) -> str | None:
        rows = self.mem_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.mem_table.item(rows[0].row(), 0)
        return item.text() if item else None

    def refresh_memory(self) -> None:
        q = self.mem_search.text().strip()
        status = self.mem_filter.currentText()
        if q:
            mems = self.neko.memory.keyword_search(q, limit=100, include_pending=True)
        else:
            mems = self.neko.memory.list(status=None if status == "all" else status, limit=300)
        _fill(self.mem_table, [[m.id, m.kind, m.trust.value, m.status, f"{m.confidence:.2f}", m.use_count, m.content]
                               for m in mems])

    def _show_provenance(self) -> None:
        mid = self._selected_memory_id()
        if not mid:
            return
        prov = self.neko.memory.provenance(mid)
        uses = self.neko.db.query("SELECT score, reason, created_at FROM memory_retrievals WHERE memory_id=? "
                                  "ORDER BY id DESC LIMIT 5", (mid,))
        lines = ["Provenance:"] + [f"  {time.ctime(p['created_at'])}: {p['source_type']} {p['source_ref']} - {p['note']}"
                                   for p in prov]
        lines += ["Why it was retrieved (latest uses):"] + [f"  {u['score']:.2f}: {u['reason']}" for u in uses]
        self.mem_detail.setPlainText("\n".join(lines))

    def _mem_add(self) -> None:
        text, ok = QInputDialog.getMultiLineText(self, "Add memory", "What should N.E.K.O. remember?")
        if ok and text.strip():
            self.neko.memory.add(text.strip(), kind="fact")
            self.refresh_memory()

    def _mem_approve(self) -> None:
        mid = self._selected_memory_id()
        if mid:
            self.neko.memory.approve(mid)
            self.refresh_memory()

    def _mem_edit(self) -> None:
        mid = self._selected_memory_id()
        m = self.neko.memory.get(mid) if mid else None
        if not m:
            return
        text, ok = QInputDialog.getMultiLineText(self, "Edit memory", "Corrected text:", m.content)
        if ok and text.strip() and text.strip() != m.content:
            self.neko.memory.edit(m.id, text.strip())
            self.refresh_memory()

    def _mem_delete(self) -> None:
        mid = self._selected_memory_id()
        if mid and QMessageBox.question(self, "Delete memory", "Permanently delete this memory?") == \
                QMessageBox.StandardButton.Yes:
            self.neko.memory.delete(mid)
            self.refresh_memory()

    def _mem_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export memories", "neko-memory-export.json", "JSON (*.json)")
        if path:
            Path(path).write_text(json.dumps(self.neko.memory.export(), indent=2, default=str), encoding="utf-8")

    def _clear_history(self) -> None:
        if QMessageBox.question(self, "Clear history", "Delete ALL conversation history? Memories are kept.") == \
                QMessageBox.StandardButton.Yes:
            n = self.neko.conversations.clear_all()
            self.chat.clear()
            QMessageBox.information(self, "Cleared", f"Deleted {n} conversation(s).")

    # ------------------------------------------------------------------ models & resources
    def _build_models(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        form = QFormLayout()
        self.res_ram = QProgressBar()
        self.res_vram = QProgressBar()
        self.res_label = QLabel("-")
        self.res_label.setObjectName("Dim")
        form.addRow("RAM in use", self.res_ram)
        form.addRow("GPU memory in use", self.res_vram)
        form.addRow("", self.res_label)
        v.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(QLabel("Model selection:"))
        self.model_pin = QComboBox()
        self.model_pin.addItem("Automatic (recommended)")
        self.model_pin.currentTextChanged.connect(self._pin_model)
        row.addWidget(self.model_pin, 1)
        ref = QPushButton("Refresh models")
        ref.clicked.connect(self.refresh_models)
        row.addWidget(ref)
        v.addLayout(row)
        self.models_table = _table(["Model", "Params", "Quant.", "Size", "Capabilities", "Where", "Loaded"])
        v.addWidget(self.models_table, 2)
        v.addWidget(QLabel("Last routing decision"))
        self.routing_text = QPlainTextEdit()
        self.routing_text.setReadOnly(True)
        self.routing_text.setMaximumHeight(150)
        v.addWidget(self.routing_text)
        hint = QLabel("N.E.K.O. never downloads models by itself. To add one, follow docs/MODEL_GUIDE.md.")
        hint.setObjectName("Dim")
        v.addWidget(hint)
        self.tabs.addTab(w, "Models && Resources")

    def refresh_models(self) -> None:
        def work() -> None:
            models = self.neko.router.refresh(force=True)
            rows = [[m.name, m.parameter_size, m.quantization, f"{(m.size_bytes or 0) / 1e9:.2f} GB",
                     ", ".join(sorted(c.value for c in m.capabilities)), m.location, "yes" if m.loaded else ""]
                    for m, _ in models]
            self._models_ready = rows
        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(timeout=6)  # /api/tags is fast; avoid freezing longer than this
        rows = getattr(self, "_models_ready", [])
        _fill(self.models_table, rows)
        current = self.model_pin.currentText()
        self.model_pin.blockSignals(True)
        self.model_pin.clear()
        self.model_pin.addItem("Automatic (recommended)")
        for r in rows:
            self.model_pin.addItem(r[0])
        idx = self.model_pin.findText(current)
        self.model_pin.setCurrentIndex(max(0, idx))
        self.model_pin.blockSignals(False)

    def _pin_model(self, text: str) -> None:
        self.neko.router.override = None if text.startswith("Automatic") or not text else text

    def show_resources(self, d: dict[str, Any]) -> None:
        if d.get("ram_total_mb"):
            used = d["ram_total_mb"] - (d.get("ram_free_mb") or 0)
            self.res_ram.setMaximum(int(d["ram_total_mb"]))
            self.res_ram.setValue(int(used))
            self.res_ram.setFormat(f"{used / 1024:.1f} / {d['ram_total_mb'] / 1024:.1f} GB")
        if d.get("vram_total_mb") is not None and d.get("vram_used_mb") is not None:
            self.res_vram.setMaximum(int(d["vram_total_mb"]))
            self.res_vram.setValue(int(d["vram_used_mb"]))
            self.res_vram.setFormat(f"{d['vram_used_mb']} / {d['vram_total_mb']} MB")
        temp = d.get("gpu_temp_c")
        power = "battery" if d.get("on_battery") else "AC power" if d.get("on_battery") is False else "power unknown"
        self.res_label.setText(f"GPU {d.get('gpu_name') or 'n/a'}  \u00b7  GPU temp "
                               f"{'unknown' if temp is None else str(temp) + ' C'}  \u00b7  CPU "
                               f"{'?' if d.get('cpu_pct') is None else round(d['cpu_pct'])}%  \u00b7  {power} "
                               f"{d.get('battery_pct') or ''}%  \u00b7  disk free {d.get('disk_free_gb')} GB  "
                               "\u00b7  CPU temperature: not measured (no reliable sensor API)")

    def show_routing(self, d: dict[str, Any]) -> None:
        lines = [f"Role: {d.get('role')}  ->  {d.get('model') or 'NONE'} ({d.get('location') or '-'})",
                 f"Reason: {d.get('reason')}", f"GPU fit: {d.get('gpu_fit')}  {d.get('slow_warning') or ''}", "Candidates:"]
        for c in d.get("candidates", []):
            lines.append(f"  {c['model']}: " + (f"rejected - {c['rejected']}" if c.get("rejected") else f"score {c['score']}"))
        self.routing_text.setPlainText("\n".join(lines))

    # ------------------------------------------------------------------ diagnostics
    def _build_diagnostics(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        run = QPushButton("Run health check")
        run.setObjectName("Primary")
        run.clicked.connect(self.run_doctor)
        row.addWidget(run)
        logs = QPushButton("Open log folder")
        logs.clicked.connect(lambda: os.startfile(str(self.neko.settings.log_dir)))  # noqa: S606 - our own folder
        row.addWidget(logs)
        backup = QPushButton("Back up now")
        backup.clicked.connect(self._backup)
        row.addWidget(backup)
        row.addStretch(1)
        v.addLayout(row)
        self.doctor_out = QPlainTextEdit()
        self.doctor_out.setReadOnly(True)
        self.doctor_out.setStyleSheet("font-family: Cascadia Mono, Consolas;")
        v.addWidget(self.doctor_out, 1)
        self.tabs.addTab(w, "Diagnostics")

    def run_doctor(self) -> None:
        from ..diagnostics.doctor import format_checks, run_checks

        self.doctor_out.setPlainText("Running read-only checks...")
        threading.Thread(target=lambda: self.doctor_done.emit(format_checks(run_checks(self.neko.settings))),
                         daemon=True).start()

    def _backup(self) -> None:
        try:
            p = self.neko.db.backup(reason="manual")
            QMessageBox.information(self, "Backup", f"Backup written and verified:\n{p}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Backup failed", str(exc))

    # ------------------------------------------------------------------ settings
    def _build_settings(self) -> None:
        s = self.neko.settings
        w = QWidget()
        form = QFormLayout(w)
        self.set_name = QLineEdit(s.app.user_name)
        form.addRow("Your name", self.set_name)
        self.set_personality = QLineEdit(s.app.personality)
        form.addRow("Personality", self.set_personality)
        self.set_verbosity = QComboBox()
        self.set_verbosity.addItems(["brief", "balanced", "detailed"])
        self.set_verbosity.setCurrentText(s.app.verbosity)
        form.addRow("Answer length", self.set_verbosity)
        self.set_profile = QComboBox()
        self.set_profile.addItems(["existing-only", "laptop-lite", "desktop-16gb", "desktop-32gb"])
        self.set_profile.setCurrentText(s.models.profile)
        form.addRow("Model profile", self.set_profile)
        self.set_voice = QCheckBox("Speak replies aloud")
        self.set_voice.setChecked(s.voice.enabled)
        form.addRow("Voice", self.set_voice)
        self.set_tts = QComboBox()
        self.set_tts.addItems(["kokoro", "sapi", "piper", "none"])  # elevenlabs: config file only (cloud)
        self.set_tts.setCurrentText(s.voice.tts_engine)
        form.addRow("Speech engine", self.set_tts)
        self.set_lang = QComboBox()
        self.set_lang.addItems(["en", "bn", ""])
        self.set_lang.setCurrentText(s.voice.stt_language)
        form.addRow("Speech recognition language (blank = auto)", self.set_lang)
        self.set_learning = QCheckBox("Allow N.E.K.O. to save memories and lessons (always with your approval)")
        self.set_learning.setChecked(s.privacy.learning_enabled)
        form.addRow("Learning", self.set_learning)
        self.set_store = QCheckBox("Keep conversation history")
        self.set_store.setChecked(s.privacy.store_conversations)
        form.addRow("History", self.set_store)
        self.set_roots = QLineEdit("; ".join(s.tools.allowed_roots))
        self.set_roots.setPlaceholderText(r"e.g. D:\PROJECT; D:\Notes")
        form.addRow("Folders N.E.K.O. may read", self.set_roots)
        self.set_wroots = QLineEdit("; ".join(s.tools.writable_roots))
        form.addRow("Folders N.E.K.O. may change (with approval)", self.set_wroots)
        self.set_net = QCheckBox("Allow internet (web search, weather, YouTube music, pictures)")
        self.set_net.setChecked(s.privacy.allow_network)
        form.addRow("Internet", self.set_net)
        # Free cloud brains: you create the key on the provider's site and paste it here yourself.
        from ..models.cloud import CLOUDS, read_key

        self.cloud_keys: dict[str, QLineEdit] = {}
        for spec in CLOUDS.values():
            row = QHBoxLayout()
            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            has = bool(read_key(spec, s.data_dir))
            edit.setPlaceholderText("key saved - paste a new one to replace it" if has else "paste your free key here")
            get = QPushButton("Get a free key")
            get.clicked.connect(lambda _=False, url=spec.signup: QDesktopServices.openUrl(QUrl(url)))
            row.addWidget(edit, 1)
            row.addWidget(get)
            holder = QWidget()
            holder.setLayout(row)
            label = {"groq": "Groq key (fast everyday brain)", "gemini": "Gemini key (huge documents, deep thinking)"}
            form.addRow(label.get(spec.name, spec.name), holder)
            self.cloud_keys[spec.key_name] = edit
        self.set_autostart = QCheckBox("Start with Windows (hidden - she appears when you say her name)")
        self.set_autostart.setChecked(_autostart_on())
        form.addRow("Startup", self.set_autostart)
        self.set_cc = QCheckBox("Allow opening apps from the allow-list")
        self.set_cc.setChecked(s.tools.computer_control_enabled)
        form.addRow("Computer control", self.set_cc)
        self.set_motion = QCheckBox("Reduce motion")
        self.set_motion.setChecked(s.ui.reduced_motion)
        form.addRow("Animation", self.set_motion)
        self.set_top = QCheckBox("Keep HUD above other windows")
        self.set_top.setChecked(s.ui.always_on_top)
        form.addRow("HUD", self.set_top)
        save = QPushButton("Save settings")
        save.setObjectName("Primary")
        save.clicked.connect(self._save_settings)
        form.addRow("", save)
        note = QLabel("Saved to %LOCALAPPDATA%\\NEKO\\config.toml. Internet and folders apply at once; restart "
                      "N.E.K.O. for model and voice changes. Cloud models and remote computers can only be enabled "
                      "by editing the file (see USER_MANUAL) - on purpose.")
        note.setObjectName("Dim")
        note.setWordWrap(True)
        form.addRow("", note)
        self.tabs.addTab(w, "Settings")

    def _save_settings(self) -> None:
        split = lambda t: [p.strip() for p in t.split(";") if p.strip()]  # noqa: E731
        net = self.set_net.isChecked()
        if net and not self.neko.settings.privacy.allow_network:
            ok = QMessageBox.question(
                self, "Allow internet?",
                "Neko will be able to search the web, check the weather, show pictures and play YouTube music. "
                "Your searches go to DuckDuckGo, Open-Meteo, Wikipedia and YouTube. Your files and memories stay "
                "on this PC. Turn internet on?")
            if ok != QMessageBox.StandardButton.Yes:
                self.set_net.setChecked(False)
                net = False
        overrides = {
            "app": {"user_name": self.set_name.text().strip(), "personality": self.set_personality.text().strip(),
                    "verbosity": self.set_verbosity.currentText()},
            "models": {"profile": self.set_profile.currentText()},
            "voice": {"enabled": self.set_voice.isChecked(), "tts_engine": self.set_tts.currentText(),
                      "stt_language": self.set_lang.currentText()},
            "privacy": {"learning_enabled": self.set_learning.isChecked(),
                        "store_conversations": self.set_store.isChecked(), "allow_network": net},
            "tools": {"allowed_roots": split(self.set_roots.text()), "writable_roots": split(self.set_wroots.text()),
                      "computer_control_enabled": self.set_cc.isChecked()},
            "ui": {"reduced_motion": self.set_motion.isChecked(), "always_on_top": self.set_top.isChecked()},
        }
        try:
            path = save_user_overrides(_merge_existing(overrides))
        except ConfigError as exc:
            QMessageBox.warning(self, "Not saved", exc.user_message)
            return
        if self.set_autostart.isChecked() != _autostart_on():
            _set_autostart(self.set_autostart.isChecked())  # you ticked/unticked it: add/remove the Startup shortcut
        typed = {k: e.text() for k, e in self.cloud_keys.items() if e.text().strip()}
        if typed:
            from ..models.cloud import save_keys

            save_keys(self.neko.settings.data_dir, typed)
            for e in self.cloud_keys.values():
                e.clear()
                e.setPlaceholderText("key saved - paste a new one to replace it")
            self.neko.router.refresh(force=True)  # the cloud brain is used from the next message on
        # apply what is safe to apply live: internet and the folder lists
        s = self.neko.settings
        s.privacy.allow_network = net
        self.neko.policy.network_allowed = net
        s.tools.allowed_roots = overrides["tools"]["allowed_roots"]
        s.tools.writable_roots = overrides["tools"]["writable_roots"]
        self.neko.coordinator.paths.__init__(s.tools.allowed_roots, s.tools.writable_roots,
                                             self.neko.coordinator.paths.protected)
        self._update_privacy_pill()
        QMessageBox.information(self, "Saved", f"Saved to {path}. Internet is now {'ON' if net else 'OFF'}. "
                                "Restart N.E.K.O. for model and voice changes.")

    # ------------------------------------------------------------------ emergency
    def _estop_clicked(self) -> None:
        if self.neko.estop.tripped:
            self.resume_requested.emit()
            self.estop_btn.setText("EMERGENCY STOP")
        else:
            self.emergency_requested.emit()
            self.estop_btn.setText("RESUME (stopped)")

    def _update_privacy_pill(self) -> None:
        s = self.neko.settings
        parts = ["local only" if not (s.privacy.allow_network or s.privacy.allow_cloud_models or s.remote.enabled)
                 else "network features ON"]
        self.privacy_pill.setText("  " + " \u00b7 ".join(parts) + "  ")


def _startup_link() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / \
        "N.E.K.O..lnk"


def _autostart_on() -> bool:
    return _startup_link().exists()


def _set_autostart(on: bool) -> None:
    """Runs scripts\\autostart.ps1 (argument list, no shell string) - only when you change the checkbox."""
    import subprocess

    script = Path(__file__).resolve().parents[3] / "scripts" / "autostart.ps1"
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                    "-Enable" if on else "-Disable"], capture_output=True, timeout=30, shell=False,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _merge_existing(overrides: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Keep keys the user set by hand in config.toml that the form does not show."""
    import tomllib

    from ..configuration.settings import default_user_config_path

    path = default_user_config_path()
    if not path.exists():
        return overrides
    try:
        existing = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return overrides
    existing.pop("config_version", None)
    merged: dict[str, dict[str, Any]] = {k: dict(v) for k, v in existing.items() if isinstance(v, dict)}
    for section, values in overrides.items():
        merged.setdefault(section, {}).update(values)
    return merged
