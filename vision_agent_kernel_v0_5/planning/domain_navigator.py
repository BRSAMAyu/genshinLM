"""Q-26: Multi-floor domain navigator.

Navigates multi-floor domains (秘境) where players must clear
each floor sequentially to reach the final floor.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


class DomainFloor(str, Enum):
    FLOOR_1 = "floor_1"
    FLOOR_2 = "floor_2"
    FLOOR_3 = "floor_3"
    FLOOR_4 = "floor_4"
    FINAL = "final"
    UNKNOWN = "unknown"


class FloorState(str, Enum):
    CLEARING = "clearing"        # In combat
    CLEARED = "cleared"         # Floor complete
    WAITING = "waiting"         # Waiting for next floor
    TELEPORTING = "teleporting"  # Moving to next floor
    REWARD = "reward"           # Reward screen


@dataclass(frozen=True, slots=True)
class DomainProgress:
    """Current domain progress."""
    current_floor: DomainFloor
    floor_state: FloorState
    total_floors: int
    cleared_count: int
    time_on_floor_seconds: float
    is_boss_floor: bool


@dataclass(frozen=True, slots=True)
class FloorTransition:
    """Information about floor transitions."""
    can_advance: bool
    destination: DomainFloor | None
    waypoint_position: tuple[float, float] | None
    time_estimate_seconds: float


class DomainNavigator:
    """Navigate multi-floor domains."""

    _REF_W = 1920
    _REF_H = 1080

    def __init__(
        self,
        total_floors: int = 3,
        on_floor_change: Any = None,
    ) -> None:
        self._total_floors = total_floors
        self._current_floor = DomainFloor.FLOOR_1
        self._floor_state = FloorState.CLEARING
        self._on_floor_change = on_floor_change
        self._floor_start_time: float = 0.0
        self._cleared_floors: int = 0

    def update_progress(
        self,
        frame: np.ndarray,
        frame_id: int = 0,
        enemy_hp_ratio: float | None = None,
    ) -> DomainProgress:
        """Update domain progress.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID
            enemy_hp_ratio: Current enemy HP ratio (None if no enemies)

        Returns:
            DomainProgress with current state
        """
        import cv2

        # Check floor state from frame
        state = self._detect_floor_state(frame)
        self._floor_state = state

        # Calculate time on current floor
        elapsed = time.perf_counter() - self._floor_start_time if self._floor_start_time else 0.0

        # Check if floor cleared
        if enemy_hp_ratio is not None and enemy_hp_ratio < 0.05:
            if self._floor_state != FloorState.CLEARED:
                self._mark_floor_cleared()

        # Determine current floor
        is_boss = self._current_floor == DomainFloor.FINAL

        return DomainProgress(
            current_floor=self._current_floor,
            floor_state=self._floor_state,
            total_floors=self._total_floors,
            cleared_count=self._cleared_floors,
            time_on_floor_seconds=elapsed,
            is_boss_floor=is_boss,
        )

    def _detect_floor_state(self, frame: np.ndarray) -> FloorState:
        """Detect current floor state from frame."""
        import cv2

        if cv2 is None:
            return FloorState.CLEARING

        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        # Check for completion indicator (golden glow)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        gold_lower = np.array([20, 100, 100], dtype=np.uint8)
        gold_upper = np.array([40, 255, 255], dtype=np.uint8)
        gold_mask = cv2.inRange(hsv, gold_lower, gold_upper)
        gold_pixels = cv2.countNonZero(gold_mask)

        # Check for reward screen
        reward_lower = np.array([0, 0, 200], dtype=np.uint8)
        reward_upper = np.array([180, 30, 255], dtype=np.uint8)
        reward_mask = cv2.inRange(hsv, reward_lower, reward_upper)
        reward_pixels = cv2.countNonZero(reward_mask)

        # Check for HP bars (combat indicators)
        red_lower = np.array([0, 100, 100], dtype=np.uint8)
        red_upper = np.array([10, 255, 255], dtype=np.uint8)
        hp_mask = cv2.inRange(hsv, red_lower, red_upper)
        hp_pixels = cv2.countNonZero(hp_mask)

        if reward_pixels > 5000:
            return FloorState.REWARD
        elif gold_pixels > 3000:
            return FloorState.CLEARED
        elif hp_pixels > 500:
            return FloorState.CLEARING
        else:
            return FloorState.WAITING

    def _mark_floor_cleared(self) -> None:
        """Mark current floor as cleared."""
        if self._floor_state != FloorState.CLEARED:
            log.info("[DomainNavigator] Floor %s cleared", self._current_floor.value)
            self._cleared_floors += 1
            self._floor_state = FloorState.CLEARED

            # Advance to next floor
            self._advance_floor()

    def _advance_floor(self) -> None:
        """Advance to next floor."""
        old_floor = self._current_floor

        if self._current_floor == DomainFloor.FLOOR_1:
            if self._total_floors >= 2:
                self._current_floor = DomainFloor.FLOOR_2
            else:
                self._current_floor = DomainFloor.FINAL
        elif self._current_floor == DomainFloor.FLOOR_2:
            if self._total_floors >= 3:
                self._current_floor = DomainFloor.FLOOR_3
            else:
                self._current_floor = DomainFloor.FINAL
        elif self._current_floor == DomainFloor.FLOOR_3:
            if self._total_floors >= 4:
                self._current_floor = DomainFloor.FLOOR_4
            else:
                self._current_floor = DomainFloor.FINAL
        elif self._current_floor == DomainFloor.FLOOR_4:
            self._current_floor = DomainFloor.FINAL
        else:
            log.warning("[DomainNavigator] Already at final floor")

        self._floor_state = FloorState.TELEPORTING
        self._floor_start_time = time.perf_counter()

        if self._current_floor != old_floor:
            log.info("[DomainNavigator] Advancing from %s to %s", old_floor.value, self._current_floor.value)
            if self._on_floor_change:
                try:
                    self._on_floor_change(old_floor, self._current_floor, self._cleared_floors)
                except Exception as exc:
                    log.warning("[DomainNavigator] Floor change callback failed: %s", exc)

    def can_advance(self, progress: DomainProgress) -> FloorTransition:
        """Check if can advance to next floor."""
        if progress.floor_state == FloorState.REWARD:
            return FloorTransition(
                can_advance=False,
                destination=None,
                waypoint_position=None,
                time_estimate_seconds=0.0,
            )

        if progress.cleared_count >= progress.total_floors:
            return FloorTransition(
                can_advance=False,
                destination=DomainFloor.FINAL,
                waypoint_position=None,
                time_estimate_seconds=0.0,
            )

        # Determine destination
        if progress.current_floor == DomainFloor.FINAL:
            destination = None
        elif progress.cleared_count + 1 >= self._total_floors:
            destination = DomainFloor.FINAL
        else:
            destinations = {
                1: DomainFloor.FLOOR_2,
                2: DomainFloor.FLOOR_3,
                3: DomainFloor.FLOOR_4,
                4: DomainFloor.FINAL,
            }
            destination = destinations.get(progress.cleared_count + 1, DomainFloor.FINAL)

        return FloorTransition(
            can_advance=progress.floor_state in (FloorState.CLEARED, FloorState.WAITING),
            destination=destination,
            waypoint_position=None,
            time_estimate_seconds=3.0,
        )

    def get_floor_guidance(self, progress: DomainProgress) -> str | None:
        """Get guidance for current floor."""
        if progress.floor_state == FloorState.CLEARING:
            if progress.is_boss_floor:
                return "Boss floor - defeat the boss"
            return f"Clear floor {progress.current_floor.value}"
        elif progress.floor_state == FloorState.CLEARED:
            return "Floor cleared - advance to next"
        elif progress.floor_state == FloorState.WAITING:
            return "Waiting for transition"
        elif progress.floor_state == FloorState.REWARD:
            return "Claim your rewards"
        return None

    def is_complete(self, progress: DomainProgress) -> bool:
        """Check if domain run is complete."""
        return progress.floor_state == FloorState.REWARD and progress.cleared_count >= progress.total_floors

    def reset(self) -> None:
        """Reset navigator state."""
        self._current_floor = DomainFloor.FLOOR_1
        self._floor_state = FloorState.CLEARING
        self._cleared_floors = 0
        self._floor_start_time = 0.0
        log.info("[DomainNavigator] Navigator reset")