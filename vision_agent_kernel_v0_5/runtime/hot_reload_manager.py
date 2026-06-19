"""HotReloadManager: runtime module replacement without restart.

Watches a set of module file paths and reloads them when changed.
Used for rapid iteration on game capsules, skills, and detectors
without stopping the agent loop.

Phase 2 roadmap: enables fast development cycle for game-specific adapters.
"""
from __future__ import annotations

import importlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReloadEvent:
    module_name: str
    file_path: str
    timestamp: float
    success: bool
    error: str = ""


@dataclass(slots=True)
class HotReloadConfig:
    watch_interval_sec: float = 2.0
    max_history: int = 100
    enabled: bool = True


class HotReloadManager:
    """Watch and reload Python modules when their files change."""

    def __init__(self, config: HotReloadConfig | None = None) -> None:
        self._config = config or HotReloadConfig()
        self._watched: dict[str, float] = {}  # module_name → last_mtime
        self._module_paths: dict[str, str] = {}  # module_name → file_path
        self._history: list[ReloadEvent] = []
        self._last_check: float = 0.0

    def watch(self, module_name: str) -> None:
        """Register a module for hot-reload watching."""
        spec = importlib.util.find_spec(module_name)
        if spec is None or spec.origin is None:
            log.warning("[HotReload] Module %r not found", module_name)
            return
        file_path = spec.origin
        if not file_path.endswith(".py"):
            return
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            return
        self._watched[module_name] = mtime
        self._module_paths[module_name] = file_path
        log.debug("[HotReload] Watching %s → %s", module_name, file_path)

    def unwatch(self, module_name: str) -> None:
        self._watched.pop(module_name, None)
        self._module_paths.pop(module_name, None)

    def tick(self) -> list[ReloadEvent]:
        """Check watched modules and reload any that changed.

        Should be called periodically (e.g., every 2s from the agent loop).
        Returns list of reload events this tick.
        """
        if not self._config.enabled:
            return []
        now = time.perf_counter()
        if now - self._last_check < self._config.watch_interval_sec:
            return []
        self._last_check = now

        events: list[ReloadEvent] = []
        for module_name, last_mtime in list(self._watched.items()):
            file_path = self._module_paths.get(module_name, "")
            try:
                current_mtime = os.path.getmtime(file_path)
            except OSError:
                continue
            if current_mtime > last_mtime:
                event = self._reload_module(module_name, file_path, current_mtime)
                events.append(event)
                self._watched[module_name] = current_mtime

        return events

    def _reload_module(self, module_name: str, file_path: str, mtime: float) -> ReloadEvent:
        """Reload a single module."""
        try:
            import sys
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
            else:
                importlib.import_module(module_name)
            event = ReloadEvent(
                module_name=module_name,
                file_path=file_path,
                timestamp=time.perf_counter(),
                success=True,
            )
            log.info("[HotReload] Reloaded %s", module_name)
        except Exception as exc:
            event = ReloadEvent(
                module_name=module_name,
                file_path=file_path,
                timestamp=time.perf_counter(),
                success=False,
                error=str(exc),
            )
            log.warning("[HotReload] Failed to reload %s: %s", module_name, exc)

        self._history.append(event)
        if len(self._history) > self._config.max_history:
            self._history = self._history[-self._config.max_history:]
        return event

    @property
    def watched_modules(self) -> tuple[str, ...]:
        return tuple(self._watched.keys())

    @property
    def history(self) -> tuple[ReloadEvent, ...]:
        return tuple(self._history)

    def reload_all(self) -> list[ReloadEvent]:
        """Force-reload all watched modules regardless of mtime."""
        events: list[ReloadEvent] = []
        for module_name in list(self._watched.keys()):
            file_path = self._module_paths.get(module_name, "")
            mtime = self._watched.get(module_name, 0.0)
            event = self._reload_module(module_name, file_path, mtime)
            events.append(event)
        return events
