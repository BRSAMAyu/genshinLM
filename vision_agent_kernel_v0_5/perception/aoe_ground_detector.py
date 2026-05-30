"""AoE (Area of Effect) warning detection and timing estimation.

Implements P-34: AoE Warning Time Estimation
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
# AoE Attack Types
# ---------------------------------------------------------------------------

class AoEType(Enum):
    CIRCLE = "circle"              # Circular ground AoE
    RING = "ring"                  # Ring-shaped expanding AoE
    LINE = "line"                  # Line AoE (sword slash)
    CONE = "cone"                  # Cone AoE
    CROSS = "cross"               # Cross-shaped AoE
    SWEEP = "sweep"               # Sweeping line attack
    DOT = "dot"                   # Stationary damage zone


# ---------------------------------------------------------------------------
# AoE Detection Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AoEWWarning:
    """A detected AoE warning indicator."""
    aoe_type: AoEType
    center: tuple[float, float]    # AoE center position (x, y)
    radius_pixels: float          # Current radius in pixels
    expanding: bool                # True if AoE is expanding
    expansion_rate: float          # pixels per second
    time_until_impact: float       # seconds until damage
    time_until_dodge: float        # seconds until last safe dodge moment
    danger_level: float           # 0.0-1.0 how dangerous
    confidence: float             # Detection confidence
    telegraph_color: str           # "red", "orange", "purple", etc.
    timestamp: float


@dataclass(frozen=True, slots=True)
class AoEFieldStatus:
    warnings: tuple[AoEWWarning, ...]
    incoming_count: int            # Number of active warnings
    most_urgent: AoEWWarning | None
    safe_path: tuple[tuple[float, float], ...]  # Recommended safe path
    recommended_action: str


# ---------------------------------------------------------------------------
# Color Ranges for AoE Telegraphs
# ---------------------------------------------------------------------------

# Ground AoE telegraphs typically have distinct colors
_AOE_TELEGRAPH_COLORS: dict[str, tuple[np.ndarray, np.ndarray]] = {
    "red": (
        np.array([0, 150, 150]),
        np.array([10, 255, 255]),
    ),
    "orange": (
        np.array([10, 150, 150]),
        np.array([25, 255, 255]),
    ),
    "purple": (
        np.array([130, 100, 100]),
        np.array([160, 255, 255]),
    ),
    "blue": (
        np.array([90, 100, 100]),
        np.array([130, 255, 255]),
    ),
    "yellow": (
        np.array([15, 150, 150]),
        np.array([35, 255, 255]),
    ),
}


# ---------------------------------------------------------------------------
# P-34: AoE Ground Detector with Timing Estimation
# ---------------------------------------------------------------------------

class AoEGroundDetector:
    """Detects AoE warning indicators and estimates explosion timing.

    Features:
    - Detects ground telegraphs (colored circles, rings)
    - Analyzes expansion animation to predict impact time
    - Calculates safe dodge windows
    - Estimates danger level based on size and type

    Visual indicators:
    - Red/orange/purple ground markers
    - Expanding ring or circle animation
    - Filled vs outline markers (different timing)
    """

    _REF_W = 1920
    _REF_H = 1080

    # Detection parameters
    MIN_AOE_RADIUS = 30
    MAX_AOE_RADIUS = 600
    EXPANSION_HISTORY_FRAMES = 10

    # Timing thresholds
    URGENT_THRESHOLD_SEC = 0.5     # Immediate dodge required
    WARNING_THRESHOLD_SEC = 1.5    # Start planning escape
    SAFE_THRESHOLD_SEC = 3.0       # Plenty of time

    # Danger multipliers by type
    DANGER_MULTIPLIERS: dict[AoEType, float] = {
        AoEType.CIRCLE: 0.8,
        AoEType.RING: 0.6,
        AoEType.LINE: 0.5,
        AoEType.CONE: 0.7,
        AoEType.CROSS: 0.9,
        AoEType.SWEEP: 0.4,
        AoEType.DOT: 0.3,
    }

    def __init__(self, now_fn=None) -> None:
        self._now_fn = now_fn or time.perf_counter
        self._expansion_history: list[dict[int, list[tuple[float, float, float]]]] = {}  # aoe_id -> [(time, radius, x, y)]
        self._tracked_aoes: dict[int, AoEWWarning] = {}
        self._next_aoe_id = 0
        self._last_warnings: list[AoEWWarning] = []
        self._last_result: AoEFieldStatus | None = None

    @property
    def last_result(self) -> AoEFieldStatus | None:
        return self._last_result

    def detect(self, frame: np.ndarray, frame_id: int) -> AoEFieldStatus:
        """Detect AoE warnings and estimate timing.

        Args:
            frame: BGR frame from screen capture.
            frame_id: Current frame ID for tracking.

        Returns:
            AoEFieldStatus with all warnings and timing estimates.
        """
        if cv2 is None or frame.size == 0:
            return AoEFieldStatus((), 0, None, (), "scan")

        now = self._now_fn()
        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        warnings: list[AoEWWarning] = []

        # Scan for each telegraph color
        for color_name, (lower, upper) in _AOE_TELEGRAPH_COLORS.items():
            mask = cv2.inRange(hsv, lower, upper)

            # Clean up noise
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

            # Find contours
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                area = cv2.contourArea(contour)
                if area < 500:  # Skip small noise
                    continue

                ((cx, cy), radius) = cv2.minEnclosingCircle(contour)
                if radius < self.MIN_AOE_RADIUS * sx or radius > self.MAX_AOE_RADIUS * sx:
                    continue

                # Determine AoE type by shape analysis
                aoe_type = self._classify_aoe_shape(contour, area, radius)

                # Try to match existing tracked AoE
                aoe_id = self._match_aoe(int(cx), int(cy), frame_id)
                if aoe_id is None:
                    aoe_id = self._next_aoe_id
                    self._next_aoe_id += 1
                    self._expansion_history[aoe_id] = []

                # Record expansion
                self._expansion_history[aoe_id].append((now, radius, cx, cy))
                if len(self._expansion_history[aoe_id]) > self.EXPANSION_HISTORY_FRAMES:
                    self._expansion_history[aoe_id].pop(0)

                # Calculate expansion rate and timing
                expansion_rate, time_until_impact, time_until_dodge = self._estimate_timing(
                    aoe_id, radius, sx
                )

                # Calculate danger level
                danger = self._compute_danger(aoe_type, radius / (w / 2))

                warning = AoEWWarning(
                    aoe_type=aoe_type,
                    center=(float(cx), float(cy)),
                    radius_pixels=radius,
                    expanding=expansion_rate > 0,
                    expansion_rate=expansion_rate,
                    time_until_impact=time_until_impact,
                    time_until_dodge=time_until_dodge,
                    danger_level=danger,
                    confidence=0.8,
                    telegraph_color=color_name,
                    timestamp=now,
                )
                warnings.append(warning)
                self._tracked_aoes[aoe_id] = warning

        # Prune old AoEs
        self._prune_old_aoes(now)

        # Select most urgent warning
        most_urgent = min(warnings, key=lambda w: w.time_until_dodge) if warnings else None

        # Compute safe path
        safe_path = self._compute_safe_path(warnings)

        # Determine recommended action
        action = self._compute_action(warnings)

        self._last_warnings = warnings
        self._last_result = AoEFieldStatus(
            warnings=tuple(warnings),
            incoming_count=len(warnings),
            most_urgent=most_urgent,
            safe_path=safe_path,
            recommended_action=action,
        )
        return self._last_result

    def _classify_aoe_shape(
        self,
        contour,
        area: float,
        radius: float,
    ) -> AoEType:
        """Classify AoE shape from contour analysis."""
        perimeter = cv2.arcLength(contour, True)
        circularity = 4 * np.pi * area / (perimeter * perimeter) if perimeter > 0 else 0

        # High circularity = circle
        if circularity > 0.85:
            return AoEType.CIRCLE

        # Ring detection: high ratio of outer to inner area
        circle_area = np.pi * radius * radius
        if circle_area > 0 and area < circle_area * 0.5:
            return AoEType.RING

        # Line detection: very low circularity
        if circularity < 0.3:
            # Check aspect ratio
            x, y, ww, hh = cv2.boundingRect(contour)
            aspect = max(ww, hh) / min(ww, hh) if min(ww, hh) > 0 else 1
            if aspect > 3:
                return AoEType.LINE

        return AoEType.CIRCLE

    def _match_aoe(self, x: int, y: int, frame_id: int) -> int | None:
        """Match detected AoE to existing tracked AoE."""
        match_radius = 100
        best_id = None
        best_dist = float('inf')

        for aoe_id, warning in self._tracked_aoes.items():
            history = self._expansion_history.get(aoe_id, [])
            if history:
                last_entry = history[-1]
                prev_cx, prev_cy = last_entry[2], last_entry[3]
                dist = ((x - prev_cx) ** 2 + (y - prev_cy) ** 2) ** 0.5
                if dist < match_radius and dist < best_dist:
                    best_dist = dist
                    best_id = aoe_id

        return best_id

    def _estimate_timing(
        self,
        aoe_id: int,
        current_radius: float,
        scale_x: float,
    ) -> tuple[float, float, float]:
        """Estimate expansion rate and timing.

        Returns (expansion_rate, time_until_impact, time_until_dodge).
        """
        history = self._expansion_history.get(aoe_id, [])
        if len(history) < 2:
            return 0.0, 2.0, 1.0  # Unknown, assume safe

        # Calculate expansion rate from history
        t0, r0 = history[0][0], history[0][1]
        t1, r1 = history[-1][0], history[-1][1]
        dt = t1 - t0
        dr = r1 - r0

        if dt <= 0:
            return 0.0, 2.0, 1.0

        expansion_rate = dr / dt

        # Estimate final radius (full screen radius = impact)
        max_radius = 400 * scale_x  # Approximate max damage radius
        if expansion_rate <= 0:
            # Not expanding or contracted, might be stationary
            return 0.0, 1.5, 0.5

        remaining_distance = max_radius - current_radius
        time_until_impact = remaining_distance / expansion_rate if expansion_rate > 0 else 10.0

        # Dodge window: slightly before impact
        time_until_dodge = max(0.0, time_until_impact - 0.3)

        return expansion_rate, time_until_impact, time_until_dodge

    def _compute_danger(self, aoe_type: AoEType, relative_size: float) -> float:
        """Compute danger level based on type and size."""
        base = self.DANGER_MULTIPLIERS.get(aoe_type, 0.5)
        size_factor = min(1.0, relative_size)
        return base * (0.5 + size_factor * 0.5)

    def _prune_old_aoes(self, now: float) -> None:
        """Remove AoEs that haven't been seen recently."""
        max_age = 2.0  # seconds
        to_remove = []
        for aoe_id, history in self._expansion_history.items():
            if history and now - history[-1][0] > max_age:
                to_remove.append(aoe_id)
        for aoe_id in to_remove:
            self._expansion_history.pop(aoe_id, None)
            self._tracked_aoes.pop(aoe_id, None)

    def _compute_safe_path(self, warnings: list[AoEWWarning]) -> tuple[tuple[float, float], ...]:
        """Compute recommended safe path away from AoEs."""
        if not warnings:
            return ()

        # Simple: recommend moving away from most urgent AoE center
        most_urgent = min(warnings, key=lambda w: w.time_until_dodge)
        cx, cy = most_urgent.center

        # Calculate escape direction (opposite to center, away from screen center)
        screen_cx, screen_cy = self._REF_W / 2, self._REF_H / 2

        # If player is near center, move toward edge
        # Simplified: recommend corner positions
        escape_points: list[tuple[float, float]] = []

        # Add corner positions as escape options
        escape_points.append((0.1 * self._REF_W, 0.1 * self._REF_H))  # Top-left
        escape_points.append((0.9 * self._REF_W, 0.1 * self._REF_H))  # Top-right
        escape_points.append((0.1 * self._REF_W, 0.9 * self._REF_H))  # Bottom-left
        escape_points.append((0.9 * self._REF_W, 0.9 * self._REF_H))  # Bottom-right

        return tuple(escape_points)

    def _compute_action(self, warnings: list[AoEWWarning]) -> str:
        """Compute recommended action based on warnings."""
        if not warnings:
            return "continue"

        urgent_count = sum(1 for w in warnings if w.time_until_dodge < self.URGENT_THRESHOLD_SEC)
        warning_count = sum(1 for w in warnings if w.time_until_dodge < self.WARNING_THRESHOLD_SEC)

        if urgent_count > 0:
            return "immediate_dodge"
        elif warning_count > 0:
            return "plan_escape"
        else:
            return "maintain_distance"

    def get_nearest_aoe(self, position: tuple[float, float]) -> AoEWWarning | None:
        """Get the nearest AoE warning to a given position."""
        if not self._last_warnings:
            return None

        def distance(w: AoEWWarning) -> float:
            dx = w.center[0] - position[0]
            dy = w.center[1] - position[1]
            return (dx * dx + dy * dy) ** 0.5

        return min(self._last_warnings, key=distance)

    def reset(self) -> None:
        """Reset detector state."""
        self._expansion_history.clear()
        self._tracked_aoes.clear()
        self._last_warnings.clear()
        self._last_result = None
        self._next_aoe_id = 0