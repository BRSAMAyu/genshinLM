from __future__ import annotations

from typing import TYPE_CHECKING

from app_service.apps.hsr_app import HSRApp

if TYPE_CHECKING:
    from capsules.capsule_protocol import CapsuleContext


class HSRCapsule:
    """Honkai: Star Rail capability package adhering to the Capsule Protocol."""

    capsule_id: str = "hsr"

    def __init__(self) -> None:
        self._app = HSRApp()

    def install(self, context: CapsuleContext) -> None:
        self._app.install(context)

    def activate(self) -> None:
        self._app.activate()

    def deactivate(self) -> None:
        self._app.deactivate()

    @property
    def is_active(self) -> bool:
        return self._app.is_active

    def uninstall(self, context: CapsuleContext) -> None:
        self._app.deactivate()
