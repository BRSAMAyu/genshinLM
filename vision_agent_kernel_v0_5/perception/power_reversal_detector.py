"""E-45: Power reversal (力量反转) mechanism detector.

Detects power reversal zones in Natlan's arena/coliseum areas.
These zones switch normal/powerful enemy states and may affect
player abilities temporarily.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


class ReversalState(str, Enum):
    NORMAL = "normal"      # Normal power state
    REVERSED = "reversed"  # Reversed/buffed state
    TRANSITIONING = "transitioning"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PowerReversalDetection:
    """Detected power reversal zone."""
    zone_detected: bool
    current_state: ReversalState
    target_state: ReversalState
    remaining_duration_seconds: float | None
    is_player_affected: bool
    confidence: float


class PowerReversalDetector:
    """Detect power reversal zones in Natlan arenas."""

    _REF_W = 1920
    _REF_H = 1080

    # Reversal zone colors
    # Normal state - blue glow
    _NORMAL_GLOW_LOW = np.array([100, 100, 100], dtype=np.uint8)
    _NORMAL_GLOW_HIGH = np.array([130, 255, 255], dtype=np.uint8)

    # Reversed state - purple/red glow
    _REVERSED_GLOW_LOW = np.array([140, 80, 80], dtype=np.uint8)
    _REVERSED_GLOW_HIGH = np.array([180, 255, 255], dtype=np.uint8)

    # Scan center area
    _SCAN_ROI = (400, 200, 1520, 880)

    def __init__(self) -> None:
        self._last_state: ReversalState = ReversalState.UNKNOWN
        self._transition_start: float | None = None

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> PowerReversalDetection:
        """Detect power reversal zone state.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            PowerReversalDetection with state information
        """
        import time

        if cv2 is None:
            return PowerReversalDetection(
                zone_detected=False,
                current_state=ReversalState.UNKNOWN,
                target_state=ReversalState.UNKNOWN,
                remaining_duration_seconds=None,
                is_player_affected=False,
                confidence=0.0,
            )

        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._SCAN_ROI, sx, sy)
        scan_region = frame[y1:y2, x1:x2]

        if scan_region.size == 0:
            return PowerReversalDetection(
                zone_detected=False,
                current_state=self._last_state,
                target_state=ReversalState.UNKNOWN,
                remaining_duration_seconds=None,
                is_player_affected=False,
                confidence=0.3,
            )

        hsv = cv2.cvtColor(scan_region, cv2.COLOR_BGR2HSV)

        # Check for normal glow
        normal_mask = cv2.inRange(hsv, self._NORMAL_GLOW_LOW, self._NORMAL_GLOW_HIGH)
        normal_pixels = cv2.countNonZero(normal_mask)

        # Check for reversed glow
        reversed_mask = cv2.inRange(hsv, self._REVERSED_GLOW_LOW, self._REVERSED_GLOW_HIGH)
        reversed_pixels = cv2.countNonZero(reversed_mask)

        # Determine state
        if normal_pixels > 500 and normal_pixels > reversed_pixels:
            current_state = ReversalState.NORMAL
            target_state = ReversalState.REVERSED
            confidence = min(0.9, normal_pixels / 2000)
        elif reversed_pixels > 500 and reversed_pixels > normal_pixels:
            current_state = ReversalState.REVERSED
            target_state = ReversalState.NORMAL
            confidence = min(0.9, reversed_pixels / 2000)
        else:
            current_state = ReversalState.UNKNOWN
            target_state = ReversalState.UNKNOWN
            confidence = 0.0

        # Check if zone detected
        zone_detected = normal_pixels > 100 or reversed_pixels > 100

        # Check if player is affected (center of frame shows effect)
        h2, w2 = scan_region.shape[:2]
        center_region = scan_region[h2//4:3*h2//4, w2//4:3*w2//4]
        center_hsv = cv2.cvtColor(center_region, cv2.COLOR_BGR2HSV)
        center_normal = cv2.countNonZero(cv2.inRange(center_hsv, self._NORMAL_GLOW_LOW, self._NORMAL_GLOW_HIGH))
        center_reversed = cv2.countNonZero(cv2.inRange(center_hsv, self._REVERSED_GLOW_LOW, self._REVERSED_GLOW_HIGH))
        is_affected = center_normal > 50 or center_reversed > 50

        # Estimate remaining duration (if transitioning)
        remaining = None
        if current_state != self._last_state:
            if self._transition_start is None:
                self._transition_start = time.perf_counter()
            else:
                elapsed = time.perf_counter() - self._transition_start
                remaining = max(0, 10.0 - elapsed)  # Assume 10s cycle

        self._last_state = current_state

        return PowerReversalDetection(
            zone_detected=zone_detected,
            current_state=current_state,
            target_state=target_state,
            remaining_duration_seconds=remaining,
            is_player_affected=is_affected,
            confidence=confidence,
        )

    def should_wait_for_reversal(self, detection: PowerReversalDetection) -> bool:
        """Determine if agent should wait for state reversal."""
        return detection.is_player_affected and detection.remaining_duration_seconds is not None

    def get_optimal_timing(self, detection: PowerReversalDetection) -> str:
        """Get advice on timing based on current state."""
        if detection.current_state == ReversalState.REVERSED:
            return "Wait for normal state before engaging"
        return "Current state is favorable for action"

    def _scale_roi(self, roi: tuple[int, int, int, int], sx: float, sy: float) -> tuple[int, int, int, int]:
        """Scale ROI by resolution multiplier."""
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))