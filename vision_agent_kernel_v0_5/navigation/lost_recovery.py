"""E-33: Lost recovery logic - fallback to known safe points.

When the agent gets lost (can't find expected markers or paths),
this module provides fallback strategies to known safe locations.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


class RecoveryStrategy(str, Enum):
    NEAREST_WAYPOINT = "nearest_waypoint"
    LAST_SAFE_POINT = "last_safe_point"
    REGION_ENTRANCE = "region_entrance"
    TELEPORT_HOME = "teleport_home"
    MINIMAP_SEARCH = "minimap_search"


@dataclass(frozen=True, slots=True)
class SafePoint:
    """A known safe location to recover to."""
    point_id: str
    position: tuple[float, float]  # normalized 0-1
    region: str
    waypoint_name: str | None = None
    teleport_waypoint: str | None = None
    is_waypoint: bool = False


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    """Result of recovery attempt."""
    success: bool
    strategy_used: RecoveryStrategy | None
    safe_point: SafePoint | None
    time_taken_seconds: float
    deviation_from_expected: tuple[float, float] | None = None


class LostRecovery:
    """Recovery from being lost using safe points and waypoints."""

    # Default safe points for common regions
    _DEFAULT_SAFE_POINTS: dict[str, list[SafePoint]] = {
        "mondstadt": [
            SafePoint("mondstadt_temple", (0.5, 0.3), "mondstadt", "Mondstadt Temple", "Mondstadt Cathedral", False),
            SafePoint("mondstadt_waypoint", (0.45, 0.35), "mondstadt", "Teleport Waypoint", "Mondstadt Waypoint", True),
            SafePoint("starfell_valley", (0.3, 0.4), "mondstadt", "Starfell Valley", "Starfell Valley", True),
        ],
        "liyue": [
            SafePoint("liyue_harbor", (0.6, 0.7), "liyue", "Liyue Harbor", "Liyue Harbor Waypoint", True),
            SafePoint("wangshu_inn", (0.5, 0.4), "liyue", "Wangshu Inn", "Wangshu Inn", True),
            SafePoint("qingsong_rock", (0.4, 0.5), "liyue", "Qingsong Rock", "Qingsong Rock", True),
        ],
        "inazuma": [
            SafePoint("inazuma_city", (0.5, 0.5), "inazuma", "Inazuma City", "Inazuma City Waypoint", True),
            SafePoint("raiden_shogun_temple", (0.6, 0.4), "inazuma", "Temple of the Eternal", "Raiden Temple", True),
        ],
        "sumeru": [
            SafePoint("sumeru_city", (0.5, 0.5), "sumeru", "Sumeru City", "Sumeru City Waypoint", True),
            SafePoint("port_ormos", (0.7, 0.6), "sumeru", "Port Ormos", "Port Ormos Waypoint", True),
        ],
        "fontaine": [
            SafePoint("fontaine_city", (0.5, 0.5), "fontaine", "Fontaine City", "Fontaine City Waypoint", True),
            SafePoint("erinnyes", (0.4, 0.6), "fontaine", "Erinnyes", "Erinnyes", True),
        ],
        "natlan": [
            SafePoint("natlan_city", (0.5, 0.5), "natlan", "Natlan City", "Natlan City Waypoint", True),
            SafePoint("chinvat_area", (0.3, 0.4), "natlan", "Chinvat Area", "Chinvat", True),
        ],
        "snezhnaya": [
            SafePoint("dolgora_nevajat", (0.5, 0.5), "snezhnaya", "Dolgora Nevajat", "Dolgora Waypoint", True),
        ],
    }

    def __init__(
        self,
        safe_points: dict[str, list[SafePoint]] | None = None,
        teleport_callback: Any = None,
        minimap_search_callback: Any = None,
    ) -> None:
        self._safe_points = safe_points or self._DEFAULT_SAFE_POINTS
        self._teleport_callback = teleport_callback
        self._minimap_search_callback = minimap_search_callback
        self._last_safe_point: SafePoint | None = None
        self._lost_start_time: float | None = None
        self._consecutive_lost_count: int = 0

    def register_safe_point(self, region: str, point: SafePoint) -> None:
        """Register a new safe point for a region."""
        if region not in self._safe_points:
            self._safe_points[region] = []
        if point not in self._safe_points[region]:
            self._safe_points[region].append(point)
            log.info("[LostRecovery] Registered safe point: %s in %s", point.point_id, region)

    def record_last_safe(self, point: SafePoint) -> None:
        """Record the last known safe position."""
        self._last_safe_point = point
        log.debug("[LostRecovery] Last safe point recorded: %s", point.point_id)

    def mark_lost(self) -> None:
        """Mark that agent is currently lost."""
        if self._lost_start_time is None:
            self._lost_start_time = time.perf_counter()
        self._consecutive_lost_count += 1
        log.warning(
            "[LostRecovery] Agent marked as lost (consecutive=%d, duration=%.1fs)",
            self._consecutive_lost_count,
            time.perf_counter() - (self._lost_start_time or 0)
        )

    def mark_found(self) -> None:
        """Mark that agent has found its way."""
        if self._consecutive_lost_count > 0:
            duration = time.perf_counter() - (self._lost_start_time or 0)
            log.info(
                "[LostRecovery] Agent found way (was lost for %.1fs, attempts=%d)",
                duration, self._consecutive_lost_count
            )
        self._lost_start_time = None
        self._consecutive_lost_count = 0

    def recover(
        self,
        current_region: str,
        expected_position: tuple[float, float] | None = None,
        frame: np.ndarray | None = None,
        frame_id: int = 0,
    ) -> RecoveryResult:
        """Attempt to recover from being lost.

        Args:
            current_region: Current region name
            expected_position: Expected position (normalized 0-1)
            frame: Current frame for minimap analysis
            frame_id: Current frame ID

        Returns:
            RecoveryResult with chosen strategy
        """
        started = time.perf_counter()

        # Strategy selection based on conditions
        strategy = self._select_strategy(current_region, expected_position, frame)

        log.info("[LostRecovery] Starting recovery with strategy: %s", strategy.value)

        # Execute recovery
        if strategy == RecoveryStrategy.MINIMAP_SEARCH:
            result = self._recover_via_minimap(frame, current_region)
        elif strategy == RecoveryStrategy.LAST_SAFE_POINT:
            result = self._recover_via_last_safe()
        elif strategy == RecoveryStrategy.NEAREST_WAYPOINT:
            result = self._recover_via_waypoint(current_region)
        elif strategy == RecoveryStrategy.REGION_ENTRANCE:
            result = self._recover_via_region_entrance(current_region)
        elif strategy == RecoveryStrategy.TELEPORT_HOME:
            result = self._recover_via_teleport_home(current_region)
        else:
            result = RecoveryResult(
                success=False,
                strategy_used=None,
                safe_point=None,
                time_taken_seconds=time.perf_counter() - started,
            )

        # Calculate deviation if we have expected position
        deviation = None
        if expected_position and result.safe_point:
            dx = result.safe_point.position[0] - expected_position[0]
            dy = result.safe_point.position[1] - expected_position[1]
            deviation = (dx, dy)

        return RecoveryResult(
            success=result.success,
            strategy_used=result.strategy_used,
            safe_point=result.safe_point,
            time_taken_seconds=time.perf_counter() - started,
            deviation_from_expected=deviation,
        )

    def _select_strategy(
        self,
        region: str,
        expected_position: tuple[float, float] | None,
        frame: np.ndarray | None,
    ) -> RecoveryStrategy:
        """Select best recovery strategy based on conditions."""
        # If minimap search callback exists and we have frame, try minimap search first
        if self._minimap_search_callback is not None and frame is not None:
            return RecoveryStrategy.MINIMAP_SEARCH

        # If we have a last safe point, use it
        if self._last_safe_point is not None:
            return RecoveryStrategy.LAST_SAFE_POINT

        # If region has waypoints, use nearest waypoint
        if region in self._safe_points:
            return RecoveryStrategy.NEAREST_WAYPOINT

        # Fallback to teleport home
        return RecoveryStrategy.TELEPORT_HOME

    def _recover_via_minimap(
        self, frame: np.ndarray | None, region: str
    ) -> RecoveryResult:
        """Recover using minimap search."""
        if self._minimap_search_callback is not None and frame is not None:
            try:
                matched, position = self._minimap_search_callback(frame, region)
                if matched and position:
                    safe_point = SafePoint(
                        point_id=f"minimap_match_{region}",
                        position=position,
                        region=region,
                    )
                    return RecoveryResult(
                        success=True,
                        strategy_used=RecoveryStrategy.MINIMAP_SEARCH,
                        safe_point=safe_point,
                        time_taken_seconds=0.0,
                    )
            except Exception as exc:
                log.warning("[LostRecovery] Minimap search failed: %s", exc)

        return RecoveryResult(
            success=False,
            strategy_used=RecoveryStrategy.MINIMAP_SEARCH,
            safe_point=None,
            time_taken_seconds=0.0,
        )

    def _recover_via_last_safe(self) -> RecoveryResult:
        """Recover to last known safe point."""
        if self._last_safe_point is None:
            return RecoveryResult(
                success=False,
                strategy_used=RecoveryStrategy.LAST_SAFE_POINT,
                safe_point=None,
                time_taken_seconds=0.0,
            )

        log.info("[LostRecovery] Recovering to last safe point: %s", self._last_safe_point.point_id)
        return RecoveryResult(
            success=True,
            strategy_used=RecoveryStrategy.LAST_SAFE_POINT,
            safe_point=self._last_safe_point,
            time_taken_seconds=0.0,
        )

    def _recover_via_waypoint(self, region: str) -> RecoveryResult:
        """Recover to nearest waypoint in region."""
        points = self._safe_points.get(region, [])
        waypoints = [p for p in points if p.is_waypoint]

        if not waypoints:
            return self._recover_via_region_entrance(region)

        # Return first available waypoint (in production, select nearest)
        waypoint = waypoints[0]
        log.info("[LostRecovery] Recovering via waypoint: %s", waypoint.waypoint_name)
        return RecoveryResult(
            success=True,
            strategy_used=RecoveryStrategy.NEAREST_WAYPOINT,
            safe_point=waypoint,
            time_taken_seconds=0.0,
        )

    def _recover_via_region_entrance(self, region: str) -> RecoveryResult:
        """Recover to region entrance."""
        points = self._safe_points.get(region, [])

        if not points:
            return self._recover_via_teleport_home(region)

        entrance = points[0]
        log.info("[LostRecovery] Recovering via region entrance: %s", entrance.point_id)
        return RecoveryResult(
            success=True,
            strategy_used=RecoveryStrategy.REGION_ENTRANCE,
            safe_point=entrance,
            time_taken_seconds=0.0,
        )

    def _recover_via_teleport_home(self, region: str) -> RecoveryResult:
        """Recover via teleport to region home."""
        log.info("[LostRecovery] Using teleport home for region: %s", region)
        return RecoveryResult(
            success=True,
            strategy_used=RecoveryStrategy.TELEPORT_HOME,
            safe_point=SafePoint(
                point_id=f"home_{region}",
                position=(0.5, 0.5),
                region=region,
            ),
            time_taken_seconds=0.0,
        )

    def get_safe_points(self, region: str) -> list[SafePoint]:
        """Get all safe points for a region."""
        return self._safe_points.get(region, [])