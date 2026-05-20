from __future__ import annotations

import numpy as np

from control.progress_supervisor import ProgressSupervisor, ProgressSupervisorConfig
from core.events import Interrupt
from core.state_bus import StateBus
from core.types import FocusState, Observation, TargetTrack
from orchestration.graph import ACQUIRE_TARGET, RECOVER, TRACK_AND_APPROACH, OrchestrationGraph
from perception.visual_trigger_detector import ColorTargetTracker, VisualTriggerDetector


def _track(state: str, missing_ms: float = 0.0, identity: float = 1.0) -> TargetTrack:
    return TargetTrack(
        track_id="color-target",
        class_id="red_block",
        state=state,
        bbox_xyxy=(600.0, 330.0, 664.0, 394.0),
        smoothed_center_px=(632.0, 362.0),
        velocity_px_s=(40.0, 0.0),
        confidence=identity,
        identity_confidence=identity,
        missing_duration_ms=missing_ms,
        bearing_deg=None,
        pitch_deg=None,
        estimated_range=None,
        last_seen_frame_id=1,
    )


def _observation(timestamp: float, track: TargetTrack | None) -> Observation:
    return Observation(
        frame_id=int(timestamp * 10),
        t_capture=timestamp,
        t_processed=timestamp,
        latency_ms=0.0,
        viewport_size=(1280, 720),
        target_track=track,
        obstacle_field=None,
        ui_state=None,
        visual_triggers={"target_visible": track is not None and track.state == "TRACKED"},
        os_focus=FocusState(focused=True),
        stale=track is None or track.state != "TRACKED",
    )


def test_tracker_coasts_then_lost() -> None:
    tracker = ColorTargetTracker(lost_timeout_ms=3000.0)
    first = _track("TRACKED")

    tracked = tracker.update(first, frame_id=1, timestamp=0.0)
    coasting = tracker.update(None, frame_id=2, timestamp=1.0)
    lost = tracker.update(None, frame_id=3, timestamp=3.2)

    assert tracked is not None and tracked.state == "TRACKED"
    assert coasting is not None and coasting.state == "COASTING"
    assert coasting.smoothed_center_px is not None
    assert coasting.missing_duration_ms == 1000.0
    assert lost is not None and lost.state == "LOST"
    assert lost.identity_confidence < coasting.identity_confidence


def test_tracker_keeps_track_id_and_lowers_identity_on_ambiguity() -> None:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[330:394, 600:664] = (220, 20, 20)
    frame[330:394, 720:784] = (220, 20, 20)
    detector = VisualTriggerDetector()
    tracker = ColorTargetTracker(ambiguity_distance_px=180.0)

    detections = detector.detect_targets(frame, frame_id=1, timestamp=0.0)
    track = tracker.update(detections, frame_id=1, timestamp=0.0)

    assert len(detections) == 2
    assert track is not None
    assert track.track_id == "color-target"
    assert track.identity_confidence < 1.0
    assert track.appearance_signature is not None
    assert track.appearance_signature["ambiguous"]


def test_progress_supervisor_emits_target_lost_interrupt() -> None:
    state_bus = StateBus()
    supervisor = ProgressSupervisor(
        state_bus,
        ProgressSupervisorConfig(escalate=95.0, target_lost_after_ms=3000.0),
    )

    state = supervisor.update(_observation(4.0, _track("LOST", missing_ms=3200.0, identity=0.2)))

    assert state.active_interrupt is not None
    assert state.active_interrupt.code == "TARGET_LOST"
    assert state.active_interrupt.priority == 2


def test_graph_target_lost_returns_to_acquire_then_recover() -> None:
    graph = OrchestrationGraph()
    interrupt = Interrupt(priority=2, timestamp=1.0, code="TARGET_LOST", source="unit")

    first = graph.next_for_interrupt(TRACK_AND_APPROACH, interrupt)
    second = graph.next_for_interrupt(ACQUIRE_TARGET, interrupt)

    assert first.next_state == ACQUIRE_TARGET
    assert second.next_state == RECOVER
