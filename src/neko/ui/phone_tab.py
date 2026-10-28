"""Command Center > Phone: connect Telegram, pair your phone, set the approval PIN, turn calls on/off.

Every step that connects to something or changes Tailscale happens only when you click its button.
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "phone-call.ps1"


def _row(*widgets: QWidget) -> QWidget:
    holder = QWidget()
    lay = QHBoxLayout(holder)
    lay.setContentsMargins(0, 0, 0, 0)
    for i, w in enumerate(widgets):
        lay.addWidget(w, 1 if i == 0 else 0)
    return holder


class PhoneTab(QWidget):
    message = Signal(str)   # results from background work, shown on the GUI thread
    hint = Signal(str)      # "pair your phone: send /pair 123456" (also shown on the orb)

    def __init__(self, neko: Any, phone: Any, calls: Any) -> None:
        super().__init__()
        self.neko, self.phone, self.calls = neko, phone, calls
        s = neko.settings
        form = QFormLayout(self)
        intro = QLabel("Chat or call Neko from your phone. Only your own paired phone can reach her; risky actions "
                       "ask you on the phone (high-risk ones need your PIN).")
        intro.setWordWrap(True)
        intro.setObjectName("Dim")
        form.addRow(intro)
        self.status = QLabel()
        form.addRow("Status", self.status)

        # 1. Telegram
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        from ..phone.service import bot_token

        self.key.setPlaceholderText("bot key saved - paste a new one to replace it" if bot_token(s.data_dir)
                                    else "paste the key @BotFather gave you")
        how = QPushButton("Make a bot")
        how.setToolTip("Opens @BotFather in Telegram: send /newbot, pick a name, copy the key it gives you.")
        how.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://t.me/BotFather")))
        form.addRow("1. Telegram bot key", _row(self.key, how))
        self.enable = QCheckBox("Chat with Neko from Telegram")
        self.enable.setChecked(s.phone.telegram)
        connect = QPushButton("Save && connect")
        connect.setObjectName("Primary")
        connect.clicked.connect(self._connect)
        form.addRow("", _row(self.enable, connect))

        # 2. Pairing
        pair = QPushButton("Pair my phone")
        pair.clicked.connect(self._pair)
        unpair = QPushButton("Unpair")
        unpair.clicked.connect(self._unpair)
        self.pair_info = QLabel()
        self.pair_info.setWordWrap(True)
        self.pair_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        form.addRow("2. Pairing", _row(self.pair_info, pair, unpair))

        # 3. PIN
        self.pin = QLineEdit()
        self.pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin.setPlaceholderText("4-8 digits - needed to approve high-risk actions from the phone")
        self.pin.setMaxLength(8)
        set_pin = QPushButton("Set PIN")
        set_pin.clicked.connect(self._set_pin)
        form.addRow("3. Approval PIN", _row(self.pin, set_pin))

        # 4. Calls
        self.call_btn = QPushButton()
        self.call_btn.clicked.connect(self._toggle_calls)
        send_link = QPushButton("Send call link to my phone")
        send_link.clicked.connect(self._send_link)
        self.call_info = QLabel()
        self.call_info.setWordWrap(True)
        form.addRow("4. Live calls", _row(self.call_info, self.call_btn, send_link))

        # Options
        self.voice = QComboBox()
        self.voice.addItems(["auto", "always", "never"])
        self.voice.setCurrentText(s.phone.voice_replies)
        self.voice.setToolTip("auto = she answers with a voice note when you sent one")
        form.addRow("Voice-note replies", self.voice)
        self.jobs = QCheckBox("Tell my phone when a long job on the PC finishes")
        self.jobs.setChecked(s.phone.notify_long_jobs)
        form.addRow("Alerts", self.jobs)
        self.batt = QCheckBox("Warn my phone when the PC battery is low")
        self.batt.setChecked(s.phone.notify_battery)
        form.addRow("", self.batt)
        save = QPushButton("Save options")
        save.clicked.connect(self._save_options)
        form.addRow("", save)

        self.message.connect(lambda m: (self.status.setText(m), self._refresh()))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(3000)
        self._refresh()

    # ------------------------------------------------------------------ helpers
    def _save(self, values: dict[str, Any]) -> bool:
        from ..configuration.settings import save_user_overrides
        from ..core.errors import ConfigError
        from .command_center import _merge_existing

        try:
            save_user_overrides(_merge_existing({"phone": values}))
        except ConfigError as exc:
            QMessageBox.warning(self, "Not saved", exc.user_message)
            return False
        for k, v in values.items():
            setattr(self.neko.settings.phone, k, v)
        return True

    def _refresh(self) -> None:
        p, s = self.phone, self.neko.settings
        bot = f" as @{p.bot_name}" if p.bot_name else ""
        who = f", paired with {p.state.owner_name or 'your phone'}" if p.paired else ", not paired yet"
        self.status.setText(f"Telegram: {p.status}{bot}{who if p.running else ''}  |  "
                            f"Calls: {'on' if s.phone.calls else 'off'}")
        if p.paired:
            self.pair_info.setText(f"Paired with {p.state.owner_name or 'your phone'}.")
        elif p._pair_code and time.time() < p._pair_until:
            self.pair_info.setText(f"In Telegram, open @{p.bot_name} and send:  /pair {p._pair_code}  "
                                   f"(valid {max(1, int((p._pair_until - time.time()) // 60))} more min)")
        else:
            self.pair_info.setText("Not paired - click Pair my phone.")
        self.call_btn.setText("Turn off calls" if s.phone.calls else "Turn on calls")
        self.call_info.setText("Your phone needs the free Tailscale app, signed in to your account." if not
                               s.phone.calls else "On - send yourself the link, then tap it on the phone.")

    # ------------------------------------------------------------------ actions
    def _connect(self) -> None:
        key = self.key.text().strip()
        if key:
            from ..models.cloud import save_keys

            save_keys(self.neko.settings.data_dir, {"telegram_bot_token": key})
            self.key.clear()
            self.key.setPlaceholderText("bot key saved - paste a new one to replace it")
        on = self.enable.isChecked()
        if on and not self.neko.settings.privacy.allow_network:
            QMessageBox.information(self, "Internet is off", "Telegram needs internet: tick 'Allow internet' in "
                                                             "Settings and save first.")
            return
        if not self._save({"telegram": on}):
            return
        self.status.setText("Connecting...")
        threading.Thread(target=lambda: self.message.emit(self.phone.start()), daemon=True).start()

    def _pair(self) -> None:
        if not self.phone.running:
            QMessageBox.information(self, "Connect first", "Save the bot key and connect (step 1) first.")
            return
        code = self.phone.begin_pairing()
        self.pair_info.setText(f"In Telegram, open @{self.phone.bot_name} and send:  /pair {code}  "
                               "(valid 10 minutes)")

    def _unpair(self) -> None:
        if QMessageBox.question(self, "Unpair?", "Stop answering your current phone?") == \
                QMessageBox.StandardButton.Yes:
            self.phone.unpair()
            self._refresh()

    def _set_pin(self) -> None:
        try:
            self.phone.set_pin(self.pin.text().strip())
        except ValueError as exc:
            QMessageBox.warning(self, "PIN not set", str(exc))
            return
        self.pin.clear()
        QMessageBox.information(self, "PIN set", "Saved (only a scrambled version is stored). You'll type it on "
                                                 "the phone to approve high-risk actions.")

    def _toggle_calls(self) -> None:
        s = self.neko.settings
        turning_on = not s.phone.calls
        if turning_on and QMessageBox.question(
                self, "Turn on calls?",
                "Neko's call page will run on this PC (local only), and Tailscale will share it as https on port "
                f"{s.phone.call_https_port} - only to devices signed in to YOUR Tailscale account, never the internet. "
                "Your other Tailscale shares stay as they are. Turn on?") != QMessageBox.StandardButton.Yes:
            return
        args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
                "-Enable" if turning_on else "-Disable", "-Port", str(s.phone.call_port),
                "-HttpsPort", str(s.phone.call_https_port)]
        try:
            cp = subprocess.run(args, capture_output=True, text=True, timeout=60, shell=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as exc:
            QMessageBox.warning(self, "Calls", f"Couldn't run the Tailscale step: {exc}")
            return
        if turning_on and cp.returncode != 0:
            QMessageBox.warning(self, "Calls", (cp.stdout or cp.stderr or "Tailscale refused.").strip()[:400])
            return
        if not self._save({"calls": turning_on}):
            return
        if turning_on:
            self.status.setText(self.calls.start())
        else:
            self.calls.stop()
        self._refresh()

    def _send_link(self) -> None:
        link = self.phone.call_link()
        if not link:
            QMessageBox.information(self, "Calls", "Turn on calls first (and make sure Tailscale is running).")
            return
        sent = self.phone.notify(f"Tap to call me (keep this link private):\n{link}")
        QMessageBox.information(self, "Calls", "Sent to your phone in Telegram." if sent else
                                "Telegram isn't connected - finish steps 1-2 first.")

    def _save_options(self) -> None:
        if self._save({"voice_replies": self.voice.currentText(), "notify_long_jobs": self.jobs.isChecked(),
                       "notify_battery": self.batt.isChecked()}):
            self.status.setText("Options saved.")
