"""Puzzle detection integration: bridges PuzzleDetector perception to CollaborationController.

When puzzles are detected on screen, this module triggers the appropriate
auto-downgrade in the collaboration controller and tracks puzzle state
for the planning layer.

Flow:
    PuzzleDetector → PuzzleIntegrationBridge → CollaborationController.report_puzzle_detected()
                                             → StateBus puzzle_event
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from perception.advanced_perception import PuzzleDetection, PuzzleState
from runtime.collaboration_controller import AutonomyLevel, CollaborationController

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PuzzleEvent:
    """Event emitted when a puzzle state changes."""
    puzzle_type: str
    state: PuzzleState
    confidence: float = 0.0
    requires_human: bool = False


@dataclass(slots=True)
class PuzzleIntegrationBridge:
    """Bridge between PuzzleDetector and CollaborationController.

    Usage::

        bridge = PuzzleIntegrationBridge(controller=ctrl)
        bridge.process_detections([puzzle_det])
        # If puzzle is active → auto-downgrade to ASSISTED
        # If puzzle is solved → emit solved event
    """

    controller: CollaborationController
    notify_fn: Callable[[PuzzleEvent], None] | None = None
    _active_puzzle_type: str = ""
    _active_puzzle_state: PuzzleState = PuzzleState.INACTIVE
    _puzzles_solved: int = 0

    def process_detections(self, detections: list[PuzzleDetection]) -> PuzzleEvent | None:
        """Process a list of puzzle detections and trigger appropriate actions."""
        if not detections:
            return None

        # Find the most relevant detection (first non-solved, or first overall)
        primary = detections[0]
        for d in detections:
            if d.state not in (PuzzleState.SOLVED, PuzzleState.UNKNOWN):
                primary = d
                break

        # State transition
        prev_state = self._active_puzzle_state
        self._active_puzzle_type = primary.puzzle_type
        self._active_puzzle_state = primary.state

        event: PuzzleEvent | None = None

        if primary.state == PuzzleState.ACTIVATED and prev_state != PuzzleState.ACTIVATED:
            # Puzzle detected — trigger downgrade
            event = PuzzleEvent(
                puzzle_type=primary.puzzle_type,
                state=primary.state,
                confidence=primary.confidence,
                requires_human=True,
            )
            self._trigger_puzzle_detected()

        elif primary.state == PuzzleState.SOLVED:
            event = PuzzleEvent(
                puzzle_type=primary.puzzle_type,
                state=PuzzleState.SOLVED,
                confidence=primary.confidence,
                requires_human=False,
            )
            self._puzzles_solved += 1
            self._active_puzzle_type = ""
            self._active_puzzle_state = PuzzleState.INACTIVE

        elif primary.state == PuzzleState.ERROR:
            event = PuzzleEvent(
                puzzle_type=primary.puzzle_type,
                state=PuzzleState.ERROR,
                confidence=primary.confidence,
                requires_human=True,
            )
            # Error state also triggers downgrade
            self._trigger_puzzle_detected()

        if event and self.notify_fn:
            self.notify_fn(event)

        return event

    def _trigger_puzzle_detected(self) -> None:
        """Trigger the puzzle-detected downgrade on the controller."""
        old_level = self.controller.level
        self.controller.report_puzzle_detected()
        if self.controller.level != old_level:
            log.info(
                "[PuzzleBridge] puzzle detected (%s), autonomy %s → %s",
                self._active_puzzle_type,
                old_level.name,
                self.controller.level.name,
            )

    @property
    def active_puzzle(self) -> str:
        return self._active_puzzle_type

    @property
    def active_state(self) -> PuzzleState:
        return self._active_puzzle_state

    @property
    def puzzles_solved(self) -> int:
        return self._puzzles_solved

    @property
    def stats(self) -> dict[str, int | str]:
        return {
            "active_puzzle": self._active_puzzle_type or "none",
            "active_state": self._active_puzzle_state.value,
            "puzzles_solved": self._puzzles_solved,
        }
