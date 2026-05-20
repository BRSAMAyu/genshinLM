from __future__ import annotations

import time

from core.events import Interrupt
from core.state_bus import StateBus
from app_service.apps.genshin_persona_bridge import GenshinPersonaBridge


def _make_interrupt(code: str, priority: int = 20) -> Interrupt:
    return Interrupt(
        priority=priority,
        timestamp=time.perf_counter(),
        code=code,
        source="test",
    )


class TestPersonaBridgeMapsDodgeInterrupt:
    """DODGE_REFLEX should map to DANGER_HIT and produce a response."""

    def test_maps_dodge_reflex(self) -> None:
        bus = StateBus()
        bridge = GenshinPersonaBridge(bus)
        interrupt = _make_interrupt("DODGE_REFLEX", priority=10)
        bridge.on_interrupt(interrupt)

        slot = bus.get_slot("genshin.persona_response")
        assert slot is not None
        response = slot.get()
        assert response is not None
        assert "text" in response
        assert "emotion" in response
        assert "priority" in response
        assert response["emotion"] == "worried"


class TestPersonaBridgeMapsTargetLost:
    """TARGET_LOST should map to TARGET_LOST event and produce a response."""

    def test_maps_target_lost(self) -> None:
        bus = StateBus()
        bridge = GenshinPersonaBridge(bus)
        interrupt = _make_interrupt("TARGET_LOST", priority=30)
        bridge.on_interrupt(interrupt)

        slot = bus.get_slot("genshin.persona_response")
        assert slot is not None
        response = slot.get()
        assert response is not None
        assert "text" in response
        # TARGET_LOST maps to "worried" or "surprised" variants
        assert response["emotion"] in ("worried", "surprised")


class TestPersonaBridgeIgnoresUnknownInterrupt:
    """Interrupts with unmapped codes should not produce any response."""

    def test_ignores_unknown_code(self) -> None:
        bus = StateBus()
        bridge = GenshinPersonaBridge(bus)
        interrupt = _make_interrupt("SOME_UNKNOWN_CODE", priority=50)
        bridge.on_interrupt(interrupt)

        slot = bus.get_slot("genshin.persona_response")
        assert slot is not None
        response = slot.get()
        assert response is None


class TestPersonaBridgePublishesResponseToSlot:
    """on_interrupt should publish the persona response to the registered slot."""

    def test_publishes_response(self) -> None:
        bus = StateBus()
        bridge = GenshinPersonaBridge(bus)
        # EMERGENCY_STOP -> ERROR_OCCURRED
        interrupt = _make_interrupt("EMERGENCY_STOP", priority=0)
        bridge.on_interrupt(interrupt)

        slot = bus.get_slot("genshin.persona_response")
        assert slot is not None
        response = slot.get()
        assert response is not None
        assert isinstance(response["text"], str)
        assert isinstance(response["emotion"], str)
        assert isinstance(response["priority"], int)

    def test_no_task_progress_maps(self) -> None:
        bus = StateBus()
        bridge = GenshinPersonaBridge(bus)
        interrupt = _make_interrupt("NO_TASK_PROGRESS", priority=40)
        bridge.on_interrupt(interrupt)

        slot = bus.get_slot("genshin.persona_response")
        assert slot is not None
        response = slot.get()
        assert response is not None
        assert response["emotion"] == "calm"
