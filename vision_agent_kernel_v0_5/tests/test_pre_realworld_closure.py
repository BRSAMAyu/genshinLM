from __future__ import annotations

import threading

from benchmarks.local_vlm_bench import LocalVlmBench
from core.state_bus import StateBus
from core.types import FocusState, Observation, UIStateEstimate
from execution.declarative_verifier import DeclarativeVerifierEngine
from execution.ui_action_executor import UIAnchorActionExecutor
from execution.verifier_base import VerifierContext
from interaction.calibration import CalibrationWizard
from interaction.ui_anchor import NormalizedRect, UIAnchor, UIAnchorMatcher, UIElement
from llm.vision_provider import (
    ImageInput,
    ScreenStateResult,
    UIGroundingResult,
    VisionProviderStatus,
    VisionResult,
)
from perception.observation_graph import ObservationBuilder, ObservationGraph
from runtime.claim_adjudicator import ClaimAdjudicator, ClaimRecipe
from runtime.claim_events import ClaimEventPublisher
from runtime.claim_runtime import ObservationClaim, StateDeltaClaim
from runtime.claim_worker import ClaimGraphCommand, ClaimGraphWorker
from runtime.verifier_compiler import VerifierBundle, VerifierStep


def _anchor() -> UIAnchor:
    return UIAnchor(
        anchor_id="claim_button",
        screen_state="menu",
        semantic_role="claim_reward",
        candidate_roi=NormalizedRect(0.70, 0.78, 0.16, 0.08),
        matchers=[UIAnchorMatcher("ocr", value="Claim", weight=0.9, min_confidence=0.5)],
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
        metadata={"anchor_id": "claim_button"},
    )


def _graph(screen_state: str = "menu") -> ObservationGraph:
    obs = Observation(
        frame_id=101,
        t_capture=1.0,
        t_processed=1.01,
        latency_ms=10.0,
        viewport_size=(1920, 1080),
        target_track=None,
        obstacle_field=None,
        ui_state=UIStateEstimate(frame_id=101, timestamp=1.01, state=screen_state, confidence=0.95),
        visual_triggers={},
        os_focus=FocusState(focused=True),
        extensions={
            "ui_elements": [
                {
                    "id": "claim_button",
                    "role": "button",
                    "text": "Claim",
                    "anchor_id": "claim_button",
                    "bbox_norm": [0.70, 0.78, 0.16, 0.08],
                    "confidence": 0.94,
                    "source": "ocr",
                }
            ],
            "ocr_blocks": [
                {
                    "id": "toast_1",
                    "roi_id": "toast_area",
                    "text": "+1 Reward",
                    "bbox_norm": [0.40, 0.10, 0.2, 0.08],
                    "confidence": 0.9,
                    "source": "ocr",
                }
            ],
            "navigation_signals": [{"id": "nav_1", "progress": 0.97, "confidence": 0.8, "source": "testbed"}],
            "danger_signals": [{"id": "danger_1", "danger_score": 0.1, "confidence": 0.9, "source": "testbed"}],
        },
    )
    return ObservationBuilder().build(obs, capsule_id="test")


def _claim(claim_id: str = "claim_1", claim_type: str = "ui_action_executed") -> StateDeltaClaim:
    return StateDeltaClaim(
        claim_id=claim_id,
        mission_id="m1",
        node_id="n1",
        skill_id="s1",
        claim_type=claim_type,
        claimed_delta={"screen_state": "menu"},
        risk_level="low",
    )


def test_claim_graph_worker_serializes_commands_and_publishes_state() -> None:
    bus = StateBus()
    events = []
    states = []
    bus.subscribe("claim_event", events.append)
    bus.subscribe("claim_graph_state", states.append)
    worker = ClaimGraphWorker(
        adjudicator=ClaimAdjudicator({"ui_action_executed.default": ClaimRecipe("ui_action_executed", required_families=["ui_action"])}),
        publisher=ClaimEventPublisher(bus),
        graph_id="g1",
        mission_id="m1",
    )

    def submit(index: int) -> None:
        claim = _claim(f"c{index}")
        worker.submit(ClaimGraphCommand("add_claim", claim=claim))
        worker.submit(ClaimGraphCommand("add_observation", observation=ObservationClaim(f"o{index}", claim.claim_id, "ui_action", "support", 0.9)))
        worker.submit(ClaimGraphCommand("adjudicate", claim_id=claim.claim_id))

    threads = [threading.Thread(target=submit, args=(i,)) for i in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    snapshot = worker.snapshot()
    worker.stop()

    assert snapshot["claim_count"] == 5
    assert snapshot["adjudication_count"] == 5
    assert states
    assert any(event.event_type == "claim_adjudicated" for event in events)


def test_declarative_verifier_engine_executes_core_step_types() -> None:
    graph = _graph()
    ctx = VerifierContext(
        state={"observed_delta": {"item": "reward", "delta": 1}},
        metadata={"observation_graph": graph, "stable_frames": 5},
    )
    claim = _claim("c_bundle", "collection_pickup")
    bundle = VerifierBundle(
        claim_type="collection_pickup",
        primary=[
            VerifierStep(type="screen_state_match", state="menu"),
            VerifierStep(type="anchor_exists", anchor="claim_button"),
            VerifierStep(type="text_match", roi="toast_area", contains_any=["Reward"]),
            VerifierStep(type="numeric_delta", item="reward", expected_delta=1),
            VerifierStep(type="progress_threshold", threshold=0.95),
            VerifierStep(type="danger_score_below", threshold=0.3),
        ],
        secondary=[VerifierStep(type="composite", all_of=[VerifierStep(type="screen_state_stable", state="menu", frames=5)])],
    )

    observations = DeclarativeVerifierEngine().verify_bundle(claim=claim, bundle=bundle, context=ctx)

    assert len(observations) == 7
    assert all(obs.polarity == "support" for obs in observations)
    assert {obs.source_family for obs in observations} >= {"screen_state", "anchor", "toast", "inventory_delta", "navigation_signal", "combat_danger"}


def test_ui_anchor_click_enters_claim_worker_and_requires_claim_evidence() -> None:
    adjudicator = ClaimAdjudicator({"ui_action_executed.default": ClaimRecipe("ui_action_executed", required_families=["ui_action"])})
    worker = ClaimGraphWorker(adjudicator=adjudicator, graph_id="g_ui", mission_id="m_ui")
    result = UIAnchorActionExecutor().click_anchor_with_claim(
        _anchor(),
        _graph(),
        claim=_claim("ui_claim"),
        claim_worker=worker,
        elements=[_element()],
    )
    worker.stop()

    assert result.click_result.status == "EXECUTED"
    assert result.physical_receipts and result.physical_receipts[0].bounded
    assert result.claim_result is not None
    assert result.claim_result.adjudication is not None
    assert result.claim_result.adjudication.status == "verified"


def test_profile_preflight_blocks_unattended_when_metadata_missing() -> None:
    wizard = CalibrationWizard()
    profile = wizard.build_profile("hsr", "p1", (1920, 1080), [_anchor()], metadata={"language": "zh-CN"})
    report = wizard.preflight(profile, [_element()], required_anchors=["claim_button", "back_button"])

    assert report.ready_for_unattended is False
    assert report.ready_for_supervised is False
    assert "required_anchors_declared" in report.checklist
    assert any(issue.code == "missing_anchor_definition" for issue in report.issues)


class _UnavailableProvider:
    name = "fake"

    def status(self) -> VisionProviderStatus:
        return VisionProviderStatus("fake", False, "none", "mock://", False, message="not running")

    def describe_image(self, image: ImageInput, prompt: str) -> VisionResult:  # pragma: no cover - should not be called
        raise AssertionError("unavailable provider should not be called")

    def ground_ui(self, image: ImageInput, query: str) -> UIGroundingResult:  # pragma: no cover
        raise AssertionError("unavailable provider should not be called")

    def classify_screen(self, image: ImageInput, candidates: list[str]) -> ScreenStateResult:  # pragma: no cover
        raise AssertionError("unavailable provider should not be called")

    def explain_failure_with_image(self, summary: dict[str, object], image: ImageInput) -> dict[str, object]:  # pragma: no cover
        raise AssertionError("unavailable provider should not be called")


def test_local_vlm_optional_smoke_degrades_to_human_confirm_when_unavailable() -> None:
    result = LocalVlmBench(_UnavailableProvider()).run_optional_smoke()

    assert result.ok is False
    assert result.ui_grounding_success_rate == 0.0
    assert "requires_human_confirm" in result.message
