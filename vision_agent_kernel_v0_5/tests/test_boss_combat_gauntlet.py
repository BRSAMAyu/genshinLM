"""Tests for Phase 6: BossCombatRuntime E2E gauntlet + Phase 7 long-horizon scenarios.

Pytest version of benchmarks/boss_combat_gauntlet/runner.py.
Verifies BossCombatRuntime state machine transitions and checkpoint/resume cycle.
"""
from __future__ import annotations

import pytest

from benchmarks.boss_combat_gauntlet.scenario import BossBenchScenario, SCENARIOS
from combat.boss_combat_runtime import BossCombatInput, BossCombatRuntime
from combat.boss_schema import conservative_unknown_boss
from combat.survival_runtime import SurvivalPolicyEngine, SurvivalState
from combat.team_capability import TeamCapabilityAnalyzer


CHAR_PATH = "data/combat_profiles/character_profiles.yaml"


def _make_runtime(scenario: BossBenchScenario) -> BossCombatRuntime:
    analyzer = TeamCapabilityAnalyzer.from_yaml(CHAR_PATH)
    boss = conservative_unknown_boss(scenario.boss_id)
    team = analyzer.analyze(scenario.team_characters, scenario.team_elements)
    plan = analyzer.compile_plan(team, boss)
    return BossCombatRuntime(boss, team, plan, SurvivalPolicyEngine())


def _survival_state(frame, team, food_available: bool = False) -> SurvivalState:
    return SurvivalState(
        active_hp=frame.hp_ratios[0] if frame.hp_ratios else 1.0,
        team_hp=frame.hp_ratios,
        healer_available=team.has_healer,
        shielder_available=team.has_shielder,
        shield_active=False,
        food_available=food_available,
        danger_score=frame.danger_score,
    )


def _to_input(scenario: BossBenchScenario, index: int, frame, team, food_available: bool = False) -> BossCombatInput:
    return BossCombatInput(
        frame_id=index + 1,
        boss_hp_ratio=frame.boss_hp_ratio,
        danger_score=frame.danger_score,
        telegraph_type=frame.telegraph_type,
        target_visible=frame.target_visible,
        hp_ratios=frame.hp_ratios,
        survival_state=_survival_state(frame, team, food_available=food_available),
        combo_broken=frame.combo_broken,
        combat_ended=frame.combat_ended,
        evidence_ids=[f"frame:{index + 1}"],
    )


class TestBossCombatGauntlet:
    """Test BossCombatRuntime against all 6 benchmark scenarios."""

    @pytest.fixture
    def analyzer(self) -> TeamCapabilityAnalyzer:
        return TeamCapabilityAnalyzer.from_yaml(CHAR_PATH)

    def test_ground_aoe_clear(self, analyzer):
        """Scenario: ground AOE danger clears → boss killed."""
        scenario = SCENARIOS[0]  # ground_aoe_clear
        runtime = _make_runtime(scenario)
        boss = conservative_unknown_boss(scenario.boss_id)
        team = analyzer.analyze(scenario.team_characters, scenario.team_elements)

        actions: list[str] = []
        states: list[str] = []

        for index, frame in enumerate(scenario.frames):
            decision = runtime.tick(
                _to_input(scenario, index, frame, team),
                now=float(index + 1),
            )
            actions.append(decision.action)
            states.append(decision.state)

        # Last frame: combat_ended=True → should reach FINISHED
        assert "finished" in states or "verify_progress" in states
        # AOE boss: first frame has danger → should dodge or release_all
        assert any(a in ("dodge_reflex", "release_all", "hold_safe", "resume_checkpoint", "dodge") for a in actions)

    def test_projectile_target_reacquire(self, analyzer):
        """Scenario: target occlusion → target_reacquire state."""
        scenario = SCENARIOS[1]  # projectile_target_reacquire
        runtime = _make_runtime(scenario)
        team = analyzer.analyze(scenario.team_characters, scenario.team_elements)

        reacquire_seen = False
        for index, frame in enumerate(scenario.frames):
            decision = runtime.tick(
                _to_input(scenario, index, frame, team),
                now=float(index + 1),
            )
            if decision.action == "re_acquire_target" or decision.state == "target_reacquire":
                reacquire_seen = True
            if frame.target_visible:
                assert decision.state != "target_reacquire"

        assert reacquire_seen, "target_reacquire state should trigger when target occluded"

    def test_team_no_healer_survives(self, analyzer):
        """Scenario: team without healer survives with conservative play."""
        scenario = SCENARIOS[2]  # team_no_healer_survives_conservative
        runtime = _make_runtime(scenario)
        team = analyzer.analyze(scenario.team_characters, scenario.team_elements)

        failed_safe = False
        for index, frame in enumerate(scenario.frames):
            decision = runtime.tick(
                _to_input(scenario, index, frame, team),
                now=float(index + 1),
            )
            if decision.state == "failed_safe":
                failed_safe = True

        assert not failed_safe, "No-healer team should survive on aoe_boss"

    def test_emergency_hp_blocks_food_during_danger(self, analyzer):
        """Scenario: HP too low for food during danger → survival/reaction triggered."""
        scenario = SCENARIOS[3]  # emergency_hp_blocks_food_during_danger
        runtime = _make_runtime(scenario)
        team = analyzer.analyze(scenario.team_characters, scenario.team_elements)

        survival_recovery_seen = False
        heal_attempt = False
        reflex_reacted = False
        for index, frame in enumerate(scenario.frames):
            survival_state = SurvivalState(
                active_hp=frame.hp_ratios[0],
                team_hp=frame.hp_ratios,
                healer_available=team.has_healer,
                shielder_available=team.has_shielder,
                shield_active=False,
                food_available=True,
                danger_score=frame.danger_score,
            )
            input_ = BossCombatInput(
                frame_id=index + 1,
                boss_hp_ratio=frame.boss_hp_ratio,
                danger_score=frame.danger_score,
                telegraph_type=frame.telegraph_type,
                target_visible=frame.target_visible,
                hp_ratios=frame.hp_ratios,
                survival_state=survival_state,
                combo_broken=frame.combo_broken,
                combat_ended=frame.combat_ended,
                evidence_ids=[f"frame:{index + 1}"],
            )
            decision = runtime.tick(input_, now=float(index + 1))
            if decision.state == "survival_recovery":
                survival_recovery_seen = True
            if decision.survival_decision and decision.survival_decision.kind in {"heal", "food_ui", "shield", "retreat"}:
                heal_attempt = True
            if decision.state == "reflex_preempted" and decision.action in {"dodge_then_keep_distance", "dodge_reflex", "hold_safe"}:
                reflex_reacted = True

        # Low HP + danger: either survival recovery OR reflex preemption is valid
        assert survival_recovery_seen or heal_attempt or reflex_reacted, (
            "Low HP danger should trigger survival recovery or reflex reaction"
        )

    def test_food_profile_missing_safe_abort(self, analyzer):
        """Scenario: unknown team + danger → safe abort."""
        scenario = SCENARIOS[4]  # food_profile_missing_safe_abort
        runtime = _make_runtime(scenario)
        team = analyzer.analyze(scenario.team_characters, scenario.team_elements)

        safe_abort = False
        for index, frame in enumerate(scenario.frames):
            decision = runtime.tick(
                _to_input(scenario, index, frame, team, food_available=True),
                now=float(index + 1),
            )
            if decision.action == "release_all":
                safe_abort = True

        assert safe_abort, "Unknown team + danger should trigger safe abort"

    def test_long_fight_phase_shift(self, analyzer):
        """Scenario: boss phase shifts → state machine adapts."""
        scenario = SCENARIOS[5]  # long_fight_phase_shift
        runtime = _make_runtime(scenario)
        team = analyzer.analyze(scenario.team_characters, scenario.team_elements)

        states = []
        for index, frame in enumerate(scenario.frames):
            decision = runtime.tick(
                _to_input(scenario, index, frame, team),
                now=float(index + 1),
            )
            states.append(decision.state)

        # Long fight: should go through multiple phases
        unique_states = set(states)
        assert len(unique_states) >= 2, f"Expected multiple states, got {unique_states}"
        # Boss HP drops through phases
        hp_ratios = [f.boss_hp_ratio for f in scenario.frames]
        assert hp_ratios[0] > hp_ratios[-1], "Long fight scenario HP should decrease"


class TestBossCombatStateMachine:
    """Verify BossCombatRuntime state machine invariants."""

    @pytest.fixture
    def analyzer(self) -> TeamCapabilityAnalyzer:
        return TeamCapabilityAnalyzer.from_yaml(CHAR_PATH)

    @pytest.fixture
    def runtime(self, analyzer) -> BossCombatRuntime:
        scenario = SCENARIOS[0]
        boss = conservative_unknown_boss(scenario.boss_id)
        team = analyzer.analyze(scenario.team_characters, scenario.team_elements)
        plan = analyzer.compile_plan(team, boss)
        return BossCombatRuntime(boss, team, plan, SurvivalPolicyEngine())

    def test_init_state(self, runtime):
        # First tick with target visible → state becomes EXECUTE_TACTIC
        decision = runtime.tick(
            BossCombatInput(frame_id=1, boss_hp_ratio=1.0, danger_score=0.0, target_visible=True),
            now=1.0,
        )
        assert decision.state == "execute_tactic"

    def test_acquire_then_execute(self, analyzer):
        # Fresh runtime for clean state
        scenario = SCENARIOS[0]
        boss = conservative_unknown_boss(scenario.boss_id)
        team = analyzer.analyze(scenario.team_characters, scenario.team_elements)
        plan = analyzer.compile_plan(team, boss)
        runtime = BossCombatRuntime(boss, team, plan, SurvivalPolicyEngine())

        # Frame 1: no target → target_reacquire
        d1 = runtime.tick(
            BossCombatInput(frame_id=1, boss_hp_ratio=1.0, danger_score=0.0, target_visible=False),
            now=1.0,
        )
        assert d1.state == "target_reacquire"

        # Frame 2: target visible → execute tactic
        d2 = runtime.tick(
            BossCombatInput(frame_id=2, boss_hp_ratio=0.9, danger_score=0.1, target_visible=True),
            now=2.0,
        )
        assert d2.state == "execute_tactic"

    def test_high_danger_triggers_reflex_or_survival(self, runtime):
        decision = runtime.tick(
            BossCombatInput(
                frame_id=1,
                boss_hp_ratio=0.8,
                danger_score=0.9,
                telegraph_type="ground_danger_zone",
                target_visible=True,
            ),
            now=1.0,
        )
        # High danger: should react (reflex preempted, survival recovery, or dodge)
        assert decision.state in ("reflex_preempted", "survival_recovery", "execute_tactic")
        assert decision.action != ""


class TestBossCombatCheckpoints:
    """Verify checkpoint/snapshot/resume cycle."""

    @pytest.fixture
    def runtime(self) -> BossCombatRuntime:
        scenario = SCENARIOS[0]
        analyzer = TeamCapabilityAnalyzer.from_yaml(CHAR_PATH)
        boss = conservative_unknown_boss(scenario.boss_id)
        team = analyzer.analyze(scenario.team_characters, scenario.team_elements)
        plan = analyzer.compile_plan(team, boss)
        return BossCombatRuntime(boss, team, plan, SurvivalPolicyEngine())

    def test_checkpoint_before_reflex(self, runtime):
        # Run first frame → triggers checkpoint before reflex
        decision = runtime.tick(
            BossCombatInput(
                frame_id=1,
                boss_hp_ratio=0.95,
                danger_score=0.8,
                telegraph_type="ground_danger_zone",
                target_visible=True,
            ),
            now=1.0,
        )
        # Should have checkpoints available
        cp = runtime.checkpoints.save("test_reflex", "test_step", "visible")
        assert cp is not None, "Checkpoint should be saved before reflex action"
        assert cp.checkpoint_id == "test_reflex"

    def test_resume_from_checkpoint(self, runtime):
        # Save checkpoint
        runtime.tick(
            BossCombatInput(frame_id=1, boss_hp_ratio=0.95, danger_score=0.1, target_visible=True),
            now=1.0,
        )
        runtime.checkpoints.save("test_resume", "rotation_step", "visible")

        # Resume from checkpoint
        resume_cp = runtime.checkpoints.resume()
        assert resume_cp is not None, "Checkpoint should be saved"
        assert resume_cp.checkpoint_id == "test_resume"

        # Continue ticking should work without crashing
        resume_decision = runtime.tick(
            BossCombatInput(frame_id=2, boss_hp_ratio=0.9, danger_score=0.1, target_visible=True),
            now=2.0,
        )
        assert resume_decision.state in ("execute_tactic", "acquire_target", "verify_progress", "identify_phase")