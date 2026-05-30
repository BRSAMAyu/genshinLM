"""Elemental reaction detection for Genshin Impact combat.

Implements P-33: Elemental Reaction Detector
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Element Types
# ---------------------------------------------------------------------------

class Element(Enum):
    PYRO = "pyro"
    HYDRO = "hydro"
    ELECTRO = "electro"
    CRYO = "cryo"
    ANEMO = "anemo"
    GEO = "geo"
    DENDRO = "dendro"


# ---------------------------------------------------------------------------
# Reaction Types
# ---------------------------------------------------------------------------

class ReactionType(Enum):
    VAPORIZE = "vaporize"           # Hydro + Pyro
    MELT = "melt"                   # Pyro + Cryo
    ELECTRO_CHARGED = "electro_charged"   # Electro + Hydro
    SUPERCONDUCT = "superconduct"    # Electro + Cryo
    OVERLOADED = "overloaded"       # Electro + Pyro
    BURNING = "burning"             # Pyro + Dendro
    QUICKEN = "quicken"             # Electro + Dendro
    FROZEN = "frozen"              # Hydro + Cryo
    SWIRL = "swirl"                 # Anemo + any
    CRYSTALLIZE = "crystallize"    # Geo + any
    BLOOM = "bloom"                # Dendro + Hydro
    EXPLOSION = "explosion"         # Dendro + Pyro/Electro


# ---------------------------------------------------------------------------
# Reaction Detection Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ReactionDetection:
    reaction_type: ReactionType
    primary_element: Element | None
    secondary_element: Element | None
    position: tuple[float, float]   # Center position (x, y)
    intensity: float               # 0.0-1.0 effect strength
    duration_frames: int           # How many frames detected
    confidence: float              # Detection confidence
    timestamp: float


@dataclass(frozen=True, slots=True)
class ReactionFieldStatus:
    active_reactions: tuple[ReactionDetection, ...]
    dominant_reaction: ReactionType | None
    reaction_count: int
    recommended_action: str


# ---------------------------------------------------------------------------
# HSV Color Ranges for Reactions
# ---------------------------------------------------------------------------

_REACTION_COLORS: dict[ReactionType, tuple[tuple[np.ndarray, np.ndarray], Element, Element]] = {
    # Vaporize: Yellow/orange burst
    ReactionType.VAPORIZE: (
        (np.array([10, 150, 200]), np.array([35, 255, 255])),
        Element.HYDRO,
        Element.PYRO,
    ),
    # Melt: Red/orange flame burst
    ReactionType.MELT: (
        (np.array([0, 180, 200]), np.array([15, 255, 255])),
        Element.PYRO,
        Element.CRYO,
    ),
    # Electro-Charged: Blue/purple sparks
    ReactionType.ELECTRO_CHARGED: (
        (np.array([120, 150, 150]), np.array([160, 255, 255])),
        Element.ELECTRO,
        Element.HYDRO,
    ),
    # Superconduct: Light blue ice shatter
    ReactionType.SUPERCONDUCT: (
        (np.array([85, 80, 180]), np.array([110, 255, 255])),
        Element.ELECTRO,
        Element.CRYO,
    ),
    # Overloaded: Orange explosion
    ReactionType.OVERLOADED: (
        (np.array([5, 200, 200]), np.array([25, 255, 255])),
        Element.ELECTRO,
        Element.PYRO,
    ),
    # Frozen: Blue/white ice
    ReactionType.FROZEN: (
        (np.array([90, 50, 200]), np.array([120, 255, 255])),
        Element.HYDRO,
        Element.CRYO,
    ),
    # Swirl: Green/aqua spiral
    ReactionType.SWIRL: (
        (np.array([55, 120, 150]), np.array([85, 255, 255])),
        Element.ANEMO,
        Element.PYRO,  # Pyro swirl is most common
    ),
    # Crystallize: Yellow/amber shards
    ReactionType.CRYSTALLIZE: (
        (np.array([15, 100, 150]), np.array([35, 255, 255])),
        Element.GEO,
        Element.PYRO,
    ),
    # Burning: Orange flame with green tinge
    ReactionType.BURNING: (
        (np.array([10, 150, 150]), np.array([50, 255, 255])),
        Element.PYRO,
        Element.DENDRO,
    ),
    # Quicken: Green/purple sparkles
    ReactionType.QUICKEN: (
        (np.array([50, 150, 150]), np.array([90, 255, 255])),
        Element.ELECTRO,
        Element.DENDRO,
    ),
    # Bloom: Green/yellow explosion
    ReactionType.BLOOM: (
        (np.array([40, 150, 150]), np.array([80, 255, 255])),
        Element.DENDRO,
        Element.HYDRO,
    ),
    # Explosion (Burgeon): Green/orange large explosion
    ReactionType.EXPLOSION: (
        (np.array([15, 150, 150]), np.array([50, 255, 255])),
        Element.DENDRO,
        Element.PYRO,
    ),
}


# ---------------------------------------------------------------------------
# P-33: Elemental Reaction Detector
# ---------------------------------------------------------------------------

class ElementalReactionDetector:
    """Detects elemental reactions from visual effects.

    Detects reactions like:
    - Melt, Vaporize (Pyro reactions)
    - Electro-Charged, Superconduct, Overloaded (Electro reactions)
    - Frozen (Cryo-Hydro)
    - Swirl, Crystallize (Anemo/Geo reactions)
    - Burning, Quicken, Bloom (Dendro reactions)

    Visual analysis:
    - Reaction-specific color bursts
    - Particle patterns
    - Duration and spread characteristics
    """

    _REF_W = 1920
    _REF_H = 1080

    # Detection parameters
    MIN_EFFECT_PIXELS = 100
    EFFECT_LIFETIME_FRAMES = 10
    MOTION_THRESHOLD = 10.0

    def __init__(self, now_fn=None) -> None:
        self._now_fn = now_fn or time.perf_counter
        self._active_reactions: list[ReactionDetection] = []
        self._reaction_history: list[ReactionDetection] = []
        self._last_frame_time: float = 0.0
        self._last_result: ReactionFieldStatus | None = None

    @property
    def last_result(self) -> ReactionFieldStatus | None:
        return self._last_result

    @property
    def active_reactions(self) -> tuple[ReactionDetection, ...]:
        return tuple(self._active_reactions)

    def detect(self, frame: np.ndarray, frame_id: int) -> ReactionFieldStatus:
        """Detect elemental reactions in current frame.

        Args:
            frame: BGR frame from screen capture.
            frame_id: Current frame ID for tracking.

        Returns:
            ReactionFieldStatus with all detected reactions.
        """
        if cv2 is None or frame.size == 0:
            return ReactionFieldStatus((), None, 0, "no_detection")

        now = self._now_fn()
        h, w = frame.shape[:2]

        # Convert to HSV for color detection
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        detections: list[ReactionDetection] = []

        for reaction_type, (color_range, primary, secondary) in _REACTION_COLORS.items():
            lower, upper = color_range
            mask = cv2.inRange(hsv, lower, upper)

            # Morphological cleanup
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

            pixel_count = cv2.countNonZero(mask)
            if pixel_count < self.MIN_EFFECT_PIXELS:
                continue

            # Calculate center of reaction effect
            moments = cv2.moments(mask)
            if moments["m00"] > 0:
                cx = moments["m10"] / moments["m00"]
                cy = moments["m01"] / moments["m00"]
            else:
                cx, cy = w / 2, h / 2

            # Calculate intensity based on coverage
            intensity = min(1.0, pixel_count / 5000.0)

            # Calculate confidence based on size and saturation
            center_region = hsv[int(cy)-50:int(cy)+50, int(cx)-50:int(cx)+50]
            if center_region.size > 0:
                avg_saturation = center_region[:, :, 1].mean()
                confidence = min(1.0, intensity * (avg_saturation / 255.0) * 2)
            else:
                confidence = intensity * 0.7

            detection = ReactionDetection(
                reaction_type=reaction_type,
                primary_element=primary,
                secondary_element=secondary,
                position=(float(cx), float(cy)),
                intensity=intensity,
                duration_frames=1,
                confidence=confidence,
                timestamp=now,
            )
            detections.append(detection)

        # Prune old reactions
        self._prune_old_reactions(now)

        # Merge overlapping detections (same reaction type nearby)
        merged = self._merge_detections(detections)

        # Update active reactions
        self._active_reactions = merged

        # Compute dominant reaction
        dominant = None
        if merged:
            dominant = max(merged, key=lambda r: r.intensity).reaction_type

        # Determine recommended action based on reactions
        action = self._compute_action(merged)

        self._last_result = ReactionFieldStatus(
            active_reactions=tuple(merged),
            dominant_reaction=dominant,
            reaction_count=len(merged),
            recommended_action=action,
        )
        return self._last_result

    def _prune_old_reactions(self, now: float) -> None:
        """Remove reactions that have expired."""
        max_age = self.EFFECT_LIFETIME_FRAMES / 60.0  # Convert frames to seconds
        self._active_reactions = [
            r for r in self._active_reactions
            if now - r.timestamp < max_age
        ]

    def _merge_detections(self, detections: list[ReactionDetection]) -> list[ReactionDetection]:
        """Merge nearby detections of the same type."""
        if not detections:
            return []

        merged: list[ReactionDetection] = []
        merge_radius = 100  # Pixels

        for detection in detections:
            merged = self._merge_or_append(merged, detection, merge_radius)

        return merged

    def _merge_or_append(
        self,
        existing: list[ReactionDetection],
        new: ReactionDetection,
        radius: float,
    ) -> list[ReactionDetection]:
        """Merge new detection with existing or append if no match."""
        for i, existing_det in enumerate(existing):
            if existing_det.reaction_type != new.reaction_type:
                continue
            # Check distance
            dx = existing_det.position[0] - new.position[0]
            dy = existing_det.position[1] - new.position[1]
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < radius:
                # Merge: average position, sum intensity
                merged = ReactionDetection(
                    reaction_type=existing_det.reaction_type,
                    primary_element=existing_det.primary_element,
                    secondary_element=existing_det.secondary_element,
                    position=(
                        (existing_det.position[0] + new.position[0]) / 2,
                        (existing_det.position[1] + new.position[1]) / 2,
                    ),
                    intensity=min(1.0, existing_det.intensity + new.intensity * 0.5),
                    duration_frames=existing_det.duration_frames + 1,
                    confidence=max(existing_det.confidence, new.confidence),
                    timestamp=new.timestamp,
                )
                existing[i] = merged
                return existing

        # No merge found, append
        existing.append(new)
        return existing

    def _compute_action(self, reactions: list[ReactionDetection]) -> str:
        """Compute recommended action based on active reactions."""
        if not reactions:
            return "continue_attack"

        # Check for reactions that indicate good team synergy
        high_value = {
            ReactionType.MELT,
            ReactionType.VAPORIZE,
            ReactionType.SUPERCONDUCT,
            ReactionType.BLOOM,
        }
        active_types = {r.reaction_type for r in reactions}

        if active_types & high_value:
            return "maintain_reaction"

        # Check for dangerous reactions
        dangerous = {ReactionType.OVERLOADED, ReactionType.EXPLOSION}
        if active_types & dangerous:
            return "evacuate_after_reaction"

        return "continue_attack"

    def get_reaction_for_element(
        self,
        element: Element,
    ) -> list[ReactionDetection]:
        """Get all reactions involving a specific element."""
        return [
            r for r in self._active_reactions
            if (r.primary_element == element or r.secondary_element == element)
        ]

    def reset(self) -> None:
        """Reset detector state."""
        self._active_reactions.clear()
        self._reaction_history.clear()
        self._last_result = None