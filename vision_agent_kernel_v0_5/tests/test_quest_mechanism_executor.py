"""Tests for planning/quest_mechanism_executor.py: decision → semantic action translation."""
from __future__ import annotations

from typing import Any

from planning.quest_mechanism_executor import QuestMechanismExecutor
from planning.quest_mechanism_router import (
    MechanismDecision,
    QuestMechanismRouter,
    QuestMechanismType,
    StealthState,
    EscortState,
    TimedState,
    DomainQuestState,
    InvestigationState,
    ARBreakthroughState,
    InazumaLockoutState,
)


class _FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None,
    ) -> bool:
        self.calls.append((action, target, context))
        return True


class _FailExecutor:
    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None,
    ) -> bool:
        return False


class TestQuestMechanismExecutor:
    def test_route_stealth(self):
        ex = _FakeExecutor()
        router = QuestMechanismRouter()
        # Default stealth state: no target, not detected → wait
        executor = QuestMechanismExecutor(router=router, executor=ex)
        result = executor.route(mechanism_type="stealth")
        assert result is True
        assert len(ex.calls) == 1
        assert ex.calls[0][0] == "idle"

    def test_route_stealth_detected(self):
        ex = _FakeExecutor()
        router = QuestMechanismRouter()
        router._stealth_state.is_detected = True
        executor = QuestMechanismExecutor(router=router, executor=ex)
        result = executor.route(mechanism_type="stealth")
        assert result is True
        assert ex.calls[0][0] == "move_to_cover"

    def test_route_escort_threat(self):
        ex = _FakeExecutor()
        router = QuestMechanismRouter()
        router._escort_state.threats_nearby = 2
        executor = QuestMechanismExecutor(router=router, executor=ex)
        result = executor.route(mechanism_type="escort")
        assert result is True
        assert ex.calls[0][0] == "combat_encounter"

    def test_route_domain_combat(self):
        ex = _FakeExecutor()
        router = QuestMechanismRouter()
        router._domain_state.phase = "combat"
        router._domain_state.enemies_remaining = 3
        executor = QuestMechanismExecutor(router=router, executor=ex)
        result = executor.route(mechanism_type="domain")
        assert result is True
        assert ex.calls[0][0] == "combat_encounter"

    def test_route_timed_active(self):
        ex = _FakeExecutor()
        router = QuestMechanismRouter()
        router._timed_state.is_active = True
        router._timed_state.time_remaining_sec = 120
        executor = QuestMechanismExecutor(router=router, executor=ex)
        result = executor.route(mechanism_type="timed")
        assert result is True

    def test_route_investigation(self):
        ex = _FakeExecutor()
        router = QuestMechanismRouter()
        router._investigation_state.current_area = "meropide"
        executor = QuestMechanismExecutor(router=router, executor=ex)
        result = executor.route(mechanism_type="investigation")
        assert result is True
        assert ex.calls[0][0] == "explore_area"

    def test_route_ar_breakthrough(self):
        ex = _FakeExecutor()
        router = QuestMechanismRouter()
        router._ar_state.is_active = True
        router._ar_state.target_ar = 25
        executor = QuestMechanismExecutor(router=router, executor=ex)
        result = executor.route(mechanism_type="ar_breakthrough")
        assert result is True

    def test_route_inazuma_lockout(self):
        ex = _FakeExecutor()
        router = QuestMechanismRouter()
        router._inazuma_lockout_state.current_ar = 20
        executor = QuestMechanismExecutor(router=router, executor=ex)
        result = executor.route(mechanism_type="inazuma_lockout")
        assert result is True

    def test_route_standard(self):
        ex = _FakeExecutor()
        router = QuestMechanismRouter()
        executor = QuestMechanismExecutor(router=router, executor=ex)
        result = executor.route(mechanism_type="standard")
        assert result is True

    def test_unknown_mechanism_type(self):
        ex = _FakeExecutor()
        router = QuestMechanismRouter()
        executor = QuestMechanismExecutor(router=router, executor=ex)
        result = executor.route(mechanism_type="nonexistent")
        assert result is False
        assert len(ex.calls) == 0

    def test_failed_execution_returns_false(self):
        ex = _FailExecutor()
        router = QuestMechanismRouter()
        executor = QuestMechanismExecutor(router=router, executor=ex)
        result = executor.route(mechanism_type="standard")
        assert result is False

    def test_context_includes_reason(self):
        ex = _FakeExecutor()
        router = QuestMechanismRouter()
        router._domain_state.phase = "boss"
        executor = QuestMechanismExecutor(router=router, executor=ex)
        executor.route(mechanism_type="domain")
        assert len(ex.calls) == 1
        ctx = ex.calls[0][2]
        assert ctx is not None
        assert "mechanism_reason" in ctx
        assert "boss" in ctx["mechanism_reason"]

    def test_stealth_with_target(self):
        ex = _FakeExecutor()
        router = QuestMechanismRouter()
        router._stealth_state.target_position = (100.0, 200.0)
        executor = QuestMechanismExecutor(router=router, executor=ex)
        executor.route(mechanism_type="stealth")
        assert ex.calls[0][0] == "interact"  # "proceed" maps to "interact"
        assert "100" in ex.calls[0][1]

    def test_all_mechanism_types_route(self):
        """All QuestMechanismType values should route without error."""
        ex = _FakeExecutor()
        router = QuestMechanismRouter()
        executor = QuestMechanismExecutor(router=router, executor=ex)
        for mtype in QuestMechanismType:
            result = executor.route(mechanism_type=mtype.value)
            assert isinstance(result, bool), f"{mtype.value} did not return bool"
