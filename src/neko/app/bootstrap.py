"""Composition root: builds every service once and wires them together.

Nothing here starts a model, a microphone, a camera or a network listener.
Those start only when the user acts (sends a message, holds push-to-talk,
enables the wake word, presses capture).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import __version__
from ..configuration.settings import Settings, load_settings
from ..core.cancel import EmergencyStop
from ..core.events import EventBus
from ..database.db import Database
from ..diagnostics.logging_setup import configure_logging
from ..memory.conversations import ConversationStore
from ..memory.store import MemoryStore
from ..models.base import ModelProvider
from ..models.ollama import OllamaProvider
from ..models.openai_compat import OpenAICompatProvider
from ..models.profiles import get_profile
from ..models.router import ModelLifecycle, ModelRouter
from ..orchestration.coordinator import Coordinator
from ..orchestration.tasks import TaskManager
from ..resources.monitor import ResourceMonitor
from ..security.paths import PathPolicy
from ..security.policy import PermissionPolicy
from ..tools.base import ToolExecutor, ToolRegistry
from ..tools.builtin import register_builtin_tools

log = logging.getLogger("neko")


@dataclass
class Neko:
    settings: Settings
    bus: EventBus
    estop: EmergencyStop
    db: Database
    memory: MemoryStore
    conversations: ConversationStore
    tasks: TaskManager
    monitor: ResourceMonitor
    providers: list[ModelProvider]
    router: ModelRouter
    lifecycle: ModelLifecycle
    policy: PermissionPolicy
    tools: ToolRegistry
    executor: ToolExecutor
    paths: PathPolicy
    coordinator: Coordinator
    log_path: Path
    routines: Any = None               # reminders + learned skills (routines/)

    def maintenance(self) -> dict[str, int]:
        """Cheap housekeeping, safe to run at startup."""
        return {
            "expired_memories": self.memory.expire(),
            "purged_memories": self.memory.purge_expired(),
            "old_messages_removed": self.conversations.apply_retention(self.settings.privacy.message_retention_days),
        }

    def shutdown(self) -> None:
        self.estop.trip()
        self.executor.shutdown()
        self.db.close()


def build(settings: Settings | None = None, *, db_path: str | None = None, console_log: bool = False,
          providers: list[Any] | None = None) -> Neko:
    s = settings or load_settings()
    s.ensure_dirs()
    log_path = configure_logging(s.log_dir, s.app.log_level, s.storage.log_max_mb, console=console_log)
    log.info("N.E.K.O. %s starting; config from %s", __version__, s.source_files)

    db = Database(db_path or s.db_path, backup_dir=s.backup_dir)
    applied = db.migrate()
    if applied:
        log.info("applied schema migrations %s", applied)

    bus = EventBus()
    estop = EmergencyStop()
    memory = MemoryStore(db)
    conversations = ConversationStore(db, store_messages=s.privacy.store_conversations)
    tasks = TaskManager(db, memory)
    monitor = ResourceMonitor(disk_path=str(s.data_dir.anchor or s.data_dir))

    if providers is None:
        providers = [OllamaProvider(s.models.ollama_url, default_timeout_s=float(s.models.request_timeout_s))]
        if s.remote.enabled:
            for ep in s.remote.endpoints:
                providers.append(OpenAICompatProvider(ep.name, ep.url, token_env=ep.token_env))
        if s.models.office_url:
            from ..models.office import OfficeProvider

            providers.append(OfficeProvider(s.models.office_url))  # the office PC's GPU over Tailscale
        if s.privacy.allow_cloud_models and s.models.cloud_brain != "off":
            from ..models.cloud import cloud_providers

            providers.extend(cloud_providers(s.data_dir))  # Groq + Gemini, only used once you add a free key
    router = ModelRouter(
        providers, get_profile(s.models.profile), db,
        ram_margin_mb=s.resources.ram_safety_margin_mb, vram_margin_mb=s.resources.vram_safety_margin_mb,
        allow_remote=s.remote.enabled or bool(s.models.office_url)
        or (s.privacy.allow_cloud_models and s.models.cloud_brain != "off"),
    )
    router.cloud_first = s.privacy.allow_cloud_models and s.models.cloud_brain != "off"
    lifecycle = ModelLifecycle(max_loaded=s.models.max_loaded_models)
    policy = PermissionPolicy(db, estop, computer_control_enabled=s.tools.computer_control_enabled,
                              network_allowed=s.privacy.allow_network)
    paths = PathPolicy(s.tools.allowed_roots, s.tools.writable_roots,
                       protected=[str(s.data_dir), str(Path(__file__).resolve().parents[3])])
    registry = ToolRegistry()

    def _model_list() -> str:
        return "\n".join(f"{m.name} ({m.parameter_size} {m.quantization}, {(m.size_bytes or 0) / 1e9:.1f} GB)"
                         + (" [loaded]" if m.loaded else "") for m in router.installed()) or "no models found"

    register_builtin_tools(registry, resource_snapshot=monitor.snapshot, model_list=_model_list)
    from ..tools.web import register_web_tools

    register_web_tools(registry)  # denied by policy unless privacy.allow_network = true
    from ..tools.dev import register_dev_tools

    register_dev_tools(registry)  # analyze_project (local) + ask_claude_code (cloud, gated)
    from ..tools.weather import register_weather_tool

    register_weather_tool(registry)
    from ..documents import register_document_tools

    register_document_tools(registry)  # PDF/Word/PowerPoint reading, Explorer selection, PDF notes
    from ..tools.pc import register_pc_tools

    register_pc_tools(registry)  # open apps/sites/files, volume, windows, power (risky ones ask first)
    from ..automation import register_automation_tools

    register_automation_tools(registry)  # buttons/menus/fields inside apps (pywinauto, optional)
    from ..media import register_media_tools

    register_media_tools(registry)  # "play <song>" from YouTube in the background (player = desktop app)
    executor = ToolExecutor(registry, policy, db)
    coordinator = Coordinator(
        settings=s, bus=bus, estop=estop, router=router, lifecycle=lifecycle, monitor=monitor, memory=memory,
        conversations=conversations, tasks=tasks, tools=registry, executor=executor, paths=paths,
    )
    neko = Neko(s, bus, estop, db, memory, conversations, tasks, monitor, providers, router, lifecycle,
                policy, registry, executor, paths, coordinator, log_path)
    from ..routines import attach_routines

    neko.routines = attach_routines(neko)  # reminders + learned skills (the UI starts the reminder clock)
    return neko
