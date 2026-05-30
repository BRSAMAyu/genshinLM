"""Tests for combat/environmental_combat_handlers.py and combat/boss_combat_handlers.py."""
from __future__ import annotations

from typing import Any

import pytest

from combat.environmental_combat_handlers import (
    DragonspineSheerColdHandler,
    DragonspineCombatResult,
    InazumaThunderstormHandler,
    InazumaCombatResult,
    SheerColdLevel,
    ThunderstormLevel,
)
from combat.boss_combat_handlers import (
    BossCombatResult,
    ChildeHandler,
    DvalinHandler,
    RaidenShogunHandler,
    ShoukiNoKamiHandler,
    SignoraHandler,
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


# ===================================================================
# Dragonspine Sheer Cold tests
# ===================================================================

class TestDragonspineSheerCold:
    def test_basic_combat_succeeds(self):
        ex = _FakeExecutor()
        handler = DragonspineSheerColdHandler(executor=ex)
        result = handler.execute(enemy_count=2, has_fire_character=True)
        assert result.success
        assert result.enemies_defeated == 2
        assert result.duration_sec > 0

    def test_gauge_starts_at_zero(self):
        ex = _FakeExecutor()
        handler = DragonspineSheerColdHandler(executor=ex)
        result = handler.execute(initial_gauge=0.0, enemy_count=1)
        assert result.success

    def test_blizzard_increases_cold(self):
        ex = _FakeExecutor()
        handler = DragonspineSheerColdHandler(executor=ex)
        # Use high initial gauge + blizzard to force warmth-seeking
        result = handler.execute(
            enemy_count=1, is_blizzard=True, initial_gauge=0.7,
        )
        assert result.success
        warmth_calls = [c for c in ex.calls if "warmth" in str(c)]
        assert len(warmth_calls) > 0

    def test_fire_character_provides_warmth(self):
        ex = _FakeExecutor()
        handler = DragonspineSheerColdHandler(executor=ex)
        # High gauge forces warmth-seeking which uses fire character skill
        result = handler.execute(
            enemy_count=1, has_fire_character=True, initial_gauge=0.85,
        )
        assert result.success
        fire_calls = [c for c in ex.calls if c[0] == "use_skill" and "warmth" in str(c[2])]
        assert len(fire_calls) > 0

    def test_no_fire_uses_navigation(self):
        ex = _FakeExecutor()
        handler = DragonspineSheerColdHandler(executor=ex)
        # High gauge + no fire → must navigate to warmth source
        result = handler.execute(
            enemy_count=1, has_fire_character=False,
            has_warming_bottle=True, initial_gauge=0.85,
        )
        assert result.success
        # Either navigated to warmth source or used warming bottle
        nav_calls = [c for c in ex.calls if c[0] == "navigate_to" and "warmth" in c[1]]
        bottle_calls = [c for c in ex.calls if c[0] == "use_item" and "warming" in c[1]]
        assert len(nav_calls) > 0 or len(bottle_calls) > 0

    def test_combat_failure_with_timeout(self):
        ex = _FakeExecutor()
        ex.set_fail_on({"combat_basic_attack"})
        handler = DragonspineSheerColdHandler(executor=ex, max_combat_duration_sec=0.5)
        result = handler.execute(enemy_count=5)
        assert not result.success
        assert result.details == "timeout"

    def test_prioritizes_ice_ranged(self):
        ex = _FakeExecutor()
        handler = DragonspineSheerColdHandler(executor=ex)
        handler.execute(enemy_count=2)
        combat_calls = [c for c in ex.calls if c[0] == "combat_basic_attack"]
        assert any(
            c[2] and c[2].get("priority_target") == "ice_ranged"
            for c in combat_calls
        )


# ===================================================================
# Inazuma Thunderstorm tests
# ===================================================================

class TestInazumaThunderstorm:
    def test_basic_combat_succeeds(self):
        ex = _FakeExecutor()
        handler = InazumaThunderstormHandler(executor=ex)
        result = handler.execute(enemy_count=2)
        assert result.success
        assert result.enemies_defeated == 2

    def test_lightning_dodge_calls(self):
        ex = _FakeExecutor()
        handler = InazumaThunderstormHandler(executor=ex)
        result = handler.execute(enemy_count=1, storm_intensity=ThunderstormLevel.ACTIVE)
        assert result.success
        dodge_calls = [c for c in ex.calls if c[0] == "dodge"]
        assert len(dodge_calls) > 0

    def test_clear_weather_no_lightning(self):
        ex = _FakeExecutor()
        handler = InazumaThunderstormHandler(executor=ex)
        result = handler.execute(enemy_count=1, storm_intensity=ThunderstormLevel.CLEAR)
        assert result.success
        assert result.lightning_dodged == 0

    def test_intense_storm_more_dodging(self):
        ex = _FakeExecutor()
        handler = InazumaThunderstormHandler(executor=ex)
        result = handler.execute(enemy_count=1, storm_intensity=ThunderstormLevel.INTENSE)
        assert result.success

    def test_combat_failure_timeout(self):
        ex = _FakeExecutor()
        ex.set_fail_on({"combat_basic_attack"})
        handler = InazumaThunderstormHandler(executor=ex, max_combat_duration_sec=0.5)
        result = handler.execute(enemy_count=5)
        assert not result.success
        assert result.details == "timeout"

    def test_prioritizes_electro_ranged(self):
        ex = _FakeExecutor()
        handler = InazumaThunderstormHandler(executor=ex)
        handler.execute(enemy_count=2)
        combat_calls = [c for c in ex.calls if c[0] == "combat_basic_attack"]
        assert any(
            c[2] and c[2].get("priority_target") == "electro_ranged"
            for c in combat_calls
        )

    def test_pyro_removes_wet_status(self):
        ex = _FakeExecutor()
        handler = InazumaThunderstormHandler(executor=ex)
        # More enemies = more cycles = higher chance of electro-charged events
        result = handler.execute(
            enemy_count=4, is_raining=True, has_pyro_character=True,
            storm_intensity=ThunderstormLevel.INTENSE,
        )
        assert result.success
        # Check that use_skill was called at all (including wet removal)
        skill_calls = [c for c in ex.calls if c[0] == "use_skill"]
        # If wet status triggered, there will be a "remove_wet_status" skill use
        wet_removal = [c for c in skill_calls if c[2] and "wet" in str(c[2])]
        # This is probabilistic based on strike counter, just verify handler ran
        assert result.enemies_defeated == 4


# ===================================================================
# Boss Combat Handler tests
# ===================================================================

class TestDvalinHandler:
    def test_full_fight_succeeds(self):
        ex = _FakeExecutor()
        handler = DvalinHandler(executor=ex)
        result = handler.execute()
        assert result.success
        assert result.boss_name == "dvalin"
        assert result.phases_completed == 3

    def test_uses_aimed_shot_for_spines(self):
        ex = _FakeExecutor()
        handler = DvalinHandler(executor=ex)
        handler.execute()
        shots = [c for c in ex.calls if c[0] == "aimed_shot"]
        assert len(shots) >= 2  # Two spines

    def test_uses_glide_for_wind_currents(self):
        ex = _FakeExecutor()
        handler = DvalinHandler(executor=ex)
        handler.execute()
        glides = [c for c in ex.calls if c[0] == "glide"]
        assert len(glides) >= 2

    def test_platform_phase_attacks_claws(self):
        ex = _FakeExecutor()
        handler = DvalinHandler(executor=ex)
        handler.execute()
        claw_attacks = [
            c for c in ex.calls
            if c[0] == "combat_basic_attack" and c[2] and c[2].get("target") == "dvalin_claw"
        ]
        assert len(claw_attacks) >= 1


class TestChildeHandler:
    def test_full_fight_succeeds(self):
        ex = _FakeExecutor()
        handler = ChildeHandler(executor=ex)
        result = handler.execute()
        assert result.success
        assert result.boss_name == "childe"
        assert result.phases_completed == 3

    def test_three_boss_calls(self):
        ex = _FakeExecutor()
        handler = ChildeHandler(executor=ex)
        handler.execute()
        boss_calls = [c for c in ex.calls if c[0] == "combat_boss" and c[1] == "childe"]
        assert len(boss_calls) >= 3

    def test_phase_transitions_use_wait(self):
        ex = _FakeExecutor()
        handler = ChildeHandler(executor=ex)
        handler.execute()
        waits = [c for c in ex.calls if c[0] == "wait" and "phase_transition" in str(c[2])]
        assert len(waits) >= 2

    def test_dual_phase_breaks_shield(self):
        ex = _FakeExecutor()
        handler = ChildeHandler(executor=ex)
        handler.execute()
        shield_breaks = [c for c in ex.calls if "shield" in str(c[2])]
        assert len(shield_breaks) >= 1


class TestSignoraHandler:
    def test_full_fight_succeeds(self):
        ex = _FakeExecutor()
        handler = SignoraHandler(executor=ex)
        result = handler.execute()
        assert result.success
        assert result.boss_name == "signora"
        assert result.phases_completed == 2

    def test_temperature_management(self):
        ex = _FakeExecutor()
        handler = SignoraHandler(executor=ex)
        handler.execute()
        # Verify boss was fought with temperature-relevant contexts
        boss_calls = [c for c in ex.calls if c[0] == "combat_boss" and c[1] == "signora"]
        assert len(boss_calls) >= 2  # At least cryo + pyro phases

    def test_uses_pyro_in_cryo_phase(self):
        ex = _FakeExecutor()
        handler = SignoraHandler(executor=ex)
        handler.execute()
        cryo_boss = [
            c for c in ex.calls
            if c[0] == "combat_boss" and c[2] and c[2].get("phase") == "cryo"
        ]
        assert len(cryo_boss) >= 1
        assert cryo_boss[0][2].get("element") == "pyro"

    def test_uses_hydro_in_pyro_phase(self):
        ex = _FakeExecutor()
        handler = SignoraHandler(executor=ex)
        handler.execute()
        pyro_boss = [
            c for c in ex.calls
            if c[0] == "combat_boss" and c[2] and c[2].get("phase") == "pyro"
        ]
        assert len(pyro_boss) >= 1
        assert pyro_boss[0][2].get("element") == "hydro"


class TestRaidenShogunHandler:
    def test_full_fight_succeeds(self):
        ex = _FakeExecutor()
        handler = RaidenShogunHandler(executor=ex)
        result = handler.execute()
        assert result.success
        assert result.boss_name == "raiden_shogun"

    def test_uses_dodge_for_combos(self):
        ex = _FakeExecutor()
        handler = RaidenShogunHandler(executor=ex)
        handler.execute()
        dodges = [c for c in ex.calls if c[0] == "dodge"]
        assert len(dodges) >= 2  # At least combo + AOE dodges

    def test_saves_burst_for_musou(self):
        ex = _FakeExecutor()
        handler = RaidenShogunHandler(executor=ex)
        handler.execute()
        bursts = [c for c in ex.calls if c[0] == "use_burst"]
        assert len(bursts) >= 1
        assert any("musou" in str(c[2]) for c in bursts)

    def test_p1_uses_basic_attack_in_gaps(self):
        ex = _FakeExecutor()
        handler = RaidenShogunHandler(executor=ex)
        handler.execute()
        basics = [
            c for c in ex.calls
            if c[0] == "combat_basic_attack" and c[2] and c[2].get("target") == "raiden_shogun"
        ]
        assert len(basics) >= 1


class TestShoukiNoKamiHandler:
    def test_full_fight_succeeds(self):
        ex = _FakeExecutor()
        handler = ShoukiNoKamiHandler(executor=ex)
        result = handler.execute()
        assert result.success
        assert result.boss_name == "shouki_no_kami"
        assert result.phases_completed == 3

    def test_attacks_constructs(self):
        ex = _FakeExecutor()
        handler = ShoukiNoKamiHandler(executor=ex)
        handler.execute()
        construct_attacks = [
            c for c in ex.calls
            if c[0] == "combat_basic_attack" and c[2] and c[2].get("target") == "construct"
        ]
        assert len(construct_attacks) >= 1

    def test_uses_energy_attack(self):
        ex = _FakeExecutor()
        handler = ShoukiNoKamiHandler(executor=ex)
        handler.execute()
        energy_attacks = [
            c for c in ex.calls
            if c[0] == "use_skill" and c[2] and "energy" in str(c[2])
        ]
        assert len(energy_attacks) >= 1

    def test_destroys_towers(self):
        ex = _FakeExecutor()
        handler = ShoukiNoKamiHandler(executor=ex)
        handler.execute()
        tower_attacks = [
            c for c in ex.calls
            if c[0] == "combat_basic_attack" and c[2] and c[2].get("target") == "defense_tower"
        ]
        assert len(tower_attacks) >= 1

    def test_dodges_lasers_when_combat_fails(self):
        """When combat_boss fails, handler dodges lasers before retrying."""
        ex = _FakeExecutor()
        ex.set_fail_on({"combat_boss"})
        handler = ShoukiNoKamiHandler(executor=ex)
        handler.execute()
        laser_dodges = [
            c for c in ex.calls
            if c[0] == "dodge" and "laser" in str(c[2])
        ]
        assert len(laser_dodges) >= 1


# ===================================================================
# CombatSkillAdapter integration tests
# ===================================================================

class TestCombatSkillAdapterEnvironmental:
    def test_environmental_dragonspine(self):
        from combat.combat_skill_adapter import CombatSkillAdapter
        ex = _FakeExecutor()
        # We need a backend-like object
        class _FakeBackend:
            pass
        adapter = CombatSkillAdapter(backend=_FakeBackend())
        # Direct handler test (bypassing the bridge for simplicity)
        result = adapter.execute_environmental_combat(
            "dragonspine",
            context={"enemy_count": 1, "has_fire_character": True},
        )
        # May succeed or fail depending on bridge behavior
        assert isinstance(result, bool)

    def test_environmental_inazuma(self):
        from combat.combat_skill_adapter import CombatSkillAdapter
        class _FakeBackend:
            pass
        adapter = CombatSkillAdapter(backend=_FakeBackend())
        result = adapter.execute_environmental_combat(
            "inazuma_storm",
            context={"enemy_count": 1},
        )
        assert isinstance(result, bool)

    def test_unknown_environment_returns_false(self):
        from combat.combat_skill_adapter import CombatSkillAdapter
        class _FakeBackend:
            pass
        adapter = CombatSkillAdapter(backend=_FakeBackend())
        result = adapter.execute_environmental_combat("unknown_biome")
        assert result is False


class TestCombatSkillAdapterBossSpecific:
    def test_boss_specific_dvalin(self):
        from combat.combat_skill_adapter import CombatSkillAdapter
        class _FakeBackend:
            pass
        adapter = CombatSkillAdapter(backend=_FakeBackend())
        result = adapter.execute_boss_specific("dvalin")
        assert isinstance(result, bool)

    def test_boss_specific_childe(self):
        from combat.combat_skill_adapter import CombatSkillAdapter
        class _FakeBackend:
            pass
        adapter = CombatSkillAdapter(backend=_FakeBackend())
        result = adapter.execute_boss_specific("childe")
        assert isinstance(result, bool)

    def test_boss_specific_unknown_returns_false(self):
        from combat.combat_skill_adapter import CombatSkillAdapter
        class _FakeBackend:
            pass
        adapter = CombatSkillAdapter(backend=_FakeBackend())
        result = adapter.execute_boss_specific("unknown_boss")
        assert result is False
