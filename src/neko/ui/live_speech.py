"""Speak while she is still writing: cut the token stream into finished sentences.

Pure logic (no Qt), so it is unit-tested. The controller feeds tokens in, and gets back sentences
ready for the voice. Code blocks are never read aloud, and very long answers stop being spoken after
``max_chars`` (the rest stays on screen), the way a person summarises instead of reading a page.
"""

from __future__ import annotations

import re

_END = re.compile(r"(?<!\b\d[.)])(?<=[.!?…])[\"')\]]*\s+|\n{1,}")  # "1. " is a list, not an end
_MARKUP = re.compile(r"^\s*(#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)")


class SentenceFeeder:
    def __init__(self, max_chars: int = 650, first_min_chars: int = 12) -> None:
        self.buf = ""
        self.spoken = 0
        self.max_chars = max_chars
        self.first_min_chars = first_min_chars
        self.stopped = False   # code block or length limit reached: say nothing more
        self.started = False

    def _clean(self, sentence: str) -> str:
        s = _MARKUP.sub("", sentence).replace("**", "").replace("__", "").replace("`", "")
        return re.sub(r"\s+", " ", s).strip()

    def _take(self, sentence: str) -> str | None:
        if self.stopped:
            return None
        s = self._clean(sentence)
        if not s:
            return None
        if self.spoken + len(s) > self.max_chars and self.started:
            self.stopped = True
            return None
        self.spoken += len(s)
        self.started = True
        return s

    def feed(self, text: str) -> list[str]:
        if self.stopped:
            return []
        self.buf += text
        if "```" in self.buf:  # code is for reading, not for hearing
            before = self.buf.split("```", 1)[0]
            out = [s for s in (self._take(p) for p in _END.split(before)) if s]
            self.buf, self.stopped = "", True
            return out
        out: list[str] = []
        while True:
            m = _END.search(self.buf)
            if not m:
                break
            sentence, self.buf = self.buf[:m.start()], self.buf[m.end():]
            if not self.started and len(sentence.strip()) < self.first_min_chars and not self.buf.strip():
                # "Hmm." alone: wait for a little more so the first chunk sounds natural
                self.buf = sentence + " " + self.buf
                break
            took = self._take(sentence)
            if took:
                out.append(took)
            if self.stopped:
                break
        return out

    def flush(self) -> str | None:
        """The last sentence (no final punctuation yet) once the reply is complete."""
        rest, self.buf = self.buf, ""
        return self._take(rest) if rest.strip() else None
