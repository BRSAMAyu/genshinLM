"""E-43: Lava detector for volcanic areas.

Detects lava surfaces and proximity for safety assessment.
Used in Inazuma (Tataratsuna) and other volcanic regions.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class LavaDetection:
    """Detected lava surface."""
    lava_detected: bool
    proximity_distance_px: int | None  # Distance to nearest lava
    is_in_danger_zone: bool
    danger_severity: float  # 0.0-1.0
    confidence: float


class LavaDetector:
    """Detect lava surfaces for safety assessment."""

    _REF_W = 1920
    _REF_H = 1080

    # Lava colors (bright red/orange/yellow)
    _LAVA_RED_LOW = np.array([0, 100, 100], dtype=np.uint8)
    _LAVA_RED_HIGH = np.array([20, 255, 255], dtype=np.uint8)

    _LAVA_ORANGE_LOW = np.array([10, 150, 150], dtype=np.uint8)
    _LAVA_ORANGE_HIGH = np.array([25, 255, 255], dtype=np.uint8)

    _LAVA_YELLOW_LOW = np.array([20, 150, 200], dtype=np.uint8)
    _LAVA_YELLOW_HIGH = np.array([35, 255, 255], dtype=np.uint8)

    # Safe distance threshold (pixels)
    _DANGER_DISTANCE_PX = 200

    def __init__(self) -> None:
        self._last_detection: LavaDetection | None = None

    def detect(self, frame: np.ndarray, character_pos: tuple[int, int] | None = None, frame_id: int = 0) -> LavaDetection:
        """Detect lava and assess danger.

        Args:
            frame: BGR image from screen capture
            character_pos: Optional character screen position
            frame_id: Current frame ID

        Returns:
            LavaDetection with proximity and danger info
        """
        if cv2 is None:
            return LavaDetection(
                lava_detected=False,
                proximity_distance_px=None,
                is_in_danger_zone=False,
                danger_severity=0.0,
                confidence=0.0,
            )

        h, w = frame.shape[:2]

        # Convert to HSV for color detection
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Detect lava colors
        red_mask = cv2.inRange(hsv, self._LAVA_RED_LOW, self._LAVA_RED_HIGH)
        orange_mask = cv2.inRange(hsv, self._LAVA_ORANGE_LOW, self._LAVA_ORANGE_HIGH)
        yellow_mask = cv2.inRange(hsv, self._LAVA_YELLOW_LOW, self._LAVA_YELLOW_HIGH)

        lava_mask = cv2.bitwise_or(red_mask, orange_mask)
        lava_mask = cv2.bitwise_or(lava_mask, yellow_mask)

        # Clean up noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        lava_mask = cv2.morphologyEx(lava_mask, cv2.MORPH_OPEN, kernel)

        lava_pixels = cv2.countNonZero(lava_mask)
        lava_ratio = lava_pixels / lava_mask.size

        if lava_ratio < 0.01:  # Very little lava detected
            return LavaDetection(
                lava_detected=False,
                proximity_distance_px=None,
                is_in_danger_zone=False,
                danger_severity=0.0,
                confidence=0.0,
            )

        # Calculate proximity to character if position provided
        proximity = None
        is_in_danger = False
        severity = min(1.0, lava_ratio * 10)

        if character_pos is not None:
            # Find closest lava pixel to character
            cx, cy = character_pos

            # Erode mask to get solid lava regions
            lava_solid = cv2.erode(lava_mask, kernel, iterations=2)

            # Find contours
            contours, _ = cv2.findContours(lava_solid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            min_distance = float('inf')
            for contour in contours:
                for point in contour:
                    px, py = point[0]
                    dist = np.sqrt((px - cx) ** 2 + (py - cy) ** 2)
                    min_distance = min(min_distance, dist)

            proximity = int(min_distance)
            is_in_danger = min_distance < self._DANGER_DISTANCE_PX
            severity = min(1.0, 1.0 - (min_distance / 500))

        confidence = min(0.9, 0.4 + lava_ratio * 5)

        detection = LavaDetection(
            lava_detected=True,
            proximity_distance_px=proximity,
            is_in_danger_zone=is_in_danger,
            danger_severity=severity,
            confidence=confidence,
        )

        self._last_detection = detection
        return detection

    def should_flee(self, detection: LavaDetection) -> bool:
        """Determine if agent should flee from lava."""
        return detection.is_in_danger_zone and detection.danger_severity >= 0.3

    def get_flee_direction(self, detection: LavaDetection, character_pos: tuple[int, int]) -> tuple[int, int]:
        """Get direction to flee from lava."""
        if not detection.lava_detected:
            return (0, 0)

        # In production, calculate actual flee direction
        # For now, suggest moving backward
        return (0, 100)  # Move up/back on screen