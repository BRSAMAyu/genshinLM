"""E-29: Sandstorm detection using tan/brown color masking.

Sandstorms in Genshin (e.g., Desert of Maalala or Sumeru) appear as
a tan/brown overlay that reduces visibility significantly.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


class SandstormIntensity(str, Enum):
    NONE = "none"
    LIGHT = "light"      # Slight tan tint
    MODERATE = "moderate"  # Visible particles, reduced visibility
    SEVERE = "severe"    # Heavy overlay, near-blindness


@dataclass(frozen=True, slots=True)
class SandstormDetection:
    """Result of sandstorm detection."""
    detected: bool
    intensity: SandstormIntensity
    confidence: float
    coverage_ratio: float  # 0.0-1.0, percentage of frame affected
    particle_density: float  # 0.0-1.0


class SandstormDetector:
    """Detect sandstorm conditions in Genshin screens."""

    # Sandstorm color ranges in HSV
    _HUE_MIN = 10   # Yellow-orange
    _HUE_MAX = 35   # Brown-orange
    _SAT_MIN = 40   # Moderate saturation
    _SAT_MAX = 255
    _VAL_MIN = 80
    _VAL_MAX = 255

    # Thresholds
    _LIGHT_COVERAGE = 0.15
    _MODERATE_COVERAGE = 0.35
    _SEVERE_COVERAGE = 0.60

    _REF_W = 1920
    _REF_H = 1080

    def __init__(self) -> None:
        self._mask_cache: np.ndarray | None = None
        self._last_frame_id = -1

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> SandstormDetection:
        """Detect sandstorm from frame.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID for caching

        Returns:
            SandstormDetection with intensity and confidence
        """
        if cv2 is None:
            return SandstormDetection(
                detected=False,
                intensity=SandstormIntensity.NONE,
                confidence=0.0,
                coverage_ratio=0.0,
                particle_density=0.0,
            )

        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        # Convert to HSV
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Create mask for sandstorm colors
        lower = np.array([self._HUE_MIN, self._SAT_MIN, self._VAL_MIN], dtype=np.uint8)
        upper = np.array([self._HUE_MAX, self._SAT_MAX, self._VAL_MAX], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)

        # Morphological operations to clean up noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # Calculate coverage ratio
        total_pixels = mask.size
        sand_pixels = cv2.countNonZero(mask)
        coverage_ratio = sand_pixels / total_pixels

        # Calculate particle density (non-uniform regions)
        # High density = many small contours, low density = few large regions
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            contour_areas = [cv2.contourArea(c) for c in contours if cv2.contourArea(c) > 10]
            avg_area = np.mean(contour_areas) if contour_areas else 0
            # Small avg area = high density
            particle_density = max(0.0, min(1.0, 1.0 - (avg_area / (w * h * 0.1))))
        else:
            particle_density = 0.0

        # Determine intensity
        if coverage_ratio < self._LIGHT_COVERAGE:
            intensity = SandstormIntensity.NONE
            detected = False
            confidence = 0.0
        elif coverage_ratio < self._MODERATE_COVERAGE:
            intensity = SandstormIntensity.LIGHT
            detected = True
            confidence = 0.6
        elif coverage_ratio < self._SEVERE_COVERAGE:
            intensity = SandstormIntensity.MODERATE
            detected = True
            confidence = 0.8
        else:
            intensity = SandstormIntensity.SEVERE
            detected = True
            confidence = 0.9

        # Cache mask
        self._mask_cache = mask
        self._last_frame_id = frame_id

        return SandstormDetection(
            detected=detected,
            intensity=intensity,
            confidence=confidence,
            coverage_ratio=coverage_ratio,
            particle_density=particle_density,
        )

    def get_affected_region_mask(self, frame: np.ndarray) -> np.ndarray | None:
        """Return binary mask of sandstorm-affected regions."""
        if self._mask_cache is not None:
            return self._mask_cache
        self.detect(frame)
        return self._mask_cache

    def should_seek_shelter(self, detection: SandstormDetection) -> bool:
        """Determine if agent should seek shelter based on detection."""
        return detection.detected and detection.intensity in (
            SandstormIntensity.MODERATE,
            SandstormIntensity.SEVERE,
        )