"""E-47: Timed chest (限时紧迫感) detector.

Detects timed chest urgency indicators (countdown timer, urgency particles)
to prioritize time-sensitive chests over regular exploration.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class TimedChestDetection:
    """Detected timed chest state."""
    is_timed: bool
    time_remaining_seconds: float | None
    urgency_level: str  # "none" | "low" | "medium" | "high" | "critical"
    has_countdown_ui: bool
    chest_position: tuple[int, int] | None
    confidence: float


class TimedChestDetector:
    """Detect timed chest urgency indicators."""

    _REF_W = 1920
    _REF_H = 1080

    # Timed chest urgency particles (golden sparks)
    _URGENCY_GOLD_LOW = np.array([20, 150, 150], dtype=np.uint8)
    _URGENCY_GOLD_HIGH = np.array([35, 255, 255], dtype=np.uint8)

    # Countdown UI colors (red for urgent)
    _COUNTDOWN_RED_LOW = np.array([0, 100, 100], dtype=np.uint8)
    _COUNTDOWN_RED_HIGH = np.array([10, 255, 255], dtype=np.uint8)

    # Scan area around chest location
    _SCAN_ROI = (0, 0, 1920, 1080)

    def __init__(self) -> None:
        self._last_urgency_level: str = "none"
        self._particle_history: list[int] = []

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> TimedChestDetection:
        """Detect timed chest urgency.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            TimedChestDetection with urgency information
        """
        if cv2 is None:
            return TimedChestDetection(
                is_timed=False,
                time_remaining_seconds=None,
                urgency_level="none",
                has_countdown_ui=False,
                chest_position=None,
                confidence=0.0,
            )

        h, w = frame.shape[:2]

        # Detect urgency particles (golden sparks around chest)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        urgency_mask = cv2.inRange(hsv, self._URGENCY_GOLD_LOW, self._URGENCY_GOLD_HIGH)

        # Clean up
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        urgency_mask = cv2.morphologyEx(urgency_mask, cv2.MORPH_OPEN, kernel)

        urgency_pixels = cv2.countNonZero(urgency_mask)

        # Track particle count for urgency
        self._particle_history.append(urgency_pixels)
        if len(self._particle_history) > 10:
            self._particle_history.pop(0)

        # Check for countdown UI
        countdown_mask = cv2.inRange(hsv, self._COUNTDOWN_RED_LOW, self._COUNTDOWN_RED_HIGH)
        countdown_pixels = cv2.countNonZero(countdown_mask)
        has_countdown = countdown_pixels > 200

        # Find chest position
        chest_pos = self._find_chest_position(frame)

        # Determine urgency level
        avg_particles = sum(self._particle_history) / max(len(self._particle_history), 1)
        particle_rate = urgency_pixels

        if has_countdown:
            urgency_level = "critical"
            time_remaining = 10.0  # Placeholder
        elif particle_rate > 2000:
            urgency_level = "high"
            time_remaining = 30.0
        elif particle_rate > 1000:
            urgency_level = "medium"
            time_remaining = 60.0
        elif particle_rate > 500:
            urgency_level = "low"
            time_remaining = 120.0
        else:
            urgency_level = "none"
            time_remaining = None

        is_timed = urgency_level != "none"

        confidence = 0.5
        if is_timed:
            confidence = min(0.9, 0.4 + avg_particles / 2000)

        return TimedChestDetection(
            is_timed=is_timed,
            time_remaining_seconds=time_remaining,
            urgency_level=urgency_level,
            has_countdown_ui=has_countdown,
            chest_position=chest_pos,
            confidence=confidence,
        )

    def _find_chest_position(self, frame: np.ndarray) -> tuple[int, int] | None:
        """Find chest position in frame."""
        # Detect golden chest
        chest_lower = np.array([15, 100, 100], dtype=np.uint8)
        chest_upper = np.array([40, 255, 255], dtype=np.uint8)

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, chest_lower, chest_upper)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            largest = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest)
            if area > 500:
                M = cv2.moments(largest)
                if M["m00"] > 0:
                    return (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))

        return None

    def should_prioritize(self, detection: TimedChestDetection) -> bool:
        """Determine if this chest should be prioritized."""
        return detection.is_timed and detection.urgency_level in ("high", "critical", "medium")

    def get_priority_score(self, detection: TimedChestDetection) -> float:
        """Get priority score for chest (higher = more urgent)."""
        if not detection.is_timed:
            return 0.0

        scores = {"none": 0.0, "low": 0.3, "medium": 0.6, "high": 0.8, "critical": 1.0}
        return scores.get(detection.urgency_level, 0.0)

    def get_time_warning(self, detection: TimedChestDetection) -> str | None:
        """Get time-related warning message."""
        if detection.urgency_level == "critical":
            return "Open immediately - almost out of time!"
        elif detection.urgency_level == "high":
            return "Hurry - limited time remaining"
        elif detection.urgency_level == "medium":
            return "Moderate urgency - prioritize this chest"
        return None