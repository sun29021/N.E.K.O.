"""Plain data types shared across layers. Kept dependency-free on purpose."""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:16]}"


def now() -> float:
    return time.time()


class AssistantState(str, enum.Enum):
    """States shown by the HUD core. Mirrors docs/UI_UX_SPEC.md section 2."""

    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    TOOL = "tool"
    AWAITING_APPROVAL = "awaiting_approval"
    SPEAKING = "speaking"
    RECOVERING = "recovering"
    ERROR = "error"
    OFFLINE = "offline"


class RiskLevel(enum.IntEnum):
    """Risk levels from docs/SAFETY_AND_PERMISSIONS.md."""

    READ_ONLY = 0
    LOW = 1
    MATERIAL = 2
    HIGH = 3


class Capability(str, enum.Enum):
    CHAT = "chat"
    REASONING = "reasoning"
    CODING = "coding"
    VISION = "vision"
    EMBEDDING = "embedding"
    TOOLS = "tools"


class TaskKind(str, enum.Enum):
    SMALL_TALK = "small_talk"
    QUESTION = "question"
    PLANNING = "planning"
    CODING = "coding"
    VISION = "vision"
    MEMORY = "memory"
    COMMAND = "command"


class Role(str, enum.Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Trust(str, enum.Enum):
    """Provenance trust used for memory ranking and prompt fencing."""

    USER_STATED = "user_stated"      # the user said it directly
    VERIFIED = "verified"            # backed by evidence (file exists, test passed...)
    OBSERVED = "observed"            # seen in a tool result, not yet verified
    INFERRED = "inferred"            # model-generated conclusion
    UNTRUSTED = "untrusted"          # web page, document, screenshot text


TRUST_WEIGHT: dict[Trust, float] = {
    Trust.USER_STATED: 1.0,
    Trust.VERIFIED: 0.95,
    Trust.OBSERVED: 0.7,
    Trust.INFERRED: 0.5,
    Trust.UNTRUSTED: 0.3,
}


@dataclass
class ChatMessage:
    role: Role
    content: str
    images: list[bytes] = field(default_factory=list)
    name: str | None = None                 # tool name for role=tool messages
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # [{"name", "arguments"}]

    def to_ollama(self) -> dict[str, Any]:
        import base64

        msg: dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.images:
            msg["images"] = [base64.b64encode(b).decode("ascii") for b in self.images]
        if self.tool_calls:
            msg["tool_calls"] = [{"function": {"name": c["name"], "arguments": c["arguments"]}}
                                 for c in self.tool_calls]
        if self.role == Role.TOOL and self.name:
            msg["tool_name"] = self.name
        return msg


@dataclass
class GenerationRequest:
    messages: list[ChatMessage]
    model: str
    temperature: float = 0.6
    max_tokens: int = 768
    num_ctx: int = 4096
    stream: bool = True
    json_mode: bool = False
    keep_alive: str | None = None
    timeout_s: float = 120.0
    # Native function calling (Ollama /api/chat "tools"). JSON-schema function definitions.
    tools: list[dict[str, Any]] | None = None
    # "Thinking" models (qwen3, deepseek-r1...) reason silently before answering. On a 4 GB GPU that
    # measured 38 s for "hi" and could exhaust the token budget, so it is off unless requested.
    think: bool = False


@dataclass
class GenerationResult:
    text: str
    model: str
    provider: str
    location: str                    # "local" | "lan:<name>" | "cloud:<name>"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    load_ms: float | None = None
    first_token_ms: float | None = None
    total_ms: float | None = None
    cancelled: bool = False
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # native calls: [{"name", "arguments"}]
    eval_ms: float | None = None     # runtime-reported generation time (preferred for tok/s)

    @property
    def tokens_per_second(self) -> float | None:
        if self.completion_tokens and self.eval_ms:
            return self.completion_tokens / (self.eval_ms / 1000)
        if self.completion_tokens and self.total_ms and self.total_ms > 0:
            gen_ms = self.total_ms - (self.first_token_ms or 0)
            if gen_ms > 0:
                return self.completion_tokens / (gen_ms / 1000)
        return None
