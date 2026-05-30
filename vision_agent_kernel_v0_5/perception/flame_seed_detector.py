"""E-44: Flame seed (火种) energy detector.

Detects flame seed pickups in Natlan's volcanic areas.
Flame seeds restore phlogiston and provide heat immunity temporarily.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class FlameSeedDetection:
    """Detected flame seed."""
    seed_detected: bool
    position: tuple[int, int] | None
    intensity: float  # 0.0-1.0 glow intensity
    radius: int
    nearby_count: int  # How many seeds nearby
    confidence: float


class FlameSeedDetector:
    """Detect flame seed energy pickups."""

    _REF_W = 1920
    _REF_H = 1080

    # Flame seed colors (bright red/orange with glow)
    _SEED_GLOW_LOW = np.array([0, 150, 150], dtype=np.uint8)
    _SEED_GLOW_HIGH = np.array([30, 255, 255], dtype=np.uint8)

    # Scan entire frame
    _SCAN_ROI = (0, 0, 1920, 1080)

    # Minimum seed size
    _MIN_SEED_AREA = 100
    _MAX_SEED_AREA = 5000

    def __init__(self) -> None:
        self._last_seeds: list[tuple[int, int]] = []

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> FlameSeedDetection:
        """Detect flame seeds in frame.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            FlameSeedDetection with seed info
        """
        if cv2 is None:
            return FlameSeedDetection(
                seed_detected=False,
                position=None,
                intensity=0.0,
                radius=0,
                nearby_count=0,
                confidence=0.0,
            )

        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._SCAN_ROI, sx, sy)
        scan_region = frame[y1:y2, x1:x2]

        if scan_region.size == 0:
            return FlameSeedDetection(
                seed_detected=False,
                position=None,
                intensity=0.0,
                radius=0,
                nearby_count=0,
                confidence=0.0,
            )

        hsv = cv2.cvtColor(scan_region, cv2.COLOR_BGR2HSV)

        # Detect flame glow
        glow_mask = cv2.inRange(hsv, self._SEED_GLOW_LOW, self._SEED_GLOW_HIGH)

        # Clean up
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        glow_mask = cv2.morphologyEx(glow_mask, cv2.MORPH_OPEN, kernel)

        # Find contours
        contours, _ = cv2.findContours(glow_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        seeds: list[tuple[int, int, int, float]] = []  # (x, y, radius, intensity)

        for contour in contours:
            area = cv2.contourArea(contour)
            if self._MIN_SEED_AREA < area < self._MAX_SEED_AREA:
                M = cv2.moments(contour)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"]) + x1
                    cy = int(M["m01"] / M["m00"]) + y1
                    radius = int(np.sqrt(area / 3.14))
                    # Intensity based on brightness
                    intensity = min(1.0, area / 1000)
                    seeds.append((cx, cy, radius, intensity))

        if not seeds:
            self._last_seeds = []
            return FlameSeedDetection(
                seed_detected=False,
                position=None,
                intensity=0.0,
                radius=0,
                nearby_count=0,
                confidence=0.0,
            )

        # Sort by intensity
        seeds.sort(key=lambda s: s[3], reverse=True)
        best = seeds[0]

        # Count nearby seeds
        nearby_count = sum(
            1 for s in seeds[1:]
            if np.sqrt((s[0] - best[0]) ** 2 + (s[1] - best[1]) ** 2) < 200
        )

        self._last_seeds = [(s[0], s[1]) for s in seeds]

        return FlameSeedDetection(
            seed_detected=True,
            position=(best[0], best[1]),
            intensity=best[3],
            radius=best[2],
            nearby_count=nearby_count,
            confidence=min(0.9, 0.5 + best[3] * 0.5),
        )

    def should_collect(self, detection: FlameSeedDetection) -> bool:
        """Determine if agent should collect detected seed."""
        return detection.seed_detected and detection.intensity >= 0.3

    def get_collection_target(self, detection: FlameSeedDetection) -> tuple[int, int] | None:
        """Get screen position to move towards for collection."""
        return detection.position

    def _scale_roi(self, roi: tuple[int, int, int, int], sx: float, sy: float) -> tuple[int, int, int, int]:
        """Scale ROI by resolution multiplier."""
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))