"""Gap-free speech playback with word timing, shared by the voices (Edge neural voices, Kokoro).

A producer yields ``Utterance`` pieces (one sentence of 24 kHz float32 audio + its words and their start
times). The sound card callback plays them back to back and fires ``on_words(text_so_far)`` as each word
is heard, so subtitles appear word by word in sync with the voice (not the whole reply at once). The
next sentence is synthesised while the current one plays. ``token`` stops everything at once.
"""

from __future__ import annotations

import queue
import re
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from ..core.cancel import CancelToken

RATE = 24000


@dataclass
class Utterance:
    audio: Any                                   # numpy float32, mono, 24 kHz (pause included at the end)
    words: list[tuple[str, float]] = field(default_factory=list)   # (word, start seconds in this piece)


def estimate_words(text: str, speech_seconds: float, lead_s: float = 0.05) -> list[tuple[str, float]]:
    """Word start times when the engine doesn't report them (Kokoro): spread by word length."""
    words = re.findall(r"\S+", text)
    if not words:
        return []
    weights = [len(re.sub(r"\W", "", w)) + 2 for w in words]
    total, t, out = float(sum(weights)), lead_s, []
    span = max(0.1, speech_seconds - lead_s)
    for w, wt in zip(words, weights, strict=False):
        out.append((w, t))
        t += span * wt / total
    return out


def play(pieces: Iterable[Utterance], token: CancelToken, *, on_level: Callable[[float], None] | None = None,
         on_words: Callable[[str], None] | None = None, volume: float = 1.0) -> None:
    import numpy as np
    import sounddevice as sd

    q: queue.Queue[Any] = queue.Queue(maxsize=4)
    done = threading.Event()

    def producer() -> None:
        try:
            for piece in pieces:
                if token.cancelled:
                    break
                q.put(piece)
        finally:
            q.put(None)

    threading.Thread(target=producer, daemon=True, name="neko-tts-synth").start()
    state: dict[str, Any] = {"cur": None, "pos": 0, "finished": False, "wi": 0, "shown": []}
    lev_acc: list[float] = []

    def callback(outdata, frames, _time, _status) -> None:  # noqa: ANN001
        out = np.zeros(frames, dtype=np.float32)
        filled = 0
        while filled < frames and not state["finished"]:
            cur = state["cur"]
            if cur is None or state["pos"] >= len(cur.audio):
                try:
                    nxt = q.get_nowait()
                except queue.Empty:
                    break  # waiting for the next sentence (synthesis or the model is behind): play silence
                if nxt is None:
                    state["finished"] = True
                    break
                state.update(cur=nxt, pos=0, wi=0, shown=[])
                cur = nxt
            n = min(frames - filled, len(cur.audio) - state["pos"])
            out[filled:filled + n] = cur.audio[state["pos"]:state["pos"] + n] * volume
            filled += n
            state["pos"] += n
            if on_words is not None and state["wi"] < len(cur.words):
                now_s = state["pos"] / RATE
                changed = False
                while state["wi"] < len(cur.words) and cur.words[state["wi"]][1] <= now_s:
                    state["shown"].append(cur.words[state["wi"]][0])
                    state["wi"] += 1
                    changed = True
                if changed:
                    on_words(" ".join(state["shown"]))
        outdata[:, 0] = out
        if on_level is not None:
            lev_acc.append(float(np.sqrt(np.mean(out * out))) if frames else 0.0)
            if len(lev_acc) * frames >= 1200:  # ~50 ms
                on_level(min(1.0, (sum(lev_acc) / len(lev_acc)) * 6.0))
                lev_acc.clear()
        if state["finished"]:
            done.set()
            raise sd.CallbackStop

    with sd.OutputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=1024, latency="high",
                         callback=callback, finished_callback=done.set):
        while not done.is_set():
            if token.wait(0.05):
                break
    if on_level is not None:
        on_level(0.0)


__all__ = ["RATE", "Utterance", "estimate_words", "play"]
