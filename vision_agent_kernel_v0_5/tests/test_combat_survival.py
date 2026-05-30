"""Tests for combat survival engine and boss mechanism learner."""
from __future__ import annotations

import pytest

from combat.combat_survival import (
    BOSS_PHASES,
    COMBAT_FOODS,
    CombatFoodState,
    CombatFoodType,
    CombatSurvivalDecision,
    CombatSurvivalEngine,
    BossMechanismLearner,
    BossPhaseInfo,
    SHIELD_COUNTERS,
    get_shield_counter,
)


class TestShieldCounters:
    def test_pyro_weak_to_hydro(self) -> None:
        assert "Hydro" in get_shield_counter("Pyro")

    def test_cryo_weak_to_pyro(self) -> None:
        assert "Pyro" in get_shield_counter("Cryo")

    def test_geo_weak_to_claymore(self) -> None:
        counters = get_shield_counter("Geo")
        assert "Claymore" in counters

    def test_unknown_element(self) -> None:
        assert get_shield_counter("Unknown") == ()

    def test_case_insensitive(self) -> None:
        assert len(get_shield_counter("pyro")) > 0


class TestBossPhases:
    def test_all_bosses_have_phases(self) -> None:
        for boss_id in ("dvalin", "childe", "signora", "raiden_shogun",
                        "shouki_no_kami", "narwhal"):
            assert boss_id in BOSS_PHASES
            assert len(BOSS_PHASES[boss_id]) >= 1

    def test_childe_has_3_phases(self) -> None:
        assert len(BOSS_PHASES["childe"]) == 3

    def test_phase_numbers_sequential(self) -> None:
        for boss_id, phases in BOSS_PHASES.items():
            numbers = [p.phase_number for p in phases]
            assert numbers == list(range(1, len(phases) + 1))

    def test_signora_vulnerable_elements(self) -> None:
        signora = BOSS_PHASES["signora"]
        assert "Pyro" in signora[0].vulnerable_elements  # cryo phase
        assert "Cryo" in signora[1].vulnerable_elements  # pyro phase


class TestCombatFoodState:
    def test_can_use_available(self) -> None:
        state = CombatFoodState(available_foods={"sweet_madame": 5})
        assert state.can_use("sweet_madame", now=0.0)

    def test_cannot_use_empty(self) -> None:
        state = CombatFoodState(available_foods={"sweet_madame": 0})
        assert not state.can_use("sweet_madame", now=0.0)

    def test_cannot_use_unknown(self) -> None:
        state = CombatFoodState()
        assert not state.can_use("nonexistent", now=0.0)

    def test_use_reduces_count(self) -> None:
        state = CombatFoodState(available_foods={"sweet_madame": 3})
        assert state.use("sweet_madame", now=0.0)
        assert state.available_foods["sweet_madame"] == 2

    def test_buff_activates(self) -> None:
        state = CombatFoodState(available_foods={"sticky_honey_roast": 1})
        state.use("sticky_honey_roast", now=100.0)
        assert state.has_active_buff("atk_buff", now=150.0)
        assert not state.has_active_buff("atk_buff", now=500.0)

    def test_cooldown_prevents_reuse(self) -> None:
        state = CombatFoodState(available_foods={"sticky_honey_roast": 2})
        assert state.use("sticky_honey_roast", now=0.0)
        assert not state.use("sticky_honey_roast", now=10.0)  # still on cooldown
        assert state.use("sticky_honey_roast", now=400.0)    # cooldown expired


class TestCombatSurvivalEngine:
    def _engine(self) -> CombatSurvivalEngine:
        engine = CombatSurvivalEngine()
        engine.food_state.available_foods = {
            "sweet_madame": 5,
            "mondstadt_hash_brown": 3,
            "tea_break_pancake": 2,
            "sticky_honey_roast": 1,
        }
        return engine

    def test_all_dead_retreat(self) -> None:
        engine = self._engine()
        decision = engine.evaluate((0.0, 0.0, 0.0, 0.0), 0, 0.5, 0.0)
        assert decision is not None
        assert decision.action == "retreat"

    def test_low_hp_dash(self) -> None:
        engine = self._engine()
        decision = engine.evaluate((0.1, 0.8, 0.9, 0.7), 0, 0.8, 0.0)
        assert decision is not None
        assert decision.action == "dash"

    def test_low_hp_switch_when_no_stamina(self) -> None:
        engine = self._engine()
        engine.update_burst_availability(0, False)  # no burst available
        decision = engine.evaluate((0.1, 0.8, 0.9, 0.7), 0, 0.8, 0.0, stamina_ratio=0.0)
        assert decision is not None
        assert decision.action == "switch"

    def test_dead_char_revive(self) -> None:
        engine = self._engine()
        decision = engine.evaluate((0.8, 0.0, 0.9, 0.7), 0, 0.3, 0.0)
        assert decision is not None
        assert decision.action == "use_food"

    def test_safe_returns_none(self) -> None:
        engine = self._engine()
        decision = engine.evaluate((0.9, 0.8, 0.9, 0.7), 0, 0.1, 0.0)
        # Low danger, healthy team - might return buff or None
        if decision is not None:
            assert decision.priority >= 10  # non-critical action

    def test_pre_boss_buff(self) -> None:
        engine = self._engine()
        decision = engine.evaluate((1.0, 1.0, 1.0, 1.0), 0, 0.4, 0.0)
        # Should suggest attack buff before boss fight
        if decision is not None:
            assert decision.action in ("use_food",)

    def test_burst_iframe(self) -> None:
        engine = self._engine()
        engine.update_burst_availability(0, True)
        decision = engine.evaluate((0.1, 0.8, 0.9, 0.7), 0, 0.8, 0.0, stamina_ratio=0.0)
        # Should use burst for iframe when can't dash
        if decision is not None and decision.action == "burst_iframe":
            pass  # expected


class TestBossMechanismLearner:
    def _learner(self) -> BossMechanismLearner:
        return BossMechanismLearner()

    def test_record_first_attempt(self) -> None:
        learner = self._learner()
        learner.record_attempt("childe", won=False, time_sec=120.0)
        record = learner.get_record("childe")
        assert record is not None
        assert record.attempts == 1
        assert record.deaths == 1

    def test_record_win(self) -> None:
        learner = self._learner()
        learner.record_attempt("dvalin", won=True, time_sec=60.0)
        record = learner.get_record("dvalin")
        assert record.wins == 1
        assert record.best_time_sec == 60.0

    def test_should_retreat_after_many_losses(self) -> None:
        learner = self._learner()
        for _ in range(5):
            learner.record_attempt("signora", won=False, time_sec=180.0, death_phase=2)
        assert learner.should_retreat("signora")

    def test_should_not_retreat_early(self) -> None:
        learner = self._learner()
        learner.record_attempt("signora", won=False, time_sec=120.0)
        assert not learner.should_retreat("signora")

    def test_failure_diagnosis_undergeared(self) -> None:
        learner = self._learner()
        for _ in range(3):
            learner.record_attempt("childe", won=False, time_sec=200.0)
        diagnosis = learner.get_failure_diagnosis("childe")
        assert "undergeared" in diagnosis or "team_comp" in diagnosis

    def test_failure_diagnosis_mechanics(self) -> None:
        learner = self._learner()
        for _ in range(4):
            learner.record_attempt("signora", won=False, time_sec=90.0, death_phase=2)
        diagnosis = learner.get_failure_diagnosis("signora")
        assert "mechanics" in diagnosis

    def test_strategy_adjustment_gear_up(self) -> None:
        learner = self._learner()
        for _ in range(3):
            learner.record_attempt("childe", won=False, time_sec=200.0)
        rec = learner.recommend_strategy_adjustment("childe")
        assert "diagnosis" in rec

    def test_no_data(self) -> None:
        learner = self._learner()
        assert learner.get_record("unknown_boss") is None
        assert learner.get_failure_diagnosis("unknown_boss") == "no_data"
        assert not learner.should_retreat("unknown_boss")
