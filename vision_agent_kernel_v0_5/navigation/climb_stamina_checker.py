"""E-34: Vertical climb stamina pre-check and fall detection.

Before attempting to climb, verify sufficient stamina.
Detect falling and emergency landing situations.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class StaminaState(str, Enum):
    FULL = "full"            # 100-80%
    GOOD = "good"            # 80-50%
    LOW = "low"              # 50-20%
    CRITICAL = "critical"    # <20%
    EMPTY = "empty"          # 0%
    RECOVERING = "recovering"


class FallState(str, Enum):
    STABLE = "stable"        # On ground, normal
    JUMPING = "jumping"      # In air from jump
    GLIDING = "gliding"      # Using wind current
    FALLING = "falling"      # Uncontrolled descent
    LANDING = "landing"      # Just landed
    DEAD = "dead"            # Died from fall damage


@dataclass(frozen=True, slots=True)
class StaminaCheck:
    """Result of stamina pre-check for climbing."""
    current_ratio: float  # 0.0-1.0
    state: StaminaState
    sufficient_for_climb: bool
    estimated_climb_cost: float  # stamina units needed
    warning: str | None = None


@dataclass(frozen=True, slots=True)
class FallDetection:
    """Detection of falling state."""
    state: FallState
    fall_distance_m: float  # estimated meters fallen
    damage_risk: float  # 0.0-1.0, probability of death
    height_above_ground_px: int
    time_in_air_seconds: float


class ClimbStaminaChecker:
    """Pre-check stamina for climbing and detect falls."""

    _REF_W = 1920
    _REF_H = 1080

    # Stamina bar region (bottom center, typically)
    _STAMINA_ROI = (880, 1020, 1040, 1080)

    # Green stamina color range
    _STAMINA_GREEN_LOW = np.array([40, 100, 100], dtype=np.uint8)
    _STAMINA_GREEN_HIGH = np.array([80, 255, 255], dtype=np.uint8)

    # Stamina thresholds
    _CLIMB_MIN_STAMINA = 0.30  # Need at least 30% to start climbing
    _CLIMB_ESTIMATED_COST = 0.40  # Climbing costs ~40% stamina
    _LOW_STAMINA_THRESHOLD = 0.20
    _CRITICAL_STAMINA_THRESHOLD = 0.10

    def __init__(self) -> None:
        self._last_stamina_ratio: float = 1.0
        self._jump_start_time: float | None = None
        self._last_y_position: int | None = None
        self._fall_history: list[tuple[float, int]] = []  # (time, y_pos)

    def check_climb_stamina(self, frame: np.ndarray, frame_id: int = 0) -> StaminaCheck:
        """Check if current stamina is sufficient for climbing.

        Args:
            frame: BGR screen frame
            frame_id: Current frame ID

        Returns:
            StaminaCheck with feasibility assessment
        """
        if cv2 is None:
            return StaminaCheck(
                current_ratio=0.0,
                state=StaminaState.UNKNOWN,
                sufficient_for_climb=False,
                estimated_climb_cost=self._CLIMB_ESTIMATED_COST,
                warning="CV2 not available",
            )

        stamina_ratio = self._detect_stamina_ratio(frame)
        self._last_stamina_ratio = stamina_ratio

        # Determine state
        state = self._ratio_to_state(stamina_ratio)

        # Check if sufficient for climb
        sufficient = stamina_ratio >= self._CLIMB_MIN_STAMINA

        warning = None
        if not sufficient:
            warning = f"Insufficient stamina for climb (need {self._CLIMB_MIN_STAMINA:.0%}, have {stamina_ratio:.0%})"
        elif stamina_ratio < self._CLIMB_ESTIMATED_COST:
            warning = f"May not complete climb (need ~{self._CLIMB_ESTIMATED_COST:.0%})"

        log.debug(
            "[ClimbStamina] ratio=%.2f, state=%s, sufficient=%s",
            stamina_ratio, state.value, sufficient
        )

        return StaminaCheck(
            current_ratio=stamina_ratio,
            state=state,
            sufficient_for_climb=sufficient,
            estimated_climb_cost=self._CLIMB_ESTIMATED_COST,
            warning=warning,
        )

    def _detect_stamina_ratio(self, frame: np.ndarray) -> float:
        """Detect stamina bar fill ratio."""
        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._STAMINA_ROI, sx, sy)
        stamina_roi = frame[y1:y2, x1:x2]

        if stamina_roi.size == 0:
            return self._last_stamina_ratio

        hsv = cv2.cvtColor(stamina_roi, cv2.COLOR_BGR2HSV)
        green_mask = cv2.inRange(hsv, self._STAMINA_GREEN_LOW, self._STAMINA_GREEN_HIGH)

        # Also check yellow/amber (regenerating)
        yellow_mask = cv2.inRange(hsv, (20, 100, 100), (35, 255, 255))
        stamina_mask = cv2.bitwise_or(green_mask, yellow_mask)

        total_pixels = stamina_roi.shape[0] * stamina_roi.shape[1]
        stamina_pixels = cv2.countNonZero(stamina_mask)

        ratio = stamina_pixels / max(total_pixels, 1)
        return min(ratio, 1.0)

    def _ratio_to_state(self, ratio: float) -> StaminaState:
        """Convert stamina ratio to state enum."""
        if ratio >= 0.80:
            return StaminaState.FULL
        elif ratio >= 0.50:
            return StaminaState.GOOD
        elif ratio >= 0.20:
            return StaminaState.LOW
        elif ratio >= 0.05:
            return StaminaState.CRITICAL
        elif ratio > 0.0:
            return StaminaState.RECOVERING
        else:
            return StaminaState.EMPTY

    def _scale_roi(self, roi: tuple[int, int, int, int], sx: float, sy: float) -> tuple[int, int, int, int]:
        """Scale ROI by resolution multiplier."""
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))

    def detect_fall(self, frame: np.ndarray, frame_id: int = 0) -> FallDetection:
        """Detect if character is falling and assess damage risk.

        Args:
            frame: BGR screen frame
            frame_id: Current frame ID

        Returns:
            FallDetection with fall state and risk assessment
        """
        current_time = time.perf_counter()
        h, w = frame.shape[:2]

        # Track character's vertical position (simplified - use ground detection)
        ground_y = self._estimate_ground_level(frame)
        char_y = h * 0.7  # Approximate character position (lower third of screen)

        current_y = int(char_y)

        # Add to fall history
        self._fall_history.append((current_time, current_y))
        # Keep only recent history
        self._fall_history = [(t, y) for t, y in self._fall_history if current_time - t < 5.0]

        # Calculate fall metrics
        if len(self._fall_history) >= 2:
            time_delta = current_time - self._fall_history[0][0]
            y_delta = self._fall_history[-1][1] - self._fall_history[0][1]

            # Detect falling (moving down rapidly)
            is_falling = y_delta > 20 and time_delta > 0.5

            # Estimate fall distance (rough conversion from pixels)
            fall_distance_px = max(0, y_delta)
            fall_distance_m = fall_distance_px / 100.0  # Rough estimate

            # Calculate damage risk based on fall distance
            damage_risk = min(1.0, max(0.0, (fall_distance_m - 10) / 20.0)) if fall_distance_m > 10 else 0.0

            state = FallState.FALLING if is_falling else FallState.STABLE
        else:
            fall_distance_m = 0.0
            damage_risk = 0.0
            state = FallState.STABLE

        time_in_air = current_time - (self._jump_start_time or current_time)

        return FallDetection(
            state=state,
            fall_distance_m=fall_distance_m,
            damage_risk=damage_risk,
            height_above_ground_px=max(0, ground_y - current_y),
            time_in_air_seconds=time_in_air,
        )

    def _estimate_ground_level(self, frame: np.ndarray) -> int:
        """Estimate ground level from frame."""
        h, w = frame.shape[:2]

        # Look for ground color/texture in lower portion of frame
        ground_region = frame[int(h * 0.6):, :]
        gray = cv2.cvtColor(ground_region, cv2.COLOR_BGR2GRAY)

        # Find lowest edge (simplified ground detection)
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, 3.14 / 180, threshold=50, minLineLength=50, maxLineGap=10)

        if lines is not None:
            # Find lowest line
            lowest = max(y2 for line in lines for x1, y1, x2, y2 in [line] if y2 > h * 0.6)
            return int(lowest)

        return int(h * 0.9)

    def record_jump(self) -> None:
        """Record that character has jumped (start tracking fall)."""
        self._jump_start_time = time.perf_counter()

    def should_cancel_climb(self, check: StaminaCheck) -> bool:
        """Determine if climbing should be cancelled mid-climb."""
        return check.state in (StaminaState.CRITICAL, StaminaState.EMPTY)

    def get_stamina_warning(self, check: StaminaCheck) -> str | None:
        """Get warning message based on stamina state."""
        if check.current_ratio < self._CRITICAL_STAMINA_THRESHOLD:
            return "CRITICAL: Stamina nearly depleted! Cancel climb immediately!"
        elif check.current_ratio < self._LOW_STAMINA_THRESHOLD:
            return "WARNING: Stamina low, consider stopping climb soon"
        elif check.current_ratio < self._CLIMB_MIN_STAMINA:
            return "WARNING: Not enough stamina to start climbing"
        return None