"""Validated configuration.

Load order (later wins):
  1. ``defaults.toml`` shipped in the package
  2. user config: ``%LOCALAPPDATA%\\NEKO\\config.toml`` (or ``NEKO_CONFIG``)
  3. selected environment variables (``NEKO_OLLAMA_URL``, ``NEKO_DATA_DIR``)

Secrets are never read from TOML. Anything secret (remote tokens, optional
cloud API keys) is referenced by the *name* of an environment variable.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..core.errors import ConfigError

CONFIG_VERSION = 1
_DEFAULTS_PATH = Path(__file__).with_name("defaults.toml")


@dataclass
class AppSection:
    data_dir: str = ""
    log_level: str = "INFO"
    assistant_name: str = "N.E.K.O."
    user_name: str = ""
    personality: str = ""
    verbosity: str = "balanced"
    language: str = "en"
    reply_language: str = ""            # "" = same as the user | "bn" = always Bangla | "en" = always English
    location: str = ""                 # city for weather; empty = estimate from your IP address


@dataclass
class PrivacySection:
    allow_network: bool = False
    allow_cloud_models: bool = False
    store_conversations: bool = True
    learning_enabled: bool = True
    message_retention_days: int = 90
    temporary_memory_hours: int = 24
    log_message_content: bool = False


@dataclass
class ModelsSection:
    cloud_brain: str = "auto"           # auto = use free Groq/Gemini when you added a key; off = local only
    office_url: str = ""                # "auto" = the office PC's GPU over Tailscale when it's online; "" = off
    runtime: str = "ollama"
    ollama_url: str = "http://127.0.0.1:11434"
    profile: str = "laptop-lite"
    keep_alive: str = "5m"
    max_loaded_models: int = 1
    request_timeout_s: float = 180
    num_ctx: int = 4096
    allow_model_downloads: bool = False


@dataclass
class ResourcesSection:
    ram_safety_margin_mb: int = 2048
    vram_safety_margin_mb: int = 400
    disk_min_free_gb: float = 10
    pause_background_on_battery_below: int = 35
    poll_interval_s: float = 5
    gpu_temp_soft_limit_c: int = 85


@dataclass
class StorageSection:
    model_budget_gb: float = 25
    backup_keep: int = 10
    log_max_mb: int = 20


@dataclass
class VoiceSection:
    enabled: bool = False
    input_device: str = ""
    stt_engine: str = "faster-whisper"
    stt_model: str = "small"
    stt_device: str = "auto"
    stt_compute_type: str = "int8"
    stt_model_dir: str = ""            # where downloaded speech models live ("" = Hugging Face cache)
    stt_language: str = "en"
    tts_engine: str = "kokoro"
    gender: str = "female"            # female | male - her voice (both the online and the offline one)
    barge_in: bool = True              # say "Neko, stop" (or a new request) while she talks to interrupt her
    edge_voice_en: str = ""            # override the online English voice ("" = Ava / Andrew by gender)
    edge_voice_bn: str = ""            # override the online Bangla voice ("" = Nabanita / Pradeep)
    kokoro_voice: str = "af_heart"
    kokoro_voice_male: str = "am_michael"
    kokoro_speed: float = 0.92
    kokoro_dir: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_key_env: str = "ELEVENLABS_API_KEY"
    piper_exe: str = ""
    piper_voice: str = ""
    tts_rate: float = 1.0
    tts_volume: float = 0.9
    push_to_talk_hotkey: str = "Ctrl+Space"
    always_listen: bool = False        # continuous listening; responds when you say her name
    wake_names: list[str] = field(default_factory=lambda: ["neko", "nico", "niko", "neeko", "necko", "nekko"])
    follow_up_seconds: float = 8.0     # after she answers, keep talking without the name for this long
    pause_seconds: float = 1.6         # silence that ends what you're saying
    addressed_pause_seconds: float = 2.5  # ... while you're talking to her (room to think mid-sentence)
    wait_rest_seconds: float = 6.0     # an unfinished-sounding sentence waits this long for the rest
    max_speech_seconds: float = 60.0   # longest single request
    vocabulary: list[str] = field(default_factory=list)  # names/words you say (spelling hint for speech recognition)
    expressive: bool = True            # female persona with emotion tags + natural interjections
    wakeword_enabled: bool = False
    wakeword_model: str = "hey_jarvis"
    wakeword_threshold: float = 0.6
    keep_recordings: bool = False


@dataclass
class VisionSection:
    enabled: bool = True
    max_image_side: int = 1344
    retain_screenshots: bool = False
    auto_screen_context: bool = True   # "what's wrong with this?" -> she looks at the screen herself


@dataclass
class UISection:
    music_autoplay: bool = True        # when a song ends, play YouTube's next one ("stop the music" ends it)
    theme: str = "aurum"
    style: str = "orb"                 # orb (just the holographic orb) | panel (orb + text panel)
    reduced_motion: bool = False
    always_on_top: bool = True
    hud_opacity: float = 0.94
    idle_hide_seconds: int = 240  # orb dissolves after this long idle (0 = never)
    music_volume: float = 0.6       # background music volume 0..1 ("louder" / "quieter" change it)
    visual_panel_seconds: int = 90  # the "show me" panel closes itself after this (0 = stays open)
    start_compact: bool = True
    emergency_stop_hotkey: str = "Ctrl+Shift+F12"


@dataclass
class ToolsSection:
    computer_control_enabled: bool = False
    allowed_roots: list[str] = field(default_factory=list)
    writable_roots: list[str] = field(default_factory=list)
    approved_scripts_dir: str = ""
    max_read_bytes: int = 200_000
    claude_code: bool = True           # hand coding/project tasks to Claude Code if installed + cloud allowed
    cloud_documents: bool = False      # let Claude Code read your documents for study notes (sends them to Anthropic)
    study_folder: str = ""            # where study notes/cheat sheets go ("" = first writable folder\\Study)
    allowed_apps: dict[str, str] = field(default_factory=dict)
    programs_root: str = ""            # your own programs ("" = D:\PROJECT, or C:\PROJECT with one drive)


@dataclass
class PhoneSection:
    # Chat with her from Telegram (text, voice notes, photos, files). Needs privacy.allow_network and a bot
    # key in secrets.toml; only the paired owner's chat is ever answered.
    telegram: bool = False
    # Live call page, reachable only through Tailscale (scripts/phone-call.ps1 shares it inside the tailnet).
    calls: bool = False
    call_port: int = 8791              # local only (127.0.0.1); Tailscale serves it as https on call_https_port
    call_https_port: int = 8443
    voice_replies: str = "auto"        # auto = a voice note back when you sent one; always; never
    notify_long_jobs: bool = True      # "done: ..." on the phone when a long PC job finishes
    notify_battery: bool = True        # "battery at 15%" on the phone
    # Only the owner's phone can approve: the PC's own approval window can deny but not approve (e.g. the office
    # PC, where someone else sits at the screen). Needs a paired, connected owner phone; otherwise the PC approves.
    owner_approves_all: bool = False
    link_server: bool = False          # let your other PC's Neko use this one (phone/link.py)
    link_url: str = ""                 # the other PC to use (from its link code; the key is in secrets.toml)


@dataclass
class RemoteEndpoint:
    name: str
    url: str
    token_env: str = ""
    allow_sensitive: bool = False


@dataclass
class RemoteSection:
    enabled: bool = False
    endpoints: list[RemoteEndpoint] = field(default_factory=list)


@dataclass
class Settings:
    config_version: int = CONFIG_VERSION
    app: AppSection = field(default_factory=AppSection)
    privacy: PrivacySection = field(default_factory=PrivacySection)
    models: ModelsSection = field(default_factory=ModelsSection)
    resources: ResourcesSection = field(default_factory=ResourcesSection)
    storage: StorageSection = field(default_factory=StorageSection)
    voice: VoiceSection = field(default_factory=VoiceSection)
    vision: VisionSection = field(default_factory=VisionSection)
    ui: UISection = field(default_factory=UISection)
    tools: ToolsSection = field(default_factory=ToolsSection)
    remote: RemoteSection = field(default_factory=RemoteSection)
    phone: PhoneSection = field(default_factory=PhoneSection)
    source_files: list[str] = field(default_factory=list)

    # ---- derived paths (all outside the source repository) ----
    @property
    def data_dir(self) -> Path:
        if self.app.data_dir:
            return Path(os.path.expandvars(self.app.data_dir)).expanduser()
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "NEKO"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "neko.db"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.log_dir, self.backup_dir, self.cache_dir):
            p.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------------
# loading / merging / validation
# ----------------------------------------------------------------------------

def default_user_config_path() -> Path:
    env = os.environ.get("NEKO_CONFIG")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "NEKO" / "config.toml"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        # utf-8-sig: tolerate the byte-order mark that Notepad / PowerShell 5.1 add when saving
        return tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}", user_message=f"Config file {path} is not valid TOML: {exc}") from exc


def _coerce(section_cls: type, data: dict[str, Any], where: str) -> Any:
    known = {f.name: f for f in fields(section_cls)}
    unknown = set(data) - set(known)
    if unknown:
        raise ConfigError(f"Unknown setting(s) in [{where}]: {', '.join(sorted(unknown))}")
    kwargs: dict[str, Any] = {}
    defaults = section_cls()
    for name, value in data.items():
        expected = getattr(defaults, name)
        if isinstance(expected, bool):
            if not isinstance(value, bool):
                raise ConfigError(f"[{where}] {name} must be true or false, got {value!r}")
        elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ConfigError(f"[{where}] {name} must be a number, got {value!r}")
            value = type(expected)(value) if isinstance(expected, float) else value
        elif isinstance(expected, str):
            if not isinstance(value, str):
                raise ConfigError(f"[{where}] {name} must be text, got {value!r}")
        elif isinstance(expected, list):
            if not isinstance(value, list):
                raise ConfigError(f"[{where}] {name} must be a list")
        elif isinstance(expected, dict):
            if not isinstance(value, dict):
                raise ConfigError(f"[{where}] {name} must be a table")
        kwargs[name] = value
    return section_cls(**kwargs)


def settings_from_dict(raw: dict[str, Any]) -> Settings:
    raw = dict(raw)
    version = raw.pop("config_version", CONFIG_VERSION)
    if version != CONFIG_VERSION:
        raise ConfigError(
            f"config_version {version} is not supported (expected {CONFIG_VERSION}). "
            "See docs/BACKUP_AND_RECOVERY.md 'Configuration migration'."
        )
    s = Settings()
    simple = {
        "app": AppSection, "privacy": PrivacySection, "models": ModelsSection,
        "resources": ResourcesSection, "storage": StorageSection, "voice": VoiceSection,
        "vision": VisionSection, "ui": UISection, "tools": ToolsSection, "phone": PhoneSection,
    }
    for key, value in raw.items():
        if key in simple:
            if not isinstance(value, dict):
                raise ConfigError(f"[{key}] must be a table")
            setattr(s, key, _coerce(simple[key], value, key))
        elif key == "remote":
            endpoints = [RemoteEndpoint(**e) for e in value.get("endpoints", [])]
            s.remote = RemoteSection(enabled=bool(value.get("enabled", False)), endpoints=endpoints)
        else:
            raise ConfigError(f"Unknown config section [{key}]")
    validate(s)
    return s


_PRIVATE_PREFIXES = ("127.", "10.", "192.168.", "169.254.")


def _is_private_host(host: str) -> bool:
    if host in ("localhost", "::1"):
        return True
    if host.startswith(_PRIVATE_PREFIXES):
        return True
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
            return 16 <= second <= 31
        except (IndexError, ValueError):
            return False
    return False


def validate(s: Settings) -> None:
    problems: list[str] = []
    if s.app.verbosity not in ("brief", "balanced", "detailed"):
        problems.append("app.verbosity must be brief, balanced or detailed")
    if s.app.log_level.upper() not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        problems.append("app.log_level must be DEBUG, INFO, WARNING or ERROR")
    if s.phone.voice_replies not in ("auto", "always", "never"):
        problems.append("phone.voice_replies must be auto, always or never")
    if not (1024 <= s.phone.call_port <= 65535) or not (1 <= s.phone.call_https_port <= 65535):
        problems.append("phone.call_port / call_https_port must be valid port numbers")
    url = urlparse(s.models.ollama_url)
    if url.scheme not in ("http", "https") or not url.hostname:
        problems.append("models.ollama_url must look like http://127.0.0.1:11434")
    elif not _is_private_host(url.hostname):
        problems.append("models.ollama_url must point to this computer or your private network")
    if s.models.max_loaded_models < 1:
        problems.append("models.max_loaded_models must be at least 1")
    if not 512 <= s.models.num_ctx <= 131072:
        problems.append("models.num_ctx must be between 512 and 131072")
    if s.voice.tts_engine not in ("edge", "kokoro", "sapi", "piper", "elevenlabs", "none"):
        problems.append("voice.tts_engine must be edge, kokoro, sapi, piper, elevenlabs or none")
    if s.models.office_url not in ("", "auto"):
        from ..models.office import is_tailnet_or_private

        if not is_tailnet_or_private(s.models.office_url):
            problems.append("models.office_url must be \"auto\" or an address inside Tailscale / your private network")
    if s.voice.gender not in ("female", "male"):
        problems.append("voice.gender must be female or male")
    if not 0.5 <= s.voice.kokoro_speed <= 2.0:
        problems.append("voice.kokoro_speed must be between 0.5 and 2.0")
    if s.voice.stt_device not in ("auto", "cpu", "cuda"):
        problems.append("voice.stt_device must be auto, cpu or cuda")
    if not 0.0 < s.voice.wakeword_threshold < 1.0:
        problems.append("voice.wakeword_threshold must be between 0 and 1")
    if s.ui.theme not in ("aurum", "nebula"):
        problems.append("ui.theme must be aurum or nebula")
    if s.ui.style not in ("orb", "panel"):
        problems.append("ui.style must be orb or panel")
    if not 0.3 <= s.ui.hud_opacity <= 1.0:
        problems.append("ui.hud_opacity must be between 0.3 and 1.0")
    if s.resources.ram_safety_margin_mb < 512:
        problems.append("resources.ram_safety_margin_mb below 512 risks Windows instability")
    for ep in s.remote.endpoints:
        host = urlparse(ep.url).hostname or ""
        if urlparse(ep.url).scheme != "https":
            problems.append(f"remote endpoint {ep.name!r} must use https")
        if not _is_private_host(host):
            problems.append(f"remote endpoint {ep.name!r} must be a private LAN address")
    if problems:
        raise ConfigError("; ".join(problems), user_message="Configuration problems:\n- " + "\n- ".join(problems))


def load_settings(user_path: Path | None = None, *, extra: dict[str, Any] | None = None) -> Settings:
    merged = _read_toml(_DEFAULTS_PATH)
    sources = [str(_DEFAULTS_PATH)]
    path = user_path or default_user_config_path()
    if path.exists():
        merged = _deep_merge(merged, _read_toml(path))
        sources.append(str(path))
    if os.environ.get("NEKO_OLLAMA_URL"):
        merged = _deep_merge(merged, {"models": {"ollama_url": os.environ["NEKO_OLLAMA_URL"]}})
    if os.environ.get("NEKO_DATA_DIR"):
        merged = _deep_merge(merged, {"app": {"data_dir": os.environ["NEKO_DATA_DIR"]}})
    if extra:
        merged = _deep_merge(merged, extra)
    s = settings_from_dict(merged)
    s.source_files = sources
    return s


# ----------------------------------------------------------------------------
# minimal TOML writer for user overrides (flat tables of simple values)
# ----------------------------------------------------------------------------

def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    raise TypeError(f"cannot serialise {type(v).__name__} to TOML")


def dump_overrides(overrides: dict[str, dict[str, Any]]) -> str:
    """Serialise ``{"section": {"key": value}}`` to TOML text."""
    lines = [f"config_version = {CONFIG_VERSION}", ""]
    for section, values in overrides.items():
        nested = {k: v for k, v in values.items() if isinstance(v, dict)}
        tables = {k: v for k, v in values.items()
                  if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)}
        flat = {k: v for k, v in values.items() if k not in nested and k not in tables}
        lines.append(f"[{section}]")
        lines += [f"{k} = {_toml_value(v)}" for k, v in flat.items()]
        lines.append("")
        for sub, subvals in nested.items():
            lines.append(f"[{section}.{sub}]")
            lines += [f'"{k}" = {_toml_value(v)}' for k, v in subvals.items()]
            lines.append("")
        for sub, items in tables.items():
            for item in items:
                lines.append(f"[[{section}.{sub}]]")
                lines += [f"{k} = {_toml_value(v)}" for k, v in item.items()]
                lines.append("")
    return "\n".join(lines)


def save_user_overrides(overrides: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    path = path or default_user_config_path()
    text = dump_overrides(overrides)
    settings_from_dict(_deep_merge(_read_toml(_DEFAULTS_PATH), tomllib.loads(text)))  # validate first
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    if path.exists():
        path.replace(path.with_suffix(".toml.bak"))
    tmp.replace(path)
    return path


def as_dict(obj: Any) -> Any:
    if is_dataclass(obj):
        return {f.name: as_dict(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, list):
        return [as_dict(x) for x in obj]
    return obj


def update_user_setting(section: str, key: str, value: Any, path: Path | None = None) -> Path:
    """Change ONE setting in the user's config file, keeping everything else (used by voice commands like
    "use a male voice"). Validated before writing; the old file is kept as config.toml.bak."""
    path = path or default_user_config_path()
    existing = _read_toml(path) if path.exists() else {}
    existing.pop("config_version", None)
    merged: dict[str, dict[str, Any]] = {k: dict(v) for k, v in existing.items() if isinstance(v, dict)}
    merged.setdefault(section, {})[key] = value
    return save_user_overrides(merged, path)
