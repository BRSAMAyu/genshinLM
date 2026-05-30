"""Tests for NarwhalHandler and CombatSkillAdapter boss-specific routing."""
from __future__ import annotations

from typing import Any

from combat.boss_combat_handlers import (
    NarwhalHandler,
    NarwhalPhase,
    NarwhalState,
    BossCombatResult,
)
from combat.combat_skill_adapter import CombatSkillAdapter, _CombatExecutorBridge
from execution.console_backend import ConsoleInputBackend


class _FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self._fail_actions: set[str] = set()

    def set_fail_on(self, actions: set[str]) -> None:
        self._fail_actions = actions

    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None,
    ) -> bool:
        self.calls.append((action, target, context))
        return action not in self._fail_actions


class TestNarwhalHandler:
    def test_execute_returns_result(self):
        ex = _FakeExecutor()
        handler = NarwhalHandler(executor=ex)
        result = handler.execute()
        assert isinstance(result, BossCombatResult)
        assert result.boss_name == "narwhal"

    def test_cycles_through_outside_inside_phases(self):
        ex = _FakeExecutor()
        handler = NarwhalHandler(executor=ex)
        result = handler.execute()
        # Check that both outside and inside combat occurred
        boss_calls = [c for c in ex.calls if c[0] == "combat_boss"]
        attack_calls = [c for c in ex.calls if c[0] == "combat_basic_attack"]
        assert len(boss_calls) >= 2  # outside + final
        assert len(attack_calls) >= 1  # parasite killing

    def test_parasite_defeat_on_success(self):
        ex = _FakeExecutor()
        handler = NarwhalHandler(executor=ex)
        handler.execute()
        parasite_calls = [
            c for c in ex.calls if c[0] == "combat_basic_attack" and
            (c[2] or {}).get("target") == "parasite"
        ]
        assert len(parasite_calls) >= 1

    def test_navigate_to_parasite_cluster(self):
        ex = _FakeExecutor()
        handler = NarwhalHandler(executor=ex)
        handler.execute()
        nav_calls = [c for c in ex.calls if c[0] == "navigate_to"]
        assert len(nav_calls) >= 1
        assert nav_calls[0][1] == "parasite_cluster"

    def test_failure_when_combat_fails(self):
        ex = _FakeExecutor()
        ex.set_fail_on({"combat_boss"})
        handler = NarwhalHandler(executor=ex)
        result = handler.execute()
        assert isinstance(result, BossCombatResult)
        assert not result.success

    def test_state_transitions(self):
        state = NarwhalState()
        assert state.phase == NarwhalPhase.OUTSIDE
        assert state.cycle_count == 0
        state.phase = NarwhalPhase.INGESTED
        state.cycle_count = 1
        assert state.phase == NarwhalPhase.INGESTED
        state.phase = NarwhalPhase.BERSERK
        assert state.phase == NarwhalPhase.BERSERK

    def test_max_cycles_bounded(self):
        ex = _FakeExecutor()
        handler = NarwhalHandler(executor=ex)
        handler.MAX_CYCLES = 2  # Reduce for testing
        result = handler.execute()
        # With MAX_CYCLES=2, should have 2 outside+inside cycles + final
        boss_calls = [c for c in ex.calls if c[0] == "combat_boss"]
        # At least outside phases for each cycle + final berserk
        assert len(boss_calls) >= 3


class TestCombatSkillAdapterBossRouting:
    def test_narwhal_alias_routes_correctly(self):
        adapter = CombatSkillAdapter(backend=ConsoleInputBackend())
        handlers = adapter._get_boss_handlers(
            _CombatExecutorBridge(adapter)
        )
        assert "narwhal" in handlers
        assert "all_devouring_narwhal" in handlers

    def test_execute_boss_specific_narwhal(self):
        adapter = CombatSkillAdapter(backend=ConsoleInputBackend())
        result = adapter.execute_boss_specific("narwhal")
        assert result is True

    def test_execute_boss_specific_all_devouring_narwhal(self):
        adapter = CombatSkillAdapter(backend=ConsoleInputBackend())
        result = adapter.execute_boss_specific("all_devouring_narwhal")
        assert result is True

    def test_execute_narwhal_combat(self):
        adapter = CombatSkillAdapter(backend=ConsoleInputBackend())
        result = adapter.execute_narwhal_combat()
        assert result is True

    def test_execute_narwhal_combat_custom_timeout(self):
        adapter = CombatSkillAdapter(backend=ConsoleInputBackend())
        result = adapter.execute_narwhal_combat(context={"timeout_sec": 120.0})
        assert result is True

    def test_execute_boss_specific_unknown_boss_returns_false(self):
        adapter = CombatSkillAdapter(backend=ConsoleInputBackend())
        result = adapter.execute_boss_specific("nonexistent_boss_xyz")
        assert result is False
