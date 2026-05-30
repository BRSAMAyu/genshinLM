"""Tests for planning/newbie_tutorial_chain.py: 21-phase tutorial chain."""
from __future__ import annotations

from typing import Any

from planning.newbie_tutorial_chain import (
    NewbieTutorialChain,
    PhaseResult,
    TUTORIAL_PHASES,
    TutorialPhase,
)


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


class TestTutorialPhases:
    def test_21_phases_defined(self):
        assert len(TUTORIAL_PHASES) == 21

    def test_phase_ids_sequential(self):
        ids = [p.phase_id for p in TUTORIAL_PHASES]
        expected = [f"T{i:02d}" for i in range(1, 22)]
        assert ids == expected

    def test_combat_phases_marked(self):
        combat_phases = [p for p in TUTORIAL_PHASES if p.has_combat]
        assert len(combat_phases) >= 6  # T08, T15, T16, T17, T19, T20

    def test_dialog_phases_marked(self):
        dialog_phases = [p for p in TUTORIAL_PHASES if p.has_dialog]
        assert len(dialog_phases) >= 6


class TestNewbieTutorialChain:
    def test_full_chain_completes(self):
        ex = _FakeExecutor()
        chain = NewbieTutorialChain(executor=ex)
        results = chain.run()
        assert chain.completed
        assert len(results) == 21
        assert all(r.success for r in results)
        assert chain.progress_pct == 100.0

    def test_progress_tracking(self):
        ex = _FakeExecutor()
        chain = NewbieTutorialChain(executor=ex)
        assert chain.current_phase_idx == 0
        assert chain.current_phase is not None
        assert chain.current_phase.phase_id == "T01"

    def test_phase_failure_retries(self):
        ex = _FakeExecutor()
        # Fail "navigate_to" which T03 uses via _handle_movement_tutorial
        ex.set_fail_on({"navigate_to"})
        chain = NewbieTutorialChain(executor=ex, max_phase_retries=2)
        results = chain.run()
        # T01/T02 succeed (don't use navigate_to), T03 fails and chain aborts
        assert not chain.completed
        failed = [r for r in results if not r.success]
        assert len(failed) > 0

    def test_actions_per_phase(self):
        ex = _FakeExecutor()
        chain = NewbieTutorialChain(executor=ex)
        # Run just the first phase
        phase = TUTORIAL_PHASES[0]  # T01: cutscene skip
        result = chain._execute_phase(phase)
        assert result.success
        assert any("skip_cutscene" == c[0] for c in ex.calls)

    def test_boss_phases_use_boss_combat(self):
        ex = _FakeExecutor()
        chain = NewbieTutorialChain(executor=ex)
        # Run T19: boss aerial
        result = chain._execute_phase(TUTORIAL_PHASES[18])
        assert result.success
        boss_calls = [c for c in ex.calls if c[0] == "combat_boss"]
        assert len(boss_calls) >= 1
        assert boss_calls[0][1] == "stormterror_dvalin"

    def test_statue_phase_uses_scenario(self):
        ex = _FakeExecutor()
        chain = NewbieTutorialChain(executor=ex)
        result = chain._execute_phase(TUTORIAL_PHASES[6])  # T07
        assert result.success
        scenario_calls = [c for c in ex.calls if c[0] == "explore_scenario"]
        assert len(scenario_calls) >= 1

    def test_summary(self):
        ex = _FakeExecutor()
        chain = NewbieTutorialChain(executor=ex)
        chain.run()
        s = chain.summary()
        assert s["completed"] is True
        assert s["phases_completed"] == 21
        assert s["total_phases"] == 21
        assert s["progress_pct"] == "100%"
        assert s["success_rate"] == 1.0
        assert len(s["failed_phases"]) == 0

    def test_partial_completion_summary(self):
        ex = _FakeExecutor()
        chain = NewbieTutorialChain(executor=ex)
        # Simulate partial completion
        chain.results = [
            PhaseResult(phase_id="T01", success=True, duration_sec=10.0),
            PhaseResult(phase_id="T02", success=True, duration_sec=15.0),
            PhaseResult(phase_id="T03", success=False, duration_sec=30.0),
        ]
        chain.current_phase_idx = 3
        s = chain.summary()
        assert s["completed"] is False
        assert s["phases_completed"] == 3
        assert s["success_rate"] == 2 / 3
        assert "T03" in s["failed_phases"]
