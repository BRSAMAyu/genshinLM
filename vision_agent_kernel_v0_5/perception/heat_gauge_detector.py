"""E-38: Heat gauge detector for Inazuma's Mikage Furnace.

Detects the heat gauge UI in Mikage Furnace area to manage
overheat damage from the furnace's thermal vents.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


class HeatLevel(str, Enum):
    SAFE = "safe"          # 0-30%
    WARNING = "warning"    # 30-60%
    DANGER = "danger"      # 60-85%
    CRITICAL = "critical" # 85-100%


@dataclass(frozen=True, slots=True)
class HeatGaugeDetection:
    """Detected heat gauge state."""
    heat_ratio: float  # 0.0-1.0
    level: HeatLevel
    is_overheating: bool
    warning_shown: bool
    confidence: float


class HeatGaugeDetector:
    """Detect heat gauge in Mikage Furnace (御影炉心)."""

    _REF_W = 1920
    _REF_H = 1080

    # Heat gauge region (typically top-right corner)
    _GAUGE_ROI = (1500, 50, 1900, 150)

    # Heat gauge colors (red/orange gradient)
    _HEAT_RED_LOW = np.array([0, 100, 100], dtype=np.uint8)
    _HEAT_RED_HIGH = np.array([15, 255, 255], dtype=np.uint8)

    _HEAT_ORANGE_LOW = np.array([10, 150, 150], dtype=np.uint8)
    _HEAT_ORANGE_HIGH = np.array([25, 255, 255], dtype=np.uint8)

    # Thresholds
    _SAFE_THRESHOLD = 0.30
    _WARNING_THRESHOLD = 0.60
    _DANGER_THRESHOLD = 0.85

    def __init__(self) -> None:
        self._last_heat_ratio: float = 0.0

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> HeatGaugeDetection:
        """Detect heat gauge state.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            HeatGaugeDetection with heat level
        """
        if cv2 is None:
            return HeatGaugeDetection(
                heat_ratio=0.0,
                level=HeatLevel.SAFE,
                is_overheating=False,
                warning_shown=False,
                confidence=0.0,
            )

        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._GAUGE_ROI, sx, sy)
        gauge_region = frame[y1:y2, x1:x2]

        if gauge_region.size == 0:
            return HeatGaugeDetection(
                heat_ratio=self._last_heat_ratio,
                level=self._ratio_to_level(self._last_heat_ratio),
                is_overheating=self._last_heat_ratio > self._WARNING_THRESHOLD,
                warning_shown=False,
                confidence=0.3,
            )

        hsv = cv2.cvtColor(gauge_region, cv2.COLOR_BGR2HSV)

        # Detect heat (red/orange) portion
        heat_mask = cv2.inRange(hsv, self._HEAT_RED_LOW, self._HEAT_RED_HIGH)
        orange_mask = cv2.inRange(hsv, self._HEAT_ORANGE_LOW, self._HEAT_ORANGE_HIGH)
        combined_heat_mask = cv2.bitwise_or(heat_mask, orange_mask)

        # Calculate heat ratio
        total_pixels = gauge_region.shape[0] * gauge_region.shape[1]
        heat_pixels = cv2.countNonZero(combined_heat_mask)
        heat_ratio = heat_pixels / max(total_pixels, 1)

        self._last_heat_ratio = heat_ratio

        # Determine level
        level = self._ratio_to_level(heat_ratio)

        # Check for warning indicator
        warning_shown = self._detect_warning_indicator(gauge_region)

        confidence = 0.7 if heat_pixels > 50 else 0.4

        return HeatGaugeDetection(
            heat_ratio=heat_ratio,
            level=level,
            is_overheating=level in (HeatLevel.DANGER, HeatLevel.CRITICAL),
            warning_shown=warning_shown,
            confidence=confidence,
        )

    def _ratio_to_level(self, ratio: float) -> HeatLevel:
        """Convert ratio to heat level."""
        if ratio < self._SAFE_THRESHOLD:
            return HeatLevel.SAFE
        elif ratio < self._WARNING_THRESHOLD:
            return HeatLevel.WARNING
        elif ratio < self._DANGER_THRESHOLD:
            return HeatLevel.DANGER
        else:
            return HeatLevel.CRITICAL

    def _detect_warning_indicator(self, region: np.ndarray) -> bool:
        """Detect heat warning UI indicator."""
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

        # Bright yellow warning
        yellow_mask = cv2.inRange(hsv, (25, 150, 200), (35, 255, 255))
        yellow_pixels = cv2.countNonZero(yellow_mask)

        return yellow_pixels > 100

    def should_cool_down(self, detection: HeatGaugeDetection) -> bool:
        """Determine if agent should seek cooling."""
        return detection.level in (HeatLevel.DANGER, HeatLevel.CRITICAL) or detection.warning_shown

    def get_cooling_guidance(self, detection: HeatGaugeDetection) -> str | None:
        """Get guidance for cooling down."""
        if detection.level == HeatLevel.CRITICAL:
            return "CRITICAL: Leave the furnace area immediately!"
        elif detection.level == HeatLevel.DANGER:
            return "DANGER: Move to cooling area or use elemental skill"
        elif detection.level == HeatLevel.WARNING:
            return "Warning: Consider moving to cooler area"
        return None

    def _scale_roi(self, roi: tuple[int, int, int, int], sx: float, sy: float) -> tuple[int, int, int, int]:
        """Scale ROI by resolution multiplier."""
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))