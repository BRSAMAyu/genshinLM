"""E-36: Underground water detector for Enkanomiya/below-surface areas.

Detects water surfaces in underground areas, distinguishing from
regular water for navigation purposes.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class WaterSurfaceDetection:
    """Detected water surface in underground area."""
    water_detected: bool
    surface_y: int | None  # Y coordinate of water surface
    depth_ratio: float  # 0.0=shallow, 1.0=deep
    is_underwater: bool  # Character is currently underwater
    confidence: float


class UndergroundWaterDetector:
    """Detect water surfaces in underground/below-surface areas."""

    _REF_W = 1920
    _REF_H = 1080

    # Underground water has blue/cyan tint (darker than surface water)
    _WATER_BLUE_LOW = np.array([90, 50, 30], dtype=np.uint8)
    _WATER_BLUE_HIGH = np.array([130, 150, 200], dtype=np.uint8)

    # Scan entire frame
    _SCAN_ROI = (0, 300, 1920, 1080)

    def __init__(self, depth_threshold: float = 0.5) -> None:
        self._depth_threshold = depth_threshold

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> WaterSurfaceDetection:
        """Detect water in underground areas.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            WaterSurfaceDetection with water information
        """
        if cv2 is None:
            return WaterSurfaceDetection(
                water_detected=False,
                surface_y=None,
                depth_ratio=0.0,
                is_underwater=False,
                confidence=0.0,
            )

        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._SCAN_ROI, sx, sy)
        scan_region = frame[y1:y2, x1:x2]

        if scan_region.size == 0:
            return WaterSurfaceDetection(
                water_detected=False,
                surface_y=None,
                depth_ratio=0.0,
                is_underwater=False,
                confidence=0.0,
            )

        # Detect blue/cyan water regions
        hsv = cv2.cvtColor(scan_region, cv2.COLOR_BGR2HSV)
        water_mask = cv2.inRange(hsv, self._WATER_BLUE_LOW, self._WATER_BLUE_HIGH)

        # Check water coverage
        total_pixels = water_mask.size
        water_pixels = cv2.countNonZero(water_mask)
        water_coverage = water_pixels / total_pixels

        if water_coverage < 0.05:  # Too little water to be significant
            return WaterSurfaceDetection(
                water_detected=False,
                surface_y=None,
                depth_ratio=0.0,
                is_underwater=False,
                confidence=0.0,
            )

        # Find water surface (topmost water pixels in each column)
        water_rows = np.where(water_mask > 0)[0]
        if len(water_rows) == 0:
            return WaterSurfaceDetection(
                water_detected=False,
                surface_y=None,
                depth_ratio=0.0,
                is_underwater=False,
                confidence=0.0,
            )

        surface_y = int(np.min(water_rows)) + y1

        # Estimate depth ratio based on how much of the frame is water
        depth_ratio = min(1.0, water_coverage * 3)

        # Check if character is underwater (UI indicator)
        is_underwater = self._check_underwater_ui(frame)

        confidence = 0.6 + water_coverage * 0.3

        return WaterSurfaceDetection(
            water_detected=True,
            surface_y=surface_y,
            depth_ratio=depth_ratio,
            is_underwater=is_underwater,
            confidence=confidence,
        )

    def _check_underwater_ui(self, frame: np.ndarray) -> bool:
        """Check if underwater UI indicator is visible."""
        # Check for underwater oxygen bar (typically in upper portion of screen)
        h, w = frame.shape[:2]
        ui_region = frame[0:int(h * 0.2), w // 4:3 * w // 4]

        if ui_region.size == 0:
            return False

        # Look for blue oxygen bar
        hsv = cv2.cvtColor(ui_region, cv2.COLOR_BGR2HSV)
        oxygen_mask = cv2.inRange(hsv, (100, 50, 150), (130, 200, 255))

        oxygen_pixels = cv2.countNonZero(oxygen_mask)
        oxygen_ratio = oxygen_pixels / oxygen_mask.size

        return oxygen_ratio > 0.1

    def _scale_roi(self, roi: tuple[int, int, int, int], sx: float, sy: float) -> tuple[int, int, int, int]:
        """Scale ROI by resolution multiplier."""
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))