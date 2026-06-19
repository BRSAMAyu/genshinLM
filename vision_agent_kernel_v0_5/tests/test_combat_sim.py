"""Tests for the reactive combat controller + combat-sim dogfood (Phase 2)."""
from __future__ import annotations

import pytest

from combat.reactive_combat_controller import (
    CombatCharView,
    CombatView,
    ReactiveCombatController,
)
from harness.batch import run_batch
from harness.core import Scenario, ScenarioResult
from harness.runner import ScenarioRunner
from harness.sim.combat_world import CombatPolicy, CombatWorldEnv, make_combat_scenarios


def _char(i, role="dps", hp=1.0, energy=0.0, skill=True, burst=False, element="pyro") -> CombatCharView:
    return CombatCharView(
        index=i, name=role, element=element, role=role,
        hp_ratio=hp, energy_ratio=energy, skill_ready=skill, burst_ready=burst,
    )


def _view(chars, active=0, enemy_hp=1.0, aura="", incoming=False, can_dodge=True,
          weaknesses=()) -> CombatView:
    return CombatView(
        active_index=active, chars=tuple(chars), enemy_hp_ratio=enemy_hp,
        enemy_aura=aura, incoming_attack=incoming, can_dodge=can_dodge,
        enemy_weaknesses=tuple(weaknesses),
    )


# --- controller priority contract ------------------------------------------


def test_dodges_incoming_attack_first() -> None:
    c = ReactiveCombatController()
    act = c.decide(_view([_char(0, burst=True)], incoming=True, can_dodge=True))
    assert act.kind == "dodge"


def test_no_dodge_when_on_cooldown_falls_through() -> None:
    c = ReactiveCombatController()
    act = c.decide(_view([_char(0, skill=True)], incoming=True, can_dodge=False))
    assert act.kind != "dodge"  # can't dodge -> proceeds to offense


def test_routes_to_healer_when_low() -> None:
    c = ReactiveCombatController()
    chars = [_char(0, role="dps", hp=0.3), _char(1, role="healer", hp=1.0, skill=True)]
    act = c.decide(_view(chars, active=0))
    assert act.kind == "switch" and act.switch_to == 1


def test_heals_when_healer_active_and_low() -> None:
    c = ReactiveCombatController()
    chars = [_char(0, role="healer", hp=0.3, skill=True)]
    act = c.decide(_view(chars, active=0))
    assert act.kind == "heal"


def test_bursts_when_ready() -> None:
    c = ReactiveCombatController()
    act = c.decide(_view([_char(0, burst=True)], enemy_hp=0.9))
    assert act.kind == "burst"


def test_does_not_waste_burst_on_near_dead_enemy() -> None:
    c = ReactiveCombatController()
    act = c.decide(_view([_char(0, burst=True, skill=True)], enemy_hp=0.02))
    assert act.kind != "burst"  # saves burst, uses skill instead


def test_uses_skill_then_attack() -> None:
    c = ReactiveCombatController()
    assert c.decide(_view([_char(0, skill=True, burst=False)])).kind == "skill"
    assert c.decide(_view([_char(0, skill=False, burst=False)])).kind == "attack"


def test_rotates_to_offfield_ready_skill() -> None:
    c = ReactiveCombatController()
    chars = [_char(0, role="dps", skill=False), _char(1, role="sub", skill=True)]
    act = c.decide(_view(chars, active=0))
    assert act.kind == "switch" and act.switch_to == 1


# --- weakness/reaction-aware rotation (curated data is load-bearing) --------


def test_rotation_picks_weakness_element_over_field_order() -> None:
    # Two ready off-field subs; index 1 is anemo (no weakness), index 2 is cryo
    # (a weakness). Without weakness data, field order would pick index 1; the
    # curated weakness must flip the choice to index 2.
    c = ReactiveCombatController()
    chars = [
        _char(0, role="dps", skill=False),
        _char(1, role="sub", skill=True, element="anemo"),
        _char(2, role="sub", skill=True, element="cryo"),
    ]
    no_data = c.decide(_view(chars, active=0))
    with_weak = c.decide(_view(chars, active=0, weaknesses=("cryo",)))
    assert no_data.switch_to == 1                  # field order without data
    assert with_weak.switch_to == 2                # weakness flips the target
    assert "weakness" in with_weak.reason


def test_rotation_prefers_reaction_trigger_with_aura() -> None:
    # Enemy has a hydro aura; pyro triggers vaporize. Pick the pyro char even if
    # it's later in field order than an inert (matching-aura) option.
    c = ReactiveCombatController()
    chars = [
        _char(0, role="dps", skill=False),
        _char(1, role="sub", skill=True, element="hydro"),   # same as aura -> no reaction
        _char(2, role="sub", skill=True, element="pyro"),    # triggers reaction
    ]
    act = c.decide(_view(chars, active=0, aura="hydro"))
    assert act.switch_to == 2
    assert "reaction" in act.reason


def test_weakness_bonus_speeds_clear_in_sim() -> None:
    # A team whose element matches the enemy weakness should clear faster (fewer
    # steps) than one that doesn't — proves the sim models the weakness bonus.
    base_team = [{"name": "dps", "element": "cryo", "role": "dps", "hp": 1000.0, "atk": 70.0,
                  "skill_cd": 6, "skill_mult": 3.5, "burst_cost": 30.0, "burst_mult": 7.0}]

    def run(weaknesses):
        s = Scenario(
            scenario_id="wk", objective="clear", tags=("combat", "mob"),
            setup={"team": base_team,
                   "enemy": {"hp": 1200.0, "atk": 30.0, "aura": "", "attack_interval": 8,
                             "telegraph_lead": 1, "weaknesses": weaknesses},
                   "max_ticks": 300},
            max_steps=300,
        )
        return ScenarioRunner(CombatWorldEnv(), CombatPolicy()).run(s)

    weak = run(["cryo"])    # enemy weak to our element
    tough = run(["pyro"])   # enemy weak to a different element
    assert weak.passed and tough.passed
    assert weak.steps < tough.steps, f"weak={weak.steps} tough={tough.steps}"


# --- dogfood: real controller in the combat sim ----------------------------


def test_single_mob_fight_is_winnable() -> None:
    scenario = Scenario(
        scenario_id="mob1", objective="defeat mob",
        setup={
            "team": [{"name": "dps", "element": "pyro", "role": "dps", "hp": 1000.0, "atk": 70.0,
                      "skill_cd": 6, "skill_mult": 3.5, "burst_cost": 30.0, "burst_mult": 7.0}],
            "enemy": {"hp": 900.0, "atk": 60.0, "aura": "hydro", "attack_interval": 6, "telegraph_lead": 1},
            "max_ticks": 300,
        },
        max_steps=300, tags=("combat", "mob"),
    )
    result = ScenarioRunner(CombatWorldEnv(), CombatPolicy()).run(scenario)
    assert result.passed, f"{result.failure_code}: {result.reason}"


def test_combat_batch_clear_rate_and_clusters() -> None:
    scenarios = make_combat_scenarios(45, seed=5)

    def run_one(s: Scenario) -> ScenarioResult:
        return ScenarioRunner(CombatWorldEnv(), CombatPolicy()).run(s)

    report = run_batch(scenarios, run_one)
    # Reference controller should clear a solid majority across mixed tiers;
    # hardest tiers remain a real failure cluster to drive future iterations.
    assert report.pass_rate >= 0.55, (
        f"pass_rate={report.pass_rate:.2f}; clusters={[(c.signature, c.count) for c in report.clusters]}"
    )
