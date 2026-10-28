"""Approval dialog (docs/SAFETY_AND_PERMISSIONS.md section 4).

Design rules:
* The default (Enter) button is **Deny**; approving needs a deliberate click
  or Alt+A. Level 3 additionally requires ticking "I understand".
* It is an ordinary application-modal dialog, *not* always-on-top, so it can
  never cover Windows security (UAC) or sign-in prompts.
* It shows exactly what will happen, the risk level, whether it can be undone,
  and the raw (redacted) arguments.
* Gestures and voice can never approve (docs/VISION_AND_GESTURES.md).
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.types import RiskLevel
from ..security.policy import ApprovalRequest
from ..security.redact import redact
from .theme import COLORS

_RISK_TEXT = {
    RiskLevel.LOW: ("Low risk", COLORS["ok"]),
    RiskLevel.MATERIAL: ("Material change", COLORS["warn"]),
    RiskLevel.HIGH: ("HIGH IMPACT", COLORS["error"]),
}


class ApprovalDialog(QDialog):
    def __init__(self, req: ApprovalRequest, parent: QWidget | None = None, timeout_s: int = 280) -> None:
        super().__init__(parent)
        self.req = req
        self.setWindowTitle("N.E.K.O. needs your approval")
        self.setModal(True)
        self.setMinimumWidth(460)
        label, color = _RISK_TEXT.get(req.risk, ("Approval", COLORS["warn"]))

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        risk = QLabel(f"<b style='color:{color}'>{label}</b> &nbsp; level {int(req.risk)} &middot; tool "
                      f"<code>{req.tool}</code>")
        risk.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(risk)
        what = QLabel(req.summary)
        what.setWordWrap(True)
        what.setStyleSheet("font-size: 11.5pt;")
        lay.addWidget(what)
        effects = QLabel(f"Effect: {req.side_effects}. Can be undone: {'yes' if req.reversible else 'NO'}.")
        effects.setObjectName("Dim")
        effects.setWordWrap(True)
        lay.addWidget(effects)
        safe_args = redact(req.args)
        details = QPlainTextEdit("\n".join(
            f"{k}: {v if isinstance(v, str) else json.dumps(v, default=str)}" for k, v in safe_args.items())
            or "(no arguments)")
        details.setReadOnly(True)
        details.setMaximumHeight(140)
        details.setAccessibleName("Action details")
        lay.addWidget(details)
        note = QLabel("Only approve if you asked for this. Text in files, web pages or screenshots can try to "
                      "trick an assistant - N.E.K.O. will never approve on its own.")
        note.setObjectName("Dim")
        note.setWordWrap(True)
        lay.addWidget(note)

        self.confirm = QCheckBox("I understand this may not be reversible")
        self.confirm.setVisible(req.risk >= RiskLevel.HIGH)
        lay.addWidget(self.confirm)

        row = QHBoxLayout()
        row.addStretch(1)
        self.deny_btn = QPushButton("&Deny")
        self.approve_btn = QPushButton("&Approve")
        self.approve_btn.setObjectName("Danger" if req.risk >= RiskLevel.HIGH else "Primary")
        self.deny_btn.setDefault(True)
        self.deny_btn.setAutoDefault(True)
        self.approve_btn.setAutoDefault(False)
        row.addWidget(self.deny_btn)
        row.addWidget(self.approve_btn)
        lay.addLayout(row)

        self.approve_btn.setEnabled(req.risk < RiskLevel.HIGH)
        self.confirm.toggled.connect(self.approve_btn.setEnabled)
        self.deny_btn.clicked.connect(self.reject)
        self.approve_btn.clicked.connect(self.accept)
        self.deny_btn.setFocus()
        # Expire before the engine's own timeout so the two never disagree.
        self._expiry = QTimer(self)
        self._expiry.setSingleShot(True)
        self._expiry.timeout.connect(self.reject)
        self._expiry.start(timeout_s * 1000)
        self._resolved = False
        # Answered on your phone instead: close this copy of the question.
        self._elsewhere = QTimer(self)
        self._elsewhere.timeout.connect(self._check_elsewhere)
        self._elsewhere.start(400)

    def _check_elsewhere(self) -> None:
        if self.req.decided and not self._resolved:
            self._resolved = True
            self._expiry.stop()
            self._elsewhere.stop()
            super().done(QDialog.DialogCode.Rejected.value)

    def done(self, result: int) -> None:  # noqa: D401 - Qt override
        if not self._resolved:
            self._resolved = True
            self._expiry.stop()
            self._elsewhere.stop()
            self.req.resolve(result == QDialog.DialogCode.Accepted.value
                             if isinstance(result, int) else result == QDialog.DialogCode.Accepted)
        super().done(result)
