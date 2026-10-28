"""Always-on listening with the assistant's name as the wake word ("Neko, ...").

How it works (all local, nothing recorded to disk):
 1. The microphone streams 16 kHz audio in 30 ms frames.
 2. A cheap energy-based voice-activity detector with an adaptive noise floor finds where speech
    starts and stops (no transcription while it's quiet, so idle CPU use stays tiny).
 3. Each finished utterance (0.4-15 s) is transcribed by faster-whisper, biased towards the name.
 4. If the text contains the name (or a common mis-hearing such as "Nico"), the rest of the sentence
    is the command. "Neko" alone opens a short window for the command that follows.
 5. Right after N.E.K.O. answers, a follow-up window lets you keep talking without the name.
 6. While N.E.K.O. is speaking the microphone input is ignored (plus a short tail), so she never
    "hears herself". Limitation: you can't interrupt her by voice - use the Stop button.

Why not openWakeWord? Its pre-trained models don't include "Neko" (training one needs thousands of
samples and a GPU), and its models are non-commercial. Whisper keyword matching works with any name.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from ..core.cancel import CancelToken
from ..core.errors import PeripheralUnavailableError
from .audio import SAMPLE_RATE, SpeechGate

log = logging.getLogger("neko.voice.listener")

FRAME = 480  # 30 ms at 16 kHz
DEFAULT_NAMES = ("neko", "nico", "niko", "neeko", "necko", "nekko", "nekoh", "neco", "nikko", "nako")


def build_name_pattern(names: list[str] | tuple[str, ...]) -> re.Pattern[str]:
    alts = "|".join(re.escape(n.lower()) for n in sorted(set(names), key=len, reverse=True))
    return re.compile(rf"\b(?:hey|hi|ok|okay|yo)?[\s,]*(?:{alts})\b[\s,.!?:;-]*", re.IGNORECASE)


_DANGLING = re.compile(r"\b(the|a|an|and|or|but|to|of|for|with|about|when|what|which|that|my|your|is|are|"
                       r"if|so|because|like|in|on|at|from|can|could|would|how)$", re.IGNORECASE)


_STOP_WORDS = re.compile(r"^(stop|wait|hold on|enough|shut up|be quiet|quiet|cancel|never ?mind|pause|okay stop|ok stop)\W*$",
                        re.IGNORECASE)


def barge_in_command(text: str, pattern: re.Pattern[str]) -> str | None:
    """While she is speaking: None = ignore (her own echo, background), "" = just stop talking,
    otherwise the new request to handle ("Neko, wait - what's the time?" -> "what's the time?")."""
    heard, command = split_wake(text or "", pattern)
    if not heard:
        return None
    command = re.sub(r"^(stop|wait|hold on|sorry)\W+", "", command.strip(), flags=re.IGNORECASE).strip()
    return "" if not command or _STOP_WORDS.match(command) else command


def looks_unfinished(text: str) -> bool:
    """Whisper marks a cut-off sentence with "..." or it ends on a word like "the"/"when"."""
    t = text.strip()
    if not t:
        return False
    if t.endswith(("...", "…", ",", "-")):
        return True
    return bool(_DANGLING.search(t.rstrip(".!? ")) and not t.endswith(("?", "!")))


def split_wake(text: str, pattern: re.Pattern[str]) -> tuple[bool, str]:
    """Return (name_heard, command_without_the_name)."""
    m = pattern.search(text)
    if not m:
        return False, text.strip()
    before, after = text[: m.start()].strip(" ,.!?"), text[m.end():].strip()
    # "What time is it, Neko?" -> name at the end: the command is what came before it
    command = after if len(after) >= len(before) else before
    return True, command.strip(" ,")


# Live listening (GPU): a caption every ~1.2 s while you talk; at 0.6 s of quiet, check whether what you
# said is already a complete request, and if so stop waiting after 0.6 s (question) / 0.9 s (statement).
PARTIAL_EVERY_FRAMES = 40
EARLY_CHECK_FRAMES = 20
EARLY_END_QUESTION_S = 0.6
EARLY_END_SENTENCE_S = 0.9
REVISE_WINDOW_S = 2.0  # speech starting this soon after an early end continues the same request
MUSIC_WINDOW_S = 4.0  # while music plays: short chunks, so "pause" is heard within about a second
MUSIC_HOTWORDS = "Neko, pause, stop, resume, next, skip, louder, quieter, turn it up, turn it down"


class EnergyVAD:
    """Adaptive-threshold voice activity detector over 30 ms int16 frames."""

    def __init__(self, start_ratio: float = 3.0, min_rms: float = 220.0, end_silence_s: float = 1.3,
                 min_speech_s: float = 0.35, max_speech_s: float = 30.0) -> None:
        # 1.3 s: measured 2026-10-28, 0.75 s cut people off mid-sentence when they paused to think
        # ("can you just show me the last time when..."). While she is being addressed it is 1.8 s.
        self.start_ratio = start_ratio
        self.min_rms = min_rms
        self.end_frames = int(end_silence_s / 0.03)
        self.min_frames = int(min_speech_s / 0.03)
        self.max_frames = int(max_speech_s / 0.03)
        self.floor = 150.0
        self._buf: list[bytes] = []
        self._pre: deque[bytes] = deque(maxlen=10)  # 300 ms pre-roll so the first syllable isn't cut
        self._silent = 0
        self._loud = 0
        self._pre_n = 0
        self.active = False

    def feed(self, frame: bytes, rms: float) -> bytes | None:
        """Returns a finished utterance (PCM bytes) or None."""
        threshold = max(self.min_rms, self.floor * self.start_ratio)
        if not self.active:
            self._pre.append(frame)
            if rms > threshold:
                self._loud += 1
                if self._loud >= 3:  # 90 ms of sound
                    self.active = True
                    self._buf = list(self._pre)
                    self._pre_n = len(self._buf) - 3  # pre-roll doesn't count as speech
                    self._silent = 0
            else:
                self._loud = 0
                self.floor = 0.97 * self.floor + 0.03 * max(50.0, rms)  # learn background noise
            return None
        self._buf.append(frame)
        self._silent = self._silent + 1 if rms < threshold * 0.6 else 0
        if self._silent >= self.end_frames or len(self._buf) >= self.max_frames:
            pcm, n = b"".join(self._buf), len(self._buf) - self._pre_n - self._silent
            self.reset()
            return pcm if n >= self.min_frames else None
        return None

    def reset(self) -> None:
        self._buf, self._silent, self._loud, self.active = [], 0, 0, False
        self._pre.clear()


class WakeNameListener:
    def __init__(
        self,
        recognizer: Any,
        *,
        names: list[str] | tuple[str, ...] = DEFAULT_NAMES,
        language: str | None = "en",
        gate: SpeechGate | None = None,
        device: str | int | None = None,
        follow_up_s: float = 8.0,
        pause_s: float = 1.6,
        addressed_pause_s: float = 2.5,
        wait_rest_s: float = 6.0,
        max_speech_s: float = 60.0,
        on_command: Callable[[str], None] | None = None,
        on_wake: Callable[[], None] | None = None,
        on_speech_start: Callable[[], None] | None = None,
        on_level: Callable[[float], None] | None = None,
        on_idle: Callable[[], None] | None = None,
        on_heard: Callable[[], None] | None = None,
        music_active: Callable[[], bool] | None = None,
        direct_command: Callable[[str], str | None] | None = None,
        vocabulary: Callable[[], str] | None = None,
        on_partial: Callable[[str], None] | None = None,
        on_revise: Callable[[str], None] | None = None,
        on_barge_in: Callable[[str], None] | None = None,
        barge_in: bool = True,
    ) -> None:
        self.recognizer = recognizer
        self.pattern = build_name_pattern(names)
        self.hotword = names[0] if names else "Neko"
        self.language = language or None
        self.gate = gate
        self.device = device or None
        self.follow_up_s = follow_up_s
        # Silence that ends a sentence: longer while she is being talked to (thinking pauses), and how
        # long an unfinished-sounding sentence waits for the rest. Tunable in [voice] settings.
        self.pause_s = pause_s
        self.addressed_pause_s = addressed_pause_s
        self.wait_rest_s = wait_rest_s
        self.max_speech_s = max_speech_s
        self.on_command = on_command
        self.on_wake = on_wake
        self.on_speech_start = on_speech_start
        self.on_level = on_level
        self.on_idle = on_idle
        self.on_heard = on_heard
        # While music plays: listen in short windows, and accept a bare "pause" / "stop" without her
        # name (`direct_command` decides which short phrases count). Seen live 2026-10-28: the speakers
        # kept the microphone "loud", so one 60 s blob of song was transcribed and "pause" was lost.
        self.music_active = music_active
        self.direct_command = direct_command
        self.on_barge_in = on_barge_in  # you said her name while she was talking: '' = stop, else a new request
        self.barge_in = barge_in
        self.on_revise = on_revise    # an early-ended request was continued: replace it with this
        self._revisable: tuple[float, str] | None = None
        self.on_partial = on_partial  # live caption of what you're saying (GPU only)
        self.vocabulary = vocabulary  # -> whisper prompt with the user's own words (names, songs, places)
        self._armed_until = 0.0     # after "Neko" alone / after a reply: accept speech without the name
        self._wake_armed = False    # armed by saying her name (not just by a reply)
        self._pending = ""          # a command that sounded unfinished, waiting for the rest
        self._pending_until = 0.0
        self._token: CancelToken | None = None
        self._thread: threading.Thread | None = None
        self.paused = False

    # ------------------------------------------------------------------ control
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        try:
            import sounddevice  # noqa: F401
        except (ImportError, OSError) as exc:
            raise PeripheralUnavailableError(str(exc), user_message="Voice components are not installed.") from exc
        if self.running:
            return
        self._token = CancelToken()
        self._thread = threading.Thread(target=self._run, args=(self._token,), daemon=True, name="neko-listen")
        self._thread.start()
        log.info("always-listening started (microphone on, audio kept in memory only)")

    def stop(self) -> None:
        if self._token is not None:
            self._token.cancel("stopped")

    def arm_follow_up(self, seconds: float | None = None) -> None:
        """Call after N.E.K.O. finishes answering: the next sentence needs no name."""
        self._armed_until = time.monotonic() + (seconds if seconds is not None else self.follow_up_s)
        self._wake_armed = False

    # ------------------------------------------------------------------ processing
    def flush_pending(self) -> str | None:
        """If an unfinished-sounding command got no continuation in time, send it as it is."""
        if self._pending and time.monotonic() >= self._pending_until:
            cmd, self._pending = self._pending, ""
            self._armed_until = 0.0
            if self.on_command:
                self.on_command(cmd)
            return cmd
        return None

    @property
    def addressed(self) -> bool:
        """True right after her name / a reply: allow longer thinking pauses."""
        return time.monotonic() < self._armed_until or bool(self._pending)

    def _stt_text(self, pcm: bytes) -> str:
        # time limit grows with the recording (seen live: long requests hit a fixed 30 s limit and were lost)
        limit = max(30.0, len(pcm) / (SAMPLE_RATE * 2) * 1.5)
        music_on = self.music_active is not None and self.music_active()
        # During music, hint the few words that matter (measured: "pause" over music went from "more" to
        # "pause"). Not used otherwise: the hint made whisper drop her name in normal speech.
        extra: dict[str, Any] = {"hotwords": MUSIC_HOTWORDS} if music_on else {}
        vocab = self.vocabulary() if self.vocabulary is not None else ""
        if vocab and not music_on:
            extra["prompt"] = vocab
        t = self.recognizer.transcribe(pcm, SAMPLE_RATE, language=self.language, token=CancelToken(timeout_s=limit),
                                       **extra)
        return (t.text or "").strip()

    @property
    def fast(self) -> bool:
        """GPU transcription (~0.3 s) makes live captions and early end-of-turn checks affordable."""
        return getattr(self.recognizer, "device", "cpu") == "cuda"

    def end_check(self, text: str) -> float | None:
        """Is what was said so far a finished request? Returns the silence (s) after which to stop
        listening, or None to keep waiting (it sounds unfinished, or isn't meant for her)."""
        if not text:
            return None
        heard, command = split_wake(text, self.pattern)
        armed = time.monotonic() < self._armed_until or bool(self._pending)
        if heard and not command:
            return EARLY_END_QUESTION_S  # just "Neko." - answer "Yes?" quickly
        cmd = command if heard else text
        if not (heard or armed) or looks_unfinished(cmd) or len(cmd.split()) < 2:
            return None
        if cmd.rstrip().endswith(("?", "!")):
            return EARLY_END_QUESTION_S
        if cmd.rstrip().endswith("."):
            return EARLY_END_SENTENCE_S
        return None

    def caption_for(self, text: str) -> str | None:
        """Live caption while speaking: only for speech meant for her (her name, or a follow-up)."""
        heard, command = split_wake(text, self.pattern)
        if heard:
            return command or "..."
        if time.monotonic() < self._armed_until or self._pending:
            return text
        return None

    def handle_utterance(self, pcm: bytes, text: str | None = None, *, early: bool = False,
                         started_at: float | None = None) -> str | None:
        """Transcribe one utterance (unless ``text`` was already transcribed while listening) and decide
        whether it is meant for N.E.K.O. Returns the command that was dispatched (for tests), or None."""
        music = self.music_active is not None and self.music_active()
        # with music on, the follow-up window would turn lyrics into commands: only "Neko" arms it then
        armed = time.monotonic() < self._armed_until and (not music or self._wake_armed)
        # No hotword biasing: measured 2026-10-27, whisper's hotword prompt made it DROP the name
        # ("Neko, how much..." -> "How much..."), while plain decoding reliably gives "Nico",
        # which the name list accepts.
        if text is None:
            text = self._stt_text(pcm)
        if not text or len(re.sub(r"[^\w]", "", text)) < 2:
            return None
        heard, command = split_wake(text, self.pattern)
        rev = self._revisable
        if rev is not None and not heard and (started_at or time.monotonic()) < rev[0]:
            # You kept talking right after she decided you'd finished ("...the weather in" / pause /
            # "Dhaka tomorrow?"): the whole sentence replaces the first part.
            self._revisable = None
            joined = f"{rev[1].rstrip('.?! ')} {text}".strip()
            (self.on_revise or self.on_command or (lambda _c: None))(joined)
            return joined
        if heard:
            log.info("wake name heard")  # never log what was said (privacy)
        now = time.monotonic()
        if self._pending and now < self._pending_until:  # the rest of an unfinished sentence
            command, heard = (self._pending + " " + (command if heard else text)).strip(), True
            self._pending = ""
        if heard and not command:
            self._armed_until = now + self.follow_up_s
            self._wake_armed = True
            if self.on_wake:
                self.on_wake()
            return None
        if not heard and self.direct_command is not None and self.music_active is not None and self.music_active():
            short = text.strip(" .,!?")
            direct = self.direct_command(short) if len(short.split()) <= 5 else None
            if direct:
                if self.on_command:
                    self.on_command(direct)
                return direct
        if heard or armed:
            cmd = command if heard else text
            if looks_unfinished(cmd):
                # "can you just show me the last time when..." -> wait a moment for the rest
                self._pending, self._pending_until = cmd.rstrip(". "), now + self.wait_rest_s
                self._armed_until = now + self.wait_rest_s
                return None
            self._armed_until = 0.0
            self._revisable = (time.monotonic() + REVISE_WINDOW_S, cmd) if early else None
            if self.on_command:
                self.on_command(cmd)
            return cmd
        return None

    def _run(self, token: CancelToken) -> None:
        import numpy as np
        import sounddevice as sd

        vad = EnergyVAD(max_speech_s=self.max_speech_s)
        work: deque[tuple[bytes, str | None, float, float]] = deque(maxlen=3)
        busy = threading.Event()
        # Live transcription while you talk (GPU only): captions, and an early end of turn when what you
        # said is already a complete request (measured before: up to 2.5 s silence + 6 s "unfinished" wait).
        peek_jobs: deque[tuple[int, str, bytes, int, int]] = deque(maxlen=1)
        peek: dict[str, Any] = {"result": None, "busy": False}
        utt: dict[str, Any] = {"id": 0, "partial_at": 0, "end_sent": False, "started": 0.0}

        def peeker() -> None:
            while not token.cancelled:
                if not peek_jobs:
                    token.wait(0.02)
                    continue
                uid, kind, pcm, buf_len, silent = peek_jobs.popleft()
                peek["busy"] = True
                try:
                    text = self._stt_text(pcm)
                except Exception:  # noqa: BLE001 - a failed preview just means no preview
                    text = ""
                finally:
                    peek["busy"] = False
                if kind == "partial":
                    cap = self.caption_for(text)
                    if cap and self.on_partial and uid == utt["id"]:
                        self.on_partial(cap)
                else:
                    peek["result"] = (uid, text, buf_len, silent, self.end_check(text))

        def worker() -> None:
            while not token.cancelled:
                if not work:
                    if not vad.active:
                        self.flush_pending()
                    token.wait(0.05)
                    continue
                pcm, text, ended_at, started_at = work.popleft()
                busy.set()
                try:
                    self.handle_utterance(pcm, text, early=text is not None, started_at=started_at)
                    log.info("utterance %.1f s of audio, %s, handled %.0f ms after you stopped",
                             len(pcm) / (SAMPLE_RATE * 2), "early end" if text is not None else "silence end",
                             (time.monotonic() - ended_at) * 1000)  # timings only, never the words
                except Exception:  # noqa: BLE001 - keep listening whatever happens
                    log.exception("utterance handling failed")
                finally:
                    busy.clear()
                    if self.on_idle and not vad.active:
                        self.on_idle()

        threading.Thread(target=worker, daemon=True, name="neko-listen-stt").start()
        threading.Thread(target=peeker, daemon=True, name="neko-listen-peek").start()
        # barge-in detector: louder threshold and short chunks (her voice from the speakers is also loud)
        bvad = EnergyVAD(start_ratio=4.0, min_rms=900.0, end_silence_s=0.5, max_speech_s=4.0)
        barge: dict[str, Any] = {"busy": False}

        def check_barge(pcm: bytes) -> None:
            try:
                command = barge_in_command(self._stt_text(pcm), self.pattern)
                if command is not None:
                    log.info("barge-in: interrupted while speaking")
                    self.on_barge_in(command)
            except Exception:  # noqa: BLE001 - never break listening
                log.exception("barge-in check failed")
            finally:
                barge["busy"] = False

        speaking_until = 0.0
        try:
            with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME,
                                   device=self.device) as stream:
                while not token.cancelled:
                    data, _ = stream.read(FRAME)
                    frame = bytes(data)
                    now = time.monotonic()
                    if self.gate is not None and self.gate.speaking:
                        speaking_until = now + 0.5
                    if self.paused or now < speaking_until:
                        vad.reset()
                        if self.barge_in and self.on_barge_in and self.fast and not self.paused:
                            # Barge-in: while she talks, short chunks are checked for her NAME ("Neko, stop",
                            # "Neko, wait - play Believer instead"). Her own voice from the speakers almost
                            # never contains her name, so it can't interrupt itself.
                            arr = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
                            brms = float(np.sqrt(np.mean(arr * arr))) if len(arr) else 0.0
                            chunk = bvad.feed(frame, brms)
                            if chunk is not None and not barge["busy"]:
                                barge["busy"] = True
                                threading.Thread(target=check_barge, args=(chunk,), daemon=True,
                                                 name="neko-barge-in").start()
                        continue
                    vad.end_frames = int((self.addressed_pause_s if self.addressed else self.pause_s) / 0.03)
                    music = self.music_active is not None and self.music_active()
                    vad.max_frames = int((MUSIC_WINDOW_S if music else self.max_speech_s) / 0.03)
                    arr = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
                    rms = float(np.sqrt(np.mean(arr * arr))) if len(arr) else 0.0
                    was_active = vad.active
                    utterance = vad.feed(frame, rms)
                    if vad.active and not was_active:
                        utt.update(id=utt["id"] + 1, partial_at=0, end_sent=False, started=now)
                        peek["result"] = None
                        if self.on_speech_start:
                            self.on_speech_start()
                    if self.on_level and vad.active:
                        self.on_level(min(1.0, rms / 4000.0))
                    early_text: str | None = None
                    if vad.active and self.fast and not music:
                        n, silent = len(vad._buf), vad._silent
                        if n - utt["partial_at"] >= PARTIAL_EVERY_FRAMES and silent < 5 and not peek["busy"]:
                            utt["partial_at"] = n
                            peek_jobs.append((utt["id"], "partial", b"".join(vad._buf), n, silent))
                        if silent == EARLY_CHECK_FRAMES and n >= 25 and not utt["end_sent"]:
                            utt["end_sent"] = True
                            peek_jobs.append((utt["id"], "end", b"".join(vad._buf), n, silent))
                        if silent < EARLY_CHECK_FRAMES:
                            utt["end_sent"] = False  # you started talking again: check again at the next pause
                        res = peek["result"]
                        if res is not None and res[0] == utt["id"] and res[4] is not None:
                            _uid, text, buf_len, silent_then, need_s = res
                            still_quiet = silent - silent_then == n - buf_len  # no speech since the check
                            if not still_quiet:
                                peek["result"] = None
                            elif silent * 0.03 >= need_s:
                                utterance, early_text = b"".join(vad._buf), text
                                vad.reset()
                                peek["result"] = None
                    if utterance is not None:
                        if self.on_level:
                            self.on_level(0.0)
                        if (self.addressed or early_text is not None) and self.on_heard:
                            self.on_heard()  # instant "got it" while whisper is still transcribing
                        work.append((utterance, early_text, time.monotonic(), utt.get("started", now)))
                    elif was_active and not vad.active and self.on_idle and not busy.is_set():
                        self.on_idle()
        except Exception as exc:  # noqa: BLE001
            log.error("microphone stream stopped: %s", exc)
