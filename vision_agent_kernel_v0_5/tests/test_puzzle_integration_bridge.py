"""Tests for planning/puzzle_integration_bridge.py: puzzle detection → collaboration downgrade."""
from __future__ import annotations

from perception.advanced_perception import PuzzleDetection, PuzzleState
from planning.puzzle_integration_bridge import (
    PuzzleEvent,
    PuzzleIntegrationBridge,
)
from runtime.collaboration_controller import AutonomyLevel, CollaborationController


class TestPuzzleEvent:
    def test_frozen(self):
        ev = PuzzleEvent(puzzle_type="torch", state=PuzzleState.ACTIVATED)
        mutated = False
        try:
            ev.puzzle_type = "other"  # type: ignore[misc]
        except AttributeError:
            mutated = True
        assert mutated

    def test_defaults(self):
        ev = PuzzleEvent(puzzle_type="torch", state=PuzzleState.SOLVED)
        assert ev.confidence == 0.0
        assert ev.requires_human is False


class TestPuzzleIntegrationBridge:
    def _make_bridge(self, level: AutonomyLevel = AutonomyLevel.SUPERVISED) -> PuzzleIntegrationBridge:
        ctrl = CollaborationController()
        ctrl.level = level
        return PuzzleIntegrationBridge(controller=ctrl)

    def test_no_detections_returns_none(self):
        bridge = self._make_bridge()
        assert bridge.process_detections([]) is None

    def test_activated_puzzle_triggers_downgrade(self):
        bridge = self._make_bridge(AutonomyLevel.SUPERVISED)
        det = PuzzleDetection(
            puzzle_type="torch", state=PuzzleState.ACTIVATED,
            confidence=0.9, position=(100, 200),
        )
        event = bridge.process_detections([det])
        assert event is not None
        assert event.state == PuzzleState.ACTIVATED
        assert event.requires_human is True
        assert bridge.controller.level == AutonomyLevel.ASSISTED

    def test_solved_puzzle_emits_event(self):
        bridge = self._make_bridge(AutonomyLevel.SUPERVISED)
        # First activate
        bridge.process_detections([
            PuzzleDetection(puzzle_type="torch", state=PuzzleState.ACTIVATED, confidence=0.9),
        ])
        # Then solve
        event = bridge.process_detections([
            PuzzleDetection(puzzle_type="torch", state=PuzzleState.SOLVED, confidence=0.95),
        ])
        assert event is not None
        assert event.state == PuzzleState.SOLVED
        assert bridge.puzzles_solved == 1
        assert bridge.active_puzzle == ""

    def test_error_puzzle_triggers_downgrade(self):
        bridge = self._make_bridge(AutonomyLevel.SUPERVISED)
        det = PuzzleDetection(
            puzzle_type="totem", state=PuzzleState.ERROR,
            confidence=0.7,
        )
        event = bridge.process_detections([det])
        assert event is not None
        assert event.state == PuzzleState.ERROR
        assert bridge.controller.level == AutonomyLevel.ASSISTED

    def test_inactive_puzzle_no_downgrade(self):
        bridge = self._make_bridge(AutonomyLevel.SUPERVISED)
        det = PuzzleDetection(
            puzzle_type="torch", state=PuzzleState.INACTIVE, confidence=0.5,
        )
        event = bridge.process_detections([det])
        # No state change from INACTIVE
        assert bridge.controller.level == AutonomyLevel.SUPERVISED

    def test_notify_fn_called(self):
        events: list[PuzzleEvent] = []

        def on_notify(ev: PuzzleEvent) -> None:
            events.append(ev)

        bridge = self._make_bridge()
        bridge.notify_fn = on_notify
        bridge.process_detections([
            PuzzleDetection(puzzle_type="torch", state=PuzzleState.ACTIVATED, confidence=0.8),
        ])
        assert len(events) == 1
        assert events[0].puzzle_type == "torch"

    def test_already_at_assisted_no_crash(self):
        bridge = self._make_bridge(AutonomyLevel.ASSISTED)
        det = PuzzleDetection(puzzle_type="torch", state=PuzzleState.ACTIVATED, confidence=0.9)
        bridge.process_detections([det])
        assert bridge.controller.level == AutonomyLevel.ASSISTED

    def test_manual_level_no_downgrade(self):
        bridge = self._make_bridge(AutonomyLevel.MANUAL)
        det = PuzzleDetection(puzzle_type="torch", state=PuzzleState.ACTIVATED, confidence=0.9)
        bridge.process_detections([det])
        assert bridge.controller.level == AutonomyLevel.MANUAL

    def test_stats(self):
        bridge = self._make_bridge()
        bridge.process_detections([
            PuzzleDetection(puzzle_type="totem", state=PuzzleState.ACTIVATED, confidence=0.8),
        ])
        stats = bridge.stats
        assert stats["active_puzzle"] == "totem"
        assert stats["active_state"] == "activated"
        assert stats["puzzles_solved"] == 0

    def test_multiple_solves_counted(self):
        bridge = self._make_bridge()
        for i in range(3):
            bridge.process_detections([
                PuzzleDetection(puzzle_type=f"puzzle_{i}", state=PuzzleState.SOLVED, confidence=0.9),
            ])
        assert bridge.puzzles_solved == 3

    def test_multi_detection_picks_first_non_solved(self):
        bridge = self._make_bridge()
        dets = [
            PuzzleDetection(puzzle_type="solved_one", state=PuzzleState.SOLVED, confidence=0.9),
            PuzzleDetection(puzzle_type="torch", state=PuzzleState.ACTIVATED, confidence=0.8),
            PuzzleDetection(puzzle_type="totem", state=PuzzleState.INACTIVE, confidence=0.5),
        ]
        event = bridge.process_detections(dets)
        assert event is not None
        assert event.puzzle_type == "torch"
        assert bridge.active_puzzle == "torch"
