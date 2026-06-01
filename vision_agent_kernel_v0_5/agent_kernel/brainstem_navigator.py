"""BrainstemNavigatorImpl — concrete L3-L4 BrainstemNavigator.

Wraps HeadingServo, StuckDetector from control/navigation_runtime.py,
implementing the BrainstemNavigator protocol from the ADR.

L3-L4 runs at 10-20Hz, providing:
- PID heading servo for navigation
- Stuck state detection via position/progress monitoring
- Unstuck routines (jump, dash_back, teleport_fallback)
"""
from __future__ import annotations

import logging
import time

from agent_kernel.protocols import BrainstemNavigator as BrainstemNavigatorProtocol
from agent_kernel.types import RouteSegment
from control.navigation_runtime import HeadingServo, NavigationSample, StuckDetector

log = logging.getLogger(__name__)


class BrainstemNavigatorImpl(BrainstemNavigatorProtocol):
    """Concrete L3-L4 BrainstemNavigator.

    Usage:
        nav = BrainstemNavigatorImpl()
        nav.update_heading_servo(current_yaw, target_segment)
        if nav.detect_stuck_state(current_pos, elapsed):
            nav.execute_unstuck_routine("jump")
    """

    def __init__(
        self,
        heading_gain: float = 0.25,
        dead_zone_deg: float = 3.0,
        stuck_window: int = 4,
    ) -> None:
        self._servo = HeadingServo(gain=heading_gain, dead_zone_deg=dead_zone_deg)
        self._stuck_detector = StuckDetector(window=stuck_window)
        self._last_position: tuple[float, float, float] | None = None
        self._heading_error: float = 0.0

    def update_heading_servo(
        self,
        current_yaw: float,
        target_segment: RouteSegment,
    ) -> None:
        """Update heading servo to face the next route segment."""
        target_yaw = self._target_yaw_from_segment(target_segment)
        self._heading_error = target_yaw - current_yaw
        # Normalize to [-180, 180]
        while self._heading_error > 180:
            self._heading_error -= 360
        while self._heading_error < -180:
            self._heading_error += 360
        self._servo.mouse_delta_for(self._heading_error)

    def detect_stuck_state(
        self,
        current_pos: tuple[float, float, float],
        elapsed_sec: float,
    ) -> bool:
        """Detect if agent is stuck (no meaningful position change)."""
        if self._last_position is None:
            self._last_position = current_pos
            return False

        dx = current_pos[0] - self._last_position[0]
        dy = current_pos[1] - self._last_position[1]
        dz = current_pos[2] - self._last_position[2]
        distance = (dx * dx + dy * dy + dz * dz) ** 0.5

        self._last_position = current_pos

        sample = NavigationSample(
            timestamp=time.perf_counter(),
            distance_to_target=distance,
            heading_error_deg=abs(self._heading_error),
            optical_flow=min(distance, 1.0),
            progress=distance,
        )
        return self._stuck_detector.update(sample)

    def execute_unstuck_routine(self, method: str = "jump") -> None:
        """Execute an unstuck routine."""
        log.info("[L3-L4] Executing unstuck routine: %s", method)
        if method == "jump":
            pass  # Caller should send Space key
        elif method == "dash_back":
            pass  # Caller should send backward + sprint
        elif method == "teleport_fallback":
            log.warning("[L3-L4] Teleport fallback requested — needs map navigation")
        else:
            log.warning("[L3-L4] Unknown unstuck method: %s", method)

    @property
    def heading_error(self) -> float:
        return self._heading_error

    @property
    def servo(self) -> HeadingServo:
        return self._servo

    def _target_yaw_from_segment(self, segment: RouteSegment) -> float:
        """Extract target yaw from a route segment."""
        # RouteSegment.target_position is (x, y, z) — yaw is computed
        # from the direction to the target. For now, return 0 as default;
        # real implementation uses minimap bearing.
        return 0.0
