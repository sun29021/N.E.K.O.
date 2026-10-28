"""Push-to-talk and spoken replies, wired to the UI.

Flow: press-and-hold mic button -> LISTENING (level meter drives the orb) ->
release -> TRANSCRIBING (faster-whisper, local) -> text goes to the normal
request path -> reply -> SPEAKING (SAPI/Piper) unless muted. The Stop button
cancels speech instantly. Everything here is optional; if components are
missing the mic button explains what to install instead of failing.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from ..core.cancel import CancelToken
from ..core.errors import NekoError
from ..core.types import AssistantState
from ..voice.audio import SAMPLE_RATE, PushToTalkRecorder, SpeechGate
from ..voice.base import TextStream
from ..voice.stt_whisper import FasterWhisperRecognizer
from ..voice.tts import build_synthesizer

log = logging.getLogger("neko.voice")


_BARE_STOP = {"stop", "stop it", "stop that", "enough", "quiet", "be quiet", "turn it off", "shut it off"}


_SOUNDS_LIKE_PAUSE = {"paws", "pose", "pause it", "pause that", "pause please", "hold on", "wait"}


def _music_active() -> bool:
    from .. import media

    return media.player is not None and media.player.status().get("state") in ("playing", "paused", "loading")


def music_shortcut(text: str) -> str | None:
    """While music plays, these short phrases work without saying her name. Returns the command
    to run, or None. (Lyrics rarely are just "pause" or "turn it up"; longer phrases still need "Neko".)"""
    from ..orchestration.smart import music_request

    low = text.lower().strip(" .,!?")
    if low in _BARE_STOP:
        return "stop the music"
    if low in _SOUNDS_LIKE_PAUSE:
        return "pause"
    action, _ = music_request(low)
    return low if action in ("pause", "resume", "stop", "louder", "quieter", "next") else None


class VoiceController(QObject):
    state = Signal(object, str)
    level = Signal(float)
    transcript = Signal(str)
    revised = Signal(str)       # you kept talking: replace the request she just started on
    subtitle = Signal(str)      # words she has spoken so far in the current sentence
    barged_in = Signal(str)     # you said her name while she was talking: "" = stop, else a new request
    problem = Signal(str)

    def __init__(self, settings: object, vram_free_mb: int | None = None) -> None:
        super().__init__()
        v = settings.voice  # type: ignore[attr-defined]
        self.settings = v
        from ..voice.vocabulary import vocabulary_for

        self.vocabulary = vocabulary_for(settings)  # her personal word list (spelling hints for speech)
        self.recorder = PushToTalkRecorder(device=v.input_device or None)
        self.stt = FasterWhisperRecognizer(v.stt_model, v.stt_device, v.stt_compute_type,
                                           download_root=v.stt_model_dir or None, vram_free_mb=vram_free_mb)
        self._privacy = settings.privacy  # type: ignore[attr-defined]
        self.tts: Any = None
        self._build_voice()
        self.gate = SpeechGate()
        self.muted = not v.enabled
        self._speak_token: CancelToken | None = None
        self._queued_tokens: list[CancelToken] = []
        self._speak_thread: threading.Thread | None = None
        self._meter = QTimer(self)
        self._meter.timeout.connect(lambda: self.level.emit(self.recorder.level))
        self.listener: Any = None

    # ------------------------------------------------------------------ always listening
    def _build_voice(self) -> None:
        self.tts = build_synthesizer(self.settings, cloud_allowed=self._privacy.allow_cloud_models,
                                     network_allowed=self._privacy.allow_network)
        if hasattr(self.tts, "on_words"):
            self.tts.on_words = self.subtitle.emit  # word-by-word subtitles, in time with the voice
        if hasattr(self.tts, "on_level"):
            self.tts.on_level = self.level.emit  # real speech loudness drives the core (thread-safe signal)

    def apply_settings(self, _changes: dict | None = None) -> None:
        """Voice gender / language changed by a voice command: switch now (no restart)."""
        self._build_voice()
        if self.listener is not None:
            self.listener.language = self.settings.stt_language or None

    def _warm_up(self) -> None:
        try:
            self.stt._load()
        except NekoError as exc:
            log.warning("speech model warm-up failed: %s", exc)

    def start_listening(self) -> bool:
        """Continuous listening; commands are sent when the name is heard (or right after a reply)."""
        from ..voice.listener import WakeNameListener

        ok, why = self.mic_available()
        if ok:  # load the speech model now (large-v3-turbo takes ~4 s), not on the first sentence
            threading.Thread(target=self._warm_up, daemon=True, name="neko-stt-warmup").start()
        if not ok:
            self.problem.emit(f"Always-listening isn't available: {why}")
            return False
        if self.listener is None:
            self.listener = WakeNameListener(
                self.stt, names=list(self.settings.wake_names) or ["neko"],
                language=self.settings.stt_language or None, gate=self.gate,
                device=self.settings.input_device or None, follow_up_s=float(self.settings.follow_up_seconds),
                pause_s=float(self.settings.pause_seconds),
                addressed_pause_s=float(self.settings.addressed_pause_seconds),
                wait_rest_s=float(self.settings.wait_rest_seconds),
                max_speech_s=float(self.settings.max_speech_seconds),
                on_command=self.transcript.emit,
                on_wake=self._on_wake,
                on_speech_start=self._on_speech_start,
                on_level=self.level.emit,
                on_idle=lambda: self.state.emit(AssistantState.IDLE, ""),
                on_heard=lambda: self.state.emit(AssistantState.TRANSCRIBING, "got it..."),
                music_active=_music_active,
                direct_command=music_shortcut,
                vocabulary=self.vocabulary.prompt,
                on_revise=self.revised.emit,
                on_barge_in=self.barged_in.emit,
                barge_in=bool(getattr(self.settings, "barge_in", True)),
                on_partial=lambda text: self.state.emit(AssistantState.LISTENING, f"“{text}”"),
            )
        try:
            self.listener.start()
        except NekoError as exc:
            self.problem.emit(exc.user_message)
            return False
        return True

    def stop_listening(self) -> None:
        if self.listener is not None:
            self.listener.stop()

    @property
    def listening(self) -> bool:
        return self.listener is not None and self.listener.running

    def _on_speech_start(self) -> None:
        # only light up when she is actually being talked to (after her name / in the follow-up window);
        # background talk used to show LISTENING and then nothing happened
        if self.listener is not None and self.listener.addressed:
            self.state.emit(AssistantState.LISTENING, "I'm listening...")

    def _on_wake(self) -> None:
        self.state.emit(AssistantState.LISTENING, "Yes? I'm listening...")
        if not self.muted:
            self.speak("[happy] Yes?", arm_follow_up=False)

    def reply_finished(self) -> None:
        """Open the follow-up window so the next sentence needs no name (called after each reply)."""
        if self.listener is not None and self.listener.running:
            self.listener.arm_follow_up()

    def mic_available(self) -> tuple[bool, str]:
        ok, why = PushToTalkRecorder.available()
        if not ok:
            return ok, why
        return self.stt.available()

    # ------------------------------------------------------------------ push to talk
    def press(self) -> None:
        ok, why = self.mic_available()
        if not ok:
            self.problem.emit(f"Voice input isn't ready: {why}")
            return
        self.stop_speaking()
        try:
            self.recorder.start()
        except NekoError as exc:
            self.problem.emit(exc.user_message)
            return
        self._meter.start(50)
        self.state.emit(AssistantState.LISTENING, "hold to talk, release to send")

    def release(self) -> None:
        if self.recorder._stream is None:
            return
        self._meter.stop()
        pcm = self.recorder.stop()
        self.level.emit(0.0)
        if len(pcm) < SAMPLE_RATE * 2 * 0.3:  # < 0.3 s
            self.state.emit(AssistantState.IDLE, "")
            return
        self.state.emit(AssistantState.TRANSCRIBING, "")
        threading.Thread(target=self._transcribe, args=(pcm,), daemon=True, name="neko-stt").start()

    def _transcribe(self, pcm: bytes) -> None:
        try:
            lang = self.settings.stt_language or None
            t = self.stt.transcribe(pcm, SAMPLE_RATE, language=lang, token=CancelToken(timeout_s=60),
                                    prompt=self.vocabulary.prompt() or None)  # push-to-talk uses it too
        except NekoError as exc:
            self.problem.emit(exc.user_message)
            self.state.emit(AssistantState.IDLE, "")
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("transcription failed")
            self.problem.emit(f"Transcription failed: {exc}")
            self.state.emit(AssistantState.ERROR, "")
            return
        finally:
            del pcm  # raw audio is never kept (voice.keep_recordings is not implemented in v0.1)
        if not t.text:
            self.problem.emit("I didn't catch that - nothing was transcribed.")
            self.state.emit(AssistantState.IDLE, "")
            return
        if t.low_confidence:
            self.problem.emit("Transcription confidence was low; please check the text before relying on it.")
        self.transcript.emit(t.text)

    # ------------------------------------------------------------------ speech output
    def speak_stream(self, emotion: str = "neutral") -> TextStream | None:
        """Start speaking a reply that is still being written: `put` sentences, then `close`.
        Returns None when muted."""
        if self.muted:
            return None
        stream = TextStream()
        self.speak(stream, emotion)
        return stream

    def speak(self, text: str | TextStream, emotion: str = "neutral", *, arm_follow_up: bool = True,
              queue: bool = False) -> None:
        """Say a reply. queue=True waits for the current sentence to finish instead of cutting it off
        (used when a background task finishes while she is talking)."""
        if self.muted:
            return
        from ..core.emotion import split_emotion

        if isinstance(text, str):
            tagged, text = split_emotion(text)
            emotion = tagged if tagged != "neutral" else emotion
        previous = self._speak_thread
        if not queue:
            self.stop_speaking()
        tok = CancelToken(timeout_s=300)
        if queue and self._speak_token is not None:
            self._queued_tokens.append(self._speak_token)  # Stop must still silence the current one
        self._speak_token = tok

        def run() -> None:
            if queue and previous is not None and previous.is_alive():
                previous.join(timeout=240)
                if tok.cancelled:
                    return
            self.state.emit(AssistantState.SPEAKING, "")
            try:
                spoken = text
                if isinstance(text, TextStream) and not getattr(self.tts, "supports_stream", False):
                    spoken = text.full_text(tok)  # this engine can only say whole texts
                self.gate.speak_with_gate(self.tts, spoken, tok, emotion)
            except NekoError as exc:
                self.problem.emit(exc.user_message)
            finally:
                if not tok.cancelled or tok.reason != "superseded":
                    self.state.emit(AssistantState.IDLE, "")
                    if arm_follow_up:
                        self.reply_finished()

        self._speak_thread = threading.Thread(target=run, daemon=True, name="neko-tts")
        self._speak_thread.start()

    def stop_speaking(self) -> None:
        for t in self._queued_tokens:
            t.cancel("superseded")
        self._queued_tokens.clear()
        if self._speak_token is not None:
            self._speak_token.cancel("superseded")
            self._speak_token = None
