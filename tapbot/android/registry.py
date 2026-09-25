"""Per-device Android Agent configuration and runtime registry."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from threading import RLock

from tapbot.android.client import AndroidAgentClient
from tapbot.device.android import AndroidRemoteController
from tapbot.screen.android import AndroidRemoteScreenSource
from tapbot.ui.android_debug import AndroidDebugService
from tapbot.ui.services import EventLog
from tapbot.ui_resolution.accessibility import AndroidAccessibilityUiTreeProvider
from tapbot.vision.detector import Detector


_DEVICE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class AndroidDeviceConfig:
    id: str
    name: str
    base_url: str
    token: str
    enabled: bool = True

    def __post_init__(self) -> None:
        if not _DEVICE_ID.fullmatch(self.id):
            raise ValueError(
                "Android device id must start with a lowercase letter or digit and "
                "contain only lowercase letters, digits, '-' or '_'"
            )
        if not self.name.strip():
            raise ValueError(f"Android device {self.id!r} has an empty name")
        if not self.base_url.strip():
            raise ValueError(f"Android device {self.id!r} has an empty base_url")
        if not self.token.strip():
            raise ValueError(f"Android device {self.id!r} has an empty token")


@dataclass(frozen=True, slots=True)
class AndroidDeviceContext:
    config: AndroidDeviceConfig
    client: AndroidAgentClient
    source: AndroidRemoteScreenSource
    controller: AndroidRemoteController
    debug_service: AndroidDebugService
    ui_tree_provider: AndroidAccessibilityUiTreeProvider


class AndroidDeviceRegistry:
    """Own one completely separate Android debug stack per configured device."""

    def __init__(
        self,
        detectors: Iterable[Detector],
        event_log: EventLog,
        *,
        capture_dir: str | Path = "tapbot-captures/android",
        default_device_id: str | None = None,
        client_factory: Callable[[str, str], AndroidAgentClient] = AndroidAgentClient,
    ) -> None:
        self._detectors = tuple(detectors)
        self._event_log = event_log
        self._capture_dir = Path(capture_dir)
        self._client_factory = client_factory
        self._contexts: dict[str, AndroidDeviceContext] = {}
        self._health: dict[str, dict[str, object]] = {}
        self._lock = RLock()
        self._configured_default = default_device_id

    @property
    def default_device_id(self) -> str | None:
        with self._lock:
            if self._configured_default in self._contexts:
                return self._configured_default
            if len(self._contexts) == 1:
                return next(iter(self._contexts))
            return None

    @property
    def event_log(self) -> EventLog:
        return self._event_log

    def register(
        self,
        config: AndroidDeviceConfig,
        *,
        client: AndroidAgentClient | None = None,
        debug_service: AndroidDebugService | None = None,
    ) -> AndroidDeviceContext | None:
        with self._lock:
            if config.id in self._contexts:
                raise ValueError(f"Duplicate Android device id: {config.id}")
            if not config.enabled:
                return None
        device_client = client or self._client_factory(config.base_url, config.token)
        service = debug_service or AndroidDebugService(
            device_client,
            self._detectors,
            self._event_log,
            device_id=config.id,
            device_name=config.name,
            capture_dir=self._capture_dir / config.id,
        )
        context = AndroidDeviceContext(
            config=config,
            client=device_client,
            source=service.source,
            controller=service.controller,
            debug_service=service,
            ui_tree_provider=service.ui_tree_provider,
        )
        with self._lock:
            if config.id in self._contexts:
                raise ValueError(f"Duplicate Android device id: {config.id}")
            self._contexts[config.id] = context
            self._health[config.id] = self._offline_summary(context, error=None)
        return context

    def unregister(self, device_id: str) -> AndroidDeviceContext:
        with self._lock:
            try:
                context = self._contexts.pop(device_id)
            except KeyError as error:
                raise KeyError(device_id) from error
            self._health.pop(device_id, None)
        context.debug_service.close()
        return context

    def get(self, device_id: str) -> AndroidDeviceContext:
        with self._lock:
            try:
                return self._contexts[device_id]
            except KeyError as error:
                raise KeyError(device_id) from error

    def list(self) -> tuple[AndroidDeviceContext, ...]:
        with self._lock:
            return tuple(self._contexts.values())

    def refresh(self, device_id: str) -> dict[str, object]:
        context = self.get(device_id)
        with self._lock:
            was_connected = bool(self._health.get(device_id, {}).get("connected"))
        try:
            status = context.debug_service.status()
            summary = self._summary_from_status(context, status)
        except Exception as error:
            summary = self._offline_summary(context, error=str(error))
        with self._lock:
            if device_id in self._contexts:
                self._health[device_id] = summary
        is_connected = bool(summary["connected"])
        if is_connected != was_connected:
            state = "connected" if is_connected else "disconnected"
            self._event_log.add(
                f"Android device {state}: {context.config.name}",
                event_type=f"android.device.{state}",
                category="android",
                status="success" if is_connected else "warning",
                payload={"device_id": device_id},
            )
        return dict(summary)

    def refresh_all(self) -> list[dict[str, object]]:
        contexts = self.list()
        if contexts:
            with ThreadPoolExecutor(
                max_workers=len(contexts),
                thread_name_prefix="android-health",
            ) as pool:
                futures = {
                    pool.submit(self.refresh, context.config.id): context.config.id
                    for context in contexts
                }
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception:
                        # refresh() contains errors per device; this is a final guard so
                        # one broken context can never abort the remaining refreshes.
                        pass
        return self.summaries()

    def summaries(self) -> list[dict[str, object]]:
        with self._lock:
            return [dict(self._health[device_id]) for device_id in self._contexts]

    @classmethod
    def from_config_file(
        cls,
        path: str | Path,
        detectors: Iterable[Detector],
        event_log: EventLog,
        *,
        capture_dir: str | Path = "tapbot-captures/android",
        client_factory: Callable[[str, str], AndroidAgentClient] = AndroidAgentClient,
    ) -> "AndroidDeviceRegistry":
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(document, dict) or not isinstance(document.get("devices"), list):
            raise ValueError("Android devices config must contain a devices array")
        raw_default = document.get("default_device_id")
        if raw_default is not None and not isinstance(raw_default, str):
            raise ValueError("default_device_id must be a string")
        registry = cls(
            detectors,
            event_log,
            capture_dir=capture_dir,
            default_device_id=raw_default,
            client_factory=client_factory,
        )
        seen: set[str] = set()
        enabled_ids: set[str] = set()
        for raw in document["devices"]:
            if not isinstance(raw, dict):
                raise ValueError("Each Android device config must be an object")
            device_id = _required(raw, "id")
            if device_id in seen:
                raise ValueError(f"Duplicate Android device id: {device_id}")
            seen.add(device_id)
            enabled = _boolean(raw.get("enabled", True), device_id)
            token = _device_token_override(device_id)
            if not token:
                raw_token = raw.get("token")
                if isinstance(raw_token, str) and raw_token.strip():
                    token = raw_token.strip()
                elif enabled:
                    raise ValueError(
                        "Android device config field 'token' must be a non-empty string"
                    )
                else:
                    token = "disabled"
            config = AndroidDeviceConfig(
                id=device_id,
                name=_required(raw, "name"),
                base_url=_required(raw, "base_url"),
                token=token,
                enabled=enabled,
            )
            if config.enabled:
                enabled_ids.add(config.id)
                registry.register(config)
        if raw_default is not None and raw_default not in enabled_ids:
            raise ValueError("default_device_id must reference an enabled device")
        return registry

    def _summary_from_status(
        self,
        context: AndroidDeviceContext,
        status: dict[str, object],
    ) -> dict[str, object]:
        agent = status.get("agent")
        agent = agent if isinstance(agent, dict) else {}
        stream = status.get("stream")
        stream = stream if isinstance(stream, dict) else {}
        connected = bool(status.get("connected"))
        with self._lock:
            previous = self._health.get(context.config.id, {})
        return {
            "id": context.config.id,
            "name": context.config.name,
            "connected": connected,
            "last_seen_at": (
                _now() if connected else previous.get("last_seen_at")
            ),
            "capture_ready": bool(agent.get("capture_ready")),
            "stream_running": bool(stream.get("running", agent.get("stream_running"))),
            "accessibility_enabled": bool(agent.get("accessibility_enabled")),
            "remote_control_enabled": bool(agent.get("remote_control_enabled")),
            "macro_status": context.debug_service.macro_status,
            "last_error": status.get("error"),
        }

    def _offline_summary(
        self,
        context: AndroidDeviceContext,
        *,
        error: str | None,
    ) -> dict[str, object]:
        with self._lock:
            previous = self._health.get(context.config.id, {})
        return {
            "id": context.config.id,
            "name": context.config.name,
            "connected": False,
            "last_seen_at": previous.get("last_seen_at"),
            "capture_ready": False,
            "stream_running": False,
            "accessibility_enabled": False,
            "remote_control_enabled": False,
            "macro_status": context.debug_service.macro_status,
            "last_error": error,
        }


def registry_from_environment(
    detectors: Iterable[Detector],
    event_log: EventLog,
    *,
    capture_dir: str | Path = "tapbot-captures/android",
) -> AndroidDeviceRegistry:
    config_path = os.getenv("TAPBOT_ANDROID_DEVICES_CONFIG", "").strip()
    if config_path:
        return AndroidDeviceRegistry.from_config_file(
            config_path,
            detectors,
            event_log,
            capture_dir=capture_dir,
        )
    registry = AndroidDeviceRegistry(detectors, event_log, capture_dir=capture_dir)
    url = os.getenv("TAPBOT_ANDROID_AGENT_URL", "").strip()
    token = os.getenv("TAPBOT_ANDROID_AGENT_TOKEN", "").strip()
    if url and token:
        registry.register(
            AndroidDeviceConfig("default", "Android Device", url, token)
        )
    return registry


def _required(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"Android device config field {key!r} must be a non-empty string")
    return item.strip()


def _boolean(value: object, device_id: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"Android device {device_id!r} enabled must be a boolean")
    return value


def _device_token_override(device_id: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]", "_", device_id).upper()
    return os.getenv(f"TAPBOT_ANDROID_DEVICE_{suffix}_TOKEN", "").strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
