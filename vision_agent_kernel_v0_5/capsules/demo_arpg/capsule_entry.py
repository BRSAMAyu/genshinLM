from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from capsules.capsule_protocol import CapsuleContext


class DemoArpgCapsule:
    """Demo ARPG capsule implementing the Capsule protocol."""

    capsule_id: str = "demo_arpg"

    def __init__(self) -> None:
        self._active: bool = False
        self._screen_slot: object | None = None
        self._danger_slot: object | None = None
        self._subscription_ids: list[str] = []

    def install(self, context: CapsuleContext) -> None:
        """Register slots and skills for the demo ARPG."""
        self._screen_slot = context.state_bus.register_slot("demo_arpg.screen_state")
        self._danger_slot = context.state_bus.register_slot("demo_arpg.danger_state")

        # Register a simple skill with the orchestrator.
        from capsules.demo_arpg.skills.dummy_skill import DummySkill

        if hasattr(context.orchestrator, "register_skill"):
            context.orchestrator.register_skill("demo_arpg_dummy", DummySkill())

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
