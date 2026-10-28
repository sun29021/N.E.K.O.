"""Context-window budgeting.

Token counts are *estimates* (no tokenizer dependency): ~4 characters per
token for Latin text, ~1.5-2 for Bengali/other scripts. The budget keeps a
reserve for the response and tool outputs, and reports what it dropped so the
assistant can say "I left out older parts of our conversation".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.types import ChatMessage, Role


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    other = len(text) - ascii_chars
    return max(1, int(ascii_chars / 4 + other / 1.6) + 1)


@dataclass
class ContextReport:
    total_tokens: int = 0
    dropped_messages: int = 0
    truncated_untrusted: bool = False
    memory_count: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class ContextBudget:
    num_ctx: int = 4096
    response_reserve: int = 768
    tool_reserve: int = 256

    @property
    def prompt_budget(self) -> int:
        return max(256, self.num_ctx - self.response_reserve - self.tool_reserve)

    def assemble(
        self,
        system: str,
        history: list[ChatMessage],
        user: ChatMessage,
        *,
        memory_block: str = "",
        summary: str = "",
        untrusted_block: str = "",
        untrusted_max_tokens: int = 900,
    ) -> tuple[list[ChatMessage], ContextReport]:
        """Priority: system policy > current request > memory > untrusted data > summary > recent history."""
        report = ContextReport()
        budget = self.prompt_budget

        sys_text = system
        if memory_block:
            sys_text += "\n\n" + memory_block
        sys_cost = estimate_tokens(sys_text)
        user_cost = estimate_tokens(user.content)
        remaining = budget - sys_cost - user_cost
        if remaining < 0:
            # Even the essentials do not fit: truncate the user message tail (never the policy).
            keep_chars = max(200, (budget - sys_cost) * 4)
            user = ChatMessage(user.role, user.content[:keep_chars] + "\n[...truncated to fit context...]", user.images)
            report.notes.append("your message was too long and was truncated")
            remaining = 0

        if untrusted_block:
            limit = min(untrusted_max_tokens, max(0, remaining - 64))
            if estimate_tokens(untrusted_block) > limit:
                untrusted_block = untrusted_block[: limit * 4] + "\n[...untrusted content truncated...]"
                report.truncated_untrusted = True
                report.notes.append("long document/tool content was truncated")
            remaining -= estimate_tokens(untrusted_block)

        msgs: list[ChatMessage] = [ChatMessage(Role.SYSTEM, sys_text)]
        if summary and remaining > estimate_tokens(summary) + 32:
            msgs.append(ChatMessage(Role.SYSTEM, "Summary of earlier conversation:\n" + summary))
            remaining -= estimate_tokens(summary)

        kept: list[ChatMessage] = []
        for m in reversed(history):
            cost = estimate_tokens(m.content) + 4
            if cost > remaining:
                report.dropped_messages = len(history) - len(kept)
                break
            kept.append(m)
            remaining -= cost
        kept.reverse()
        if report.dropped_messages:
            report.notes.append(f"{report.dropped_messages} older message(s) were left out of context")
        msgs.extend(kept)

        if untrusted_block:
            msgs.append(ChatMessage(Role.USER, untrusted_block))
        msgs.append(user)
        report.total_tokens = sum(estimate_tokens(m.content) for m in msgs)
        return msgs, report
