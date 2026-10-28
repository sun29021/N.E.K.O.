"""Use the office PC's GPU from the laptop (over Tailscale - your own private, encrypted network).

The office PC runs Ollama on localhost and shares it ONLY inside your tailnet with
``tailscale serve --tcp=11434`` (scripts/share-gpu.ps1, run there with your approval). This laptop then
talks to it like a local Ollama. ``models.office_url``:
* ``""``   - off
* ``"auto"`` - find it: online Windows peers in your tailnet that answer on port 11434 (checked every few
  minutes, 1.5 s per probe, never the internet)
* ``"http://office-pc:11434"`` or ``"http://100.x.y.z:11434"`` - a fixed address.
When the office PC is off or unreachable, it is skipped for a minute and the local/cloud brains answer.
Audio (hearing, voice) always stays on the laptop.
"""

from __future__ import annotations

import ipaddress
import json
import os
import shutil
import subprocess
import time
import urllib.request
from typing import Any
from urllib.parse import urlparse

from ..core.errors import ModelTimeoutError, ModelUnavailableError
from .base import ModelInfo
from .ollama import OllamaProvider

_TAILNET = ipaddress.ip_network("100.64.0.0/10")   # Tailscale addresses (CGNAT range)


def tailscale_exe() -> str | None:
    for c in (shutil.which("tailscale"), r"C:\Program Files\Tailscale\tailscale.exe"):
        if c and os.path.exists(c):
            return c
    return None


def tailnet_peers(timeout_s: float = 6.0) -> list[dict[str, Any]]:
    """Online peers of YOUR tailnet: [{"name", "ip", "os"}] (fixed command, no shell)."""
    exe = tailscale_exe()
    if not exe:
        return []
    try:
        cp = subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=timeout_s,
                            shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        data = json.loads(cp.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return []
    out = []
    for p in (data.get("Peer") or {}).values():
        ips = [ip for ip in p.get("TailscaleIPs") or [] if ":" not in ip]
        if p.get("Online") and ips:
            out.append({"name": (p.get("DNSName") or p.get("HostName") or "").split(".")[0], "ip": ips[0],
                        "os": p.get("OS", "")})
    return out


def answers_ollama(url: str, timeout_s: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/version", timeout=timeout_s) as r:  # noqa: S310 - tailnet only
            return r.status == 200
    except OSError:
        return False


def is_tailnet_or_private(url: str) -> bool:
    """Office addresses must stay inside your own networks: Tailscale (100.64/10, *.ts.net, MagicDNS
    short names) or a private LAN address. Never a public internet address."""
    host = urlparse(url).hostname or ""
    if host.endswith(".ts.net") or ("." not in host and host not in ("", "localhost")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip in _TAILNET or ip.is_private


class OfficeProvider(OllamaProvider):
    id = "ollama-office"

    def __init__(self, setting: str, *, default_timeout_s: float = 180.0) -> None:
        self.setting = setting.strip()
        super().__init__(self.setting if self.setting.startswith("http") else "http://127.0.0.1:1",
                         location="lan:office", default_timeout_s=default_timeout_s)
        self._down_until = 0.0
        self._found_at = 0.0
        self.peer_name = ""

    def _locate(self) -> bool:
        """Point at the office PC (auto: discover it in the tailnet). False if it isn't reachable now."""
        now = time.monotonic()
        if now < self._down_until:
            return False
        if self.setting.startswith("http"):
            return True
        if self._found_at and now - self._found_at < 300:
            return True
        for peer in tailnet_peers():
            if peer["os"].lower().startswith("windows") and answers_ollama(f"http://{peer['ip']}:11434"):
                self.host, self.port, self.peer_name, self._found_at = peer["ip"], 11434, peer["name"], now
                return True
        self._down_until = now + 120
        return False

    def list_models(self) -> list[ModelInfo]:
        if not self._locate():
            return []
        try:
            data = self._request("GET", "/api/tags", timeout=2.5)
        except (ModelUnavailableError, ModelTimeoutError):
            self._down_until, self._found_at = time.monotonic() + 60, 0.0
            return []
        out = []
        from .ollama import infer_capabilities

        for m in data.get("models", []):
            d = m.get("details", {}) or {}
            out.append(ModelInfo(name=m["name"], provider=self.id, location=self.location,
                                 capabilities=infer_capabilities(m["name"], d.get("family", ""), d.get("families")),
                                 size_bytes=m.get("size"), parameter_size=d.get("parameter_size", ""),
                                 quantization=d.get("quantization_level", ""), family="office"))
        return out

    def loaded_models(self) -> list[ModelInfo]:
        if time.monotonic() < self._down_until or not (self.setting.startswith("http") or self._found_at):
            return []
        try:
            data = self._request("GET", "/api/ps", timeout=2)
        except (ModelUnavailableError, ModelTimeoutError):
            return []
        return [ModelInfo(name=m["name"], provider=self.id, location=self.location, loaded=True)
                for m in data.get("models", [])]

    def unload(self, model: str) -> None:
        return None  # never unload models on the office PC from here


__all__ = ["OfficeProvider", "answers_ollama", "is_tailnet_or_private", "tailnet_peers", "tailscale_exe"]
