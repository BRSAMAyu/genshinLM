"""Tests for Sentinel Recovery — somatic state, recipes, runtime."""
from __future__ import annotations

import threading

import pytest

from control.sentinel.somatic_state import (
    PositionEstimate,
    ResourceState,
    SomaticState,
    TeamState,
)
from control.sentinel.recovery_recipe import RecoveryRecipe, RecoveryResult
from control.sentinel.recipes import (
    CombatDefeatRecovery,
    DriftRecovery,
    LowHealthRecovery,
    LoadingTimeoutRecovery,
    ModelProviderFailureRecovery,
    StuckRecovery,
    TargetLostRecovery,
    UILostRecovery,
    default_recipes,
)
from control.sentinel.sentinel_runtime import SentinelRuntime, SentinelEvent


# -- SomaticState tests --

class TestSomaticState:
    def test_evolve(self) -> None:
        s = SomaticState(active_quest_id="q1")
        s2 = s.evolve(active_quest_id="q2", frame_id=10)
        assert s2.active_quest_id == "q2"
        assert s2.frame_id == 10
        assert s.active_quest_id == "q1"  # original unchanged

    def test_is_healthy_no_hp(self) -> None:
        s = SomaticState()
        assert s.is_healthy()  # unknown = assume healthy

    def test_is_healthy_with_hp(self) -> None:
        s = SomaticState(team_state=TeamState(hp_ratios=(0.5, 0.0)))
        assert s.is_healthy()

    def test_is_unhealthy_all_dead(self) -> None:
        s = SomaticState(team_state=TeamState(hp_ratios=(0.0, 0.0)))
        assert not s.is_healthy()

    def test_is_safe_screen(self) -> None:
        assert SomaticState(last_safe_screen_state="world_viewport").is_safe_screen()
        assert SomaticState(last_safe_screen_state="combat").is_safe_screen() is False

    def test_position_estimate(self) -> None:
        pos = PositionEstimate(x=100.0, y=200.0, confidence=0.8, source="minimap")
        assert pos.confidence == 0.8


# -- Recipe tests --

class TestRecipes:
    def test_ui_lost_recovery(self) -> None:
        r = UILostRecovery()
        assert r.check_precondition(SomaticState(last_safe_screen_state="unknown"))
        assert not r.check_precondition(SomaticState(last_safe_screen_state="world_viewport"))
        assert not r.check_precondition(SomaticState(last_safe_screen_state="loading"))
        result = r.execute_recovery()
        assert result.status == "success"
        assert r.failure_policy == "ask_user"

    def test_stuck_recovery(self) -> None:
        r = StuckRecovery()
        assert r.check_precondition(SomaticState(is_stuck=True))
        assert not r.check_precondition(SomaticState(is_stuck=False))
        result = r.execute_recovery()
        assert result.status == "success"

    def test_target_lost_recovery(self) -> None:
        r = TargetLostRecovery()
        assert r.check_precondition(SomaticState(is_target_lost=True))
        assert not r.check_precondition(SomaticState(is_target_lost=False))

    def test_loading_timeout_recovery(self) -> None:
        r = LoadingTimeoutRecovery()
        assert r.check_precondition(SomaticState(is_loading=True))
        assert not r.check_precondition(SomaticState(is_loading=False))

    def test_combat_defeat_recovery(self) -> None:
        r = CombatDefeatRecovery()
        dead = SomaticState(team_state=TeamState(hp_ratios=(0.0,)))
        assert r.check_precondition(dead)
        alive = SomaticState(team_state=TeamState(hp_ratios=(1.0,)))
        assert not r.check_precondition(alive)

    def test_low_health_recovery(self) -> None:
        r = LowHealthRecovery()
        low = SomaticState(team_state=TeamState(hp_ratios=(0.1, 0.5)))
        assert r.check_precondition(low)
        high = SomaticState(team_state=TeamState(hp_ratios=(0.8, 0.5)))
        assert not r.check_precondition(high)
        unknown = SomaticState()
        assert not r.check_precondition(unknown)

    def test_drift_recovery(self) -> None:
        r = DriftRecovery()
        assert r.check_precondition(SomaticState(is_drifting=True))
        assert not r.check_precondition(SomaticState(is_drifting=False))

    def test_model_provider_recovery(self) -> None:
        r = ModelProviderFailureRecovery()
        assert r.check_precondition(SomaticState(model_provider_failed=True))
        assert not r.check_precondition(SomaticState(model_provider_failed=False))

    def test_default_recipes_count(self) -> None:
        recipes = default_recipes()
        assert len(recipes) == 8

    def test_all_recipes_have_ids(self) -> None:
        for r in default_recipes():
            assert r.recipe_id
            assert r.max_budget > 0

    def test_recipe_verify(self) -> None:
        for r in default_recipes():
            assert r.verify_restabilized()


# -- SentinelRuntime tests --

class TestSentinelRuntime:
    def test_no_anomaly_returns_none(self) -> None:
        sentinel = SentinelRuntime()
        # SomaticState with safe screen and healthy team → no anomaly
        snapshot = SomaticState(
            last_safe_screen_state="world_viewport",
            team_state=TeamState(hp_ratios=(1.0,)),
        )
        result = sentinel.intervene(snapshot)
        assert result is None

    def test_detect_combat_defeat(self) -> None:
        sentinel = SentinelRuntime()
        dead = SomaticState(
            last_safe_screen_state="world_viewport",
            team_state=TeamState(hp_ratios=(0.0,)),
        )
        event = sentinel.intervene(dead)
        assert event is not None
        assert event.result is not None
        assert event.result.status == "success"

    def test_budget_exhaustion(self) -> None:
        sentinel = SentinelRuntime(max_global_budget=2)
        dead = SomaticState(team_state=TeamState(hp_ratios=(0.0,)))

        # First two should succeed
        e1 = sentinel.intervene(dead)
        e2 = sentinel.intervene(dead)
        assert e1 is not None and e1.result is not None
        assert e2 is not None and e2.result is not None

        # Third should be budget exhausted
        e3 = sentinel.intervene(dead)
        assert e3 is not None
        assert e3.result is not None
        assert e3.result.status == "budget_exhausted"

    def test_budget_remaining(self) -> None:
        sentinel = SentinelRuntime(max_global_budget=5)
        assert sentinel.budget_remaining == 5
        dead = SomaticState(team_state=TeamState(hp_ratios=(0.0,)))
        sentinel.intervene(dead)
        assert sentinel.budget_remaining == 4

    def test_reset_budget(self) -> None:
        sentinel = SentinelRuntime(max_global_budget=3)
        dead = SomaticState(team_state=TeamState(hp_ratios=(0.0,)))
        sentinel.intervene(dead)
        assert sentinel.budget_remaining == 2
        sentinel.reset_budget()
        assert sentinel.budget_remaining == 3

    def test_reset(self) -> None:
        sentinel = SentinelRuntime()
        dead = SomaticState(team_state=TeamState(hp_ratios=(0.0,)))
        sentinel.intervene(dead)
        assert len(sentinel.interventions) == 1
        sentinel.reset()
        assert len(sentinel.interventions) == 0
        assert sentinel.budget_remaining > 0

    def test_update_snapshot(self) -> None:
        sentinel = SentinelRuntime()
        s = SomaticState(active_quest_id="q1")
        sentinel.update_snapshot(s)
        # No crash = success (snapshot stored internally)

    def test_interventions_history(self) -> None:
        sentinel = SentinelRuntime()
        dead = SomaticState(team_state=TeamState(hp_ratios=(0.0,)))
        sentinel.intervene(dead)
        history = sentinel.interventions
        assert len(history) == 1
        assert history[0].recipe_id == "COMBAT_DEFEAT_RECOVERY"

    def test_concurrent_interventions_reserve_budget_atomically(self) -> None:
        class HighBudgetCombatDefeatRecovery(CombatDefeatRecovery):
            max_budget = 10

        sentinel = SentinelRuntime(
            recipes=[HighBudgetCombatDefeatRecovery()],
            max_global_budget=10,
        )
        dead = SomaticState(team_state=TeamState(hp_ratios=(0.0,)))
        results: list[SentinelEvent | None] = []
        lock = threading.Lock()

        def worker() -> None:
            event = sentinel.intervene(dead)
            with lock:
                results.append(event)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        successful = [r for r in results if r is not None and r.result is not None and r.result.status == "success"]
        assert len(successful) == 10
        assert len(sentinel.interventions) == 10
        assert sentinel.budget_remaining == 0
        assert len({event.event_id for event in successful}) == 10
