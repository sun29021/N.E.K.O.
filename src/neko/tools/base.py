"""Tool gateway: typed tool declarations, argument validation, permission
checks, timeouts, cancellation, verification and audit.

Every tool declares (docs/TOOLS_AND_MCP.md section 2):
  name, description, input schema, output description, risk level, category,
  side effects, reversibility, timeout, whether it needs network, and a
  verification strategy that checks the *real* outcome.
"""

from __future__ import annotations

import concurrent.futures
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..core.cancel import CancelToken
from ..core.errors import (
    CancelledError,
    NekoError,
    PermissionDeniedError,
    ToolError,
    ToolValidationError,
)
from ..core.types import RiskLevel, new_id
from ..database.db import Database
from ..security.paths import PathPolicy
from ..security.policy import ApprovalRequest, Decision, PermissionPolicy
from ..security.redact import redact

# A deliberately small JSON-schema subset: {"name": {"type": "string", "required": True, ...}}
_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,), "integer": (int,), "number": (int, float), "boolean": (bool,),
    "array": (list,), "object": (dict,),
}


@dataclass
class ToolContext:
    token: CancelToken
    paths: PathPolicy
    task_id: str | None = None
    settings: Any = None
    # True once untrusted content (file text, web, OCR, tool output) is in the
    # model's context for this turn. Any non-read-only call then needs approval,
    # so injected text can never silently trigger an action.
    tainted: bool = False


@dataclass
class ToolResult:
    ok: bool
    summary: str                      # short, user-safe description
    data: Any = None                  # returned to the model as UNTRUSTED content
    verified: bool | None = None      # None = no verification possible
    verification: str = ""
    invocation_id: str = ""


Verifier = Callable[[dict[str, Any], ToolResult, ToolContext], tuple[bool, str]]


@dataclass
class ToolSpec:
    name: str
    description: str
    params: dict[str, dict[str, Any]]
    handler: Callable[[dict[str, Any], ToolContext], ToolResult]
    risk: RiskLevel
    category: str = "general"
    side_effects: str = "none"
    reversible: bool = True
    timeout_s: float = 30.0
    needs_network: bool = False
    prohibited: bool = False
    output: str = "text"
    verifier: Verifier | None = None
    summarize: Callable[[dict[str, Any]], str] | None = None
    risk_fn: Callable[[dict[str, Any]], RiskLevel] | None = None   # dynamic escalation

    def schema_for_model(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "risk_level": int(self.risk),
            "parameters": {k: {kk: vv for kk, vv in v.items() if kk != "required"} | {"required": bool(v.get("required"))}
                           for k, v in self.params.items()},
        }

    def effective_risk(self, args: dict[str, Any]) -> RiskLevel:
        if self.risk_fn is None:
            return self.risk
        return max(self.risk, self.risk_fn(args))


def validate_args(spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(args, dict):
        raise ToolValidationError("arguments must be an object")
    unknown = set(args) - set(spec.params)
    if unknown:
        raise ToolValidationError(f"unknown argument(s): {', '.join(sorted(unknown))}")
    clean: dict[str, Any] = {}
    for name, rules in spec.params.items():
        if name not in args:
            if rules.get("required"):
                raise ToolValidationError(f"missing required argument {name!r}")
            if "default" in rules:
                clean[name] = rules["default"]
            continue
        value = args[name]
        expected = _TYPES[rules.get("type", "string")]
        if isinstance(value, bool) and rules.get("type") in ("integer", "number"):
            raise ToolValidationError(f"{name} must be a number")
        if not isinstance(value, expected):
            raise ToolValidationError(f"{name} must be of type {rules.get('type', 'string')}")
        if isinstance(value, str):
            if len(value) > rules.get("max_length", 4096):
                raise ToolValidationError(f"{name} is too long")
            if "\x00" in value:
                raise ToolValidationError(f"{name} contains a NUL byte")
            if "enum" in rules and value not in rules["enum"]:
                raise ToolValidationError(f"{name} must be one of {rules['enum']}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "min" in rules and value < rules["min"]:
                raise ToolValidationError(f"{name} must be >= {rules['min']}")
            if "max" in rules and value > rules["max"]:
                raise ToolValidationError(f"{name} must be <= {rules['max']}")
        clean[name] = value
    return clean


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool {spec.name} already registered")
        if spec.risk >= RiskLevel.MATERIAL and spec.verifier is None and spec.side_effects != "none":
            raise ValueError(f"tool {spec.name} changes state but declares no verifier")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise ToolValidationError(f"unknown tool {name!r}")
        return self._tools[name]

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def native_schemas(self, max_risk: RiskLevel = RiskLevel.HIGH) -> list[dict[str, Any]]:
        """Function definitions for native tool calling (OpenAI/Ollama JSON-schema format)."""
        out = []
        for s in self._tools.values():
            if s.prohibited or s.risk > max_risk:
                continue
            props = {}
            for name, rules in s.params.items():
                p: dict[str, Any] = {"type": rules.get("type", "string")}
                if "enum" in rules:
                    p["enum"] = rules["enum"]
                if "description" in rules:
                    p["description"] = rules["description"]
                if p["type"] == "array":
                    p["items"] = {"type": "string"}
                props[name] = p
            out.append({"type": "function", "function": {
                "name": s.name, "description": s.description,
                "parameters": {"type": "object", "properties": props,
                               "required": [n for n, r in s.params.items() if r.get("required")]},
            }})
        return out

    def describe_for_model(self, max_risk: RiskLevel = RiskLevel.HIGH) -> str:
        specs = [s.schema_for_model() for s in self._tools.values() if s.risk <= max_risk and not s.prohibited]
        return json.dumps(specs, indent=None)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, policy: PermissionPolicy, db: Database) -> None:
        self.registry = registry
        self.policy = policy
        self.db = db
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="neko-tool")

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def run(self, name: str, raw_args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        inv_id = new_id("ti_")
        spec = self.registry.get(name)
        try:
            args = validate_args(spec, raw_args)
        except ToolValidationError as exc:
            self._log(inv_id, ctx, spec, raw_args, "failed", f"invalid arguments: {exc}", RiskLevel(spec.risk))
            return ToolResult(False, f"Invalid arguments for {name}: {exc}", invocation_id=inv_id)

        risk = spec.effective_risk(args)
        verdict = self.policy.evaluate(
            name, risk, args, category=spec.category, prohibited=spec.prohibited, needs_network=spec.needs_network
        )
        if verdict.decision == Decision.DENY:
            self._log(inv_id, ctx, spec, args, "denied", verdict.reason, risk)
            return ToolResult(False, f"Not permitted: {verdict.reason}", invocation_id=inv_id)

        needs_approval = verdict.decision == Decision.NEEDS_APPROVAL
        if ctx.tainted and risk >= RiskLevel.LOW:
            needs_approval = True  # untrusted content is in context: ask the human

        approval_id = None
        if needs_approval:
            summary = spec.summarize(args) if spec.summarize else f"{name}({json.dumps(redact(args))[:300]})"
            req = ApprovalRequest(
                tool=name, risk=risk, summary=summary, args=args,
                side_effects=spec.side_effects, reversible=spec.reversible,
            )
            approval_id = req.id
            self._log(inv_id, ctx, spec, args, "awaiting_approval", summary, risk, approval_id)
            if not self.policy.request_approval(req, ctx.token):
                self._finish(inv_id, "denied", "user did not approve")
                return ToolResult(False, "You did not approve this action, so I did not do it.", invocation_id=inv_id)
            self._finish(inv_id, "running", "approved")
        else:
            self._log(inv_id, ctx, spec, args, "running", verdict.reason, risk)

        tool_token = ctx.token.child(timeout_s=spec.timeout_s)
        sub_ctx = ToolContext(token=tool_token, paths=ctx.paths, task_id=ctx.task_id, settings=ctx.settings,
                              tainted=ctx.tainted)
        future = self._pool.submit(spec.handler, args, sub_ctx)
        try:
            result = future.result(timeout=spec.timeout_s)
        except concurrent.futures.TimeoutError:
            tool_token.cancel("timeout")
            self._finish(inv_id, "timeout", f"exceeded {spec.timeout_s}s")
            return ToolResult(False, f"{name} timed out after {spec.timeout_s:.0f}s. "
                                     "It may have partially completed.", invocation_id=inv_id)
        except CancelledError:
            self._finish(inv_id, "cancelled", "cancelled")
            return ToolResult(False, f"{name} was cancelled.", invocation_id=inv_id)
        except PermissionDeniedError as exc:
            self._finish(inv_id, "denied", str(exc))
            return ToolResult(False, exc.user_message if exc.user_message != PermissionDeniedError.user_message
                              else str(exc), invocation_id=inv_id)
        except (NekoError, OSError, ValueError) as exc:
            self._finish(inv_id, "failed", f"{type(exc).__name__}: {exc}")
            return ToolResult(False, f"{name} failed: {exc}", invocation_id=inv_id)

        result.invocation_id = inv_id
        if spec.verifier is not None and result.ok:
            try:
                passed, detail = spec.verifier(args, result, sub_ctx)
            except Exception as exc:  # noqa: BLE001
                passed, detail = False, f"verifier error: {exc}"
            result.verified, result.verification = passed, detail
            if ctx.task_id:
                self.db.execute(
                    """INSERT INTO verification_evidence(task_id, invocation_id, method, passed, detail, created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (ctx.task_id, inv_id, spec.name + ".verifier", int(passed), detail[:1000], time.time()),
                )
            if not passed:
                result.ok = False
                result.summary += f" (verification FAILED: {detail})"
        self._finish(inv_id, "succeeded" if result.ok else "failed", result.summary)
        return result

    # ------------------------------------------------------------------ audit
    def _log(self, inv_id: str, ctx: ToolContext, spec: ToolSpec, args: dict[str, Any], status: str,
             note: str, risk: RiskLevel, approval_id: str | None = None) -> None:
        self.db.execute(
            """INSERT INTO tool_invocations(id, task_id, tool, risk_level, args_redacted, status, result_summary,
                   started_at, approval_id) VALUES (?,?,?,?,?,?,?,?,?)""",
            (inv_id, ctx.task_id, spec.name, int(risk), json.dumps(redact(args), default=str)[:4000],
             status, note[:1000], time.time(), approval_id),
        )
        self.db.audit("tool", status, invocation=inv_id, tool=spec.name, risk=int(risk))

    def _finish(self, inv_id: str, status: str, summary: str) -> None:
        self.db.execute(
            "UPDATE tool_invocations SET status=?, result_summary=?, finished_at=? WHERE id=?",
            (status, redact(summary)[:1000], time.time(), inv_id),
        )


@dataclass
class ToolCall:
    """A tool call proposed by the model (parsed from its JSON output)."""

    tool: str
    args: dict[str, Any] = field(default_factory=dict)
