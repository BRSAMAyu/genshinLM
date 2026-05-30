"""Shield type detector for Genshin Impact elemental shields.

P-45~P-46: Detects and classifies elemental shield types (Geo, Cryo, Electro, etc.)
and identifies weak state (虚弱) that reduces enemy defense.

Color library for shield identification:
- Geo (岩盾): Yellow/amber color scheme
- Cryo (冰盾): Light blue/white frost
- Electro (雷盾): Purple/violet electric
- Hydro (水盾): Blue/teal water
- Pyro (火盾): Red/orange flame
- Anemo (风盾): Green/aqua wind
- Dendro (草盾): Green/yellow plant
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class ShieldType(Enum):
    """Elemental shield types."""
    GEO = "geo"
    CRYO = "cryo"
    ELECTRO = "electro"
    HYDRO = "hydro"
    PYRO = "pyro"
    ANEMO = "anemo"
    DENDRO = "dendro"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class ShieldDetection:
    """P-45: Shield type detection result."""
    shield_type: ShieldType
    intensity: float                    # 0.0-1.0 shield strength
    position: tuple[float, float]       # Center position
    radius: float                      # Shield size estimate
    confidence: float
    frame_id: int
    is_weak: bool = False              # Weak state (虚弱) detected


@dataclass(frozen=True, slots=True)
class ShieldFieldStatus:
    """Overall shield field status."""
    primary_shield: ShieldType
    all_shields: tuple[ShieldDetection, ...]
    has_weak_enemies: bool
    recommended_element: str            # Counter element for current shield
    threat_level: Literal["low", "medium", "high"]


class ShieldTypeDetector:
    """Detect elemental shield types on enemies.

    Features:
    - Color-based shield type classification
    - Shield intensity estimation
    - Weak state (虚弱) detection
    - Counter element recommendations

    Uses HSV color ranges for element identification.
    """

    _REF_W = 1920
    _REF_H = 1080

    # Shield color ranges in HSV (OpenCV: H=0-179, S=0-255, V=0-255)
    _SHIELD_COLORS: dict[ShieldType, tuple[np.ndarray, np.ndarray]] = {
        # Geo: Yellow/amber shield
        ShieldType.GEO: (
            np.array([15, 100, 150]),
            np.array([35, 255, 255]),
        ),
        # Cryo: Light blue/white frost
        ShieldType.CRYO: (
            np.array([85, 50, 180]),
            np.array([115, 200, 255]),
        ),
        # Electro: Purple/violet electric
        ShieldType.ELECTRO: (
            np.array([130, 100, 150]),
            np.array([160, 255, 255]),
        ),
        # Hydro: Blue/teal water
        ShieldType.HYDRO: (
            np.array([90, 80, 120]),
            np.array([120, 255, 255]),
        ),
        # Pyro: Red/orange flame
        ShieldType.PYRO: (
            np.array([0, 150, 150]),
            np.array([15, 255, 255]),
        ),
        # Anemo: Green/aqua wind
        ShieldType.ANEMO: (
            np.array([55, 80, 150]),
            np.array([85, 255, 255]),
        ),
        # Dendro: Green/yellow plant
        ShieldType.DENDRO: (
            np.array([35, 100, 100]),
            np.array([80, 255, 255]),
        ),
    }

    # Weak state (虚弱) detection colors
    _WEAK_INDICATOR_LOW = np.array([0, 0, 200])
    _WEAK_INDICATOR_HIGH = np.array([180, 30, 255])

    # Counter elements
    _COUNTER_ELEMENTS: dict[ShieldType, str] = {
        ShieldType.GEO: "geo",        # Geo shatters Geo
        ShieldType.CRYO: "pyro",      # Pyro melts Cryo
        ShieldType.ELECTRO: "pyro",   # Overloaded
        ShieldType.HYDRO: "electro",  # Electro-Charged
        ShieldType.PYRO: "hydro",     # Vaporize
        ShieldType.ANEMO: "swirl",    # Anemo swirls
        ShieldType.DENDRO: "pyro",    # Burning
    }

    # Detection parameters
    MIN_SHIELD_PIXELS = 200
    SHIELD_EXPANSION_THRESHOLD = 0.3  # Shield grows by this ratio when strong

    def __init__(self, now_fn=None) -> None:
        """Initialize shield type detector.

        Args:
            now_fn: Time function (default: time.perf_counter)
        """
        self._now_fn = now_fn or time.perf_counter
        self._last_result: ShieldFieldStatus | None = None

    @property
    def last_result(self) -> ShieldFieldStatus | None:
        """Get last detection result."""
        return self._last_result

    def detect(
        self,
        frame: np.ndarray,
        frame_id: int,
        target_roi: tuple[int, int, int, int] | None = None,
    ) -> ShieldFieldStatus:
        """Detect shield types in frame.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID
            target_roi: Optional region to focus on (enemy position)

        Returns:
            ShieldFieldStatus with detected shield information
        """
        if cv2 is None or frame.size == 0:
            return ShieldFieldStatus(
                primary_shield=ShieldType.NONE,
                all_shields=(),
                has_weak_enemies=False,
                recommended_element="none",
                threat_level="low",
            )

        now = self._now_fn()

        # Get ROI
        if target_roi:
            x1, y1, x2, y2 = target_roi
            roi = frame[y1:y2, x1:x2]
            offset_x, offset_y = x1, y1
        else:
            roi = frame
            offset_x, offset_y = 0, 0

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        detections: list[ShieldDetection] = []
        primary_shield = ShieldType.NONE
        max_intensity = 0.0

        # Scan for each shield type
        for shield_type, (lower, upper) in self._SHIELD_COLORS.items():
            mask = cv2.inRange(hsv, lower, upper)
            pixel_count = cv2.countNonZero(mask)

            if pixel_count < self.MIN_SHIELD_PIXELS:
                continue

            # Calculate position
            moments = cv2.moments(mask)
            if moments["m00"] > 0:
                cx = moments["m10"] / moments["m00"] + offset_x
                cy = moments["m01"] / moments["m00"] + offset_y
            else:
                cx, cy = roi.shape[1] / 2 + offset_x, roi.shape[0] / 2 + offset_y

            # Calculate intensity
            intensity = min(1.0, pixel_count / 5000.0)

            # Calculate radius from area
            radius = (pixel_count / 3.14159) ** 0.5

            # Check for weak state
            is_weak = self._check_weak_state(hsv, int(cx - offset_x), int(cy - offset_y))

            detection = ShieldDetection(
                shield_type=shield_type,
                intensity=intensity,
                position=(float(cx), float(cy)),
                radius=radius,
                is_weak=is_weak,
                confidence=min(intensity * 2, 1.0),
                frame_id=frame_id,
            )
            detections.append(detection)

            if intensity > max_intensity:
                max_intensity = intensity
                primary_shield = shield_type

        # Determine threat level
        threat_level = self._compute_threat_level(detections)

        # Get recommended counter element
        recommended = self._COUNTER_ELEMENTS.get(primary_shield, "none")

        result = ShieldFieldStatus(
            primary_shield=primary_shield,
            all_shields=tuple(detections),
            has_weak_enemies=any(d.is_weak for d in detections),
            recommended_element=recommended,
            threat_level=threat_level,
        )

        self._last_result = result
        return result

    def _check_weak_state(self, hsv: np.ndarray, cx: int, cy: int) -> bool:
        """Check if enemy is in weak (虚弱) state."""
        # Weak state often shows as a purple/gray aura
        # Check region around center
        h, w = hsv.shape[:2]

        # Extract region
        x1 = max(0, cx - 50)
        y1 = max(0, cy - 50)
        x2 = min(w, cx + 50)
        y2 = min(h, cy + 50)

        region = hsv[y1:y2, x1:x2]
        if region.size == 0:
            return False

        # Check for weak indicator colors
        weak_mask = cv2.inRange(region, self._WEAK_INDICATOR_LOW, self._WEAK_INDICATOR_HIGH)
        weak_ratio = cv2.countNonZero(weak_mask) / max(weak_mask.size, 1)

        return weak_ratio > 0.15

    def _compute_threat_level(
        self,
        detections: list[ShieldDetection],
    ) -> Literal["low", "medium", "high"]:
        """Compute threat level based on shields."""
        if not detections:
            return "low"

        # Check for strong shields
        strong_shields = sum(1 for d in detections if d.intensity > 0.7)

        if strong_shields >= 2:
            return "high"

        if any(d for d in detections if d.intensity > 0.5):
            return "medium"

        return "low"

    def get_weak_targets(self) -> list[ShieldDetection]:
        """Get all detected weak targets."""
        if self._last_result is None:
            return []

        return [d for d in self._last_result.all_shields if d.is_weak]

    def get_counter_recommendation(self, shield_type: ShieldType) -> str:
        """Get recommended counter element for a shield type."""
        return self._COUNTER_ELEMENTS.get(shield_type, "none")

    def is_shielded(self) -> bool:
        """Check if any shields are currently detected."""
        if self._last_result is None:
            return False

        return self._last_result.primary_shield != ShieldType.NONE

    def reset(self) -> None:
        """Reset detector state."""
        self._last_result = None