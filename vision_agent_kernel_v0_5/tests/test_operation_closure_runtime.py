from __future__ import annotations

import json
from pathlib import Path

from app_service.skill_manager import RecordedEvent, SkillDraft
from benchmarks.aurorabench_v2 import AuroraBenchV2Summary, benchmark_result_to_dict_v2
from benchmarks.benchmark_types import BenchmarkMetrics, BenchmarkResult
from control.navigation_runtime import NavigationController, NavigationSample, RouteSegment
from core.types import FocusState, Observation, UIStateEstimate
from evidence.evidence_nodes import NODE_TYPE_ACTION_INTENT, NODE_TYPE_INPUT_LEASE, NODE_TYPE_OBSERVATION
from execution.observation_verifiers import (
    CombatDangerClearedVerifier,
    NavigationProgressVerifier,
    ObservationGraphUIVerifier,
)
from execution.ui_action_executor import UIAnchorActionExecutor
from execution.verifier_base import VerifierContext
from interaction.calibration import CalibrationWizard
from interaction.ui_anchor import NormalizedRect, UIAnchor, UIAnchorMatcher, UIElement
from perception.observation_graph import ObservationBuilder
from planning.capsule_plan_templates import CapsulePlanTemplateLibrary
from recording.semantic_distiller import SemanticSkillDistiller
from runtime.context_compactor import ContextCompactor
from runtime.run_state_store import RunCheckpoint, RunStateStore


def _anchor(anchor_id: str = "claim") -> UIAnchor:
    return UIAnchor(
        anchor_id=anchor_id,
        screen_state="menu",
        semantic_role="claim_reward",
        candidate_roi=NormalizedRect(0.68, 0.75, 0.2, 0.12),
        matchers=[
            UIAnchorMatcher("ocr", value="Claim", weight=0.9, min_confidence=0.5),
            UIAnchorMatcher("calibrated", weight=0.8, roi=NormalizedRect(0.70, 0.78, 0.16, 0.08)),
        ],
        post_action_verifier="reward_claimed",
    )


def _element() -> UIElement:
    return UIElement(
        element_id="claim_button",
        role="button",
        bbox=NormalizedRect(0.70, 0.78, 0.16, 0.08),
        confidence=0.94,
        source="ocr",
        text="Claim",
    )


def _observation_graph(screen_state: str = "menu", progress: float = 0.0, danger: float = 0.0):
    obs = Observation(
        frame_id=7,
        t_capture=1.0,
        t_processed=1.01,
        latency_ms=10.0,
        viewport_size=(1920, 1080),
        target_track=None,
        obstacle_field=None,
        ui_state=UIStateEstimate(frame_id=7, timestamp=1.01, state=screen_state, confidence=0.95),
        visual_triggers={},
        os_focus=FocusState(focused=True),
        extensions={
            "ui_elements": [
                {
                    "id": "claim_button",
                    "role": "button",
                    "text": "Claim",
                    "anchor_id": "claim",
                    "bbox_norm": [0.70, 0.78, 0.16, 0.08],
                    "confidence": 0.94,
                    "source": "ocr",
                }
            ],
            "navigation_signals": [{"id": "nav_1", "progress": progress, "confidence": 0.8, "source": "testbed"}],
            "danger_signals": [{"id": "danger_1", "danger_score": danger, "confidence": danger, "source": "testbed"}],
        },
    )
    return ObservationBuilder().build(obs, capsule_id="test")


def test_calibration_wizard_reports_ready_and_low_confidence() -> None:
    wizard = CalibrationWizard()
    profile = wizard.build_profile("hsr", "profile_1080p", (1920, 1080), [_anchor()])

    ready = wizard.validate(profile, [_element()])
    assert ready.ready is True
    assert ready.issues == []

    weak = UIElement(
        element_id="weak",
        role="button",
        bbox=NormalizedRect(0.70, 0.78, 0.16, 0.08),
        confidence=0.4,
        source="ocr",
        text="Claim",
    )
    report = wizard.validate(profile, [weak])
    assert report.ready is False
    assert report.issues[0].code in {"low_confidence", "anchor_not_found_requires_fallback_agent"}


def test_ui_anchor_executor_dry_run_creates_evidence_and_blocks_missing_anchor() -> None:
    graph = _observation_graph()
    executor = UIAnchorActionExecutor()

    result = executor.click_anchor(_anchor(), graph)
    assert result.click_result.status == "EXECUTED"
    assert len(result.evidence_ids) == 3
    assert executor.evidence_graph.get_nodes_by_type(NODE_TYPE_OBSERVATION)
    assert executor.evidence_graph.get_nodes_by_type(NODE_TYPE_ACTION_INTENT)
    assert executor.evidence_graph.get_nodes_by_type(NODE_TYPE_INPUT_LEASE)

    missing = executor.click_anchor(_anchor("missing"), _observation_graph(screen_state="inventory"))
    assert missing.click_result.status in {"BLOCKED_LOW_CONFIDENCE", "BLOCKED_NOT_FOUND"}
    assert missing.click_result.failure_code is not None


def test_observation_graph_verifiers_accept_only_grounded_evidence() -> None:
    graph = _observation_graph(progress=0.2, danger=0.1)
    ctx = VerifierContext(metadata={"observation_graph": graph})

    ui = ObservationGraphUIVerifier(expected_screen_state="menu", required_anchor="claim").verify(ctx)
    nav = NavigationProgressVerifier().verify(ctx)
    danger = CombatDangerClearedVerifier().verify(ctx)
    assert ui.ok is True and ui.frame_id == 7
    assert nav.ok is True
    assert danger.ok is True

    hot = CombatDangerClearedVerifier().verify(VerifierContext(metadata={"observation_graph": _observation_graph(danger=0.8)}))
    assert hot.ok is False


def test_semantic_skill_distiller_binds_raw_clicks_to_anchors() -> None:
    draft = SkillDraft(
        draft_id="draft_1",
        raw_events=[
            RecordedEvent(
                event_type="mouse_click",
                timestamp=1.0,
                active_window_title="dry-run",
                observation_summary={},
                target_state="menu",
                payload={"x": 1498, "y": 886},
            )
        ],
        segments=[],
        suggested_preconditions=[],
        suggested_visual_checkpoints=[],
        suggested_success_criteria=[],
        suggested_fallbacks=[],
        suggestions=[],
    )
    distilled = SemanticSkillDistiller().distill(draft, [_anchor()], [_element()], (1920, 1080), "menu")
    assert distilled.ui_anchors == ["claim"]
    assert distilled.semantic_actions[0].intent == "click_anchor"
    assert distilled.verifier_contracts[0]["verifier_id"] == "claim_post_click"


def test_navigation_controller_moves_recovers_and_escalates() -> None:
    controller = NavigationController()
    segment = RouteSegment("seg_1", "wp_1", expected_bearing=20.0, max_duration_s=10.0, stuck_policy={"max_recoveries": 1})

    moving = controller.step(segment, NavigationSample(1.0, distance_to_target=8.0, heading_error_deg=20.0, progress=0.1), now=1.0)
    assert moving.status == "move"
    assert moving.lease is not None
    assert moving.lease.key_states["W"] == "DOWN"
    assert moving.lease.expires_at - moving.lease.created_at <= 0.25

    for i in range(4):
        decision = controller.step(segment, NavigationSample(2.0 + i, 8.0, 0.0, optical_flow=0.0, progress=0.1), now=2.0 + i)
    assert decision.status == "recover"
    assert "release_all" in decision.recovery_actions

    for i in range(4, 8):
        decision = controller.step(segment, NavigationSample(2.0 + i, 8.0, 0.0, optical_flow=0.0, progress=0.1), now=2.0 + i)
    assert decision.status == "escalate"


def test_capsule_plan_templates_produce_verifiable_dry_run_graphs() -> None:
    templates = CapsulePlanTemplateLibrary()
    hsr = templates.hsr_daily_flow()
    genshin = templates.genshin_material_flow()

    assert hsr.capsule_id == "hsr"
    assert [node.node_type for node in hsr.nodes] == ["ui_interact", "dialog", "claim_reward"]
    assert all(node.verifier for node in hsr.nodes)
    assert hsr.to_queue().requires_user_confirmation is True

    assert genshin.capsule_id == "genshin"
    assert [node.node_type for node in genshin.nodes] == ["ui_interact", "ui_interact", "navigate", "collect"]
    assert all(node.verifier for node in genshin.nodes)


def test_run_state_store_checkpoint_revalidation_and_context_resume(tmp_path: Path) -> None:
    mission = CapsulePlanTemplateLibrary().hsr_daily_flow().to_queue()
    summary = ContextCompactor().compact(
        mission,
        current_node=mission.nodes[1].id,
        completed_nodes=[mission.nodes[0].id],
        observation_graph=_observation_graph(),
        verifier_results=[{"ok": True, "fact": "menu opened"}],
    )
    store = RunStateStore(tmp_path)
    store.save_mission(mission)
    store.save_summary(summary)
    store.save_checkpoint(
        RunCheckpoint(
            checkpoint_id="cp_1",
            mission_id=mission.mission_id,
            node_id=mission.nodes[0].id,
            verified=True,
            evidence_refs=["obs:test:7"],
            profile_id="profile_1080p",
            capsule_id="hsr",
            skill_versions={"hsr_navigation": 1},
        )
    )

    checkpoint = store.latest_verified_checkpoint(mission.mission_id)
    assert checkpoint is not None
    assert store.revalidation_errors(checkpoint, profile_id="profile_1080p", capsule_id="hsr", skill_versions={"hsr_navigation": 1}) == []
    assert "profile_mismatch" in store.revalidation_errors(checkpoint, profile_id="profile_720p", capsule_id="hsr")

    mission_json = json.loads((tmp_path / f"{mission.mission_id}.mission.json").read_text(encoding="utf-8"))
    assert mission_json["nodes"][0]["id"] == "open_hsr_menu"


def test_aurorabench_v2_metrics_are_serialized_and_aggregated() -> None:
    result = BenchmarkResult(
        benchmark_id="b1",
        run_id="r1",
        suite_name="ui_grounding",
        scenario_name="claim_reward",
        passed=True,
        metrics=BenchmarkMetrics(
            evidence_coverage=1.0,
            task_success_rate=1.0,
            anchor_resolution_rate=1.0,
            click_success_rate=1.0,
            release_all_success_rate=1.0,
            context_compaction_success_rate=1.0,
            reflex_latency_p95=30.0,
        ),
        evidence_ids=["e1"],
    )
    serialized = benchmark_result_to_dict_v2(result)
    assert serialized["metrics"]["anchor_resolution_rate"] == 1.0

    summary = AuroraBenchV2Summary().summarize_results([result])
    assert summary["pass_rate"] == 1.0
    assert summary["metrics"]["click_success_rate"] == 1.0
