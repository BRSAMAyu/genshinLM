"""Weakpoint targeting and detection system.

Implements C-43: Weakpoint Hit Detection
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from core.types import TargetTrack

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# C-43: Weakpoint System
# ---------------------------------------------------------------------------

class WeakpointState(str, Enum):
    """Weakpoint exposure states."""
    HIDDEN = "hidden"           # Weakpoint not visible
    EXPOSED = "exposed"         # Weakpoint visible and targetable
    BROKEN = "broken"           # Weakpoint was broken recently
    RECOVERING = "recovering"   # Weakpoint respawning


@dataclass(frozen=True, slots=True)
class WeakpointInfo:
    """Information about a weakpoint target."""
    name: str
    world_position: tuple[float, float, float] | None
    screen_position: tuple[float, float]
    size_pixels: float
    exposure_duration_ms: float
    is_critical: bool
    state: WeakpointState
    break_damage_required: float


@dataclass(frozen=True, slots=True)
class WeakpointHitResult:
    """Result of a weakpoint hit attempt."""
    hit: bool
    weakpoint_name: str | None
    damage_dealt: float
    is_critical: bool
    weakpoint_broken: bool
    next_exposure_predict: float | None


@dataclass(frozen=True, slots=True)
class WeakpointTargetingStatus:
    """Current weakpoint targeting status."""
    active_weakpoint: WeakpointInfo | None
    targeting_priority: float  # 0.0-1.0
    recommended_action: str
    aim_adjustment: tuple[float, float]  # yaw, pitch offset


# Weakpoint patterns for common enemies
_WEAKPOINT_PATTERNS: dict[str, tuple[tuple[float, float], ...]] = {
    "ruin_guard": ((0.5, 0.2),),  # Single eye weakpoint
    "ruin_hunter": ((0.5, 0.3),),  # Single eye weakpoint
    "ruin_grader": ((0.5, 0.4),),  # Single eye weakpoint
    "stone_lawachurl": ((0.5, 0.15),),  # Head weakpoint
    "electro_lawachurl": ((0.5, 0.15),),
    "cryo_regisvine": ((0.5, 0.7),),  # Cryo flower weakpoint center
    "pyro_regisvine": ((0.5, 0.7),),
}


class WeakpointTargetingSystem:
    """Detects and tracks enemy weakpoints for precision targeting.

    Weakpoints are specific parts of enemies that:
    - Deal bonus damage when hit
    - Often need to be exposed through mechanics
    - Can be broken to stagger the enemy

    Examples:
    - Ruin Guard: Eye must be shot when open
    - Perpetual Mechanical Array: Crystal on back
    - Pyro Hypostasis: Core in center when exposed
    """

    def __init__(self) -> None:
        self._now_fn = time.perf_counter
        self._last_detection: WeakpointTargetingStatus | None = None
        self._exposure_history: dict[str, list[float]] = {}
        self._current_target: str | None = None
        self._targeting_start_time: float = 0.0

    @property
    def last_status(self) -> WeakpointTargetingStatus | None:
        return self._last_detection

    def detect_weakpoint(
        self,
        target: TargetTrack | None,
        frame: np.ndarray | None,
        enemy_type: str | None,
        core_exposed: bool,
        timestamp: float | None = None,
    ) -> WeakpointTargetingStatus:
        """Detect weakpoint state and provide targeting info.

        Args:
            target: Current target track.
            frame: Frame for visual detection.
            enemy_type: Type of enemy (for pattern matching).
            core_exposed: Whether core/weakpoint is visibly exposed.
            timestamp: Current time.

        Returns:
            WeakpointTargetingStatus with targeting recommendations.
        """
        now = timestamp if timestamp is not None else self._now_fn()

        if target is None or enemy_type is None:
            status = WeakpointTargetingStatus(
                active_weakpoint=None,
                targeting_priority=0.0,
                recommended_action="no_target",
                aim_adjustment=(0.0, 0.0),
            )
            self._last_detection = status
            return status

        # Determine weakpoint state
        state = self._determine_state(core_exposed, now, enemy_type)

        # Get weakpoint info
        pattern = _WEAKPOINT_PATTERNS.get(enemy_type.lower())
        if pattern and target.smoothed_center_px:
            cx, cy = target.smoothed_center_px
            # Apply weakpoint pattern offset
            wp_offset = pattern[0]
            wp_x = cx + (wp_offset[0] - 0.5) * 100
            wp_y = cy + (wp_offset[1] - 0.5) * 100

            weakpoint_info = WeakpointInfo(
                name=f"{enemy_type}_weakpoint",
                world_position=None,
                screen_position=(wp_x, wp_y),
                size_pixels=30.0,
                exposure_duration_ms=0.0,
                is_critical=True,
                state=state,
                break_damage_required=500.0,
            )
        else:
            weakpoint_info = None

        # Calculate targeting priority
        priority = self._calculate_priority(weakpoint_info, state, now)

        # Determine recommended action
        action = self._recommend_action(state, priority, weakpoint_info)

        # Calculate aim adjustment
        aim_adj = self._calculate_aim_adjustment(
            target, weakpoint_info, state
        )

        status = WeakpointTargetingStatus(
            active_weakpoint=weakpoint_info,
            targeting_priority=priority,
            recommended_action=action,
            aim_adjustment=aim_adj,
        )

        self._last_detection = status
        self._current_target = target.track_id
        self._targeting_start_time = now

        return status

    def _determine_state(
        self,
        core_exposed: bool,
        timestamp: float,
        enemy_type: str,
    ) -> WeakpointState:
        """Determine current weakpoint state."""
        history = self._exposure_history.get(enemy_type, [])

        if core_exposed:
            # Check if just exposed or was already exposed
            if history and (timestamp - history[-1]) < 10.0:
                return WeakpointState.EXPOSED
            return WeakpointState.EXPOSED

        # Check if recently broken
        if history and (timestamp - history[-1]) < 5.0:
            return WeakpointState.BROKEN

        # Check if recovering
        if len(history) >= 2:
            last_break = history[-1] if history else 0
            recovery_interval = 15.0  # 15 second recovery
            if (timestamp - last_break) < recovery_interval:
                return WeakpointState.RECOVERING

        return WeakpointState.HIDDEN

    def _calculate_priority(
        self,
        weakpoint: WeakpointInfo | None,
        state: WeakpointState,
        timestamp: float,
    ) -> float:
        """Calculate weakpoint targeting priority (0.0-1.0)."""
        if weakpoint is None:
            return 0.0

        if state == WeakpointState.EXPOSED:
            # High priority when exposed
            elapsed = timestamp - self._targeting_start_time
            time_factor = min(1.0, elapsed / 2.0)  # Max after 2 seconds
            return 0.8 + (0.2 * time_factor)

        if state == WeakpointState.RECOVERING:
            # Medium priority - time until next exposure
            elapsed = timestamp - self._targeting_start_time
            if elapsed < 10.0:
                return 0.5

        return 0.2  # Low priority when hidden

    def _recommend_action(
        self,
        state: WeakpointState,
        priority: float,
        weakpoint: WeakpointInfo | None,
    ) -> str:
        """Recommend action based on weakpoint state."""
        if weakpoint is None:
            return "wait_for_weakpoint"

        if state == WeakpointState.EXPOSED:
            if priority >= 0.8:
                return "focus_weakpoint"
            return "prepare_weakpoint"

        if state == WeakpointState.RECOVERING:
            return "prepare_aim"

        if state == WeakpointState.BROKEN:
            return "max_damage_window"

        return "continue_normal"

    def _calculate_aim_adjustment(
        self,
        target: TargetTrack,
        weakpoint: WeakpointInfo | None,
        state: WeakpointState,
    ) -> tuple[float, float]:
        """Calculate aim adjustment to hit weakpoint."""
        if weakpoint is None or target.smoothed_center_px is None:
            return (0.0, 0.0)

        if state != WeakpointState.EXPOSED:
            return (0.0, 0.0)  # Don't aim off-center when not exposed

        cx, cy = target.smoothed_center_px
        wpx, wpy = weakpoint.screen_position

        # Calculate offset (in degrees, assuming 90 degree FOV)
        fov_h = 90.0
        # Assuming 1920x1080 reference resolution
        ref_w = 1920.0
        offset_x = (wpx - cx) / ref_w * fov_h
        offset_y = (wpy - cy) / 1080 * 60  # ~60 deg vertical FOV

        return (offset_x, offset_y)

    def record_hit(
        self,
        weakpoint_name: str,
        is_critical: bool,
        timestamp: float | None = None,
    ) -> WeakpointHitResult:
        """Record a hit on a weakpoint."""
        now = timestamp if timestamp is not None else self._now_fn()

        enemy_type = weakpoint_name.split("_weakpoint")[0]
        history = self._exposure_history.setdefault(enemy_type, [])

        # Record break time
        if is_critical:
            history.append(now)
            # Keep only recent history
            self._exposure_history[enemy_type] = history[-10:]

        # Predict next exposure
        next_exposure = self._predict_exposure(enemy_type, now)

        return WeakpointHitResult(
            hit=True,
            weakpoint_name=weakpoint_name,
            damage_dealt=200.0 if is_critical else 100.0,  # Placeholder
            is_critical=is_critical,
            weakpoint_broken=is_critical,
            next_exposure_predict=next_exposure,
        )

    def _predict_exposure(
        self,
        enemy_type: str,
        timestamp: float,
    ) -> float | None:
        """Predict when next weakpoint exposure will occur."""
        history = self._exposure_history.get(enemy_type, [])

        if len(history) >= 2:
            intervals = [history[i] - history[i-1] for i in range(1, len(history))]
            avg_interval = sum(intervals) / len(intervals)
            return timestamp + avg_interval

        # Default 15 second interval
        return timestamp + 15.0

    def reset(self) -> None:
        """Reset targeting system."""
        self._last_detection = None
        self._exposure_history.clear()
        self._current_target = None
        self._targeting_start_time = 0.0