from __future__ import annotations

import time

from core.state_bus import StateBus
from core.types import SkillResult
from app_service.apps.genshin_failure_bridge import GenshinFailureBridge


def _failed_result(
    skill_name: str = "test_skill",
    failure_code: str = "COMBAT_TIMEOUT",
) -> SkillResult:
    now = time.perf_counter()
    return SkillResult(
        skill_name=skill_name,
        status="FAILED",
        failure_code=failure_code,
        started_at=now - 1.0,
        finished_at=now,
        payload={},
    )


def _success_result(skill_name: str = "test_skill") -> SkillResult:
    now = time.perf_counter()
    return SkillResult(
        skill_name=skill_name,
        status="SUCCESS",
        failure_code=None,
        started_at=now - 1.0,
        finished_at=now,
        payload={},
    )


class TestFailureBridgeRecordsFailedSkillResult:
    """Calling on_skill_result with a FAILED result should record the failure."""

    def test_records_failure(self) -> None:
        bus = StateBus()
        bridge = GenshinFailureBridge(bus)
        result = _failed_result("combat_slash", "COMBAT_TIMEOUT")
        bridge.on_skill_result(result)

        # The internal analyzer should have recorded one failure.
        stats = bridge._analyzer.get_failure_stats()
        assert "combat_timeout" in stats
        assert stats["combat_timeout"] == 1

    def test_maps_failure_code_to_category(self) -> None:
        bus = StateBus()
        bridge = GenshinFailureBridge(bus)
        result = _failed_result("collect_herb", "COLLECTION_FAILED")
        bridge.on_skill_result(result)

        stats = bridge._analyzer.get_failure_stats()
        assert "collection_failed" in stats

    def test_default_category_on_unknown_code(self) -> None:
        bus = StateBus()
        bridge = GenshinFailureBridge(bus)
        result = _failed_result("wild_skill", "UNKNOWN_CODE")
        bridge.on_skill_result(result)

        stats = bridge._analyzer.get_failure_stats()
        # Unknown codes fall back to COMBAT_TIMEOUT
        assert "combat_timeout" in stats


class TestFailureBridgeIgnoresSuccess:
    """Calling on_skill_result with a non-FAILED result should do nothing."""

    def test_ignores_success(self) -> None:
        bus = StateBus()
        bridge = GenshinFailureBridge(bus)
        result = _success_result("combat_slash")
        bridge.on_skill_result(result)

        stats = bridge._analyzer.get_failure_stats()
        assert len(stats) == 0

    def test_ignores_other_status(self) -> None:
        bus = StateBus()
        bridge = GenshinFailureBridge(bus)
        now = time.perf_counter()
        result = SkillResult(
            skill_name="test",
            status="CANCELLED",
            failure_code=None,
            started_at=now - 1.0,
            finished_at=now,
            payload={},
        )
        bridge.on_skill_result(result)

        stats = bridge._analyzer.get_failure_stats()
        assert len(stats) == 0


class TestFailureBridgePublishesToSlot:
    """on_skill_result should publish analysis data to the failure slot."""

    def test_publishes_to_slot(self) -> None:
        bus = StateBus()
        bridge = GenshinFailureBridge(bus)
        result = _failed_result("combat_slash", "COMBAT_TIMEOUT")
        bridge.on_skill_result(result)

        slot = bus.get_slot("genshin.failure_state")
        assert slot is not None
        data = slot.get()
        assert data is not None
        assert "failure_id" in data
        assert "patterns" in data
        assert "suggestions" in data
        assert isinstance(data["failure_id"], str)
        assert isinstance(data["patterns"], list)

    def test_slot_contains_context(self) -> None:
        bus = StateBus()
        bridge = GenshinFailureBridge(bus)
        result = _failed_result("dodge_skill", "DANGER_UNAVOIDED")
        bridge.on_skill_result(result)

        slot = bus.get_slot("genshin.failure_state")
        assert slot is not None
        data = slot.get()
        assert data is not None
        assert data["failure_id"] != ""

    def test_automatic_subscription_via_state_bus_publish(self) -> None:
        bus = StateBus()
        bridge = GenshinFailureBridge(bus)
        bus.subscribe("skill_result", bridge.on_skill_result)
        
        result = _failed_result("dodge_skill", "DANGER_UNAVOIDED")
        bus.publish("skill_result", result)

        slot = bus.get_slot("genshin.failure_state")
        assert slot is not None
        data = slot.get()
        assert data is not None
        assert data["failure_id"] != ""
