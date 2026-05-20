from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from capsules.capsule_protocol import CapsuleContext


class DesktopUiCapsule:
    """Desktop UI automation capsule implementing the Capsule protocol."""

    capsule_id: str = "desktop_ui"

    def __init__(self) -> None:
        self._active: bool = False
        self._grounded_slot: object | None = None
        self._safety_slot: object | None = None
        self._subscription_ids: list[str] = []

    def install(self, context: CapsuleContext) -> None:
        """Register slots and skills for desktop UI automation."""
        self._grounded_slot = context.state_bus.register_slot("desktop_ui.grounded_elements")
        self._safety_slot = context.state_bus.register_slot("desktop_ui.safety_state")

        from capsules.desktop_ui.skills.ui_grounding_skill import UiGroundingSkill

        if hasattr(context.orchestrator, "register_skill"):
            context.orchestrator.register_skill("desktop_ui_grounding", UiGroundingSkill())

    def activate(self) -> None:
        """Start the capsule."""
        self._active = True

    def deactivate(self) -> None:
        """Stop the capsule."""
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    def uninstall(self, context: CapsuleContext) -> None:
        """Clean up: unsubscribe all tracked subscriptions."""
        for sub_id in self._subscription_ids:
            context.state_bus.unsubscribe(sub_id)
        self._subscription_ids.clear()
