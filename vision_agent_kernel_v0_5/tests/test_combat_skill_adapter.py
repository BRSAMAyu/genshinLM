"""Tests for CombatSkillAdapter: semantic combat action bridge."""
from __future__ import annotations

from combat.combat_skill_adapter import CombatSkillAdapter, CombatSkillAdapterConfig
from execution.console_backend import ConsoleInputBackend


class _FakeBus:
    class _Slot:
        def get(self):
            return None

    latest_observation = _Slot()


def test_basic_attack_executes():
    adapter = CombatSkillAdapter(
        backend=ConsoleInputBackend(),
        config=CombatSkillAdapterConfig(default_combat_duration_sec=1.0),
    )
    result = adapter.execute_basic_attack(duration_sec=0.5)
    assert result is True


def test_execute_combat_with_unknown_enemy():
    adapter = CombatSkillAdapter(
        backend=ConsoleInputBackend(),
        state_bus=_FakeBus(),
        config=CombatSkillAdapterConfig(default_combat_duration_sec=30.0, max_retries=0),
    )
    result = adapter.execute_combat(
        team_elements=["pyro", "hydro", "cryo", "anemo"],
        team_characters=["hutao", "xingqiu", "ganyu", "venti"],
        enemy_id="hilichurl_camp",
        duration_sec=30.0,
    )
    assert result is True


def test_execute_combat_with_elemental_weakness():
    adapter = CombatSkillAdapter(
        backend=ConsoleInputBackend(),
        state_bus=_FakeBus(),
        config=CombatSkillAdapterConfig(default_combat_duration_sec=30.0, max_retries=0),
    )
    result = adapter.execute_combat(
        team_elements=["pyro", "hydro"],
        team_characters=["hutao", "xingqiu"],
        enemy_id="abyss_mage_water",
        enemy_weaknesses=["electro", "dendro"],
        duration_sec=30.0,
    )
    assert result is True


def test_boss_combat_generates_playbook():
    adapter = CombatSkillAdapter(
        backend=ConsoleInputBackend(),
        state_bus=_FakeBus(),
        config=CombatSkillAdapterConfig(default_combat_duration_sec=1.0),
    )
    result = adapter.execute_boss_combat(
        team_elements=["pyro", "hydro", "cryo", "anemo"],
        team_characters=["hutao", "xingqiu", "ganyu", "venti"],
        duration_sec=2.0,
    )
    assert result is True


def test_get_combat_context_no_bus():
    adapter = CombatSkillAdapter(backend=ConsoleInputBackend())
    ctx = adapter.get_combat_context()
    assert ctx.target_visible is False  # safe default: no target without bus
    assert ctx.hp_ratio == 1.0


def test_get_combat_context_with_fake_bus():
    adapter = CombatSkillAdapter(backend=ConsoleInputBackend(), state_bus=_FakeBus())
    ctx = adapter.get_combat_context()
    assert ctx.target_visible is False  # no observation → no target visible


def test_rotation_to_steps_converts_correctly():
    from combat.genshin_combat_planner import CombatAction
    rotation = [
        CombatAction("normal_attack", 1, repeat=3),
        CombatAction("e_skill", 2, condition="skill_e_ready"),
        CombatAction("q_burst", 3, condition="energy_full"),
        CombatAction("switch", 4),
    ]
    steps = CombatSkillAdapter._rotation_to_steps(rotation)
    assert len(steps) == 4
    assert steps[0]["type"] == "attack"
    assert steps[0]["duration"] == 1.5
    assert steps[1]["type"] == "skill_e"
    assert steps[2]["type"] == "burst_q"
    assert steps[3]["type"] == "switch"
    assert steps[3]["character"] == 4


def test_rotation_to_steps_handles_all_action_types():
    from combat.genshin_combat_planner import CombatAction
    rotation = [
        CombatAction("dodge", 1),
        CombatAction("charge_attack", 1, repeat=2),
        CombatAction("dash", 2),
        CombatAction("heal", 3),
        CombatAction("shield", 4),
        CombatAction("retreat", 1),
    ]
    steps = CombatSkillAdapter._rotation_to_steps(rotation)
    assert len(steps) == 6
    assert steps[0]["type"] == "dodge"
    assert steps[1]["type"] == "attack"  # charge_attack → attack
    assert steps[2]["type"] == "dodge"   # dash → dodge
    assert steps[3]["type"] == "skill_e" # heal → skill_e
    assert steps[4]["type"] == "skill_e" # shield → skill_e
    assert steps[5]["type"] == "dodge"   # retreat → dodge


def test_execute_combat_single_element_team():
    adapter = CombatSkillAdapter(
        backend=ConsoleInputBackend(),
        config=CombatSkillAdapterConfig(default_combat_duration_sec=30.0, max_retries=0),
    )
    result = adapter.execute_combat(
        team_elements=["pyro"],
        team_characters=["amber"],
        enemy_id="slime_pyro",
        duration_sec=30.0,
    )
    assert result is True
