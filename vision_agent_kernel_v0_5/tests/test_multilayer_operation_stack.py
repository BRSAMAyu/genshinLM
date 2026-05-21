from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from capsules.capsule_protocol import load_manifest_from_yaml
from execution.semantic_action import ActionContractValidator, click_anchor_action
from interaction.capsule_anchors import anchors_from_manifest
from interaction.ui_anchor import NormalizedRect, UIAnchorResolver, UIElement
from perception.observation_graph import ObservationBuilder
from core.types import FocusState, Observation, UIStateEstimate
from planning.capability_planner import CapabilityPlanner
from planning.mission_graph import MissionDAGCompiler
from planning.mission_queue import MissionGoal
from planning.skill_capability_catalog import SkillCapabilityCatalog
from runtime.context_compactor import ContextCompactor
from runtime.long_run_policy import HealthSample, LongRunWatchdog


def test_capsule_manifest_declares_resolvable_ui_anchors() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = load_manifest_from_yaml(str(root / "capsules" / "hsr" / "capsule.yaml"))
    anchors = anchors_from_manifest(manifest)
    claim = next(anchor for anchor in anchors if anchor.anchor_id == "hsr_claim_reward_button")

    resolver = UIAnchorResolver()
    elements = [
        UIElement(
            element_id="claim_button",
            role="button",
            bbox=NormalizedRect(0.70, 0.78, 0.16, 0.08),
            confidence=0.91,
            source="ocr",
            text="领取",
        )
    ]
    resolution_1080p = resolver.resolve(claim, elements, viewport=(1920, 1080), screen_state="menu")
    resolution_720p = resolver.resolve(claim, elements, viewport=(1280, 720), screen_state="menu")

    assert resolution_1080p.ok is True
    assert resolution_1080p.strategy == "ocr"
    assert resolution_1080p.click_point == (1498, 886)
    assert resolution_720p.ok is True
    assert resolution_720p.click_point == (998, 590)


def test_anchor_resolution_blocks_low_confidence_and_screen_mismatch() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = load_manifest_from_yaml(str(root / "capsules" / "genshin" / "capsule.yaml"))
    anchor = next(a for a in anchors_from_manifest(manifest) if a.anchor_id == "genshin_teleport_confirm")
    resolver = UIAnchorResolver()

    mismatch = resolver.resolve(anchor, [], viewport=(1920, 1080), screen_state="overworld")
    assert mismatch.ok is False
    assert "screen_state_mismatch" in mismatch.reason

    fallback = resolver.resolve(anchor, [], viewport=(1920, 1080), screen_state="map")
    assert fallback.strategy == "calibrated"
    assert fallback.ok is False
    assert fallback.requires_confirmation is True


def test_observation_builder_promotes_extensions_to_observation_graph() -> None:
    obs = Observation(
        frame_id=42,
        t_capture=1.0,
        t_processed=1.02,
        latency_ms=20.0,
        viewport_size=(1920, 1080),
        target_track=None,
        obstacle_field=None,
        ui_state=UIStateEstimate(frame_id=42, timestamp=1.02, state="menu", confidence=0.88),
        visual_triggers={},
        os_focus=FocusState(focused=True),
        extensions={
            "ui_elements": [
                {
                    "id": "btn_claim",
                    "role": "button",
                    "text": "Claim",
                    "bbox_norm": [0.7, 0.78, 0.16, 0.08],
                    "confidence": 0.92,
                    "source": "ocr",
                }
            ],
            "danger_signals": [{"id": "danger_1", "confidence": 0.2, "source": "hsv"}],
        },
    )

    graph = ObservationBuilder().build(obs, capsule_id="hsr")
    assert graph.screen_state() == "menu"
    assert graph.evidence_summary()["kinds"]["ui_element"] == 1
    assert graph.evidence_summary()["kinds"]["danger_signal"] == 1
    assert graph.ui_elements()[0].text == "Claim"


def test_action_contract_rejects_raw_coordinates_and_requires_verifier() -> None:
    contract = click_anchor_action("a1", "hsr_claim_reward_button")
    result = ActionContractValidator().validate(contract)
    assert result.ok is True

    bad = click_anchor_action("a2", "hsr_claim_reward_button")
    bad = replace(
        bad,
        semantic_action=replace(bad.semantic_action, parameters={"x": 100, "y": 200}),
        verifier_contract={},
    )
    bad_result = ActionContractValidator().validate(bad)
    assert bad_result.ok is False
    assert any("raw x/y" in error for error in bad_result.errors)
    assert any("verifier_contract" in error for error in bad_result.errors)


def test_capability_planner_compiles_verifiable_mission_graph() -> None:
    root = Path(__file__).resolve().parents[1]
    hsr = load_manifest_from_yaml(str(root / "capsules" / "hsr" / "capsule.yaml"))
    catalog = SkillCapabilityCatalog.from_sources(manifests=[hsr])
    proposal = CapabilityPlanner(catalog).plan("claim reward", active_capsule_id="hsr")
    graph = MissionDAGCompiler().compile(
        proposal,
        MissionGoal(type="claim", resource_id="hsr_reward_claim"),
        mission_id="hsr_claim_reward_mission",
    )
    queue = graph.to_queue()

    assert graph.nodes[0].node_type == "claim_reward"
    assert graph.nodes[0].verifier == "reward_claimed"
    assert queue.requires_user_confirmation is True
    assert queue.nodes[0].skill_binding == "hsr_claim_rewards"


def test_context_compactor_and_long_run_watchdog() -> None:
    root = Path(__file__).resolve().parents[1]
    hsr = load_manifest_from_yaml(str(root / "capsules" / "hsr" / "capsule.yaml"))
    catalog = SkillCapabilityCatalog.from_sources(manifests=[hsr])
    proposal = CapabilityPlanner(catalog).plan("dialog progression", active_capsule_id="hsr")
    mission = MissionDAGCompiler().compile(
        proposal,
        MissionGoal(type="dialog", resource_id="hsr_dialog_progression"),
        mission_id="dialog_mission",
    ).to_queue()

    summary = ContextCompactor().compact(
        mission,
        current_node=mission.nodes[0].id,
        completed_nodes=[],
        verifier_results=[{"ok": True, "verifier_id": "dialog_progressed", "fact": "dialog advanced"}],
        failures=[],
        cold_refs=["data/recordings/dialog/events.jsonl"],
    )
    assert summary.verified_facts == ["dialog advanced"]
    assert summary.cold_context_refs == ["data/recordings/dialog/events.jsonl"]

    watchdog = LongRunWatchdog()
    assert watchdog.evaluate(HealthSample(elapsed_s=10.0, focus_ok=True, profile_ok=True)) == []
    assert "window_revalidation_failed" in watchdog.evaluate(HealthSample(elapsed_s=10.0, focus_ok=False))
