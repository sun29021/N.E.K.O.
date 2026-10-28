"""Agent registry: explicit capability boundaries for specialist roles.

Honest scope for v0.1: specialists are *roles* executed sequentially by the
single Coordinator (a role picks the model role, prompt hint, allowed tools
and budgets). There is no free-running multi-agent swarm: on a 4 GB GPU
parallel agents would compete for the same model and memory, and every extra
agent is another place for a prompt injection to land. Agents cannot create
agents (max delegation depth 1), and agent output is treated as untrusted
until the Coordinator validates it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.types import RiskLevel, TaskKind


@dataclass(frozen=True)
class AgentSpec:
    name: str
    purpose: str
    model_role: str                         # router role
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    max_risk: RiskLevel = RiskLevel.READ_ONLY
    max_tool_steps: int = 3
    token_budget: int = 2048
    timeout_s: float = 180
    can_delegate: bool = False
    status: str = "implemented"             # implemented | planned


AGENTS: dict[str, AgentSpec] = {a.name: a for a in [
    AgentSpec("coordinator", "Understands intent, owns the final answer, enforces policy.", "chat",
              frozenset({"list_dir", "read_text_file", "search_files", "system_status", "list_models",
                         "write_note", "move_file", "open_app", "run_approved_script"}),
              RiskLevel.HIGH, max_tool_steps=4, can_delegate=True),
    AgentSpec("planner", "Breaks goals into steps with dependencies and done-criteria.", "reasoning",
              frozenset({"list_dir", "read_text_file", "search_files"})),
    AgentSpec("coding", "Reads permitted project files, proposes patches and explains them.", "coding",
              frozenset({"list_dir", "read_text_file", "search_files", "write_note"}), RiskLevel.LOW),
    AgentSpec("vision", "Describes authorised screenshots/images; states uncertainty.", "vision", frozenset()),
    AgentSpec("memory_curator", "Proposes memories, checks duplicates/contradictions; needs approval.", "fast",
              frozenset()),
    AgentSpec("diagnostics", "Collects approved health info and writes troubleshooting reports.", "chat",
              frozenset({"system_status", "list_models"})),
    AgentSpec("voice", "Push-to-talk transcription and speech output; no raw audio kept.", "fast", frozenset()),
    AgentSpec("research", "Searches approved web sources with citations (needs network permission).", "chat",
              frozenset(), status="planned"),
    AgentSpec("code_reviewer", "Independently reviews diffs for defects and security issues.", "coding",
              frozenset({"read_text_file"}), status="planned"),
    AgentSpec("windows_automation", "UI Automation with state verification; stops when unsure.", "chat",
              frozenset({"open_app"}), RiskLevel.LOW, status="planned"),
    AgentSpec("security_auditor", "Reviews permissions/tools/dependencies; cannot weaken policy.", "reasoning",
              frozenset({"read_text_file"}), status="planned"),
    AgentSpec("resource_manager", "Recommends unloading/throttling; never kills user apps.", "fast",
              frozenset({"system_status", "list_models"})),
]}

_KIND_TO_AGENT = {
    TaskKind.PLANNING: "planner", TaskKind.CODING: "coding", TaskKind.VISION: "vision",
}


def agent_for(kind: TaskKind) -> AgentSpec:
    return AGENTS[_KIND_TO_AGENT.get(kind, "coordinator")]
