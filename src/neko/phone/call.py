"""Live voice calls from your phone.

A tiny web server on **127.0.0.1 only** (``phone.call_port``). It is never reachable from the network by
itself: ``scripts/phone-call.ps1`` asks Tailscale to share it as https inside *your* tailnet, so only your
own devices (signed in to your Tailscale account) can open it - and every request must also carry the
private call key (sent to you in Telegram with /call, kept in the link's #fragment, never in server logs).

The page records while you talk (echo-cancelled), sends each sentence when you pause, and plays her
answer sentence by sentence while she is still thinking, with live subtitles. Talking over her stops her.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ..core import origin
from ..core.cancel import CancelToken
from ..core.errors import NekoError

log = logging.getLogger("neko.phone.call")
PAGE = Path(__file__).with_name("call_page.html")
MAX_UPLOAD = 6 * 1024 * 1024


def tailnet_name() -> str:
    """This PC's MagicDNS name, e.g. 'fleet-host.tail1234.ts.net' ('' without Tailscale)."""
    import subprocess

    from ..models.office import tailscale_exe

    exe = tailscale_exe()
    if not exe:
        return ""
    try:
        cp = subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=8, shell=False,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return str((json.loads(cp.stdout or "{}").get("Self") or {}).get("DNSName", "")).rstrip(".")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return ""


def call_url(settings: Any, key: str) -> str:
    if not settings.phone.calls:
        return ""
    host = tailnet_name()
    if not host:
        return ""
    port = settings.phone.call_https_port
    return f"https://{host}{'' if port == 443 else f':{port}'}/#k={key}"


class CallServer:
    def __init__(self, neko: Any, service: Any, *, voice: Any) -> None:
        self.neko, self.service, self.voice = neko, service, voice
        self._httpd: ThreadingHTTPServer | None = None
        self._current: CancelToken | None = None
        self._events: queue.Queue[dict[str, Any]] | None = None
        self._bad: list[float] = []
        self._turn_lock = threading.Lock()
        service.approval_listeners.append(self._approval_notice)

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> str:
        if self._httpd is not None:
            return "running"
        if not self.neko.settings.phone.calls:
            return "Calls are switched off."
        port = self.neko.settings.phone.call_port
        try:
            self._httpd = ThreadingHTTPServer(("127.0.0.1", port), self._handler_class())
        except OSError as exc:
            return f"Port {port} is busy: {exc}"
        self._httpd.daemon_threads = True
        threading.Thread(target=self._httpd.serve_forever, daemon=True, name="neko-call-server").start()
        log.info("call page on 127.0.0.1:%d (shared only through Tailscale)", port)
        return "running"

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    # ------------------------------------------------------------------ auth
    def authorized(self, key: str) -> bool:
        now = time.time()
        self._bad = [t for t in self._bad if now - t < 60]
        if len(self._bad) >= 20:
            return False  # someone is guessing: refuse everything for a minute
        ok = bool(key) and hmac.compare_digest(key.encode(), self.service.state.call_key.encode())
        if not ok:
            self._bad.append(now)
            log.warning("call page: request with a wrong key")
        return ok

    # ------------------------------------------------------------------ a turn of the conversation
    def turn(self, *, audio: bytes | None = None, text: str = "", emit: Any) -> None:
        """Hear (or read) one thing you said and stream her answer as {"type": ...} events."""
        self.stop_speaking()  # you spoke again: the previous answer is no longer wanted
        with self._turn_lock:  # one answer at a time; a new one has already cancelled the old
            token = CancelToken(timeout_s=600)
            self._current = token
            if audio is not None:
                text = self._hear(audio)
                if not text:
                    emit({"type": "nothing"})
                    return
                emit({"type": "heard", "text": text})
            self._answer(text, token, emit)

    def stop_speaking(self) -> None:
        if self._current is not None:
            self._current.cancel("you talked over her")

    def _hear(self, audio: bytes) -> str:
        from .audio import to_pcm16

        vc = self.voice()
        if vc is None:
            raise NekoError("voice off", user_message="Voice is switched off on the PC.")
        pcm = to_pcm16(audio)
        if len(pcm) < 16000 * 2 * 0.3:  # under 0.3 s: a cough or a click
            return ""
        t = vc.stt.transcribe(pcm, 16000, language=vc.settings.stt_language or None, token=CancelToken(timeout_s=60),
                              prompt=vc.vocabulary.prompt() or None)
        return t.text.strip()

    def _answer(self, text: str, token: CancelToken, emit: Any) -> None:
        from ..ui.live_speech import SentenceFeeder
        from .audio import clip_for_call

        vc = self.voice()
        tts = vc.tts if vc is not None else None
        feeder = SentenceFeeder()
        sentences: queue.Queue[str | None] = queue.Queue()
        emotion = {"value": "neutral"}

        def speak_worker() -> None:
            while True:
                s = sentences.get()
                if s is None or token.cancelled:
                    return
                if tts is None:
                    emit({"type": "say", "text": s})
                    continue
                try:
                    data, mime, words = clip_for_call(tts, s, emotion["value"])
                    emit({"type": "say", "text": s, "mime": mime, "words": words,
                          "audio": base64.b64encode(data).decode("ascii")})
                except Exception as exc:  # noqa: BLE001
                    log.warning("call voice failed: %s", exc)
                    emit({"type": "say", "text": s})

        speaker = threading.Thread(target=speak_worker, daemon=True, name="neko-call-voice")
        speaker.start()

        def on_token(piece: str) -> None:
            for s in feeder.feed(piece):
                sentences.put(s)

        conv = self.service._conversation()
        with origin.from_origin(origin.PHONE):
            reply = self.neko.coordinator.handle(text, conversation_id=conv, token=token, on_token=on_token)
        emotion["value"] = reply.emotion
        if feeder.started:
            last = feeder.flush()
            if last:
                sentences.put(last)
        elif reply.text and not token.cancelled:  # commands answer without streaming
            for s in [reply.speech or reply.text]:
                sentences.put(s)
        sentences.put(None)
        speaker.join(timeout=120)
        emit({"type": "done", "text": reply.text, "ok": reply.succeeded})

    def _approval_notice(self, req: Any) -> None:
        q = self._events
        if q is not None:
            q.put({"type": "status", "text": "Waiting for your approval in Telegram (or at the PC): "
                                             f"{req.summary[:120]}"})

    # ------------------------------------------------------------------ HTTP
    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        server = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "NEKO"
            sys_version = ""

            def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401 - never log URLs/keys
                return

            def _send(self, code: int, body: bytes, ctype: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                if self.path.split("?")[0] in ("/", "/index.html"):
                    self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                elif self.path == "/manifest.json":
                    self._send(200, json.dumps({"name": "Neko", "short_name": "Neko", "display": "standalone",
                                                "background_color": "#05060a", "theme_color": "#05060a",
                                                "start_url": "/"}).encode(), "application/manifest+json")
                else:
                    self._send(404, b"not found", "text/plain")

            def do_POST(self) -> None:  # noqa: N802
                if not server.authorized(self.headers.get("X-Neko-Key", "")):
                    self._send(403, b"forbidden", "text/plain")
                    return
                size = int(self.headers.get("Content-Length") or 0)
                if size > MAX_UPLOAD:
                    self._send(413, b"too large", "text/plain")
                    return
                body = self.rfile.read(size) if size else b""
                route = self.path.split("?")[0]
                if route == "/api/ping":
                    self._send(200, b'{"ok":true}', "application/json")
                elif route == "/api/stop":
                    server.stop_speaking()
                    self._send(200, b'{"ok":true}', "application/json")
                elif route in ("/api/turn", "/api/text"):
                    self._stream(route, body)
                else:
                    self._send(404, b"not found", "text/plain")

            def _stream(self, route: str, body: bytes) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                events: queue.Queue[dict[str, Any] | None] = queue.Queue()
                server._events = events  # type: ignore[assignment]

                def run() -> None:
                    try:
                        if route == "/api/text":
                            text = str(json.loads(body.decode("utf-8") or "{}").get("text", ""))[:2000]
                            server.turn(text=text, emit=events.put)
                        else:
                            server.turn(audio=body, emit=events.put)
                    except NekoError as exc:
                        events.put({"type": "error", "text": exc.user_message})
                    except Exception as exc:  # noqa: BLE001
                        log.exception("call turn failed")
                        events.put({"type": "error", "text": f"Something went wrong: {exc}"})
                    finally:
                        events.put(None)

                threading.Thread(target=run, daemon=True, name="neko-call-turn").start()
                try:
                    while True:
                        try:
                            ev = events.get(timeout=15)
                        except queue.Empty:
                            self.wfile.write(b": keep-alive\n\n")  # waiting for an approval, a slow model...
                            self.wfile.flush()
                            continue
                        if ev is None:
                            break
                        self.wfile.write(b"data: " + json.dumps(ev).encode("utf-8") + b"\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    server.stop_speaking()  # the phone hung up
                finally:
                    if server._events is events:
                        server._events = None

        return Handler


__all__ = ["CallServer", "call_url", "tailnet_name"]
