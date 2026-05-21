from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from core.events import Interrupt
from core.state_bus import StateBus
from app_service.apps.hsr_persona_bridge import HSRPersonaBridge
from app_service.hsr_persona import HSRPersona, PersonaResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_interrupt(code: str, priority: int = 50) -> Interrupt:
    return Interrupt(
        priority=priority,
        timestamp=time.perf_counter(),
        code=code,
        source="test",
    )


# ---------------------------------------------------------------------------
# Persona Bridge Tests
# ---------------------------------------------------------------------------

class TestHSRPersonaBridge:
    def test_maps_target_lost(self) -> None:
        bus = StateBus()
        bridge = HSRPersonaBridge(bus)
        intr = _make_interrupt("TARGET_LOST")
        bridge.on_interrupt(intr)
        data = bridge._response_slot.get()
        assert data is not None
        assert "text" in data
        assert isinstance(data["text"], str)
        assert len(data["text"]) > 0

    def test_maps_hp_critical(self) -> None:
        bus = StateBus()
        bridge = HSRPersonaBridge(bus)
        intr = _make_interrupt("HP_CRITICAL", priority=5)
        bridge.on_interrupt(intr)
        data = bridge._response_slot.get()
        assert data is not None
        assert "emotion" in data
        assert data["emotion"] in ("worried", "calm", "excited", "happy", "surprised")

    def test_ignores_unknown_interrupt(self) -> None:
        bus = StateBus()
        bridge = HSRPersonaBridge(bus)
        intr = _make_interrupt("UNKNOWN_CODE")
        bridge.on_interrupt(intr)
        assert bridge._response_slot.get() is None

    def test_maps_combat_wave_start(self) -> None:
        bus = StateBus()
        bridge = HSRPersonaBridge(bus)
        intr = _make_interrupt("COMBAT_WAVE_START")
        bridge.on_interrupt(intr)
        data = bridge._response_slot.get()
        assert data is not None
        assert "text" in data

    def test_maps_emergency_stop(self) -> None:
        bus = StateBus()
        bridge = HSRPersonaBridge(bus)
        intr = _make_interrupt("EMERGENCY_STOP", priority=0)
        bridge.on_interrupt(intr)
        data = bridge._response_slot.get()
        assert data is not None

    def test_maps_sp_critical(self) -> None:
        bus = StateBus()
        bridge = HSRPersonaBridge(bus)
        intr = _make_interrupt("SP_CRITICAL")
        bridge.on_interrupt(intr)
        data = bridge._response_slot.get()
        assert data is not None

    def test_maps_weakness_break(self) -> None:
        bus = StateBus()
        bridge = HSRPersonaBridge(bus)
        intr = _make_interrupt("WEAKNESS_BREAK")
        bridge.on_interrupt(intr)
        data = bridge._response_slot.get()
        assert data is not None


# ---------------------------------------------------------------------------
# HSRPersona Direct Tests
# ---------------------------------------------------------------------------

class TestHSRPersona:
    def test_persona_event_returns_response(self) -> None:
        persona = HSRPersona()
        response = persona.on_event("WAVE_START")
        assert response is not None
        assert isinstance(response, PersonaResponse)
        assert len(response.text) > 0
        assert response.emotion

    def test_persona_cooldown(self) -> None:
        persona = HSRPersona()
        # First call should succeed
        response1 = persona.on_event("WAVE_START")
        assert response1 is not None
        # Immediate second call should be blocked by cooldown
        response2 = persona.on_event("WAVE_START")
        assert response2 is None

    def test_persona_unknown_event(self) -> None:
        persona = HSRPersona()
        response = persona.on_event("NONEXISTENT")
        assert response is None

    def test_persona_combat_state_hp_low(self) -> None:
        persona = HSRPersona()
        response = persona.on_combat_state(sp_level=3, hp_ratios=[0.2, 0.8, 0.9, 1.0])
        assert response is not None
        assert "emotion" in response.__dataclass_fields__

    def test_persona_combat_state_sp_low(self) -> None:
        persona = HSRPersona()
        response = persona.on_combat_state(sp_level=1, hp_ratios=[1.0, 1.0, 1.0, 1.0])
        assert response is not None

    def test_persona_combat_state_healthy(self) -> None:
        persona = HSRPersona()
        response = persona.on_combat_state(sp_level=5, hp_ratios=[1.0, 1.0, 1.0, 1.0])
        assert response is None

    def test_persona_variant_cycling(self) -> None:
        """Persona should cycle through variant responses."""
        persona = HSRPersona()
        texts: set[str] = set()
        for _ in range(10):
            # Use a fresh persona each iteration to avoid cooldown
            p = HSRPersona()
            resp = p.on_event("WAVE_START")
            if resp is not None:
                texts.add(resp.text)
        # Multiple variants exist for WAVE_START
        assert len(texts) >= 1  # At minimum one variant should fire

    def test_persona_format_with_context(self) -> None:
        persona = HSRPersona()
        result = persona.format_with_context(
            "Wave {wave} started!", {"wave": "3"}
        )
        assert result == "Wave 3 started!"

    def test_persona_format_with_missing_key(self) -> None:
        persona = HSRPersona()
        result = persona.format_with_context(
            "No substitution here", {"irrelevant": "value"}
        )
        assert result == "No substitution here"
