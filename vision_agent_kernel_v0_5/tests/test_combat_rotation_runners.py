"""Tests for combat/combat_rotation_runners.py: weekly rotation, world boss farming, multi-wave, shield."""
from __future__ import annotations

from typing import Any

from combat.combat_rotation_runners import (
    FarmingRunResult,
    MultiWaveDefense,
    MultiWaveConfig,
    ShieldMitachurlStrategy,
    WaveResult,
    WeeklyBossConfig,
    WeeklyBossResult,
    WeeklyBossRotation,
    WorldBossFarming,
    WorldBossFarmingConfig,
)


class _FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self._fail_on: set[str] = set()

    def set_fail_on(self, actions: set[str]) -> None:
        self._fail_on = actions

    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None,
    ) -> bool:
        self.calls.append((action, target, context))
        if action in self._fail_on:
            return False
        return True


# ---------------------------------------------------------------------------
# WeeklyBossRotation
# ---------------------------------------------------------------------------

class TestWeeklyBossRotation:
    def test_run_all_default_bosses(self):
        ex = _FakeExecutor()
        rotation = WeeklyBossRotation(executor=ex, config=WeeklyBossConfig(total_weekly_discounts=3))
        results = rotation.run_rotation(target_bosses=["stormterror_dvalin", "childe_tartaglia"])
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_discounts_decrement(self):
        ex = _FakeExecutor()
        rotation = WeeklyBossRotation(executor=ex, config=WeeklyBossConfig(total_weekly_discounts=3))
        rotation.run_rotation(target_bosses=["stormterror_dvalin", "childe_tartaglia", "la_signora"])
        assert rotation.discounts_remaining == 0
        assert len(rotation.completed_bosses) == 3

    def test_discounts_exhausted_stops_rotation(self):
        ex = _FakeExecutor()
        rotation = WeeklyBossRotation(executor=ex, config=WeeklyBossConfig(total_weekly_discounts=1))
        rotation.run_rotation(target_bosses=["stormterror_dvalin", "childe_tartaglia"])
        # Only first boss runs (uses the single discount), rotation stops
        assert len(rotation.completed_bosses) == 1
        assert rotation.results[0].discount_used is True
        assert rotation.discounts_remaining == 0

    def test_teleport_failure(self):
        ex = _FakeExecutor()
        ex.set_fail_on({"teleport_to"})
        rotation = WeeklyBossRotation(executor=ex)
        results = rotation.run_rotation(target_bosses=["stormterror_dvalin"])
        assert len(results) == 1
        assert not results[0].success
        assert results[0].details == "teleport_failed"

    def test_combat_failure(self):
        ex = _FakeExecutor()
        ex.set_fail_on({"combat_boss"})
        rotation = WeeklyBossRotation(executor=ex)
        results = rotation.run_rotation(target_bosses=["childe_tartaglia"])
        assert not results[0].success
        assert not results[0].discount_used

    def test_summary(self):
        ex = _FakeExecutor()
        rotation = WeeklyBossRotation(executor=ex)
        rotation.run_rotation(target_bosses=["stormterror_dvalin"])
        s = rotation.summary
        assert s["total_bosses"] == 1
        assert s["discounts_remaining"] == 2
        assert s["success_rate"] == 1.0

    def test_skips_completed_bosses(self):
        ex = _FakeExecutor()
        rotation = WeeklyBossRotation(executor=ex)
        rotation.completed_bosses = ["stormterror_dvalin"]
        results = rotation.run_rotation(target_bosses=["stormterror_dvalin", "childe_tartaglia"])
        assert len(results) == 1
        assert results[0].boss_id == "childe_tartaglia"


# ---------------------------------------------------------------------------
# WorldBossFarming
# ---------------------------------------------------------------------------

class TestWorldBossFarming:
    def test_basic_farming_run(self):
        ex = _FakeExecutor()
        farm = WorldBossFarming(executor=ex, config=WorldBossFarmingConfig(max_runs=3))
        results = farm.run(target_boss="hypostasis_pyro", available_resin=160)
        assert len(results) == 3  # 160/40 = 4, but max_runs=3
        assert farm.total_runs == 3
        assert farm.resin_spent == 120

    def test_resin_limits_runs(self):
        ex = _FakeExecutor()
        farm = WorldBossFarming(executor=ex, config=WorldBossFarmingConfig(max_runs=10))
        results = farm.run(target_boss="hypostasis_pyro", available_resin=80)
        assert len(results) == 2  # 80/40 = 2
        assert farm.resin_spent == 80

    def test_teleport_failure(self):
        ex = _FakeExecutor()
        ex.set_fail_on({"teleport_to"})
        farm = WorldBossFarming(executor=ex)
        results = farm.run(target_boss="oceanid", available_resin=160)
        assert not results[0].success

    def test_summary(self):
        ex = _FakeExecutor()
        farm = WorldBossFarming(executor=ex, config=WorldBossFarmingConfig(max_runs=2))
        farm.run(target_boss="hypostasis_pyro", available_resin=160)
        s = farm.summary
        assert s["total_runs"] == 2
        assert s["resin_spent"] == 80
        assert s["success_rate"] == 1.0


# ---------------------------------------------------------------------------
# MultiWaveDefense
# ---------------------------------------------------------------------------

class TestMultiWaveDefense:
    def test_clear_all_waves(self):
        ex = _FakeExecutor()
        wave_counter = {"v": 0}

        def enemies_fn():
            wave_counter["v"] += 1
            # Enemies appear then get cleared
            return 0 if wave_counter["v"] > 1 else 3

        defense = MultiWaveDefense(executor=ex, config=MultiWaveConfig(check_interval_sec=0.01))
        results = defense.run(total_waves=3, enemies_remaining_fn=enemies_fn)
        assert len(results) == 3
        assert defense.waves_cleared == 3

    def test_defend_target_destroyed(self):
        ex = _FakeExecutor()
        hp_values = iter([0.0])

        defense = MultiWaveDefense(executor=ex, config=MultiWaveConfig(check_interval_sec=0.01))
        results = defense.run(total_waves=3, defend_hp_fn=lambda: next(hp_values, 0.0))
        assert len(results) == 1
        assert not results[0].success
        assert "destroyed" in results[0].details

    def test_wave_timeout(self):
        ex = _FakeExecutor()
        defense = MultiWaveDefense(
            executor=ex,
            config=MultiWaveConfig(wave_timeout_sec=0.1, check_interval_sec=0.02),
        )
        # Enemies never reach 0
        results = defense.run(total_waves=1, enemies_remaining_fn=lambda: 5)
        assert len(results) == 1
        assert not results[0].success
        assert "timeout" in results[0].details

    def test_waves_cleared_property(self):
        ex = _FakeExecutor()
        defense = MultiWaveDefense(executor=ex, config=MultiWaveConfig(check_interval_sec=0.01))
        defense.results = [
            WaveResult(wave_number=1, success=True, duration_sec=5.0),
            WaveResult(wave_number=2, success=True, duration_sec=6.0),
            WaveResult(wave_number=3, success=False, duration_sec=4.0),
        ]
        assert defense.waves_cleared == 2


# ---------------------------------------------------------------------------
# ShieldMitachurlStrategy
# ---------------------------------------------------------------------------

class TestShieldMitachurlStrategy:
    def test_break_wood_shield(self):
        ex = _FakeExecutor()
        strategy = ShieldMitachurlStrategy(executor=ex)
        result = strategy.execute(shield_type="wood")
        assert result.success
        assert result.counter_element == "pyro"
        assert result.shield_type == "wood"

    def test_break_rock_shield(self):
        ex = _FakeExecutor()
        strategy = ShieldMitachurlStrategy(executor=ex)
        result = strategy.execute(shield_type="rock")
        assert result.success
        assert result.counter_element == "geo"

    def test_break_ice_shield(self):
        ex = _FakeExecutor()
        strategy = ShieldMitachurlStrategy(executor=ex)
        result = strategy.execute(shield_type="ice")
        assert result.counter_element == "pyro"

    def test_unknown_shield_defaults_pyro(self):
        ex = _FakeExecutor()
        strategy = ShieldMitachurlStrategy(executor=ex)
        result = strategy.execute(shield_type="unknown")
        assert result.counter_element == "pyro"
        assert result.success

    def test_actions_sequence(self):
        ex = _FakeExecutor()
        strategy = ShieldMitachurlStrategy(executor=ex)
        strategy.execute(shield_type="wood")
        actions = [c[0] for c in ex.calls]
        assert "switch_char" in actions
        assert "use_skill" in actions
        assert "move_to" in actions
        assert "combat_basic_attack" in actions
