"""Domain entrance detector for Genshin Impact spiral abyss and domains.

P-56: Detects domain entrance visual elements.
Identifies purple vortex and portal door frame for domain/spiral abyss entry.

Visual indicators:
- Purple swirling vortex portal
- Door frame with glowing edges
- "秘境" / "Domain" / "深渊" label
- Circular portal energy
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


class DomainType(Enum):
    """Type of domain entrance."""
    ARTIFACT_DOMAIN = "artifact_domain"
    MATERIAL_DOMAIN = "material_domain"
    WEAPON_DOMAIN = "weapon_domain"
    TALENT_DOMAIN = "talent_domain"
    SPYRAL_ABYSS = "spiral_abyss"
    TRounce_DOMAIN = "trounce_domain"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DomainEntranceDetection:
    """P-56: Domain entrance detection result."""
    is_visible: bool
    domain_type: DomainType
    position: tuple[float, float]     # Portal center position
    size: float                        # Portal size estimate
    vortex_intensity: float            # Swirl effect strength
    door_frame_visible: bool          # Door frame detected
    prompt_visible: bool              # Interaction prompt visible
    confidence: float
    frame_id: int


@dataclass(frozen=True, slots=True)
class DomainEntranceStatus:
    """Overall domain entrance status."""
    entrance_detected: DomainEntranceDetection | None
    is_in_entry_range: bool
    domain_type: DomainType
    recommended_action: str


class DomainEntranceDetector:
    """Detect domain and spiral abyss entrance portals.

    Features:
    - Purple vortex portal detection
    - Door frame edge recognition
    - Domain type classification
    - Entry range estimation

    Detection: Purple swirl colors + circular portal shape
    """

    _REF_W = 1920
    _REF_H = 1080

    # Portal vortex colors (purple/violet)
    _VORTEX_PURPLE_LOW = np.array([120, 100, 150])
    _VORTEX_PURPLE_HIGH = np.array([160, 255, 255])

    # Portal energy (bright purple/white)
    _ENERGY_BRIGHT_LOW = np.array([130, 80, 200])
    _ENERGY_BRIGHT_HIGH = np.array([170, 255, 255])

    # Door frame edges (golden/white)
    _DOOR_FRAME_LOW = np.array([15, 50, 150])
    _DOOR_FRAME_HIGH = np.array([45, 200, 255])

    # Domain label colors (white text)
    _LABEL_WHITE_LOW = np.array([0, 0, 200])
    _LABEL_WHITE_HIGH = np.array([180, 20, 255])

    # Detection parameters
    MIN_VORTEX_PIXELS = 600
    MIN_DOOR_PIXELS = 200

    # Domain type colors (for classification)
    _DOMAIN_COLORS: dict[DomainType, tuple[np.ndarray, np.ndarray]] = {
        DomainType.ARTIFACT_DOMAIN: (
            np.array([0, 80, 150]),
            np.array([15, 255, 255]),  # Orange/gold
        ),
        DomainType.MATERIAL_DOMAIN: (
            np.array([50, 80, 150]),
            np.array([85, 255, 255]),  # Green
        ),
        DomainType.WEAPON_DOMAIN: (
            np.array([100, 80, 150]),
            np.array([130, 255, 255]),  # Blue
        ),
        DomainType.TALENT_DOMAIN: (
            np.array([0, 100, 150]),
            np.array([20, 255, 255]),  # Red/orange
        ),
        DomainType.SPYRAL_ABYSS: (
            np.array([120, 100, 150]),
            np.array([160, 255, 255]),  # Purple
        ),
        DomainType.TRounce_DOMAIN: (
            np.array([0, 150, 150]),
            np.array([15, 255, 255]),  # Deep red
        ),
    }

    # Search ROI (center-bottom for ground portals)
    _PORTAL_SEARCH_ROI = (0.15, 0.25, 0.85, 0.85)

    def __init__(self, now_fn=None) -> None:
        """Initialize domain entrance detector.

        Args:
            now_fn: Time function (default: time.perf_counter)
        """
        self._now_fn = now_fn or time.perf_counter
        self._last_detection: DomainEntranceDetection | None = None
        self._frame_count: int = 0

    @property
    def last_detection(self) -> DomainEntranceDetection | None:
        """Get last domain entrance detection."""
        return self._last_detection

    def detect(
        self,
        frame: np.ndarray,
        frame_id: int,
    ) -> DomainEntranceDetection:
        """Detect domain entrance in frame.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID

        Returns:
            DomainEntranceDetection with portal information
        """
        if cv2 is None or frame.size == 0:
            return self._make_no_detection(frame_id)

        self._frame_count = frame_id

        # Get search ROI
        roi = self._get_search_roi(frame)
        if roi.size == 0:
            return self._make_no_detection(frame_id)

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Detect vortex portal
        vortex_mask = cv2.inRange(hsv, self._VORTEX_PURPLE_LOW, self._VORTEX_PURPLE_HIGH)
        vortex_pixels = cv2.countNonZero(vortex_mask)

        # Detect energy glow
        energy_mask = cv2.inRange(hsv, self._ENERGY_BRIGHT_LOW, self._ENERGY_BRIGHT_HIGH)
        energy_pixels = cv2.countNonZero(energy_mask)

        # Detect door frame
        door_mask = cv2.inRange(hsv, self._DOOR_FRAME_LOW, self._DOOR_FRAME_HIGH)
        door_pixels = cv2.countNonZero(door_mask)

        # Detect label/prompt
        label_mask = cv2.inRange(hsv, self._LABEL_WHITE_LOW, self._LABEL_WHITE_HIGH)
        label_pixels = cv2.countNonZero(label_mask)
        prompt_visible = label_pixels > 80

        # Check for domain presence
        total_domain_pixels = vortex_pixels + energy_pixels
        is_visible = total_domain_pixels >= self.MIN_VORTEX_PIXELS

        if is_visible:
            # Calculate position and size
            position = self._calculate_portal_position(
                vortex_mask if vortex_pixels > energy_pixels else energy_mask,
            )
            size = self._estimate_portal_size(vortex_pixels + energy_pixels)

            # Calculate vortex intensity
            vortex_intensity = min(total_domain_pixels / 3000.0, 1.0)

            # Classify domain type
            domain_type = self._classify_domain_type(hsv, position)

            # Door frame visible
            door_frame_visible = door_pixels >= self.MIN_DOOR_PIXELS

            # Calculate confidence
            confidence = min(vortex_intensity * 2, 1.0)

            self._last_detection = DomainEntranceDetection(
                is_visible=True,
                domain_type=domain_type,
                position=position,
                size=size,
                vortex_intensity=vortex_intensity,
                door_frame_visible=door_frame_visible,
                prompt_visible=prompt_visible,
                confidence=confidence,
                frame_id=frame_id,
            )
        else:
            self._last_detection = self._make_no_detection(frame_id)

        return self._last_detection

    def _get_search_roi(self, frame: np.ndarray) -> np.ndarray:
        """Get search region for portal detection."""
        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1, y1, x2, y2 = self._PORTAL_SEARCH_ROI
        x1 = int(x1 * sx * self._REF_W)
        y1 = int(y1 * sy * self._REF_H)
        x2 = int(x2 * sx * self._REF_W)
        y2 = int(y2 * sy * self._REF_H)

        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        return frame[y1:y2, x1:x2]

    def _calculate_portal_position(self, mask: np.ndarray) -> tuple[float, float]:
        """Calculate portal center position."""
        moments = cv2.moments(mask)
        if moments["m00"] > 0:
            cx = moments["m10"] / moments["m00"]
            cy = moments["m01"] / moments["m00"]
        else:
            h, w = mask.shape[:2]
            cx, cy = w // 2, h // 2

        return (float(cx), float(cy))

    def _estimate_portal_size(self, pixel_count: int) -> float:
        """Estimate portal size from pixel count."""
        # Approximate radius from area
        return (pixel_count / 3.14159) ** 0.5

    def _classify_domain_type(
        self,
        hsv: np.ndarray,
        position: tuple[float, float],
    ) -> DomainType:
        """Classify the type of domain based on color."""
        # Check around the detected position
        cx, cy = int(position[0]), int(position[1])
        h, w = hsv.shape[:2]

        # Extract region around position
        x1 = max(0, cx - 50)
        y1 = max(0, cy - 50)
        x2 = min(w, cx + 50)
        y2 = min(h, cy + 50)

        region = hsv[y1:y2, x1:x2]
        if region.size == 0:
            return DomainType.UNKNOWN

        # Check against domain type colors
        best_type = DomainType.UNKNOWN
        best_ratio = 0.0

        for domain_type, (lower, upper) in self._DOMAIN_COLORS.items():
            mask = cv2.inRange(region, lower, upper)
            ratio = cv2.countNonZero(mask) / max(mask.size, 1)

            if ratio > best_ratio:
                best_ratio = ratio
                best_type = domain_type

        return best_type if best_ratio > 0.02 else DomainType.UNKNOWN

    def _make_no_detection(self, frame_id: int) -> DomainEntranceDetection:
        """Create a no-detection result."""
        return DomainEntranceDetection(
            is_visible=False,
            domain_type=DomainType.UNKNOWN,
            position=(0.0, 0.0),
            size=0.0,
            vortex_intensity=0.0,
            door_frame_visible=False,
            prompt_visible=False,
            confidence=0.0,
            frame_id=frame_id,
        )

    def get_status(self, frame_id: int) -> DomainEntranceStatus:
        """Get overall domain entrance status."""
        detection = self._last_detection

        if detection is None or not detection.is_visible:
            return DomainEntranceStatus(
                entrance_detected=None,
                is_in_entry_range=False,
                domain_type=DomainType.UNKNOWN,
                recommended_action="none",
            )

        is_in_range = detection.size > 100

        action = "none"
        if detection.prompt_visible:
            action = "press_f_to_enter"
        elif is_in_range:
            action = "approach_portal"
        else:
            action = "move_closer"

        return DomainEntranceStatus(
            entrance_detected=detection,
            is_in_entry_range=is_in_range,
            domain_type=detection.domain_type,
            recommended_action=action,
        )

    def is_portal_visible(self) -> bool:
        """Quick check if domain portal is visible."""
        return self._last_detection is not None and self._last_detection.is_visible

    def should_enter(self) -> bool:
        """Check if domain entry should happen."""
        if self._last_detection is None:
            return False
        return (
            self._last_detection.prompt_visible and
            self._last_detection.size > 100
        )

    def get_domain_type(self) -> DomainType:
        """Get detected domain type."""
        if self._last_detection is None:
            return DomainType.UNKNOWN
        return self._last_detection.domain_type

    def reset(self) -> None:
        """Reset detector state."""
        self._last_detection = None
        self._frame_count = 0