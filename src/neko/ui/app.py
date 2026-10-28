"""Desktop application entry: HUD + Command Center + tray + first run."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QAction, QBrush, QColor, QIcon, QKeySequence, QPainter, QPixmap, QRadialGradient, QShortcut
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMenu, QMessageBox, QPushButton, QSystemTrayIcon, QVBoxLayout

from .. import APP_NAME
from ..app.bootstrap import Neko, build
from ..configuration.settings import default_user_config_path, load_settings
from ..core.errors import ConfigError
from ..core.types import AssistantState
from .approval import ApprovalDialog
from .bridge import UiBridge
from .capture import capture_screen_under_cursor
from .command_center import CommandCenter
from .hud import HudWindow
from .theme import COLORS, set_theme


def make_icon() -> QIcon:
    """The orb icon from packaging/neko.ico; falls back to a glyph drawn at runtime."""
    ico = Path(__file__).resolve().parents[3] / "packaging" / "neko.ico"
    if ico.exists():
        icon = QIcon(str(ico))
        if not icon.isNull():
            return icon
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QRadialGradient(QPointF(32, 32), 30)
    g.setColorAt(0, QColor("#FFFFFF"))
    g.setColorAt(0.35, QColor(COLORS["accent"]))
    g.setColorAt(1, QColor(COLORS["accent_2"]))
    p.setBrush(QBrush(g))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(32, 32), 28, 28)
    p.end()
    return QIcon(pm)


class FirstRunDialog(QDialog):
    def __init__(self, neko: Neko) -> None:
        super().__init__()
        self.setWindowTitle("Welcome to N.E.K.O.")
        lay = QVBoxLayout(self)
        models = [m.name for m in neko.router.installed()]
        health = neko.providers[0].health()
        server = "running" if health.ok else "NOT running - start it with scripts\\start-ollama.ps1"
        text = (
            "<h3>Hi! I'm N.E.K.O.</h3>"
            "<p>I run on <b>this computer</b>. Nothing you say is sent to the internet - network and cloud "
            "features are off and can only be turned on by editing the config file.</p>"
            f"<p><b>Model server:</b> {server}<br>"
            f"<b>Models found:</b> {', '.join(models) or 'none'}</p>"
            "<p>Voice is <b>off</b> until you enable it. The microphone is only used while you hold the mic "
            "button. Screenshots are taken only when you press the capture button, and are not saved.</p>"
            "<p>Anything that changes files or opens apps asks for your approval first. The red button stops "
            "everything immediately.</p>"
            "<p>See docs\\USER_MANUAL.md for a tour.</p>"
        )
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(lbl)
        ok = QPushButton("Let's go")
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        lay.addWidget(ok)


_instance_mutex: Any = None


def _single_instance() -> Any:
    """A per-user Windows mutex: returns a handle if this is the only N.E.K.O. UI, else None."""
    if sys.platform != "win32":
        return True
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, "Local\\NEKO-UI-single-instance")
    if not handle:
        return True  # can't tell: don't block starting
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        return None
    return handle


class Controller:
    """Connects bridge signals to the windows. Lives on the GUI thread."""

    def __init__(self, app: QApplication, neko: Neko) -> None:
        self.app = app
        self.neko = neko
        s = neko.settings
        self.bridge = UiBridge(neko)
        if s.ui.style == "orb":
            from .orb_window import OrbWindow

            self.hud = OrbWindow(always_on_top=s.ui.always_on_top, opacity=s.ui.hud_opacity,
                                 reduced_motion=s.ui.reduced_motion, name=s.app.assistant_name,
                                 idle_hide_s=s.ui.idle_hide_seconds)
        else:
            self.hud = HudWindow(always_on_top=s.ui.always_on_top, opacity=s.ui.hud_opacity,
                                 reduced_motion=s.ui.reduced_motion, name=s.app.assistant_name)
        self.cc = CommandCenter(neko)
        from .visual_panel import VisualPanel

        self.panel = VisualPanel(always_on_top=s.ui.always_on_top, close_after_s=s.ui.visual_panel_seconds)
        from .. import media
        from .music_player import MusicPlayer

        self.music = MusicPlayer(volume=s.ui.music_volume)
        media.player = self.music
        self.music.now_playing.connect(lambda t: self.hud.setText(f"♪ {t}") if t else None)
        self.music.state_changed.connect(lambda st: setattr(self.hud, "music_state", st))
        self.voice: Any = None
        self._streamed: list[str] = []
        self._live: Any = None             # SentenceFeeder for the reply being spoken live
        self._live_stream: Any = None
        self._live_emotion = "neutral"
        self._superseded: set[int] = set()  # bridge jobs replaced by a longer version of the request
        self._last_pulse = 0.0
        self._pending_images: list[bytes] | None = None
        self._init_voice()
        self._wire()
        self._tray()
        self._timers()

    # ------------------------------------------------------------------ setup
    def _init_voice(self) -> None:
        try:
            from .voice_controller import VoiceController
        except ImportError:
            self.hud.set_mic("voice n/a")
            return
        snap = self.neko.monitor.snapshot()
        self.voice = VoiceController(self.neko.settings, vram_free_mb=snap.vram_free_mb)
        ok, why = self.voice.mic_available()
        self.hud.set_mic("mic ready" if ok else "mic n/a")
        self.hud.mic.setToolTip("Hold to talk" if ok else f"Voice input unavailable: {why}")
        self.voice.state.connect(self._on_state)
        self.voice.level.connect(self.hud.orb.set_level)
        self.voice.transcript.connect(self._on_transcript)
        self.voice.revised.connect(self._on_revised)
        self.voice.subtitle.connect(self._on_subtitle)
        self.voice.barged_in.connect(self._on_barge_in)
        self.voice.problem.connect(lambda m: self.hud.status.setText(m))
        if ok and self.neko.settings.voice.always_listen:
            self.set_always_listen(True)

    def set_always_listen(self, on: bool) -> None:
        if self.voice is None:
            return
        name = (self.neko.settings.voice.wake_names or ["neko"])[0].capitalize()
        if on and self.voice.start_listening():
            self.hud.set_mic(f"listening for '{name}'", True)
            self.hud.mic.setToolTip(f"Always listening: say '{name}, ...'. Microphone is ON. "
                                    "Hold to talk also works.")
        else:
            self.voice.stop_listening()
            self.hud.set_mic("mic ready")
        if hasattr(self, "_listen_action"):
            self._listen_action.setChecked(self.voice.listening if on else False)

    def _wire(self) -> None:
        b = self.bridge
        b.state.connect(self._on_state)
        b.token.connect(self._on_token)
        b.reply.connect(self._on_reply)
        b.routing.connect(lambda d: (self.hud.set_model(d.get("model"), d.get("location")), self.cc.show_routing(d)))
        b.resources.connect(self.cc.show_resources)
        b.approval.connect(self._on_approval)
        b.error.connect(lambda m: self.hud.status.setText(m))
        b.task.connect(lambda _d: None)
        # The neural core reacts to real activity: a tool call fires a strong burst from the core.
        b.tool.connect(lambda d: [self.hud.orb.stimulate(1.0 if d.get("status") == "requested" else 0.7, "core")
                                  for _ in range(3)])
        b.routing.connect(lambda _d: self.hud.orb.stimulate(0.6, "random"))
        self.hud.submitted.connect(self.send)
        self.cc.send_requested.connect(lambda t: self.send(t, from_cc=True))
        self.hud.stop_requested.connect(self.stop)
        self.cc.stop_requested.connect(self.stop)
        self.hud.emergency_requested.connect(self.emergency)
        self.cc.emergency_requested.connect(self.emergency)
        self.cc.resume_requested.connect(self.bridge.resume_after_stop)
        self.hud.expand_requested.connect(self.show_cc)
        self.hud.capture_requested.connect(self.capture)
        if self.voice is not None:
            self.hud.mic_pressed.connect(self.voice.press)
            self.hud.mic_released.connect(self.voice.release)
        for w in (self.hud, self.cc):
            QShortcut(QKeySequence(self.neko.settings.ui.emergency_stop_hotkey), w, activated=self.emergency)
        if hasattr(self.hud, "listen_toggled"):  # orb-only window extras
            self.hud.listen_toggled.connect(self.set_always_listen)
            self.hud.mute_toggled.connect(lambda on: setattr(self.voice, "muted", on) if self.voice else None)
            self.hud.resume_requested.connect(self.resume)
            self.hud.quit_requested.connect(self.quit)
            self.hud.music_requested.connect(self.music.control)
            self.hud.brain_requested.connect(self.show_brain)
            self.hud.armory_requested.connect(self.show_armory)
        self.cc.resume_requested.connect(lambda: self.hud.set_stopped(False) if hasattr(self.hud, "set_stopped") else None)
        # Motion style per task: coding tasks make the rings move like gears with a radar sweep.
        b.task.connect(self._on_task)
        b.need_capture.connect(self._capture_for_engine)
        b.visual.connect(self._on_visual)
        b.emotion.connect(self._on_emotion)
        b.settings_changed.connect(lambda d: self.voice.apply_settings(d) if self.voice is not None else None)

    def _toggle_music(self) -> None:
        self.music.control("resume" if self.music.status().get("state") == "paused" else "pause")

    def _on_emotion(self, emotion: str) -> None:
        self._live_emotion = emotion
        if hasattr(self.hud.orb, "set_emotion"):
            self.hud.orb.set_emotion(emotion)  # her colour changes as soon as she starts answering

    def _on_visual(self, payload: dict) -> None:
        """'Show me ...': open the side panel beside the orb, tinted with her current emotion."""
        if hasattr(self.hud, "appear"):
            self.hud.appear()
        from .holo import EMOTION_COLORS

        accent = EMOTION_COLORS.get(getattr(self.hud.orb, "emotion", "neutral"))
        anchor = self.hud.frameGeometry() if self.hud.isVisible() else None
        self.panel.show_visual(payload, anchor=anchor, accent=accent)

    def _capture_for_engine(self) -> None:
        """She decided to look at the screen ("what's wrong with this?"): hide, grab, show again."""
        from ..vision.images import prepare_png

        self.hud.hide()

        def grab() -> None:
            png = capture_screen_under_cursor()
            self.hud.show()
            if png:
                png = prepare_png(png, self.neko.settings.vision.max_image_side).data
            self.bridge.deliver_capture(png)

        QTimer.singleShot(220, grab)

    def _tray(self) -> None:
        self.tray = QSystemTrayIcon(make_icon(), self.app)
        self.tray.setToolTip(f"{APP_NAME} - local AI assistant")
        menu = QMenu()
        for text, fn in (("Show HUD", self.show_hud), ("Command Center", self.show_cc), ("Neko's brain", self.show_brain),
                         ("Tool armory", self.show_armory),
                         ("Stop current task", self.stop), ("Pause / resume music", self._toggle_music),
                         ("Stop music", lambda: self.music.control("stop")),
                         ("EMERGENCY STOP", self.emergency), ("Quit", self.quit)):
            act = QAction(text, menu)
            act.triggered.connect(fn)
            menu.addAction(act)
        self._listen_action = QAction("Always listen (say her name)", menu)
        self._listen_action.setCheckable(True)
        self._listen_action.setChecked(bool(self.voice is not None and self.voice.listening))
        self._listen_action.toggled.connect(self.set_always_listen)
        menu.insertAction(menu.actions()[2], self._listen_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_hud()
                                    if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
        self._menu = menu

    def _timers(self) -> None:
        self.res_timer = QTimer()
        self.res_timer.timeout.connect(lambda: threading.Thread(target=self.bridge.poll_resources, daemon=True).start())
        self.res_timer.start(int(max(2.0, self.neko.settings.resources.poll_interval_s) * 1000))
        self.health_timer = QTimer()
        self.health_timer.timeout.connect(self._check_health)
        self.health_timer.start(15000)
        QTimer.singleShot(300, self._check_health)

    def _check_health(self) -> None:
        def work() -> None:
            ok = self.neko.providers[0].health(timeout_s=2).ok
            if not ok and not self.bridge.is_busy:
                self.bridge.state.emit(AssistantState.OFFLINE, "start scripts\\start-ollama.ps1")
            elif ok and self.hud.orb.state == AssistantState.OFFLINE:
                self.bridge.state.emit(AssistantState.IDLE, "")
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ actions
    def send(self, text: str, from_cc: bool = False) -> None:
        if not from_cc:
            self.cc.add_user(text)
        images, self._pending_images = self._pending_images, None
        was_fg = self.bridge.foreground_busy
        status = self.bridge.send(text, images=images)
        if status == "queued":
            n = self.bridge.queued
            self.hud.status.setText(f"Got it - that's next up{f' (#{n})' if n > 1 else ''}, right after this.")
            return
        if status == "parallel" and not was_fg:
            # a long job is running in the background: this one streams to the orb as usual
            self.hud.status.setText("On it - still working on the other task in the background, too.")
        if not was_fg:
            self._streamed = []
            self.hud.set_reply("")
            self._begin_live_speech(text)

    def _begin_live_speech(self, text: str) -> None:
        """Ordinary answers are spoken sentence by sentence while she writes them (much faster to
        hear). Slow jobs (projects, documents, music, "show me") get a short "one sec" instead, and
        their own summary at the end."""
        from ..orchestration.smart import document_request, is_long_job, music_request, visual_request
        from .live_speech import SentenceFeeder

        self._live, self._live_stream = None, None
        if self.voice is None or not self.neko.settings.voice.enabled or self.voice.muted:
            return
        music = music_request(text)[0]
        about_doc = document_request(text)[0]
        if is_long_job(text) or about_doc or visual_request(text) == "show" or music == "play":
            self.voice.speak("Okay, finding it." if music == "play" else "Mm, one sec.", "calm", arm_follow_up=False)
        if (not is_long_job(text) and not music and visual_request(text) == "") or (about_doc and not is_long_job(text)):
            self._live = SentenceFeeder()  # questions about a file are answered live too

    def _live_say(self, sentences: list[str]) -> None:
        if not sentences or self.voice is None:
            return
        if self._live_stream is None:
            self._live_stream = self.voice.speak_stream(self._live_emotion)
        if self._live_stream is not None:
            for s in sentences:
                self._live_stream.put(s)

    def stop(self) -> None:
        self._live, self._live_stream = None, None
        self.bridge.cancel()
        if self.voice is not None:
            self.voice.stop_speaking()

    def emergency(self) -> None:
        n = self.bridge.emergency_stop()
        self.music.control("stop")
        if self.voice is not None:
            self.voice.stop_speaking()
            self.set_always_listen(False)  # emergency stop also switches the microphone off
        self.hud.set_state(AssistantState.ERROR, f"EMERGENCY STOP - {n} task(s) cancelled; actions blocked. "
                                                 "Right-click me > Resume actions.")
        self.cc.estop_btn.setText("RESUME (stopped)")
        if hasattr(self.hud, "set_stopped"):
            self.hud.set_stopped(True)

    def resume(self) -> None:
        self.bridge.resume_after_stop()
        self.cc.estop_btn.setText("EMERGENCY STOP")
        if hasattr(self.hud, "set_stopped"):
            self.hud.set_stopped(False)
        self.hud.status.setText("Resumed - actions are allowed again.")

    def _on_task(self, d: dict) -> None:
        if not hasattr(self.hud.orb, "set_mode"):
            return
        if d.get("status") == "running" and d.get("kind") == "coding":
            self.hud.orb.set_mode("coding")
        elif d.get("status") != "running":
            self.hud.orb.set_state(self.hud.orb.state)  # back to the state's own motion

    def capture(self) -> None:
        self.hud.hide()
        QTimer.singleShot(250, self._do_capture)  # let the HUD disappear first

    def _do_capture(self) -> None:
        png = capture_screen_under_cursor()
        self.hud.show()
        if not png:
            self.hud.status.setText("Screen capture failed.")
            return
        from ..vision.images import prepare_png

        img = prepare_png(png, self.neko.settings.vision.max_image_side)
        self._pending_images = [img.data]
        self.hud.status.setText(f"Screenshot attached ({img.width}x{img.height}, kept in memory only). "
                                "Type your question and press Enter.")
        self.hud.input.setFocus()

    def _on_revised(self, text: str) -> None:
        """You kept talking after she thought you'd finished: drop that answer, answer the whole thing."""
        job = self.bridge.cancel()
        if job is not None:
            self._superseded.add(job)
        if self.voice is not None:
            self.voice.stop_speaking()
        self._live, self._live_stream = None, None
        self._on_transcript(text)

    def _on_barge_in(self, command: str) -> None:
        """"Neko, stop" while she talks: silence her (and the job she is on); "Neko, wait - X": do X instead."""
        job = self.bridge.cancel()
        if job is not None:
            self._superseded.add(job)
        if self.voice is not None:
            self.voice.stop_speaking()
        self._live, self._live_stream = None, None
        if command:
            self._on_transcript(command)
        else:
            self.hud.setText("Okay, I'll stop.")
            if self.voice is not None:
                self.voice.reply_finished()  # keep listening for what you say next

    def _speaking_aloud(self) -> bool:
        return self.voice is not None and self.neko.settings.voice.enabled and not self.voice.muted

    def _on_subtitle(self, text: str) -> None:
        if hasattr(self.hud, "show_subtitle"):
            self.hud.show_subtitle(text)

    def _on_transcript(self, text: str) -> None:
        self.hud.setText(f"“{text}”")  # show what she heard at once, so you know she got it
        self.send(text)  # runs now, alongside a background job, or queues as "next up"

    def _on_state(self, state: AssistantState, detail: str) -> None:
        self.hud.set_state(state, detail)
        # music steps back while she listens or talks, so she can hear you and you can hear her
        if state in (AssistantState.LISTENING, AssistantState.TRANSCRIBING, AssistantState.SPEAKING):
            self.music.duck(True)
        elif state in (AssistantState.IDLE, AssistantState.ERROR):
            self.music.duck(False)

    def _on_token(self, text: str) -> None:
        self._streamed.append(text)
        # every generated piece of text sends signals out from the core (capped at ~15/s)
        now = time.monotonic()
        if now - self._last_pulse > 0.066:
            self._last_pulse = now
            self.hud.orb.stimulate(0.45, "core")
        if not (self._speaking_aloud() and hasattr(self.hud, "show_subtitle")):
            self.hud.append_token(text)  # silent mode: show the text as it's written
        self.cc.append_token(text)
        if self._live is not None:
            self._live_say(self._live.feed(text))

    def _on_reply(self, reply: Any) -> None:
        if getattr(reply, "job_id", None) in self._superseded:  # replaced by the full sentence
            self._superseded.discard(reply.job_id)
            return
        if getattr(reply, "background", False) and self.bridge.foreground_busy:
            # A background job finished while she's answering something else: don't mix it into that
            # answer - announce it after the current reply has been spoken.
            self.cc.finish_reply(reply, "")
            self.hud.status.setText(f"Finished: {getattr(reply, 'goal', '') or 'background task'}")
            if self.voice is not None and reply.succeeded and self.neko.settings.voice.enabled:
                self.voice.speak(reply.speech or reply.text, reply.emotion, queue=True)
            return
        streamed = "".join(self._streamed)
        self._streamed = []
        spoken = self._speaking_aloud() and reply.succeeded and hasattr(self.hud, "show_subtitle")
        if streamed.strip() != reply.text.strip() and not spoken:
            self.hud.set_reply(reply.text)  # (when she speaks, word-by-word subtitles show it instead)
        self.cc.finish_reply(reply, streamed)
        if hasattr(self.hud.orb, "set_emotion"):
            self.hud.orb.set_emotion(reply.emotion)  # her colour follows her mood
        elif reply.notes:
            self.hud.status.setText(" ".join(reply.notes)[:200])
        live, self._live = self._live, None
        stream, self._live_stream = self._live_stream, None
        if stream is not None:  # already being spoken sentence by sentence
            if reply.succeeded and live is not None:
                last = live.flush()
                if last:
                    stream.put(last)
            stream.close()
        elif self.voice is not None and reply.succeeded and self.neko.settings.voice.enabled:
            self.voice.speak(reply.speech or reply.text, reply.emotion)
        elif self.voice is not None:
            self.voice.reply_finished()  # not speaking: still allow a follow-up without the name
        if getattr(reply, "action", "") == "open_brain":
            self.show_brain()
        elif getattr(reply, "action", "") == "open_armory":
            self.show_armory()
        if getattr(reply, "action", "") == "quit":  # "Neko, close yourself" - after saying goodbye
            QTimer.singleShot(int(1000 + 70 * len(reply.text)), self.quit)

    def _on_approval(self, req: Any) -> None:
        parent = self.cc if self.cc.isVisible() else None
        dlg = ApprovalDialog(req, parent)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def show_hud(self) -> None:
        self.hud.show()
        self.hud.raise_()

    def show_brain(self) -> None:
        from .brain_view import BrainWindow

        if getattr(self, "_brain", None) is None:
            self._brain = BrainWindow(self.neko)
        else:
            self._brain.rebuild()
        self._brain.show()
        self._brain.raise_()
        self._brain.activateWindow()

    def show_armory(self) -> None:
        from .armory_view import ArmoryWindow

        if getattr(self, "_armory", None) is None:
            self._armory = ArmoryWindow(self.neko)
        else:
            self._armory.refresh()
        self._armory.show()
        self._armory.raise_()
        self._armory.activateWindow()

    def show_cc(self) -> None:
        self.cc.refresh_activity()
        self.cc.refresh_models()
        self.cc.show()
        self.cc.raise_()
        self.cc.activateWindow()

    def quit(self) -> None:
        self.stop()
        self.music.shutdown()
        self.tray.hide()
        self.neko.shutdown()
        self.app.quit()


def run_ui(background: bool = False) -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # closing windows leaves the tray icon
    global _instance_mutex
    _instance_mutex = _single_instance()
    if _instance_mutex is None:
        # Seen 2026-10-28: two copies ran at once, both listening and both answering.
        QMessageBox.information(None, "N.E.K.O.", "Neko is already running - look for the orb or the tray "
                                "icon. (Say \"Neko\" to wake her.)")
        return 0
    try:
        settings = load_settings()
    except ConfigError as exc:
        QMessageBox.critical(None, "N.E.K.O. configuration error", exc.user_message)
        return 1
    app.setStyleSheet(set_theme(settings.ui.theme))
    app.setWindowIcon(make_icon())
    first_run = not default_user_config_path().exists() and not settings.db_path.exists()
    neko = build(settings)
    neko.maintenance()
    ctl = Controller(app, neko)
    if first_run:
        FirstRunDialog(neko).exec()
    if background and hasattr(ctl.hud, "start_hidden"):
        ctl.hud.start_hidden()  # started with Windows: stay invisible (still listening) until "Neko"
    elif settings.ui.start_compact:
        ctl.show_hud()
    else:
        ctl.show_cc()
    code = app.exec()
    return int(code)
