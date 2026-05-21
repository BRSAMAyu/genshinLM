from __future__ import annotations

from pathlib import Path

from benchmarks.boss_combat_gauntlet.runner import run_all_boss_combat
from combat.boss_combat_runtime import BossCombatInput, BossCombatRuntime
from combat.boss_schema import boss_signal_from_observation, conservative_unknown_boss, load_boss_profiles
from combat.genshin_combat_planner import GenshinCombatPlanner
from combat.survival_runtime import SurvivalPolicyEngine, SurvivalState
from combat.team_capability import TeamCapabilityAnalyzer
from core.types import FocusState, Observation
from perception.observation_graph import ObservationBuilder


ROOT = Path(__file__).resolve().parents[1]
BOSS_PATH = ROOT / "capsules" / "genshin" / "resources" / "boss_profiles.yaml"
CHAR_PATH = ROOT / "data" / "combat_profiles" / "character_profiles.yaml"


def test_boss_profiles_load_and_phase_signals_have_evidence() -> None:
    profiles = load_boss_profiles(BOSS_PATH)
    assert {"aoe_boss", "projectile_boss", "phase_shift_boss"} <= set(profiles)

    boss = profiles["phase_shift_boss"]
    normal = boss.phase_for_hp(0.8)
    shielded = boss.phase_for_hp(0.4)
    assert normal.phase_id == "normal"
    assert shielded.phase_id == "shielded"

    signal = boss_signal_from_observation(
        boss,
        hp_ratio=0.4,
        telegraph_type="shield_flash",
        frame_id=12,
        roi_id="boss_body",
        confidence=0.88,
    )
    assert signal.phase_id == "shielded"
    assert signal.attack_pattern_id == "shield_pulse"
    assert signal.frame_id == 12
    assert signal.roi_id == "boss_body"
    assert signal.evidence_id


def test_unknown_boss_uses_conservative_safe_loop() -> None:
    boss = conservative_unknown_boss("mystery_boss")
    phase = boss.phase_for_hp(0.5)
    assert phase.tactic == "safe_loop"
    assert boss.failure_modes == ["UNKNOWN_BOSS_PROFILE"]
    pattern = next(iter(boss.attack_patterns.values()))
    assert pattern.safe_response == "dodge_then_keep_distance"


def test_observation_builder_promotes_boss_combat_signals() -> None:
    obs = Observation(
        frame_id=31,
        t_capture=1.0,
        t_processed=1.01,
        latency_ms=10.0,
        viewport_size=(1280, 720),
        target_track=None,
        obstacle_field=None,
        ui_state=None,
        visual_triggers={},
        os_focus=FocusState(focused=True),
        extensions={
            "boss_phase_signals": [{"id": "phase", "phase_id": "enrage", "bbox_norm": [0.1, 0.1, 0.2, 0.2], "confidence": 0.9}],
            "telegraph_signals": [{"id": "telegraph", "telegraph_type": "boss_windup", "confidence": 0.8}],
            "punish_window_signals": [{"id": "punish", "window_id": "after_aoe", "confidence": 0.7}],
            "combat_resource_signals": [{"id": "hp", "active_hp": 0.4, "confidence": 0.95}],
        },
    )
    graph = ObservationBuilder().build(obs, capsule_id="genshin")
    summary = graph.evidence_summary()["kinds"]
    assert summary["boss_phase_signal"] == 1
    assert summary["telegraph_signal"] == 1
    assert summary["punish_window_signal"] == 1
    assert summary["combat_resource_signal"] == 1


def test_team_capability_analyzer_adapts_survival_by_team() -> None:
    profiles = load_boss_profiles(BOSS_PATH)
    boss = profiles["aoe_boss"]
    analyzer = TeamCapabilityAnalyzer.from_yaml(CHAR_PATH)

    healer_team = analyzer.analyze(["xiangling", "bennett", "xingqiu", "sucrose"], ["pyro", "pyro", "hydro", "anemo"])
    shield_team = analyzer.analyze(["hu_tao", "xingqiu", "zhongli", "albedo"], ["pyro", "hydro", "geo", "geo"])
    no_survival = analyzer.analyze(["diluc", "fischl", "xiangling", "sucrose"], ["pyro", "electro", "pyro", "anemo"])
    unknown = analyzer.analyze(["unknown_pyro"], ["pyro"])

    assert healer_team.has_healer is True
    assert shield_team.has_shielder is True
    assert no_survival.has_healer is False and no_survival.has_shielder is False
    assert unknown.characters[0].known is False

    healer_plan = analyzer.compile_plan(healer_team, boss)
    shield_plan = analyzer.compile_plan(shield_team, boss)
    no_survival_plan = analyzer.compile_plan(no_survival, boss)
    assert "heal_on_soft_threshold" in healer_plan.survival_chain
    assert "shield_before_punish_window" in shield_plan.survival_chain
    assert no_survival_plan.conservative_level >= 2


def test_genshin_boss_playbook_differs_by_team_survival() -> None:
    profiles = load_boss_profiles(BOSS_PATH)
    planner = GenshinCombatPlanner(TeamCapabilityAnalyzer.from_yaml(CHAR_PATH))

    healer_pb, healer_plan = planner.generate_boss_playbook(
        ["pyro", "pyro", "hydro", "anemo"],
        ["xiangling", "bennett", "xingqiu", "sucrose"],
        profiles["aoe_boss"],
    )
    shield_pb, shield_plan = planner.generate_boss_playbook(
        ["pyro", "hydro", "geo", "geo"],
        ["hu_tao", "xingqiu", "zhongli", "albedo"],
        profiles["aoe_boss"],
    )
    unsafe_pb, unsafe_plan = planner.generate_boss_playbook(
        ["pyro", "electro", "pyro", "anemo"],
        ["diluc", "fischl", "xiangling", "sucrose"],
        profiles["aoe_boss"],
    )

    assert any(trigger.action == "heal" for trigger in healer_pb.priority_triggers)
    assert any(trigger.action == "shield" for trigger in shield_pb.priority_triggers)
    assert any(trigger.action == "retreat" for trigger in unsafe_pb.priority_triggers)
    assert healer_plan.reason != unsafe_plan.reason
    assert shield_plan.reason != unsafe_plan.reason


def test_survival_policy_blocks_food_ui_when_danger_high_and_aborts_missing_profile() -> None:
    engine = SurvivalPolicyEngine()
    danger = engine.decide(SurvivalState(active_hp=0.1, team_hp=[0.1], danger_score=0.9, food_available=True, ui_profile_ready=True))
    assert danger.kind == "dodge"

    missing_profile = engine.decide(SurvivalState(active_hp=0.1, team_hp=[0.1], danger_score=0.1, food_available=True, ui_profile_ready=False))
    assert missing_profile.kind == "safe_abort"
    assert missing_profile.failure_code == "HEAL_PROFILE_NOT_READY"

    healer = engine.decide(SurvivalState(active_hp=0.3, team_hp=[0.3], danger_score=0.1, healer_available=True))
    assert healer.kind == "heal"


def _runtime_for(team_characters: list[str], team_elements: list[str], boss_id: str = "aoe_boss") -> BossCombatRuntime:
    profiles = load_boss_profiles(BOSS_PATH)
    analyzer = TeamCapabilityAnalyzer.from_yaml(CHAR_PATH)
    team = analyzer.analyze(team_characters, team_elements)
    plan = analyzer.compile_plan(team, profiles[boss_id])
    return BossCombatRuntime(profiles[boss_id], team, plan)


def test_boss_runtime_reflex_resume_and_bounded_lease() -> None:
    runtime = _runtime_for(["hu_tao", "xingqiu", "zhongli", "albedo"], ["pyro", "hydro", "geo", "geo"])
    first = runtime.tick(BossCombatInput(1, 0.9, 0.85, "ground_danger_zone", evidence_ids=["frame:1"]), now=1.0)
    assert first.state == "reflex_preempted"
    assert first.interrupt is True

    resume = None
    for i in range(2, 8):
        resume = runtime.tick(BossCombatInput(i, 0.9, 0.05, "ground_danger_zone", evidence_ids=[f"frame:{i}"]), now=float(i))
        if resume.resume_contract is not None:
            break
    assert resume is not None and resume.action == "resume_checkpoint"
    assert resume.resume_contract is not None

    action = runtime.tick(BossCombatInput(8, 0.8, 0.1, "", evidence_ids=["frame:8"]), now=8.0)
    assert action.lease is not None
    assert action.lease.expires_at - action.lease.created_at <= 0.18


def test_boss_runtime_target_lost_and_combo_break_are_safe() -> None:
    runtime = _runtime_for(["xiangling", "bennett", "xingqiu", "sucrose"], ["pyro", "pyro", "hydro", "anemo"], "projectile_boss")
    reacquire = runtime.tick(BossCombatInput(1, 0.8, 0.1, target_visible=False, evidence_ids=["frame:1"]), now=1.0)
    assert reacquire.action == "re_acquire_target"

    runtime.tick(BossCombatInput(2, 0.8, 0.1, target_visible=False, evidence_ids=["frame:2"]), now=2.0)
    failed = runtime.tick(BossCombatInput(3, 0.8, 0.1, target_visible=False, evidence_ids=["frame:3"]), now=3.0)
    assert failed.action == "release_all"
    assert failed.failure_code == "TARGET_LOST_REACQUIRE_FAILED"

    runtime2 = _runtime_for(["xiangling", "bennett", "xingqiu", "sucrose"], ["pyro", "pyro", "hydro", "anemo"], "projectile_boss")
    reset = runtime2.tick(BossCombatInput(1, 0.8, 0.1, combo_broken=True, evidence_ids=["frame:1"]), now=1.0)
    assert reset.action == "reset_tactic"


def test_bossbench_all_scenarios_pass_and_emit_metrics() -> None:
    results = run_all_boss_combat()
    assert len(results) >= 6
    assert all(result.passed for result in results)
    assert all(result.evidence_ids for result in results)
    assert all("failure_signatures" in result.report for result in results)
    assert any(result.metrics.target_reacquire_success_rate == 1.0 for result in results)
    assert any(result.metrics.safe_abort_success_rate == 1.0 for result in results)
