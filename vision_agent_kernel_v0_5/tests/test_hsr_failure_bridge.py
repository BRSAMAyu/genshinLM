from __future__ import annotations

import time

from core.events import Interrupt
from core.state_bus import StateBus
from core.types import SkillResult
from app_service.apps.hsr_failure_bridge import HSRFailureBridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    status: str = "FAILED",
    failure_code: str | None = "SP_EXHAUSTED",
    skill_name: str = "hsr_skill",
) -> SkillResult:
    now = time.perf_counter()
    return SkillResult(
        skill_name=skill_name,
        status=status,
        failure_code=failure_code,
        started_at=now - 1.0,
        finished_at=now,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHSRFailureBridge:
    def test_records_hsr_failure_codes(self) -> None:
        bus = StateBus()
        bridge = HSRFailureBridge(bus)
        result = _make_result(status="FAILED", failure_code="SP_EXHAUSTED")
        bridge.on_skill_result(result)
        # After recording, the failure slot should have data
        failure_data = bridge._failure_slot.get()
        assert failure_data is not None
        assert "failure_id" in failure_data
        assert isinstance(failure_data["failure_id"], str)

    def test_maps_weakness_not_exploited(self) -> None:
        bus = StateBus()
        bridge = HSRFailureBridge(bus)
        result = _make_result(failure_code="WEAKNESS_NOT_EXPLOITED")
        bridge.on_skill_result(result)
        failure_data = bridge._failure_slot.get()
        assert failure_data is not None
        patterns = failure_data.get("patterns", [])
        # With only 1 failure, patterns may be empty (threshold is 3)
        # But the failure should have been recorded internally
        assert bridge._analyzer.get_failure_stats().get("element_mismatch", 0) == 1

    def test_ignores_success_results(self) -> None:
        bus = StateBus()
        bridge = HSRFailureBridge(bus)
        result = _make_result(status="SUCCESS", failure_code=None)
        bridge.on_skill_result(result)
        # Slot should remain empty
        assert bridge._failure_slot.get() is None

    def test_publishes_to_failure_slot(self) -> None:
        bus = StateBus()
        bridge = HSRFailureBridge(bus)
        result = _make_result(failure_code="COMBAT_TIMEOUT")
        bridge.on_skill_result(result)
        data = bridge._failure_slot.get()
        assert data is not None
        assert "failure_id" in data
        assert isinstance(data["failure_id"], str)
        assert "patterns" in data
        assert "suggestions" in data

    def test_records_multiple_failures(self) -> None:
        bus = StateBus()
        bridge = HSRFailureBridge(bus)
        for code in ("SP_EXHAUSTED", "COMBAT_TIMEOUT", "HP_DEPLETED"):
            bridge.on_skill_result(_make_result(failure_code=code))
        stats = bridge._analyzer.get_failure_stats()
        assert stats.get("stamina_exhausted", 0) == 1
        assert stats.get("combat_timeout", 0) == 1
        assert stats.get("hp_depleted", 0) == 1

    def test_unknown_failure_code_defaults_to_combat_timeout(self) -> None:
        bus = StateBus()
        bridge = HSRFailureBridge(bus)
        result = _make_result(failure_code="SOME_NEW_CODE")
        bridge.on_skill_result(result)
        stats = bridge._analyzer.get_failure_stats()
        assert stats.get("combat_timeout", 0) == 1

    def test_hp_depleted_mapping(self) -> None:
        bus = StateBus()
        bridge = HSRFailureBridge(bus)
        result = _make_result(failure_code="HP_DEPLETED")
        bridge.on_skill_result(result)
        stats = bridge._analyzer.get_failure_stats()
        assert stats.get("hp_depleted", 0) == 1

    def test_wave_wipe_failed_mapping(self) -> None:
        bus = StateBus()
        bridge = HSRFailureBridge(bus)
        result = _make_result(failure_code="WAVE_WIPE_FAILED")
        bridge.on_skill_result(result)
        stats = bridge._analyzer.get_failure_stats()
        assert stats.get("combat_timeout", 0) == 1

    def test_ultimate_missed_mapping(self) -> None:
        bus = StateBus()
        bridge = HSRFailureBridge(bus)
        result = _make_result(failure_code="ULTIMATE_MISSED")
        bridge.on_skill_result(result)
        stats = bridge._analyzer.get_failure_stats()
        assert stats.get("skill_miss", 0) == 1
