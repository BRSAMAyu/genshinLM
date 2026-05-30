"""E-40: Desert heat detector for Sumeru desert areas.

Detects the desert heat gauge UI when exploring Sumeru's desert
regions (Desert of Maalala, Hypostyle Desert, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


class HeatStressLevel(str, Enum):
    SAFE = "safe"          # In shade or night
    WARM = "warm"          # Daytime, normal exposure
    HOT = "hot"            # Direct sunlight
    EXHAUSTED = "exhausted"  # Heat stress building
    HEATSTROKE = "heatstroke"  # Critical - need cooling


@dataclass(frozen=True, slots=True)
class DesertHeatDetection:
    """Detected desert heat state."""
    heat_ratio: float  # 0.0-1.0
    level: HeatStressLevel
    needs_water: bool
    cooling_source_nearby: bool
    confidence: float


class DesertHeatDetector:
    """Detect desert heat gauge for Sumeru exploration."""

    _REF_W = 1920
    _REF_H = 1080

    # Heat gauge region (top-right, similar to sheer cold)
    _HEAT_ROI = (1500, 50, 1900, 150)

    # Desert heat colors (orange/amber)
    _HEAT_ORANGE_LOW = np.array([10, 100, 100], dtype=np.uint8)
    _HEAT_ORANGE_HIGH = np.array([30, 255, 255], dtype=np.uint8)

    # Water/cooling indicator (blue)
    _COOL_BLUE_LOW = np.array([100, 50, 50], dtype=np.uint8)
    _COOL_BLUE_HIGH = np.array([130, 255, 255], dtype=np.uint8)

    # Thresholds
    _SAFE_THRESHOLD = 0.20
    _WARM_THRESHOLD = 0.40
    _HOT_THRESHOLD = 0.60
    _EXHAUSTED_THRESHOLD = 0.80

    def __init__(self) -> None:
        self._last_heat_ratio: float = 0.0
        self._in_shade: bool = False

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> DesertHeatDetection:
        """Detect desert heat state.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            DesertHeatDetection with heat level
        """
        if cv2 is None:
            return DesertHeatDetection(
                heat_ratio=0.0,
                level=HeatStressLevel.SAFE,
                needs_water=False,
                cooling_source_nearby=False,
                confidence=0.0,
            )

        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._HEAT_ROI, sx, sy)
        heat_region = frame[y1:y2, x1:x2]

        if heat_region.size == 0:
            return DesertHeatDetection(
                heat_ratio=self._last_heat_ratio,
                level=self._ratio_to_level(self._last_heat_ratio),
                needs_water=self._last_heat_ratio > self._WARM_THRESHOLD,
                cooling_source_nearby=False,
                confidence=0.3,
            )

        hsv = cv2.cvtColor(heat_region, cv2.COLOR_BGR2HSV)

        # Detect heat (orange) portion
        heat_mask = cv2.inRange(hsv, self._HEAT_ORANGE_LOW, self._HEAT_ORANGE_HIGH)

        # Calculate heat ratio
        total_pixels = heat_region.shape[0] * heat_region.shape[1]
        heat_pixels = cv2.countNonZero(heat_mask)
        heat_ratio = heat_pixels / max(total_pixels, 1)

        self._last_heat_ratio = heat_ratio

        # Determine level
        level = self._ratio_to_level(heat_ratio)

        # Check for cooling sources (blue indicators)
        cooling_source_nearby = self._check_cooling_sources(frame)

        # Check if in shade
        self._in_shade = self._is_in_shade(frame)

        needs_water = level in (HeatStressLevel.HOT, HeatStressLevel.EXHAUSTED, HeatStressLevel.HEATSTROKE)

        confidence = 0.7 if heat_pixels > 50 else 0.4

        return DesertHeatDetection(
            heat_ratio=heat_ratio,
            level=level,
            needs_water=needs_water,
            cooling_source_nearby=cooling_source_nearby,
            confidence=confidence,
        )

    def _ratio_to_level(self, ratio: float) -> HeatStressLevel:
        """Convert ratio to heat stress level."""
        if ratio < self._SAFE_THRESHOLD:
            return HeatStressLevel.SAFE
        elif ratio < self._WARM_THRESHOLD:
            return HeatStressLevel.WARM
        elif ratio < self._HOT_THRESHOLD:
            return HeatStressLevel.HOT
        elif ratio < self._EXHAUSTED_THRESHOLD:
            return HeatStressLevel.EXHAUSTED
        else:
            return HeatStressLevel.HEATSTROKE

    def _check_cooling_sources(self, frame: np.ndarray) -> bool:
        """Check if cooling sources (water, shade markers) are visible."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        blue_mask = cv2.inRange(hsv, self._COOL_BLUE_LOW, self._COOL_BLUE_HIGH)
        blue_pixels = cv2.countNonZero(blue_mask)
        return blue_pixels > 200

    def _is_in_shade(self, frame: np.ndarray) -> bool:
        """Detect if character is in a shaded area."""
        h, w = frame.shape[:2]
        # Check lower third for shadows
        lower_region = frame[int(h * 0.7):, :]
        gray = cv2.cvtColor(lower_region, cv2.COLOR_BGR2GRAY)
        # Darker = more shadow
        avg_brightness = np.mean(gray)
        return avg_brightness < 80

    def should_seek_shade(self, detection: DesertHeatDetection) -> bool:
        """Determine if agent should seek shade."""
        return detection.level in (HeatStressLevel.HOT, HeatStressLevel.EXHAUSTED, HeatStressLevel.HEATSTROKE)

    def get_heat_guidance(self, detection: DesertHeatDetection) -> str | None:
        """Get guidance for heat management."""
        if detection.level == HeatStressLevel.HEATSTROKE:
            return "CRITICAL: Find shade and use water immediately!"
        elif detection.level == HeatStressLevel.EXHAUSTED:
            return "Exhausted: Seek shade and drink water"
        elif detection.level == HeatStressLevel.HOT:
            return "Hot: Consider finding shade or using cooling item"
        elif detection.level == HeatStressLevel.WARM:
            return "Warm: Stay hydrated"
        return None

    def _scale_roi(self, roi: tuple[int, int, int, int], sx: float, sy: float) -> tuple[int, int, int, int]:
        """Scale ROI by resolution multiplier."""
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))