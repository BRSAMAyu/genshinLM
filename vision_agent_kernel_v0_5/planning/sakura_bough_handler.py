"""Q-37: Sacred Sakura (神樱大祓) handler for Inazuma.

Handles the Sacred Sakura cleansing puzzle across multiple
locations in Inazuma, requiring specific actions at each purification point.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class PurificationState(str, Enum):
    NOT_STARTED = "not_started"
    PURIFICATION_AVAILABLE = "purification_available"
    PURIFICATION_ACTIVE = "purification_active"
    PURIFICATION_COMPLETE = "purification_complete"
    BURST_READY = "burst_ready"


@dataclass(frozen=True, slots=True)
class PurificationPoint:
    """A single purification point in the ritual."""
    point_id: str
    location: str
    position: tuple[float, float]  # normalized 0-1
    state: PurificationState
    is_required: bool = True


@dataclass(frozen=True, slots=True)
class SakuraProgress:
    """Progress on Sacred Sakura ritual."""
    ritual_id: str
    points: list[PurificationPoint]
    completed_count: int
    total_required: int
    burst_available: bool
    guidance: str | None


class SakuraBoughHandler:
    """Handle Sacred Sakura (神樱大祓) ritual progression."""

    _REF_W = 1920
    _REF_H = 1080

    # Purification circle indicator (pink/purple glow)
    _PURIFY_PINK_LOW = np.array([140, 50, 50], dtype=np.uint8)
    _PURIFY_PINK_HIGH = np.array([170, 150, 200], dtype=np.uint8)

    # Burst indicator (bright white)
    _BURST_WHITE_LOW = np.array([0, 0, 220], dtype=np.uint8)
    _BURST_WHITE_HIGH = np.array([180, 20, 255], dtype=np.uint8)

    # Ritual area indicator
    _RITUAL_AREA_LOW = np.array([150, 30, 30], dtype=np.uint8)
    _RITUAL_AREA_HIGH = np.array([180, 100, 150], dtype=np.uint8)

    def __init__(
        self,
        on_point_complete: Any = None,
        on_ritual_complete: Any = None,
    ) -> None:
        self._on_point_complete = on_point_complete
        self._on_ritual_complete = on_ritual_complete

        self._ritual_id: str | None = None
        self._points: dict[str, PurificationPoint] = {}
        self._current_point: str | None = None
        self._burst_available = False

    def start_ritual(
        self,
        ritual_id: str,
        point_specs: list[dict[str, Any]],
    ) -> SakuraProgress:
        """Start a Sacred Sakura ritual.

        Args:
            ritual_id: Unique ritual identifier
            point_specs: List of purification point specs

        Returns:
            SakuraProgress with initial state
        """
        self._ritual_id = ritual_id
        self._points = {}
        self._current_point = None
        self._burst_available = False

        for spec in point_specs:
            point = PurificationPoint(
                point_id=spec["id"],
                location=spec.get("location", "Unknown"),
                position=spec.get("position", (0.5, 0.5)),
                state=PurificationState.NOT_STARTED,
                is_required=spec.get("required", True),
            )
            self._points[point.point_id] = point

        log.info("[SakuraBough] Started ritual %s with %d points", ritual_id, len(self._points))
        return self._get_progress()

    def detect_purification_state(
        self,
        frame: np.ndarray,
        frame_id: int = 0,
    ) -> SakuraProgress:
        """Detect purification state from frame.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            SakuraProgress with current state
        """
        if cv2 is None:
            return self._get_progress()

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Check for purification circle
        purify_mask = cv2.inRange(hsv, self._PURIFY_PINK_LOW, self._PURIFY_PINK_HIGH)
        purify_pixels = cv2.countNonZero(purify_mask)

        # Check for burst ready
        burst_mask = cv2.inRange(hsv, self._BURST_WHITE_LOW, self._BURST_WHITE_HIGH)
        burst_pixels = cv2.countNonZero(burst_mask)

        # Update burst availability
        self._burst_available = burst_pixels > 2000

        # Determine if at purification point
        if purify_pixels > 1000:
            # Find nearest incomplete point
            nearest = self._find_nearest_incomplete_point(frame)
            if nearest:
                self._current_point = nearest.point_id
                self._update_point_state(nearest.point_id, PurificationState.PURIFICATION_AVAILABLE)

        return self._get_progress()

    def _find_nearest_incomplete_point(self, frame: np.ndarray) -> PurificationPoint | None:
        """Find nearest incomplete purification point."""
        # Get character position (lower third of screen)
        h, w = frame.shape[:2]
        char_pos = (0.5, 0.7)  # Approximate

        incomplete = [p for p in self._points.values() if p.state == PurificationState.NOT_STARTED]
        if not incomplete:
            return None

        def distance(p: PurificationPoint) -> float:
            dx = p.position[0] - char_pos[0]
            dy = p.position[1] - char_pos[1]
            return dx * dx + dy * dy

        return min(incomplete, key=distance)

    def _update_point_state(self, point_id: str, state: PurificationState) -> None:
        """Update state of a purification point."""
        if point_id not in self._points:
            return

        point = self._points[point_id]
        if point.state == state:
            return

        self._points[point_id] = PurificationPoint(
            point_id=point.point_id,
            location=point.location,
            position=point.position,
            state=state,
            is_required=point.is_required,
        )

        if state == PurificationState.PURIFICATION_COMPLETE:
            log.info("[SakuraBough] Point %s complete", point_id)
            if self._on_point_complete:
                try:
                    self._on_point_complete(point_id)
                except Exception as exc:
                    log.warning("[SakuraBough] Point complete callback failed: %s", exc)

            # Check if all required points complete
            if self._check_all_required_complete():
                self._burst_available = True
                if self._on_ritual_complete:
                    try:
                        self._on_ritual_complete(self._ritual_id)
                    except Exception as exc:
                        log.warning("[SakuraBough] Ritual complete callback failed: %s", exc)

    def _check_all_required_complete(self) -> bool:
        """Check if all required purification points are complete."""
        for point in self._points.values():
            if point.is_required and point.state != PurificationState.PURIFICATION_COMPLETE:
                return False
        return True

    def mark_point_complete(self, point_id: str) -> SakuraProgress:
        """Mark a purification point as complete.

        Args:
            point_id: ID of completed point

        Returns:
            Updated SakuraProgress
        """
        self._update_point_state(point_id, PurificationState.PURIFICATION_COMPLETE)
        return self._get_progress()

    def is_burst_available(self) -> bool:
        """Check if purification burst is available."""
        return self._burst_available

    def _get_progress(self) -> SakuraProgress:
        """Get current ritual progress."""
        points_list = list(self._points.values())
        completed = sum(1 for p in points_list if p.state == PurificationState.PURIFICATION_COMPLETE)
        required = sum(1 for p in points_list if p.is_required)

        # Generate guidance
        guidance = None
        if self._burst_available:
            guidance = "All points purified - perform final burst"
        elif self._current_point:
            guidance = f"Purify current location: {self._current_point}"
        else:
            incomplete = [p for p in points_list if p.state == PurificationState.NOT_STARTED]
            if incomplete:
                guidance = f"Travel to next purification point ({len(incomplete)} remaining)"

        return SakuraProgress(
            ritual_id=self._ritual_id or "",
            points=points_list,
            completed_count=completed,
            total_required=required,
            burst_available=self._burst_available,
            guidance=guidance,
        )

    def get_next_point(self) -> PurificationPoint | None:
        """Get next purification point to visit."""
        incomplete = [p for p in self._points.values() if p.state == PurificationState.NOT_STARTED]
        if not incomplete:
            return None
        return incomplete[0]

    def get_completion_ratio(self) -> float:
        """Get ritual completion ratio."""
        progress = self._get_progress()
        if progress.total_required == 0:
            return 0.0
        return progress.completed_count / progress.total_required

    def is_ritual_complete(self) -> bool:
        """Check if ritual is complete."""
        return self._burst_available and self._check_all_required_complete()

    def reset(self) -> None:
        """Reset handler state."""
        self._ritual_id = None
        self._points = {}
        self._current_point = None
        self._burst_available = False
        log.info("[SakuraBoughHandler] Handler reset")