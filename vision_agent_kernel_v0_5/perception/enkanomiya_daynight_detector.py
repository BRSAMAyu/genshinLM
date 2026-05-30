"""E-48: Enkanomiya day/night detector for The Lost Riches.

Detects day/night state in Enkanomiya's abnormal timezone.
Enkanomiya has "white night" and "eternal night" phases which
affect certain mechanics and enemy spawns.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


class EnkanomiyaTime(str, Enum):
    WHITE_NIGHT = "white_night"     # Bright phase
    ETERNAL_NIGHT = "eternal_night" # Dark phase
    TRANSITION = "transition"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class EnkanomiyaDaynightDetection:
    """Detected Enkanomiya time state."""
    current_time: EnkanomiyaTime
    is_white_night: bool
    brightness_ratio: float  # 0.0=dark, 1.0=bright
    is_transitioning: bool
    confidence: float


class EnkanomiyaDaynightDetector:
    """Detect day/night state in Enkanomiya."""

    _REF_W = 1920
    _REF_H = 1080

    # White night indicators (bright blue-white sky)
    _WHITE_NIGHT_SKY_LOW = np.array([90, 10, 150], dtype=np.uint8)
    _WHITE_NIGHT_SKY_HIGH = np.array([130, 50, 255], dtype=np.uint8)

    # Eternal night indicators (deep blue-purple)
    _ETERNAL_NIGHT_SKY_LOW = np.array([100, 30, 20], dtype=np.uint8)
    _ETERNAL_NIGHT_SKY_HIGH = np.array([130, 100, 80], dtype=np.uint8)

    # Sky region (upper portion of screen)
    _SKY_ROI = (0, 0, 1920, 400)

    # Thresholds
    _BRIGHTNESS_THRESHOLD = 0.5
    _TRANSITION_MARGIN = 0.15

    def __init__(self) -> None:
        self._last_state: EnkanomiyaTime = EnkanomiyaTime.UNKNOWN
        self._brightness_history: list[float] = []

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> EnkanomiyaDaynightDetection:
        """Detect Enkanomiya day/night state.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            EnkanomiyaDaynightDetection with time state
        """
        if cv2 is None:
            return EnkanomiyaDaynightDetection(
                current_time=EnkanomiyaTime.UNKNOWN,
                is_white_night=False,
                brightness_ratio=0.0,
                is_transitioning=False,
                confidence=0.0,
            )

        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._SKY_ROI, sx, sy)
        sky_region = frame[y1:y2, x1:x2]

        if sky_region.size == 0:
            return EnkanomiyaDaynightDetection(
                current_time=self._last_state,
                is_white_night=self._last_state == EnkanomiyaTime.WHITE_NIGHT,
                brightness_ratio=0.0,
                is_transitioning=False,
                confidence=0.3,
            )

        hsv = cv2.cvtColor(sky_region, cv2.COLOR_BGR2HSV)

        # Calculate brightness (Value channel)
        avg_brightness = np.mean(hsv[:, :, 2]) / 255.0

        self._brightness_history.append(avg_brightness)
        if len(self._brightness_history) > 10:
            self._brightness_history.pop(0)

        # Check for white night sky
        white_night_mask = cv2.inRange(hsv, self._WHITE_NIGHT_SKY_LOW, self._WHITE_NIGHT_SKY_HIGH)
        white_night_pixels = cv2.countNonZero(white_night_mask)
        white_night_ratio = white_night_pixels / white_night_mask.size

        # Check for eternal night sky
        eternal_night_mask = cv2.inRange(hsv, self._ETERNAL_NIGHT_SKY_LOW, self._ETERNAL_NIGHT_SKY_HIGH)
        eternal_night_pixels = cv2.countNonZero(eternal_night_mask)
        eternal_night_ratio = eternal_night_pixels / eternal_night_mask.size

        # Determine state
        is_transitioning = abs(avg_brightness - self._BRIGHTNESS_THRESHOLD) < self._TRANSITION_MARGIN

        if white_night_ratio > 0.1 and white_night_ratio > eternal_night_ratio:
            current_time = EnkanomiyaTime.WHITE_NIGHT
        elif eternal_night_ratio > 0.1:
            current_time = EnkanomiyaTime.ETERNAL_NIGHT
        elif is_transitioning:
            current_time = EnkanomiyaTime.TRANSITION
        else:
            current_time = EnkanomiyaTime.UNKNOWN

        self._last_state = current_time

        confidence = 0.5
        if current_time == EnkanomiyaTime.WHITE_NIGHT:
            confidence = min(0.9, white_night_ratio * 5)
        elif current_time == EnkanomiyaTime.ETERNAL_NIGHT:
            confidence = min(0.9, eternal_night_ratio * 5)

        return EnkanomiyaDaynightDetection(
            current_time=current_time,
            is_white_night=current_time == EnkanomiyaTime.WHITE_NIGHT,
            brightness_ratio=avg_brightness,
            is_transitioning=is_transitioning,
            confidence=confidence,
        )

    def affects_mechanics(self, detection: EnkanomiyaDaynightDetection) -> bool:
        """Check if current time affects gameplay mechanics."""
        # Some treasures/sources only appear in specific phases
        return True  # Placeholder - actual implementation depends on specific mechanics

    def get_phase_guidance(self, detection: EnkanomiyaDaynightDetection) -> str:
        """Get guidance based on current phase."""
        if detection.current_time == EnkanomiyaTime.WHITE_NIGHT:
            return "White night phase - certain portals and treasures available"
        elif detection.current_time == EnkanomiyaTime.ETERNAL_NIGHT:
            return "Eternal night phase - some enemies stronger, seek light sources"
        elif detection.is_transitioning:
            return "Transitioning - prepare for phase change"
        return "Unknown phase - proceed with caution"

    def _scale_roi(self, roi: tuple[int, int, int, int], sx: float, sy: float) -> tuple[int, int, int, int]:
        """Scale ROI by resolution multiplier."""
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))