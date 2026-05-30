"""Suction skill detector for Genshin Impact crowd control abilities.

P-53: Detects vacuum/suction effects from Anemo characters.
Identifies Venti Q, Sucrose E, Kazuha Q, and similar group enemies.

Visual indicators:
- Swirling particle effect (green/aqua)
- Circular vortex appearing at target location
- Enemies being pulled toward center
- Character-specific visual effects
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class SuctionSkill(Enum):
    """Types of suction skills."""
    VENTI_BURST = "venti_burst"
    SUCROSE_BURST = "sucrose_burst"
    KAZUHA_BURST = "kazuha_burst"
    JEAN_BURST = "jean_burst"
    FARUZAN_BURST = "faruzan_burst"
    GENERIC_ANEMO = "generic_anemo"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SuctionDetection:
    """P-53: Suction effect detection result."""
    skill_type: SuctionSkill
    center: tuple[float, float]        # Center of suction effect
    radius: float                      # Effect radius in pixels
    intensity: float                   # 0.0-1.0 suction strength
    is_active: bool                    # Suction currently active
    elapsed_frames: int                # Frames since detected
    confidence: float
    frame_id: int


@dataclass(frozen=True, slots=True)
class SuctionFieldStatus:
    """Overall suction field status."""
    active_suction: SuctionDetection | None
    suction_center: tuple[float, float] | None
    suction_radius: float
    is_grouping_enemies: bool
    recommended_action: str


class SuctionSkillDetector:
    """Detect vacuum/suction effects from Anemo crowd control abilities.

    Features:
    - Swirling particle detection
    - Circular vortex pattern recognition
    - Suction center and radius estimation
    - Skill type classification (Venti, Sucrose, etc.)

    Detection: Anemo green/aqua color + spiral motion pattern
    """

    _REF_W = 1920
    _REF_H = 1080

    # Suction effect color range (Anemo green/aqua)
    _ANEMO_GREEN_LOW = np.array([55, 100, 150])
    _ANEMO_GREEN_HIGH = np.array([85, 255, 255])

    # Swirling particle colors
    _SWIRL_WHITE_LOW = np.array([0, 0, 200])
    _SWIRL_WHITE_HIGH = np.array([180, 30, 255])

    # Vortex indicator (spiral pattern)
    _VORTEX_LOW = np.array([55, 80, 120])
    _VORTEX_HIGH = np.array([85, 200, 255])

    # Detection parameters
    MIN_VORTEX_PIXELS = 500
    MIN_SWIRL_PIXELS = 200

    # Suction skill visual characteristics
    _SKILL_SIGNATURES: dict[SuctionSkill, dict] = {
        SuctionSkill.VENTI_BURST: {
            "radius_range": (150, 300),
            "color_intensity": 0.9,
            "duration_frames": 180,  # ~3 seconds
        },
        SuctionSkill.SUCROSE_BURST: {
            "radius_range": (100, 200),
            "color_intensity": 0.7,
            "duration_frames": 120,  # ~2 seconds
        },
        SuctionSkill.KAZUHA_BURST: {
            "radius_range": (120, 250),
            "color_intensity": 0.8,
            "duration_frames": 150,  # ~2.5 seconds
        },
        SuctionSkill.JEAN_BURST: {
            "radius_range": (100, 200),
            "color_intensity": 0.7,
            "duration_frames": 120,
        },
        SuctionSkill.FARUZAN_BURST: {
            "radius_range": (150, 280),
            "color_intensity": 0.85,
            "duration_frames": 150,
        },
    }

    def __init__(self, now_fn=None) -> None:
        """Initialize suction skill detector.

        Args:
            now_fn: Time function (default: time.perf_counter)
        """
        self._now_fn = now_fn or time.perf_counter
        self._active_suction: SuctionDetection | None = None
        self._suction_history: deque[tuple[float, float, float]] = deque(maxlen=30)
        self._frame_count: int = 0

    @property
    def last_result(self) -> SuctionFieldStatus | None:
        """Get last detection result."""
        if self._active_suction is None:
            return None

        return SuctionFieldStatus(
            active_suction=self._active_suction,
            suction_center=self._active_suction.center,
            suction_radius=self._active_suction.radius,
            is_grouping_enemies=self._active_suction.is_active,
            recommended_action=self._get_recommended_action(),
        )

    def detect(
        self,
        frame: np.ndarray,
        frame_id: int,
    ) -> SuctionFieldStatus:
        """Detect suction effects in frame.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID

        Returns:
            SuctionFieldStatus with suction effect information
        """
        if cv2 is None or frame.size == 0:
            return SuctionFieldStatus(
                active_suction=None,
                suction_center=None,
                suction_radius=0.0,
                is_grouping_enemies=False,
                recommended_action="none",
            )

        self._frame_count = frame_id

        # Get center region for suction detection
        h, w = frame.shape[:2]
        roi = self._get_center_roi(frame)

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Detect anemo green components
        green_mask = cv2.inRange(hsv, self._ANEMO_GREEN_LOW, self._ANEMO_GREEN_HIGH)

        # Detect swirling white particles
        white_mask = cv2.inRange(hsv, self._SWIRL_WHITE_LOW, self._SWIRL_WHITE_HIGH)

        # Detect vortex pattern
        vortex_mask = cv2.inRange(hsv, self._VORTEX_LOW, self._VORTEX_HIGH)

        # Calculate metrics
        green_pixels = cv2.countNonZero(green_mask)
        white_pixels = cv2.countNonZero(white_mask)
        vortex_pixels = cv2.countNonZero(vortex_mask)

        # Check if suction is active
        is_active = (
            green_pixels >= self.MIN_VORTEX_PIXELS or
            vortex_pixels >= self.MIN_VORTEX_PIXELS
        )

        if is_active:
            # Calculate center and radius
            center, radius = self._calculate_vortex_center(
                green_mask if green_pixels > vortex_pixels else vortex_mask,
                white_mask,
            )

            # Classify skill type
            skill_type = self._classify_skill(radius, green_pixels + white_pixels)

            # Calculate intensity
            intensity = min(1.0, (green_pixels + white_pixels) / 3000.0)

            # Track history
            self._suction_history.append((center[0], center[1], intensity))

            self._active_suction = SuctionDetection(
                skill_type=skill_type,
                center=center,
                radius=radius,
                intensity=intensity,
                is_active=True,
                elapsed_frames=len(self._suction_history),
                confidence=min(intensity * 1.5, 1.0),
                frame_id=frame_id,
            )
        else:
            # Check if suction is fading
            if self._active_suction is not None:
                elapsed = frame_id - self._active_suction.frame_id

                # Suction has ended or is about to end
                if elapsed > 60:  # More than 1 second since last detection
                    self._active_suction = SuctionDetection(
                        skill_type=self._active_suction.skill_type,
                        center=self._active_suction.center,
                        radius=self._active_suction.radius,
                        intensity=self._active_suction.intensity * 0.8,
                        is_active=False,
                        elapsed_frames=self._active_suction.elapsed_frames,
                        confidence=self._active_suction.confidence * 0.9,
                        frame_id=self._active_suction.frame_id,
                    )

                    # Clear if nearly expired
                    if self._active_suction.intensity < 0.1:
                        self._active_suction = None

        return self.last_result or SuctionFieldStatus(
            active_suction=None,
            suction_center=None,
            suction_radius=0.0,
            is_grouping_enemies=False,
            recommended_action="none",
        )

    def _get_center_roi(self, frame: np.ndarray) -> np.ndarray:
        """Get center region for suction detection."""
        h, w = frame.shape[:2]

        # Center area where suction typically appears
        cx, cy = w // 2, h // 2
        radius = min(w, h) // 4

        x1 = max(0, cx - radius)
        y1 = max(0, cy - radius)
        x2 = min(w, cx + radius)
        y2 = min(h, cy + radius)

        return frame[y1:y2, x1:x2]

    def _calculate_vortex_center(
        self,
        main_mask: np.ndarray,
        particle_mask: np.ndarray,
    ) -> tuple[tuple[float, float], float]:
        """Calculate vortex center and radius."""
        # Combine masks
        combined = cv2.bitwise_or(main_mask, particle_mask)

        # Find contours
        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            h, w = main_mask.shape[:2]
            return ((w // 2, h // 2), 50.0)

        # Find largest contour (main vortex)
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)

        # Get centroid
        M = cv2.moments(largest)
        if M["m00"] > 0:
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
        else:
            h, w = main_mask.shape[:2]
            cx, cy = w // 2, h // 2

        # Calculate radius from area
        radius = (area / 3.14159) ** 0.5

        return ((float(cx), float(cy)), float(radius))

    def _classify_skill(
        self,
        radius: float,
        pixel_count: int,
    ) -> SuctionSkill:
        """Classify which suction skill is active."""
        # Match against known signatures
        best_match = SuctionSkill.UNKNOWN
        best_score = 0.0

        for skill, sig in self._SKILL_SIGNATURES.items():
            radius_min, radius_max = sig["radius_range"]
            expected_intensity = sig["color_intensity"]

            # Check radius match
            if radius_min <= radius <= radius_max:
                radius_score = 1.0
            elif radius < radius_min:
                radius_score = radius / radius_min
            else:
                radius_score = radius_max / radius

            # Check intensity match
            actual_intensity = pixel_count / 5000.0
            intensity_score = min(actual_intensity / expected_intensity, 1.0)

            total_score = (radius_score + intensity_score) / 2

            if total_score > best_score:
                best_score = total_score
                best_match = skill

        return best_match

    def _get_recommended_action(self) -> str:
        """Get recommended action during suction."""
        if self._active_suction is None:
            return "none"

        if self._active_suction.elapsed_frames < 30:
            return "wait_for_grouping"  # Let enemies group up

        if self._active_suction.elapsed_frames < 90:
            return "prepare_damage"  # Ready to deal damage

        return "execute_damage"  # Execute combo

    def is_suction_active(self) -> bool:
        """Quick check if suction is currently active."""
        return self._active_suction is not None and self._active_suction.is_active

    def get_suction_position(self) -> tuple[float, float] | None:
        """Get current suction center position."""
        if self._active_suction is None:
            return None
        return self._active_suction.center

    def reset(self) -> None:
        """Reset detector state."""
        self._active_suction = None
        self._suction_history.clear()
        self._frame_count = 0