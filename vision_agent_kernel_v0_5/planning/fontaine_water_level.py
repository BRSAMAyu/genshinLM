"""Q-38: Fontaine water level control handler.

Handles water level mechanics in Fontaine where players can
raise or lower water levels in certain areas to access different
paths or reveal hidden treasures.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class WaterLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    FLOODED = "flooded"


class ControlAction(str, Enum):
    RAISE = "raise"
    LOWER = "lower"
    HOLD = "hold"


@dataclass(frozen=True, slots=True)
class WaterLevelZone:
    """A zone with controllable water level."""
    zone_id: str
    position: tuple[float, float]  # normalized 0-1
    current_level: WaterLevel
    target_level: WaterLevel | None
    time_to_change: float | None  # seconds


@dataclass(frozen=True, slots=True)
class WaterLevelStatus:
    """Status of water level control system."""
    active_zones: list[WaterLevelZone]
    current_level: WaterLevel
    level_change_in_progress: bool
    water_visible: bool
    depth_ratio: float  # 0.0=shallow, 1.0=deep


class FontaineWaterLevelHandler:
    """Handle Fontaine water level mechanics."""

    _REF_W = 1920
    _REF_H = 1080

    # Water detection colors
    _WATER_BLUE_LOW = np.array([90, 50, 30], dtype=np.uint8)
    _WATER_BLUE_HIGH = np.array([130, 150, 200], dtype=np.uint8)

    # Control UI elements
    _CONTROL_UI_LOW = np.array([100, 100, 100], dtype=np.uint8)
    _CONTROL_UI_HIGH = np.array([130, 200, 255], dtype=np.uint8)

    # Level indicator (varies by level)
    _LOW_INDICATOR = (20, 50, 50)
    _MEDIUM_INDICATOR = (60, 100, 100)
    _HIGH_INDICATOR = (110, 150, 150)

    _LEVEL_CHANGE_DURATION = 5.0  # seconds to change level

    def __init__(
        self,
        on_level_change: Any = None,
        on_zone_revealed: Any = None,
    ) -> None:
        self._on_level_change = on_level_change
        self._on_zone_revealed = on_zone_revealed

        self._zones: dict[str, WaterLevelZone] = {}
        self._level_change_start: float | None = None
        self._current_action: ControlAction | None = None

    def register_zone(
        self,
        zone_id: str,
        position: tuple[float, float],
        initial_level: WaterLevel = WaterLevel.MEDIUM,
    ) -> None:
        """Register a water level control zone.

        Args:
            zone_id: Unique zone identifier
            position: Zone position (normalized)
            initial_level: Starting water level
        """
        zone = WaterLevelZone(
            zone_id=zone_id,
            position=position,
            current_level=initial_level,
            target_level=None,
            time_to_change=None,
        )
        self._zones[zone_id] = zone
        log.info("[FontaineWater] Registered zone: %s at level %s", zone_id, initial_level.value)

    def detect_water_level(
        self,
        frame: np.ndarray,
        frame_id: int = 0,
    ) -> WaterLevelStatus:
        """Detect current water level status.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            WaterLevelStatus with current state
        """
        if cv2 is None:
            return WaterLevelStatus(
                active_zones=[],
                current_level=WaterLevel.MEDIUM,
                level_change_in_progress=False,
                water_visible=False,
                depth_ratio=0.5,
            )

        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Detect water
        water_mask = cv2.inRange(hsv, self._WATER_BLUE_LOW, self._WATER_BLUE_HIGH)
        water_pixels = cv2.countNonZero(water_mask)
        water_ratio = water_pixels / water_mask.size
        water_visible = water_ratio > 0.05

        # Determine depth ratio
        depth_ratio = min(1.0, water_ratio * 5)

        # Determine current level
        if depth_ratio < 0.2:
            current_level = WaterLevel.LOW
        elif depth_ratio < 0.5:
            current_level = WaterLevel.MEDIUM
        elif depth_ratio < 0.8:
            current_level = WaterLevel.HIGH
        else:
            current_level = WaterLevel.FLOODED

        # Update zone levels
        for zone in self._zones.values():
            if zone.target_level and self._level_change_start:
                elapsed = time.perf_counter() - self._level_change_start
                if elapsed >= self._LEVEL_CHANGE_DURATION:
                    # Level change complete
                    self._zones[zone.zone_id] = WaterLevelZone(
                        zone_id=zone.zone_id,
                        position=zone.position,
                        current_level=zone.target_level,
                        target_level=None,
                        time_to_change=None,
                    )
                    if self._on_level_change:
                        try:
                            self._on_level_change(zone.zone_id, zone.target_level)
                        except Exception as exc:
                            log.warning("[FontaineWater] Level change callback failed: %s", exc)
                    self._level_change_start = None

        level_change = self._level_change_start is not None and self._current_action is not None

        return WaterLevelStatus(
            active_zones=list(self._zones.values()),
            current_level=current_level,
            level_change_in_progress=level_change,
            water_visible=water_visible,
            depth_ratio=depth_ratio,
        )

    def initiate_level_change(
        self,
        zone_id: str,
        target_level: WaterLevel,
    ) -> bool:
        """Initiate a water level change.

        Args:
            zone_id: Zone to change
            target_level: Desired level

        Returns:
            True if change initiated
        """
        if zone_id not in self._zones:
            log.warning("[FontaineWater] Unknown zone: %s", zone_id)
            return False

        zone = self._zones[zone_id]
        current = zone.current_level

        # Determine action
        current_order = [WaterLevel.LOW, WaterLevel.MEDIUM, WaterLevel.HIGH, WaterLevel.FLOODED]
        current_idx = current_order.index(current)
        target_idx = current_order.index(target_level)

        if target_idx > current_idx:
            self._current_action = ControlAction.RAISE
        elif target_idx < current_idx:
            self._current_action = ControlAction.LOWER
        else:
            self._current_action = ControlAction.HOLD

        # Update zone
        self._zones[zone_id] = WaterLevelZone(
            zone_id=zone.zone_id,
            position=zone.position,
            current_level=current,
            target_level=target_level,
            time_to_change=self._LEVEL_CHANGE_DURATION,
        )

        self._level_change_start = time.perf_counter()
        log.info(
            "[FontaineWater] Initiating level change: %s -> %s (action: %s)",
            current.value, target_level.value, self._current_action.value
        )

        return True

    def cancel_level_change(self, zone_id: str) -> bool:
        """Cancel an ongoing level change.

        Args:
            zone_id: Zone where change is happening

        Returns:
            True if cancelled
        """
        if zone_id not in self._zones:
            return False

        zone = self._zones[zone_id]
        if zone.target_level is None:
            return False

        self._zones[zone_id] = WaterLevelZone(
            zone_id=zone.zone_id,
            position=zone.position,
            current_level=zone.current_level,
            target_level=None,
            time_to_change=None,
        )

        self._level_change_start = None
        self._current_action = None
        log.info("[FontaineWater] Cancelled level change for: %s", zone_id)
        return True

    def is_path_accessible(
        self,
        target_level: WaterLevel,
        current_level: WaterLevel,
    ) -> bool:
        """Check if a path is accessible at current level.

        Args:
            target_level: Level required for path
            current_level: Current water level

        Returns:
            True if path is accessible
        """
        level_order = [WaterLevel.LOW, WaterLevel.MEDIUM, WaterLevel.HIGH, WaterLevel.FLOODED]
        return level_order.index(current_level) >= level_order.index(target_level)

    def get_level_guidance(
        self,
        status: WaterLevelStatus,
        target_path_level: WaterLevel | None = None,
    ) -> str | None:
        """Get guidance based on water level.

        Args:
            status: Current water level status
            target_path_level: Level needed for target path

        Returns:
            Guidance string
        """
        if status.level_change_in_progress:
            return "Water level changing - please wait"

        if target_path_level:
            if self.is_path_accessible(target_path_level, status.current_level):
                return "Path accessible at current level"
            else:
                needed = "higher" if target_path_level.value > status.current_level.value else "lower"
                return f"Need {needed} water level to access path"

        return None

    def get_time_to_target(
        self,
        zone_id: str,
        target_level: WaterLevel,
    ) -> float | None:
        """Get estimated time to reach target level.

        Args:
            zone_id: Zone identifier
            target_level: Target level

        Returns:
            Seconds to reach target, or None if not changing
        """
        if zone_id not in self._zones:
            return None

        zone = self._zones[zone_id]
        if zone.target_level != target_level or self._level_change_start is None:
            return None

        elapsed = time.perf_counter() - self._level_change_start
        remaining = self._LEVEL_CHANGE_DURATION - elapsed
        return max(0, remaining)

    def reset(self) -> None:
        """Reset handler state."""
        self._zones = {}
        self._level_change_start = None
        self._current_action = None
        log.info("[FontaineWaterLevelHandler] Handler reset")