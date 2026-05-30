"""E-37: Lightning warning detector for Inazuma/Seirai Island.

Detects lightning strike warnings (red warning indicators) to
allow the player to take shelter before being struck.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LightningWarningDetection:
    """Detected lightning warning."""
    warning_active: bool
    warning_type: str  # "immediate" | "approaching" | "none"
    screen_position: tuple[int, int] | None  # where on screen
    urgency: float  # 0.0-1.0
    estimated_strike_time_seconds: float | None


class LightningWarningDetector:
    """Detect lightning warning indicators in Inazuma."""

    _REF_W = 1920
    _REF_H = 1080

    # Red warning color (lightning indicator)
    _RED_WARNING_LOW = np.array([0, 100, 100], dtype=np.uint8)
    _RED_WARNING_HIGH = np.array([10, 255, 255], dtype=np.uint8)

    # Orange/amber approaching warning
    _ORANGE_WARNING_LOW = np.array([10, 150, 150], dtype=np.uint8)
    _ORANGE_WARNING_HIGH = np.array([25, 255, 255], dtype=np.uint8)

    # Scan entire frame
    _WARNING_ROI = (0, 0, 1920, 1080)

    def __init__(self) -> None:
        self._last_warning_time: float = 0.0
        self._warning_history: list[float] = []

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> LightningWarningDetection:
        """Detect lightning warning indicators.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            LightningWarningDetection with warning status
        """
        if cv2 is None:
            return LightningWarningDetection(
                warning_active=False,
                warning_type="none",
                screen_position=None,
                urgency=0.0,
                estimated_strike_time_seconds=None,
            )

        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._WARNING_ROI, sx, sy)
        scan_region = frame[y1:y2, x1:x2]

        if scan_region.size == 0:
            return LightningWarningDetection(
                warning_active=False,
                warning_type="none",
                screen_position=None,
                urgency=0.0,
                estimated_strike_time_seconds=None,
            )

        hsv = cv2.cvtColor(scan_region, cv2.COLOR_BGR2HSV)

        # Detect red immediate warning
        red_mask = cv2.inRange(hsv, self._RED_WARNING_LOW, self._RED_WARNING_HIGH)
        red_pixels = cv2.countNonZero(red_mask)

        # Detect orange approaching warning
        orange_mask = cv2.inRange(hsv, self._ORANGE_WARNING_LOW, self._ORANGE_WARNING_HIGH)
        orange_pixels = cv2.countNonZero(orange_mask)

        # Determine warning state
        current_time = time.perf_counter()

        if red_pixels > 1000:  # Immediate warning (large red area)
            # Find center of warning
            M = cv2.moments(red_mask)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"]) + x1
                cy = int(M["m01"] / M["m00"]) + y1
                position = (cx, cy)
            else:
                position = (w // 2, h // 3)

            # Calculate urgency based on coverage
            urgency = min(1.0, red_pixels / 5000)
            strike_time = 1.0  # Immediate strike imminent

            self._record_warning(current_time)

            log.warning("[Lightning] IMMEDIATE warning detected! pos=%s, urgency=%.2f", position, urgency)

            return LightningWarningDetection(
                warning_active=True,
                warning_type="immediate",
                screen_position=position,
                urgency=urgency,
                estimated_strike_time_seconds=strike_time,
            )

        elif orange_pixels > 500:  # Approaching warning
            M = cv2.moments(orange_mask)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"]) + x1
                cy = int(M["m01"] / M["m00"]) + y1
                position = (cx, cy)
            else:
                position = (w // 2, h // 3)

            urgency = min(0.8, orange_pixels / 3000)
            strike_time = 3.0  # A few seconds before strike

            self._record_warning(current_time)

            log.info("[Lightning] Approaching warning detected, urgency=%.2f", urgency)

            return LightningWarningDetection(
                warning_active=True,
                warning_type="approaching",
                screen_position=position,
                urgency=urgency,
                estimated_strike_time_seconds=strike_time,
            )

        # No warning
        return LightningWarningDetection(
            warning_active=False,
            warning_type="none",
            screen_position=None,
            urgency=0.0,
            estimated_strike_time_seconds=None,
        )

    def _record_warning(self, timestamp: float) -> None:
        """Record warning occurrence for frequency analysis."""
        self._warning_history.append(timestamp)
        # Keep only recent history
        self._warning_history = [t for t in self._warning_history if timestamp - t < 30.0]
        self._last_warning_time = timestamp

    def should_seek_shelter(self, detection: LightningWarningDetection) -> bool:
        """Determine if agent should seek shelter."""
        return detection.warning_active and detection.urgency >= 0.3

    def get_warning_frequency(self) -> float:
        """Get warning frequency (warnings per minute)."""
        if len(self._warning_history) < 2:
            return 0.0
        time_span = self._warning_history[-1] - self._warning_history[0]
        if time_span <= 0:
            return 0.0
        return len(self._warning_history) / (time_span / 60.0)

    def _scale_roi(self, roi: tuple[int, int, int, int], sx: float, sy: float) -> tuple[int, int, int, int]:
        """Scale ROI by resolution multiplier."""
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))