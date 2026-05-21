from __future__ import annotations

from typing import TYPE_CHECKING

from app_service.apps.genshin_app import GenshinApp

if TYPE_CHECKING:
    from capsules.capsule_protocol import CapsuleContext


class GenshinCapsule:
    """Optional Genshin capability package implemented behind the Capsule protocol."""

    capsule_id: str = "genshin"

    def __init__(self) -> None:
        self._app = GenshinApp()

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

