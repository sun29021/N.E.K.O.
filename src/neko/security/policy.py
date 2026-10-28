"""Permission policy and approval workflow.

Decision table (docs/SAFETY_AND_PERMISSIONS.md section 2):

=========  ==========================================================
Level 0    allowed
Level 1    allowed if the tool's category is enabled; logged
Level 2    needs approval, unless a narrow, unexpired standing rule matches
Level 3    needs fresh approval *every time*; never covered by standing rules
Blocked    a tool may be marked ``prohibited``: denied regardless of approval
=========  ==========================================================

Approval must come from the human through the UI/CLI callback. Model output,
tool output and document text have no way to call ``resolve`` - the approval
object is never exposed to the model.
"""

from __future__ import annotations

import enum
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..core.cancel import CancelToken, EmergencyStop
from ..core.types import RiskLevel, new_id
from ..database.db import Database
from .redact import redact


class Decision(str, enum.Enum):
    ALLOW = "allow"
    NEEDS_APPROVAL = "needs_approval"
    DENY = "deny"


@dataclass
class PolicyResult:
    decision: Decision
    reason: str
    standing_rule_id: str | None = None


@dataclass
class ApprovalRequest:
    tool: str
    risk: RiskLevel
    summary: str                      # human-readable "what will happen"
    args: dict[str, Any]
    side_effects: str
    reversible: bool
    id: str = field(default_factory=lambda: new_id("ap_"))
    created_at: float = field(default_factory=time.time)
    _event: threading.Event = field(default_factory=threading.Event, repr=False)
    _approved: bool = field(default=False, repr=False)

    def resolve(self, approved: bool) -> None:
        if self._event.is_set():
            return  # first answer wins (PC dialog or phone)
        self._approved = approved
        self._event.set()

    @property
    def decided(self) -> bool:
        return self._event.is_set()

    def wait(self, token: CancelToken, timeout_s: float = 300) -> bool:
        deadline = time.monotonic() + timeout_s
        while not self._event.is_set():
            if token.cancelled or time.monotonic() > deadline:
                return False
            self._event.wait(0.2)
        return self._approved


ApprovalHandler = Callable[[ApprovalRequest], None]


class PermissionPolicy:
    def __init__(
        self,
        db: Database,
        estop: EmergencyStop,
        *,
        computer_control_enabled: bool = False,
        network_allowed: bool = False,
    ) -> None:
        self.db = db
        self.estop = estop
        self.computer_control_enabled = computer_control_enabled
        self.network_allowed = network_allowed
        self._handler: ApprovalHandler | None = None
        self.pending: dict[str, ApprovalRequest] = {}

    def set_approval_handler(self, handler: ApprovalHandler) -> None:
        """The UI or CLI registers how to ask the human."""
        self._handler = handler

    # ------------------------------------------------------------------ decisions
    def evaluate(
        self,
        tool: str,
        risk: RiskLevel,
        args: dict[str, Any],
        *,
        category: str = "general",
        prohibited: bool = False,
        needs_network: bool = False,
    ) -> PolicyResult:
        if prohibited:
            return PolicyResult(Decision.DENY, f"{tool} is prohibited by policy")
        if self.estop.tripped and risk >= RiskLevel.LOW:
            return PolicyResult(Decision.DENY, "emergency stop is active; only read-only actions are allowed")
        if category == "computer_control" and not self.computer_control_enabled:
            return PolicyResult(Decision.DENY, "computer control is disabled in settings")
        if needs_network and not self.network_allowed:
            return PolicyResult(Decision.DENY, "network access is disabled in privacy settings")
        if risk == RiskLevel.READ_ONLY:
            return PolicyResult(Decision.ALLOW, "read-only")
        if risk == RiskLevel.LOW:
            return PolicyResult(Decision.ALLOW, "low-risk, reversible")
        if risk == RiskLevel.MATERIAL:
            rule = self._matching_standing_rule(tool, args)
            if rule:
                return PolicyResult(Decision.ALLOW, f"covered by standing rule {rule}", rule)
            return PolicyResult(Decision.NEEDS_APPROVAL, "material change needs approval")
        return PolicyResult(Decision.NEEDS_APPROVAL, "high-impact action needs explicit confirmation")

    def _matching_standing_rule(self, tool: str, args: dict[str, Any]) -> str | None:
        rows = self.db.query(
            """SELECT id, scope_json FROM standing_permissions
               WHERE tool=? AND enabled=1 AND max_risk<=2 AND (expires_at IS NULL OR expires_at>?)""",
            (tool, time.time()),
        )
        for r in rows:
            scope = json.loads(r["scope_json"])
            if _scope_matches(scope, args):
                return str(r["id"])
        return None

    def add_standing_rule(self, tool: str, scope: dict[str, Any], *, risk: RiskLevel, days: float | None = 30) -> str:
        if risk >= RiskLevel.HIGH:
            raise ValueError("Level 3 actions can never be pre-approved")
        if not scope:
            raise ValueError("standing rules must be narrowly scoped (empty scope not allowed)")
        rid = new_id("sp_")
        self.db.execute(
            "INSERT INTO standing_permissions(id, tool, scope_json, max_risk, created_at, expires_at) VALUES (?,?,?,?,?,?)",
            (rid, tool, json.dumps(scope), int(risk), time.time(), time.time() + days * 86400 if days else None),
        )
        self.db.audit("permission", "standing_rule_added", id=rid, tool=tool, scope=scope)
        return rid

    # ------------------------------------------------------------------ approvals
    def request_approval(self, req: ApprovalRequest, token: CancelToken, timeout_s: float = 300) -> bool:
        if self._handler is None:
            self._record(req, "denied", "no approval interface available")
            return False
        self.db.execute(
            "INSERT INTO approvals(id, tool, risk_level, summary, decision, created_at) VALUES (?,?,?,?,?,?)",
            (req.id, req.tool, int(req.risk), req.summary, "pending", req.created_at),
        )
        self.pending[req.id] = req
        try:
            self._handler(req)
            approved = req.wait(token, timeout_s)
        finally:
            self.pending.pop(req.id, None)
        decision = "approved" if approved else ("expired" if not req._event.is_set() else "denied")
        self.db.execute("UPDATE approvals SET decision=?, decided_by='user', decided_at=? WHERE id=?",
                        (decision, time.time(), req.id))
        self.db.audit("permission", f"approval_{decision}", id=req.id, tool=req.tool,
                      args=redact(req.args), risk=int(req.risk))
        return approved

    def _record(self, req: ApprovalRequest, decision: str, note: str) -> None:
        self.db.audit("permission", f"approval_{decision}", id=req.id, tool=req.tool, note=note)


def _scope_matches(scope: dict[str, Any], args: dict[str, Any]) -> bool:
    """Every scope constraint must hold. Supported keys:
    ``path_prefix`` (string), ``equals`` (dict of exact arg values)."""
    from .paths import is_within, resolve

    for key, value in scope.items():
        if key == "path_prefix":
            path = args.get("path") or args.get("source") or args.get("target")
            if not path or not is_within(resolve(path), resolve(value)):
                return False
            for other in ("destination", "dest"):
                if other in args and not is_within(resolve(args[other]), resolve(value)):
                    return False
        elif key == "equals":
            if any(args.get(k) != v for k, v in value.items()):
                return False
        else:
            return False  # unknown constraint: fail closed
    return True
