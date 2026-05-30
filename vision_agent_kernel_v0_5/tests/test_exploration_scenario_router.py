"""Tests for ExplorationScenarioRouter: 11 exploration scenarios."""
from __future__ import annotations

from typing import Any

from exploration.exploration_scenario_router import (
    ExplorationScenarioConfig,
    ExplorationScenarioRouter,
    ScenarioResult,
)


class _FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def execute_semantic(
        self,
        action: str,
        target: str = "",
        context: dict[str, Any] | None = None,
    ) -> bool:
        self.calls.append((action, target, context))
        return True


def _make_router(**kwargs: Any) -> tuple[ExplorationScenarioRouter, _FakeExecutor]:
    executor = _FakeExecutor()
    router = ExplorationScenarioRouter(skill_executor=executor, **kwargs)
    return router, executor


def test_waypoint_activation():
    router, ex = _make_router()
    result = router.execute_scenario("waypoint_activation")
    assert result.success is True
    assert result.scenario == "waypoint_activation"
    actions = [c[0] for c in ex.calls]
    assert "explore_activate_waypoint" in actions


def test_statue_activation():
    router, ex = _make_router()
    result = router.execute_scenario("statue_activation")
    assert result.success is True
    actions = [c[0] for c in ex.calls]
    assert "interact" in actions


def test_statue_with_element_switch():
    router, ex = _make_router()
    result = router.execute_scenario("statue_activation", context={"switch_element": "anemo"})
    assert result.success is True
    actions = [c[0] for c in ex.calls]
    assert "statue_element_resonance" in actions


def test_common_chest():
    router, _ = _make_router()
    result = router.execute_scenario("common_chest")
    assert result.success is True
    assert result.scenario == "common_chest"


def test_exquisite_chest_with_enemies():
    router, ex = _make_router()
    result = router.execute_scenario("exquisite_chest", context={"enemies_nearby": True, "tier": "exquisite"})
    assert result.success is True
    actions = [c[0] for c in ex.calls]
    assert "combat_basic_attack" in actions


def test_elemental_monument():
    router, ex = _make_router()
    result = router.execute_scenario("elemental_monument", context={"element": "pyro"})
    assert result.success is True
    actions = [c[0] for c in ex.calls]
    assert "switch_char" in actions


def test_torch_puzzle():
    router, ex = _make_router()
    result = router.execute_scenario("torch_puzzle", context={"torch_count": 3})
    assert result.success is True
    actions = [c[0] for c in ex.calls]
    assert "use_skill" in actions


def test_pressure_plate():
    router, _ = _make_router()
    result = router.execute_scenario("pressure_plate")
    assert result.success is True


def test_pressure_plate_geo_construct():
    router, ex = _make_router()
    result = router.execute_scenario("pressure_plate", context={"use_geo_construct": True})
    assert result.success is True
    actions = [c[0] for c in ex.calls]
    assert "use_skill" in actions


def test_timed_challenge_collect():
    router, ex = _make_router()
    result = router.execute_scenario("timed_challenge", context={"type": "collect", "target_count": 3})
    assert result.success is True
    actions = [c[0] for c in ex.calls]
    assert "interact" in actions


def test_timed_challenge_combat():
    router, _ = _make_router()
    result = router.execute_scenario("timed_challenge", context={"type": "combat"})
    assert result.success is True


def test_oculus_collection():
    router, _ = _make_router()
    result = router.execute_scenario("oculus_collection")
    assert result.success is True
    assert result.scenario == "oculus_collection"


def test_withering_zone():
    router, ex = _make_router()
    result = router.execute_scenario("withering_zone", context={"tumor_count": 2})
    assert result.success is True
    actions = [c[0] for c in ex.calls]
    assert "interact" in actions


def test_underwater_exploration():
    router, ex = _make_router()
    result = router.execute_scenario("underwater_exploration", context={"objects": ["pearl_1", "pearl_2"]})
    assert result.success is True
    actions = [c[0] for c in ex.calls]
    assert "swim" in actions


def test_unknown_scenario():
    router, _ = _make_router()
    result = router.execute_scenario("nonexistent_scenario")
    assert result.success is False
    assert "unknown" in result.details


def test_all_11_scenarios_callable():
    router, _ = _make_router()
    scenarios = [
        "waypoint_activation", "statue_activation", "common_chest",
        "exquisite_chest", "elemental_monument", "torch_puzzle",
        "pressure_plate", "timed_challenge", "oculus_collection",
        "withering_zone", "underwater_exploration",
    ]
    for s in scenarios:
        result = router.execute_scenario(s)
        assert result.success is True, f"{s} failed"
