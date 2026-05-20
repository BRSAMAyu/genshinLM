from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Protocol

from control.controller_loop import ControllerLoop
from core.state_bus import StateBus
from orchestration.orchestrator import Orchestrator
from perception.pipeline import FramePostProcessor, PerceptionPipeline


class App(Protocol):
    app_id: str

    def install(self, context: AppContext) -> None: ...

    def activate(self) -> None: ...

    def deactivate(self) -> None: ...


@dataclass(slots=True)
class AppContext:
    state_bus: StateBus
    pipeline: PerceptionPipeline
    controller_loop: ControllerLoop
    orchestrator: Orchestrator
    root_dir: str = ""


class AppRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._apps: dict[str, App] = {}
        self._active: set[str] = set()

    def register_app(self, app: App, context: AppContext) -> None:
        with self._lock:
            if app.app_id in self._apps:
                return
            app.install(context)
            self._apps[app.app_id] = app

    def activate(self, app_id: str) -> bool:
        with self._lock:
            app = self._apps.get(app_id)
            if app is None:
                return False
            app.activate()
            self._active.add(app_id)
            return True

    def deactivate(self, app_id: str) -> bool:
        with self._lock:
            app = self._apps.get(app_id)
            if app is None:
                return False
            app.deactivate()
            self._active.discard(app_id)
            return True

    def unregister_app(self, app_id: str) -> bool:
        with self._lock:
            app = self._apps.pop(app_id, None)
            if app is None:
                return False
            if app_id in self._active:
                app.deactivate()
                self._active.discard(app_id)
            return True

    def get_app(self, app_id: str) -> App | None:
        with self._lock:
            return self._apps.get(app_id)

    def list_apps(self) -> list[str]:
        with self._lock:
            return list(self._apps.keys())

    def list_active(self) -> list[str]:
        with self._lock:
            return list(self._active)
