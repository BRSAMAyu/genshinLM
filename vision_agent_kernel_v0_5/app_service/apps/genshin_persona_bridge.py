from __future__ import annotations

from core.events import Interrupt
from core.state_bus import StateBus
from app_service.genshin_persona import GenshinPersona


class GenshinPersonaBridge:
    """Bridges kernel interrupts/events to GenshinPersona."""

    INTERRUPT_TO_EVENT: dict[str, str] = {
        "DODGE_REFLEX": "DANGER_HIT",
        "TARGET_LOST": "TARGET_LOST",
        "NO_TASK_PROGRESS": "OBSTACLE_BLOCKING",
        "EMERGENCY_STOP": "ERROR_OCCURRED",
    }

    def __init__(self, state_bus: StateBus) -> None:
        self._state_bus = state_bus
        self._persona = GenshinPersona()
        self._response_slot = state_bus.register_slot("genshin.persona_response")

    def on_interrupt(self, interrupt: Interrupt) -> None:
        """Convert an interrupt to a persona event and publish the response."""
        event = self.INTERRUPT_TO_EVENT.get(interrupt.code)
        if event is None:
            return

        response = self._persona.on_event(event, context={"priority": interrupt.priority})
        if response is None:
            return

        self._response_slot.put({
            "text": response.text,
            "emotion": response.emotion,
            "priority": response.priority,
        })
