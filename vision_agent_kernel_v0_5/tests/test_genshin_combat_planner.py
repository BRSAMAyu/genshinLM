from __future__ import annotations

import pytest

from combat.genshin_combat_planner import (
    CombatAction,
    CombatPlaybook,
    FallbackStrategy,
    GenshinCombatPlanner,
    PriorityTrigger,
)
from combat.genshin_playbook_executor import PlaybookExecutor, PlaybookState


# ---------------------------------------------------------------------------
# GenshinCombatPlanner tests
# ---------------------------------------------------------------------------


class TestGeneratePlaybookVaporizeTeam:
    def test_vaporize_team_chain(self) -> None:
        planner = GenshinCombatPlanner()
        pb = planner.generate_playbook(
            team_elements=["pyro", "hydro"],
            team_characters=["Hu Tao", "Xingqiu"],
            enemy_id="pyro_slime",
            enemy_weaknesses=["hydro", "cryo"],
        )
        assert "Vaporize" in pb.elemental_chain
        assert pb.team == ["Hu Tao", "Xingqiu"]
        assert pb.enemy == "pyro_slime"
        assert len(pb.default_rotation) > 0

    def test_vaporize_includes_e_skills(self) -> None:
        planner = GenshinCombatPlanner()
        pb = planner.generate_playbook(
            team_elements=["pyro", "hydro"],
            team_characters=["Hu Tao", "Xingqiu"],
            enemy_id="hilichurl",
        )
        actions = [a.action for a in pb.default_rotation]
        assert "e_skill" in actions
        assert "q_burst" in actions


class TestGeneratePlaybookPhysicalTeam:
    def test_no_reactions_normal_attacks(self) -> None:
        planner = GenshinCombatPlanner()
        pb = planner.generate_playbook(
            team_elements=["physical"],
            team_characters=["Eula"],
            enemy_id="ruin_guard",
        )
        assert pb.elemental_chain == []
        actions = [a.action for a in pb.default_rotation]
        assert "normal_attack" in actions
        assert "e_skill" in actions

    def test_physical_rotation_has_fallback(self) -> None:
        planner = GenshinCombatPlanner()
        pb = planner.generate_playbook(
            team_elements=["physical"],
            team_characters=["Eula"],
            enemy_id="ruin_guard",
        )
        assert pb.fallback.on_target_lost == "re_acquire_target"
        assert pb.fallback.on_timeout == "fallback_basic_loop"


class TestPriorityTriggersDangerHigh:
    def test_danger_trigger_present(self) -> None:
        planner = GenshinCombatPlanner()
        triggers = planner._build_priority_triggers()
        danger_triggers = [t for t in triggers if "danger" in t.condition]
        assert len(danger_triggers) >= 1
        dt = danger_triggers[0]
        assert dt.action == "dodge"
        assert dt.priority == 0
        assert dt.interrupt is True

    def test_danger_trigger_condition(self) -> None:
        planner = GenshinCombatPlanner()
        triggers = planner._build_priority_triggers()
        danger = [t for t in triggers if "danger" in t.condition][0]
        assert danger.condition == "danger > 0.7"


class TestPriorityTriggersLowHp:
    def test_hp_trigger_present(self) -> None:
        planner = GenshinCombatPlanner()
        triggers = planner._build_priority_triggers()
        hp_triggers = [t for t in triggers if "hp" in t.condition]
        assert len(hp_triggers) >= 1
        ht = hp_triggers[0]
        assert ht.action == "switch"
        assert ht.priority == 0
        assert ht.interrupt is True

    def test_hp_trigger_condition(self) -> None:
        planner = GenshinCombatPlanner()
        triggers = planner._build_priority_triggers()
        hp = [t for t in triggers if "hp" in t.condition][0]
        assert hp.condition == "hp < 0.3"


class TestReactionChainTargetsWeakness:
    def test_hydro_weakness_prioritized(self) -> None:
        planner = GenshinCombatPlanner()
        chain = planner._plan_reaction_chain(
            team_elements=["pyro", "hydro", "cryo"],
            weaknesses=["hydro"],
        )
        vaporize_idx = chain.index("Vaporize") if "Vaporize" in chain else 999
        non_weakness_reactions = [
            name for name in chain
            if name not in ("Vaporize", "Vaporize_Reverse", "Frozen")
        ]
        for other in non_weakness_reactions:
            other_idx = chain.index(other) if other in chain else 999
            assert vaporize_idx < other_idx, (
                f"Vaporize should come before {other} when hydro is a weakness"
            )

    def test_chain_sorted_by_score(self) -> None:
        planner = GenshinCombatPlanner()
        chain = planner._plan_reaction_chain(
            team_elements=["pyro", "hydro"],
            weaknesses=["hydro"],
        )
        assert len(chain) > 0
        assert chain[0] in ("Vaporize", "Vaporize_Reverse")


class TestLlmPromptIncludesTeamAndEnemy:
    def test_prompt_contains_team(self) -> None:
        planner = GenshinCombatPlanner()
        pb = CombatPlaybook(
            playbook_id="test_pb",
            team=["Hu Tao", "Xingqiu"],
            enemy="pyro_slime",
            default_rotation=[
                CombatAction(action="e_skill", character=1, condition="skill_e_ready", priority=40),
            ],
            priority_triggers=[],
            fallback=FallbackStrategy(
                on_target_lost="re_acquire",
                on_combo_break="reset",
                on_all_dead="respawn",
                on_timeout="basic",
            ),
            elemental_chain=["Vaporize"],
        )
        prompt = planner.generate_llm_prompt(
            team=["Hu Tao", "Xingqiu"], enemy="pyro_slime", playbook=pb,
        )
        assert "Hu Tao" in prompt
        assert "Xingqiu" in prompt
        assert "pyro_slime" in prompt
        assert "Vaporize" in prompt

    def test_prompt_contains_rotation(self) -> None:
        planner = GenshinCombatPlanner()
        pb = CombatPlaybook(
            playbook_id="test_pb",
            team=["Diluc"],
            enemy="cryo_slime",
            default_rotation=[
                CombatAction(action="normal_attack", character=1, repeat=5, priority=50),
            ],
            priority_triggers=[],
            fallback=FallbackStrategy(
                on_target_lost="re_acquire",
                on_combo_break="reset",
                on_all_dead="respawn",
                on_timeout="basic",
            ),
            elemental_chain=[],
        )
        prompt = planner.generate_llm_prompt(
            team=["Diluc"], enemy="cryo_slime", playbook=pb,
        )
        assert "normal_attack" in prompt


# ---------------------------------------------------------------------------
# PlaybookExecutor tests
# ---------------------------------------------------------------------------


def _make_playbook(
    rotation: list[CombatAction] | None = None,
    triggers: list[PriorityTrigger] | None = None,
) -> CombatPlaybook:
    return CombatPlaybook(
        playbook_id="test_pb",
        team=["TestChar"],
        enemy="test_enemy",
        default_rotation=rotation or [
            CombatAction(action="normal_attack", character=1, repeat=3, priority=50),
            CombatAction(action="e_skill", character=1, condition="skill_e_ready", priority=40),
        ],
        priority_triggers=triggers or [],
        fallback=FallbackStrategy(
            on_target_lost="re_acquire",
            on_combo_break="reset",
            on_all_dead="respawn",
            on_timeout="basic",
        ),
        elemental_chain=[],
    )


class TestPlaybookExecutorStartAndTick:
    def test_start_sets_executing(self) -> None:
        ex = PlaybookExecutor()
        pb = _make_playbook()
        ex.start(pb)
        assert ex.state == PlaybookState.EXECUTING

    def test_tick_returns_action(self) -> None:
        ex = PlaybookExecutor()
        rotation = [
            CombatAction(action="normal_attack", character=1, repeat=3, priority=50),
            CombatAction(action="e_skill", character=1, priority=40),
        ]
        pb = _make_playbook(rotation=rotation)
        ex.start(pb)
        action = ex.tick(dt_ms=100.0)
        assert action is not None
        assert action.action == "normal_attack"

    def test_tick_advances_through_rotation(self) -> None:
        ex = PlaybookExecutor()
        rotation = [
            CombatAction(action="normal_attack", character=1, priority=50),
            CombatAction(action="e_skill", character=1, priority=40),
        ]
        pb = _make_playbook(rotation=rotation)
        ex.start(pb)
        a1 = ex.tick(dt_ms=100.0)
        assert a1 is not None and a1.action == "normal_attack"
        a2 = ex.tick(dt_ms=100.0)
        assert a2 is not None and a2.action == "e_skill"


class TestPlaybookExecutorInterruptDodge:
    def test_danger_interrupt_returns_dodge(self) -> None:
        triggers = [
            PriorityTrigger(
                condition="danger > 0.7", action="dodge", priority=0, interrupt=True,
            ),
        ]
        pb = _make_playbook(triggers=triggers)
        ex = PlaybookExecutor()
        ex.start(pb)
        action = ex.tick(
            dt_ms=100.0,
            danger_signals={"overall_danger": 0.85},
        )
        assert action is not None
        assert action.action == "dodge"
        assert ex.state == PlaybookState.INTERRUPTED

    def test_no_danger_no_interrupt(self) -> None:
        triggers = [
            PriorityTrigger(
                condition="danger > 0.7", action="dodge", priority=0, interrupt=True,
            ),
        ]
        pb = _make_playbook(triggers=triggers)
        ex = PlaybookExecutor()
        ex.start(pb)
        action = ex.tick(
            dt_ms=100.0,
            danger_signals={"overall_danger": 0.3},
        )
        assert action is not None
        assert action.action != "dodge"
        assert ex.state == PlaybookState.EXECUTING


class TestPlaybookExecutorCheckpointResume:
    def test_snapshot_and_restore(self) -> None:
        rotation = [
            CombatAction(action="normal_attack", character=1, priority=50),
            CombatAction(action="e_skill", character=1, priority=40),
            CombatAction(action="q_burst", character=1, priority=30),
        ]
        pb = _make_playbook(rotation=rotation)
        ex = PlaybookExecutor()
        ex.start(pb)

        ex.tick(dt_ms=100.0)
        ex.tick(dt_ms=100.0)
        snap = ex.snapshot()
        assert snap.current_step_index == 2
        assert snap.elapsed_ms == pytest.approx(200.0)
        assert snap.interrupts_handled == 0

        ex.tick(dt_ms=100.0)
        assert ex.snapshot().current_step_index == 0 or ex.snapshot().current_step_index == 1

        ex.restore(snap)
        restored = ex.snapshot()
        assert restored.current_step_index == 2
        assert restored.elapsed_ms == pytest.approx(200.0)
        assert ex.state == PlaybookState.EXECUTING

    def test_resume_continues_rotation(self) -> None:
        rotation = [
            CombatAction(action="normal_attack", character=1, priority=50),
            CombatAction(action="e_skill", character=1, priority=40),
        ]
        pb = _make_playbook(rotation=rotation)
        ex = PlaybookExecutor()
        ex.start(pb)

        ex.tick(dt_ms=50.0)
        snap = ex.snapshot()

        ex.tick(dt_ms=50.0)
        ex.tick(dt_ms=50.0)

        ex.restore(snap)
        action = ex.tick(dt_ms=50.0)
        assert action is not None
        assert action.action == "e_skill"


class TestEvaluateConditionParsing:
    def test_always_true(self) -> None:
        ex = PlaybookExecutor()
        assert ex._evaluate_condition("always", {}) is True

    def test_empty_condition_true(self) -> None:
        ex = PlaybookExecutor()
        assert ex._evaluate_condition("", {}) is True

    def test_skill_e_ready(self) -> None:
        ex = PlaybookExecutor()
        assert ex._evaluate_condition("skill_e_ready", {"skill_e_ready": True}) is True
        assert ex._evaluate_condition("skill_e_ready", {"skill_e_ready": False}) is False

    def test_energy_full(self) -> None:
        ex = PlaybookExecutor()
        assert ex._evaluate_condition("energy_full", {"energy_full": True}) is True
        assert ex._evaluate_condition("energy_full", {"energy_full": False}) is False

    def test_hp_less_than_threshold(self) -> None:
        ex = PlaybookExecutor()
        assert ex._evaluate_condition("hp < 0.3", {"active_hp": 0.2}) is True
        assert ex._evaluate_condition("hp < 0.3", {"active_hp": 0.5}) is False

    def test_danger_greater_than_threshold(self) -> None:
        ex = PlaybookExecutor()
        assert ex._evaluate_condition("danger > 0.7", {"danger": 0.8}) is True
        assert ex._evaluate_condition("danger > 0.7", {"danger": 0.5}) is False

    def test_generic_comparison(self) -> None:
        ex = PlaybookExecutor()
        assert ex._evaluate_condition("value > 0.5", {"value": 0.8}) is True
        assert ex._evaluate_condition("value < 0.5", {"value": 0.3}) is True
        assert ex._evaluate_condition("value > 0.5", {"value": 0.3}) is False

    def test_unknown_condition_false(self) -> None:
        ex = PlaybookExecutor()
        assert ex._evaluate_condition("unknown_cond", {}) is False
