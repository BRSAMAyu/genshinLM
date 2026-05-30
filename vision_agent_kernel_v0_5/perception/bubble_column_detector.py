"""E-35: Bubble column detector for underwater navigation.

Detects bubble columns in water (e.g., Inazuma underwater, Enkanomiya)
which push the player upward. Essential for underwater navigation.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class BubbleColumnDetection:
    """Detected bubble column position and strength."""
    detected: bool
    center: tuple[int, int] | None  # pixel position
    strength: float  # 0.0-1.0, how strong the upward push is
    radius: int  # approximate radius of effect area
    confidence: float


class BubbleColumnDetector:
    """Detect bubble columns that push player upward in water."""

    _REF_W = 1920
    _REF_H = 1080

    # Bubble colors (light gray/white)
    _BUBBLE_COLOR_LOW = np.array([0, 0, 200], dtype=np.uint8)
    _BUBBLE_COLOR_HIGH = np.array([180, 30, 255], dtype=np.uint8)

    # Scan region (lower portion of screen for underwater)
    _SCAN_ROI = (200, 400, 1720, 1080)

    def __init__(self, sensitivity: float = 0.7) -> None:
        self._sensitivity = sensitivity

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> BubbleColumnDetection:
        """Detect bubble columns in underwater scenes.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            BubbleColumnDetection with position and strength
        """
        if cv2 is None:
            return BubbleColumnDetection(
                detected=False,
                center=None,
                strength=0.0,
                radius=0,
                confidence=0.0,
            )

        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._SCAN_ROI, sx, sy)
        scan_region = frame[y1:y2, x1:x2]

        if scan_region.size == 0:
            return BubbleColumnDetection(
                detected=False,
                center=None,
                strength=0.0,
                radius=0,
                confidence=0.0,
            )

        # Detect light bubbles
        hsv = cv2.cvtColor(scan_region, cv2.COLOR_BGR2HSV)
        bubble_mask = cv2.inRange(hsv, self._BUBBLE_COLOR_LOW, self._BUBBLE_COLOR_HIGH)

        # Morphological operations to group bubbles
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        bubble_mask = cv2.morphologyEx(bubble_mask, cv2.MORPH_OPEN, kernel)

        # Find contours of bubble clusters
        contours, _ = cv2.findContours(bubble_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return BubbleColumnDetection(
                detected=False,
                center=None,
                strength=0.0,
                radius=0,
                confidence=0.0,
            )

        # Find the largest/strongest bubble cluster (likely the main column)
        best_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(best_contour)

        if area < 500:  # Too small to be significant
            return BubbleColumnDetection(
                detected=False,
                center=None,
                strength=0.0,
                radius=0,
                confidence=0.0,
            )

        # Calculate center and properties
        M = cv2.moments(best_contour)
        if M["m00"] > 0:
            cx = int(M["m10"] / M["m00"]) + x1
            cy = int(M["m01"] / M["m00"]) + y1
        else:
            cx, cy = x1 + (x2 - x1) // 2, y1 + (y2 - y1) // 2

        # Estimate radius from area
        radius = int(np.sqrt(area / 3.14))

        # Calculate strength based on coverage and size
        total_area = scan_region.shape[0] * scan_region.shape[1]
        coverage = area / total_area
        strength = min(1.0, coverage * self._sensitivity * 10)

        confidence = min(0.9, 0.5 + coverage * 2)

        return BubbleColumnDetection(
            detected=True,
            center=(cx, cy),
            strength=strength,
            radius=radius,
            confidence=confidence,
        )

    def should_ride_column(self, detection: BubbleColumnDetection) -> bool:
        """Determine if agent should ride a detected bubble column."""
        return detection.detected and detection.strength >= 0.3

    def get_navigation_offset(
        self, detection: BubbleColumnDetection, character_pos: tuple[int, int]
    ) -> tuple[int, int]:
        """Calculate navigation offset to reach bubble column center.

        Args:
            detection: Bubble column detection result
            character_pos: Character screen position (x, y)

        Returns:
            Offset (dx, dy) to move toward center
        """
        if not detection.detected or detection.center is None:
            return (0, 0)

        dx = detection.center[0] - character_pos[0]
        dy = detection.center[1] - character_pos[1]

        return (dx, dy)

    def _scale_roi(self, roi: tuple[int, int, int, int], sx: float, sy: float) -> tuple[int, int, int, int]:
        """Scale ROI by resolution multiplier."""
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))