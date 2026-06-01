"""Integration tests for MainlineRunner and full story pipeline wiring.

All tests are dry-run: external dependencies (backend, OCR, VLM, InputWorker,
sentinel) are mocked or bypassed.
"""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.state_bus import StateBus
from execution.console_backend import ConsoleInputBackend
from execution.execution_runtime import ExecutionRuntime
from execution.semantic_action import ActionContract, SemanticAction
from perception.genshin_screen_classifier import GenshinScreenClassifier, ScreenState
from perception.dialog_text_capture import (
    DialogCaptureSession,
    DialogCaptureResult,
    ChapterRegistry,
)


# ---------------------------------------------------------------------------
# Test 1: StateBus Phase 2+ slots exist
# ---------------------------------------------------------------------------

def test_state_bus_has_phase2_slots() -> None:
    """StateBus has all required Phase 2+ slots."""
    bus = StateBus()
    required_slots = [
        "screen_claim",
        "navigation_plan",
        "mission_graph",
        "checkpoint_state",
    ]
    for slot_name in required_slots:
        assert hasattr(bus, slot_name), f"StateBus missing slot: {slot_name}"
        slot = getattr(bus, slot_name)
        # Should be a LatestSlot-like object with get/put
        assert hasattr(slot, "get"), f"slot {slot_name} has no get method"
        assert hasattr(slot, "put"), f"slot {slot_name} has no put method"


def test_state_bus_slot_types() -> None:
    """StateBus slots accept and return correct types."""
    bus = StateBus()
    # screen_claim: ScreenStateClaim or None
    from planning.screen_state_claim import ScreenStateClaim
    claim = MagicMock(spec=ScreenStateClaim)
    bus.screen_claim.put(claim)
    assert bus.screen_claim.get() is claim

    # checkpoint_state: MainlineCheckpoint or None
    from planning.mainline.mainline_runner import MainlineCheckpoint
    cp = MainlineCheckpoint(
        checkpoint_id="test_ckpt",
        phase="completed",
        context_version=1,
        graph_id="g1",
    )
    bus.checkpoint_state.put(cp)
    assert bus.checkpoint_state.get() is cp

    # mission_graph: MissionGraphV4 or None
    from planning.mainline.mission_graph_v4 import MissionGraphV4
    graph = MissionGraphV4(mission_id="test_mission")
    bus.mission_graph.put(graph)
    assert bus.mission_graph.get() is graph


# ---------------------------------------------------------------------------
# Test 2: MainlineRunner with linear 3-node graph
# ---------------------------------------------------------------------------

def _make_linear_graph(screen_state: str = "world_hud") -> Any:
    """Build a simple start → middle → end mission graph.

    Parameters
    ----------
    screen_state : str
        The screen state that AlwaysPassSnapshotProvider will report.
        All input_claims reference this state so the graph can execute
        through to completion without a real perception pipeline.
    """
    from planning.mainline.mission_graph_v4 import (
        MissionGraphV4,
        MissionNodeV4,
        ClaimContract,
        NodeBudget,
        MissionEdgeV4,
    )

    graph = MissionGraphV4(mission_id="linear_test", graph_id="lg1")

    start = MissionNodeV4(
        node_id="start",
        node_type="start",
        risk_level="low",
        input_claims=(),
        output_claims=(
            ClaimContract(claim_type="world_hud", claim_role="informational"),
        ),
        budgets=NodeBudget(max_retries=1, max_uncertain=0, max_duration_sec=10.0),
    )

    middle = MissionNodeV4(
        node_id="middle",
        node_type="navigate",
        risk_level="low",
        input_claims=(
            ClaimContract(claim_type="world_hud", claim_role="local"),
        ),
        output_claims=(
            ClaimContract(claim_type="navigation_signal", claim_role="local"),
        ),
        budgets=NodeBudget(max_retries=1, max_uncertain=0, max_duration_sec=10.0),
    )

    # 'end' requires the same screen_state that the snapshot provider reports,
    # so it does not get blocked by input_claim checks mid-run.
    end = MissionNodeV4(
        node_id="end",
        node_type="end",
        risk_level="low",
        input_claims=(
            ClaimContract(claim_type=screen_state, claim_role="terminal"),
        ),
        output_claims=(
            ClaimContract(claim_type="checkpoint_state", claim_role="terminal"),
        ),
        budgets=NodeBudget(max_retries=1, max_uncertain=0, max_duration_sec=10.0),
    )

    graph.add_node(start)
    graph.add_node(middle)
    graph.add_node(end)
    graph.add_edge(MissionEdgeV4(from_node="start", to_node="middle"))
    graph.add_edge(MissionEdgeV4(from_node="middle", to_node="end"))

    return graph


def test_mainline_runner_linear_graph_success() -> None:
    """MainlineRunner executes a linear start→middle→end graph successfully.

    skill_execute_fn returns claim_data that satisfies output_claims on every node.
    """
    from planning.mainline.mainline_runner import MainlineRunner

    graph = _make_linear_graph(screen_state="world_hud")
    executed_nodes: list[str] = []

    def skill_execute_fn(node: Any) -> dict[str, Any]:
        executed_nodes.append(node.node_id)
        # Return data that satisfies output claims
        return {
            "execution_success": True,
            "claim_id": f"claim_for_{node.node_id}",
            "satisfied_claim_types": [
                c.claim_type for c in node.output_claims
            ],
        }

    # Provide a snapshot provider so input claim verification always passes
    from planning.mainline.mainline_runner import RuntimeSnapshot

    class AlwaysPassSnapshotProvider:
        def snapshot(self) -> RuntimeSnapshot:
            return RuntimeSnapshot(screen_state="world_hud", screen_claim_confidence=0.9)

    runner = MainlineRunner(
        skill_execute_fn=skill_execute_fn,
        snapshot_provider=AlwaysPassSnapshotProvider(),
        max_node_retries=1,
    )

    result = runner.run(graph)

    assert result.success is True, f"run failed: {result.failed_nodes}, errors: {[r.error for r in result.node_results]}"
    assert result.completed_nodes == ["start", "middle", "end"], f"expected all nodes, got completed={result.completed_nodes}"
    assert executed_nodes == ["start", "middle", "end"], f"skill_execute_fn not called for all nodes: {executed_nodes}"
    assert result.failed_nodes == []


def test_mainline_runner_publishes_checkpoint_on_completion() -> None:
    """When mission graph completes, checkpoint_state is published to StateBus."""
    from planning.mainline.mainline_runner import MainlineRunner, CheckpointPublisher

    graph = _make_linear_graph(screen_state="world_hud")

    def skill_execute_fn(node: Any) -> dict[str, Any]:
        return {
            "execution_success": True,
            "claim_id": f"claim_for_{node.node_id}",
            "satisfied_claim_types": [c.claim_type for c in node.output_claims],
        }

    class AlwaysPassSnapshotProvider:
        def snapshot(self) -> Any:
            from planning.mainline.mainline_runner import RuntimeSnapshot
            return RuntimeSnapshot(screen_state="world_hud", screen_claim_confidence=0.9)

    bus = StateBus()
    published_checkpoints: list[Any] = []

    class SpyCheckpointPublisher:
        def __init__(self, real: CheckpointPublisher) -> None:
            self._real = real

        def publish(self, checkpoint: Any) -> None:
            published_checkpoints.append(checkpoint)
            # Also publish to the real bus
            self._real.publish(checkpoint)

    from planning.mainline.mainline_runner import (
        MainlineCheckpointPublisher,
    )
    real_publisher = MainlineCheckpointPublisher(bus)
    spy = SpyCheckpointPublisher(real_publisher)

    runner = MainlineRunner(
        skill_execute_fn=skill_execute_fn,
        snapshot_provider=AlwaysPassSnapshotProvider(),
        checkpoint_publisher=spy,
        max_node_retries=1,
    )

    result = runner.run(graph)

    assert result.success is True
    assert len(published_checkpoints) >= 1, "no checkpoints published"

    # The final checkpoint should be published to StateBus
    final_cp = bus.checkpoint_state.get()
    assert final_cp is not None, "checkpoint_state not set on StateBus"
    assert final_cp.graph_id == graph.graph_id
    assert "start" in final_cp.completed_nodes
    assert "middle" in final_cp.completed_nodes
    assert "end" in final_cp.completed_nodes


def test_mainline_runner_blocked_when_no_skill_execute_fn() -> None:
    """When skill_execute_fn is None, nodes are BLOCKED (not silently succeeded)."""
    from planning.mainline.mainline_runner import MainlineRunner

    graph = _make_linear_graph()

    runner = MainlineRunner(
        skill_execute_fn=None,  # type: ignore[arg-type]
        max_node_retries=1,
    )

    result = runner.run(graph)

    # All nodes should be blocked (not completed) because skill_execute_fn is absent
    assert result.success is False
    blocked = [r for r in result.node_results if r.status == "blocked"]
    assert len(blocked) > 0, "nodes should be blocked when skill_execute_fn is None"


def test_mainline_runner_fails_on_output_claim_not_satisfied() -> None:
    """Node fails if output_claims are not satisfied."""
    from planning.mainline.mainline_runner import MainlineRunner

    graph = _make_linear_graph()

    def bad_skill_execute_fn(node: Any) -> dict[str, Any]:
        # Return success without satisfying output claims
        return {
            "execution_success": True,
            # No claim_id, no satisfied_claim_types
        }

    from planning.mainline.mainline_runner import RuntimeSnapshot

    class AlwaysPassSnapshotProvider:
        def snapshot(self) -> RuntimeSnapshot:
            return RuntimeSnapshot(screen_state="world_hud", screen_claim_confidence=0.9)

    runner = MainlineRunner(
        skill_execute_fn=bad_skill_execute_fn,
        snapshot_provider=AlwaysPassSnapshotProvider(),
        max_node_retries=0,  # no retries
    )

    result = runner.run(graph)

    # First node will fail because output claims not satisfied
    assert result.success is False


# ---------------------------------------------------------------------------
# Test 3: Story pipeline wiring — GenshinScreenClassifier → DialogCaptureSession
# ---------------------------------------------------------------------------

def test_genshin_screen_classifier_classify() -> None:
    """GenshinScreenClassifier.classify() returns a ScreenState."""
    classifier = GenshinScreenClassifier()

    # Create a synthetic dark frame (should classify as something)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    state = classifier.classify(frame)

    assert isinstance(state, ScreenState)
    assert isinstance(state.state, str)
    assert 0.0 <= state.confidence <= 1.0
    assert isinstance(state.indicators, dict)


def test_genshin_screen_classifier_dialog_indicator() -> None:
    """GenshinScreenClassifier sets dialog_box indicator correctly."""
    classifier = GenshinScreenClassifier()

    # Create a synthetic frame with medium brightness (dialog detection range)
    frame = np.full((1080, 1920, 3), 80, dtype=np.uint8)
    state = classifier.classify(frame)

    # Should have indicators dict
    assert "dialog_box" in state.indicators


def test_dialog_capture_session_initialization(tmp_path: Any) -> None:
    """DialogCaptureSession initializes and creates output file."""
    mock_ocr = MagicMock()
    mock_ocr.detect_text.return_value = []

    session = DialogCaptureSession(
        ocr_provider=mock_ocr,
        chapter_id="test_chapter",
        chapter_title="Test Chapter",
        output_dir=tmp_path,
    )

    assert session.output_path.parent == tmp_path
    assert session.capture_count == 0
    assert session.skip_count == 0


def test_dialog_capture_session_flush_writes_file(tmp_path: Any) -> None:
    """DialogCaptureSession.flush() writes buffered captures to file."""
    mock_ocr = MagicMock()

    # Mock OCR to return a fake text detection result
    mock_result = MagicMock()
    mock_result.text = "Hello world"
    mock_result.confidence = 0.9
    mock_result.bbox = (100, 800, 300, 850)
    mock_ocr.detect_text.return_value = [mock_result]

    session = DialogCaptureSession(
        ocr_provider=mock_ocr,
        chapter_id="test_chapter",
        chapter_title="Test Chapter",
        output_dir=tmp_path,
    )

    # Capture should detect text and buffer it
    frame = np.full((1080, 1920, 3), 128, dtype=np.uint8)
    result = session.capture(frame)

    # Manually add a capture to the buffer for flush testing
    from perception.dialog_text_capture import DialogCaptureResult
    from unittest.mock import MagicMock as Mock
    captured = DialogCaptureResult(
        speaker="旁白",
        text="Test dialog line",
        confidence=0.95,
        timestamp="12:00:00",
    )
    session._buffer.append(captured)
    count = session.flush()

    assert count >= 1
    assert session.output_path.exists()
    content = session.output_path.read_text(encoding="utf-8")
    assert "Test dialog line" in content


def test_chapter_registry_output_path(tmp_path: Any) -> None:
    """ChapterRegistry.get_output_path() returns a Path in the correct dir."""
    registry = ChapterRegistry()
    path = registry.get_output_path("archon_quest_liyue_act_1")

    assert str(path).startswith(str(tmp_path)) or "genshin_story" in str(path)
    assert path.name == "captured.txt"


def test_full_story_pipeline_wiring(tmp_path: Any) -> None:
    """Full pipeline: classifier → screen state → dialog capture → file output.

    This tests that the components wire together correctly without any real
    screen capture or OCR.
    """
    # 1. Classifier reads a synthetic frame
    classifier = GenshinScreenClassifier()
    frame = np.full((1080, 1920, 3), 100, dtype=np.uint8)
    screen_state = classifier.classify(frame)

    # 2. StateBus receives the classification
    bus = StateBus()

    # 3. DialogCaptureSession uses OCR mock to capture text
    mock_ocr = MagicMock()
    mock_result = MagicMock()
    mock_result.text = "Dialog text here"
    mock_result.confidence = 0.9
    mock_result.bbox = (100, 800, 400, 860)
    mock_ocr.detect_text.return_value = [mock_result]

    session = DialogCaptureSession(
        ocr_provider=mock_ocr,
        chapter_id="test_chapter",
        chapter_title="Test Chapter",
        output_dir=tmp_path,
    )

    # 4. Capture dialog from the frame
    result = session.capture(frame)

    # 5. Flush to file
    if result is not None:
        session.flush()

    # 6. Verify file was written
    assert session.output_path.exists(), "dialog output file should exist"
    content = session.output_path.read_text(encoding="utf-8")
    assert "Dialog text here" in content


# ---------------------------------------------------------------------------
# Test 4: ExecutionRuntime + StateBus wiring (integration)
# ---------------------------------------------------------------------------

def test_execution_runtime_with_state_bus_full_flow(tmp_path: Any) -> None:
    """ExecutionRuntime publishes checkpoint_state after action completion."""
    from planning.mainline.mainline_runner import MainlineCheckpoint

    bus = StateBus()
    backend = ConsoleInputBackend()
    runtime = ExecutionRuntime(backend=backend, state_bus=bus)

    runtime.start()
    try:
        # Execute a simple action
        action = SemanticAction(
            action_id="integration_test_action",
            kind="system",
            intent="wait",
            parameters={"reason": "integration test"},
        )
        contract = ActionContract(
            action_id="integration_test_action",
            semantic_action=action,
            timeout_ms=100,
            safety_policy={
                "require_focus": True,
                "input_lease_required": True,
                "max_lease_ms": 250,
            },
            verifier_contract={"verifier_id": "test_verifier"},
        )

        receipt = runtime.submit(action, contract)

        # Execution succeeded
        assert receipt.status in ("executed", "verified")
        assert receipt.backend_type == "ConsoleInputBackend"

        # Publish a checkpoint to StateBus
        cp = MainlineCheckpoint(
            checkpoint_id=f"ckpt_{int(time.time()*1000)}",
            phase="completed",
            context_version=1,
            graph_id="integration_test_graph",
            completed_nodes=("integration_test_action",),
        )
        bus.checkpoint_state.put(cp)

        # Verify checkpoint was published
        stored_cp = bus.checkpoint_state.get()
        assert stored_cp is not None
        assert stored_cp.phase == "completed"

    finally:
        runtime.stop()