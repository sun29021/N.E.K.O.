"""Minimal Telegram Bot API client (standard library only).

Only outgoing HTTPS requests to api.telegram.org: long polling (``getUpdates``) means nothing on this PC
ever listens for connections. The bot key is part of every URL, so it is scrubbed from every error
message before anything is logged.
"""

from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.request
from typing import Any

from ..core.errors import ToolError

API = "https://api.telegram.org"
MAX_DOWNLOAD = 20 * 1024 * 1024    # Telegram's own limit for bots
MAX_TEXT = 4000                    # Telegram allows 4096 per message


class TelegramError(ToolError):
    user_message = "Telegram didn't answer."


class TelegramApi:
    def __init__(self, token: str, *, timeout_s: float = 30) -> None:
        if not token or ":" not in token:
            raise TelegramError("bot key missing or malformed", user_message="The Telegram bot key doesn't look right.")
        self._token = token
        self.timeout_s = timeout_s

    def _scrub(self, text: str) -> str:
        return text.replace(self._token, "<bot-key>")

    def call(self, method: str, params: dict[str, Any] | None = None, *, files: dict[str, tuple[str, bytes, str]]
             | None = None, timeout_s: float | None = None) -> Any:
        url = f"{API}/bot{self._token}/{method}"
        if files:
            body, ctype = _multipart(params or {}, files)
        else:
            body, ctype = json.dumps(params or {}).encode("utf-8"), "application/json"
        req = urllib.request.Request(url, data=body, headers={"Content-Type": ctype}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout_s or self.timeout_s) as resp:  # noqa: S310 - fixed https host
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("description", "")
            except (ValueError, OSError):
                detail = ""
            raise TelegramError(self._scrub(f"{method}: HTTP {exc.code} {detail}")) from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise TelegramError(self._scrub(f"{method}: {exc}")) from None
        if not data.get("ok"):
            raise TelegramError(self._scrub(f"{method}: {data.get('description', 'failed')}"))
        return data.get("result")

    # ------------------------------------------------------------------ helpers
    def get_updates(self, offset: int, wait_s: int = 50) -> list[dict[str, Any]]:
        return self.call("getUpdates", {"offset": offset, "timeout": wait_s,
                                        "allowed_updates": ["message", "callback_query"]},
                         timeout_s=wait_s + 15) or []

    def me(self) -> dict[str, Any]:
        return self.call("getMe")

    def send_text(self, chat_id: int, text: str, buttons: list[list[dict[str, str]]] | None = None) -> int:
        """Long replies are split. Returns the id of the last message sent."""
        text = text.strip() or "(empty)"
        chunks = [text[i:i + MAX_TEXT] for i in range(0, len(text), MAX_TEXT)]
        last = 0
        for i, chunk in enumerate(chunks):
            params: dict[str, Any] = {"chat_id": chat_id, "text": chunk}
            if buttons and i == len(chunks) - 1:
                params["reply_markup"] = {"inline_keyboard": buttons}
            last = int(self.call("sendMessage", params)["message_id"])
        return last

    def edit_text(self, chat_id: int, message_id: int, text: str) -> None:
        try:
            self.call("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text[:MAX_TEXT]})
        except TelegramError:
            pass  # e.g. unchanged text - cosmetic only

    def delete(self, chat_id: int, message_id: int) -> None:
        try:
            self.call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
        except TelegramError:
            pass

    def answer_button(self, callback_id: str, text: str = "") -> None:
        try:
            self.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:190]})
        except TelegramError:
            pass

    def typing(self, chat_id: int, action: str = "typing") -> None:
        try:
            self.call("sendChatAction", {"chat_id": chat_id, "action": action}, timeout_s=10)
        except TelegramError:
            pass

    def send_voice(self, chat_id: int, ogg: bytes, caption: str = "") -> None:
        self.call("sendVoice", {"chat_id": chat_id, "caption": caption[:1000]},
                  files={"voice": ("neko.ogg", ogg, "audio/ogg")}, timeout_s=60)

    def send_photo(self, chat_id: int, image: bytes, caption: str = "", name: str = "screen.png") -> None:
        self.call("sendPhoto", {"chat_id": chat_id, "caption": caption[:1000]},
                  files={"photo": (name, image, "image/png" if name.endswith(".png") else "image/jpeg")},
                  timeout_s=60)

    def send_document(self, chat_id: int, data: bytes, name: str, caption: str = "") -> None:
        self.call("sendDocument", {"chat_id": chat_id, "caption": caption[:1000]},
                  files={"document": (name, data, "application/octet-stream")}, timeout_s=120)

    def download(self, file_id: str) -> bytes:
        info = self.call("getFile", {"file_id": file_id})
        if int(info.get("file_size") or 0) > MAX_DOWNLOAD:
            raise TelegramError("file too large", user_message="That file is bigger than 20 MB - Telegram won't "
                                                               "let me download it.")
        url = f"{API}/file/bot{self._token}/{info['file_path']}"
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 - fixed https host
                data = resp.read(MAX_DOWNLOAD + 1)
        except (urllib.error.URLError, OSError) as exc:
            raise TelegramError(self._scrub(f"download: {exc}")) from None
        if len(data) > MAX_DOWNLOAD:
            raise TelegramError("file too large")
        return data


def _multipart(fields: dict[str, Any], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = "neko" + secrets.token_hex(12)
    out = bytearray()
    for k, v in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n").encode()
        out += (v if isinstance(v, str) else json.dumps(v)).encode("utf-8") + b"\r\n"
    for k, (name, data, ctype) in files.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{name}\"\r\n"
                f"Content-Type: {ctype}\r\n\r\n").encode()
        out += data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"
