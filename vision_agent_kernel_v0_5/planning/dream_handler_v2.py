"""Q-25: Dream loop handler (梦境循环) for Trounce Domains.

Handles the dream loop mechanic in certain Trounce Domains where
the player cycles through multiple dream phases to defeat bosses.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


class DreamPhase(str, Enum):
    WAKING = "waking"
    LIGHT_DREAM = "light_dream"
    DEEP_DREAM = "deep_dream"
    NIGHTMARE = "nightmare"
    AWAKE = "awake"  # Final phase after loop completes


@dataclass(frozen=True, slots=True)
class DreamState:
    """Current dream state."""
    phase: DreamPhase
    loop_count: int
    is_loop_active: bool
    time_in_phase_seconds: float
    enemy_hp_ratio: float | None  # 0.0-1.0


@dataclass(frozen=True, slots=True)
class DreamLoopResult:
    """Result of dream loop handling."""
    phase_changed: bool
    new_phase: DreamPhase
    should_advance: bool  # Ready to progress to next phase
    is_complete: bool      # Loop finished
    guidance: str | None


class DreamHandlerV2:
    """Handle dream loop mechanics in Trounce Domains."""

    # Dream transition indicators
    _DREAM_BLUE_LOW = np.array([90, 50, 50], dtype=np.uint8)
    _DREAM_BLUE_HIGH = np.array([130, 200, 200], dtype=np.uint8)

    _NIGHTMARE_RED_LOW = np.array([0, 100, 100], dtype=np.uint8)
    _NIGHTMARE_RED_HIGH = np.array([20, 255, 255], dtype=np.uint8)

    _AWAKE_GOLD_LOW = np.array([20, 100, 100], dtype=np.uint8)
    _AWAKE_GOLD_HIGH = np.array([40, 255, 255], dtype=np.uint8)

    _REF_W = 1920
    _REF_H = 1080

    # Phase duration estimates (seconds)
    _LIGHT_DREAM_DURATION = 60.0
    _DEEP_DREAM_DURATION = 90.0
    _NIGHTMARE_DURATION = 60.0

    def __init__(
        self,
        on_phase_change: Any = None,
        max_loops: int = 3,
    ) -> None:
        self._current_phase = DreamPhase.WAKING
        self._loop_count = 0
        self._phase_start_time: float = 0.0
        self._on_phase_change = on_phase_change
        self._max_loops = max_loops
        self._enemy_hp_ratio: float | None = None

    def detect_phase(self, frame: np.ndarray, frame_id: int = 0) -> DreamState:
        """Detect current dream phase from frame.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            DreamState with current phase information
        """
        import cv2

        if cv2 is None:
            return DreamState(
                phase=self._current_phase,
                loop_count=self._loop_count,
                is_loop_active=self._current_phase != DreamPhase.WAKING,
                time_in_phase_seconds=0.0,
                enemy_hp_ratio=self._enemy_hp_ratio,
            )

        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Check for nightmare indicators (red)
        nightmare_mask = cv2.inRange(hsv, self._NIGHTMARE_RED_LOW, self._NIGHTMARE_RED_HIGH)
        nightmare_pixels = cv2.countNonZero(nightmare_mask)

        # Check for awake/waking indicators (gold)
        awake_mask = cv2.inRange(hsv, self._AWAKE_GOLD_LOW, self._AWAKE_GOLD_HIGH)
        awake_pixels = cv2.countNonZero(awake_mask)

        # Check for dream indicators (blue)
        dream_mask = cv2.inRange(hsv, self._DREAM_BLUE_LOW, self._DREAM_BLUE_HIGH)
        dream_pixels = cv2.countNonZero(dream_mask)

        elapsed = time.perf_counter() - self._phase_start_time if self._phase_start_time else 0.0

        # Determine phase
        if nightmare_pixels > 5000:
            new_phase = DreamPhase.NIGHTMARE
        elif awake_pixels > 3000:
            new_phase = DreamPhase.AWAKE
        elif dream_pixels > 3000:
            if elapsed < self._LIGHT_DREAM_DURATION:
                new_phase = DreamPhase.LIGHT_DREAM
            elif elapsed < self._LIGHT_DREAM_DURATION + self._DEEP_DREAM_DURATION:
                new_phase = DreamPhase.DEEP_DREAM
            else:
                new_phase = DreamPhase.DEEP_DREAM
        else:
            new_phase = DreamPhase.WAKING

        # Check for phase change
        if new_phase != self._current_phase:
            self._on_phase_transition(self._current_phase, new_phase)
            self._current_phase = new_phase
            self._phase_start_time = time.perf_counter()

            if new_phase == DreamPhase.WAKING and self._current_phase == DreamPhase.AWAKE:
                self._loop_count += 1

        return DreamState(
            phase=self._current_phase,
            loop_count=self._loop_count,
            is_loop_active=self._current_phase != DreamPhase.WAKING,
            time_in_phase_seconds=time.perf_counter() - self._phase_start_time if self._phase_start_time else 0.0,
            enemy_hp_ratio=self._enemy_hp_ratio,
        )

    def _on_phase_transition(self, old: DreamPhase, new: DreamPhase) -> None:
        """Handle phase transition callback."""
        log.info("[DreamHandler] Phase transition: %s -> %s (loop %d)", old.value, new.value, self._loop_count)
        if self._on_phase_change:
            try:
                self._on_phase_change(old, new, self._loop_count)
            except Exception as exc:
                log.warning("[DreamHandler] Phase change callback failed: %s", exc)

    def should_transition(self, state: DreamState) -> bool:
        """Determine if should transition to next phase."""
        if self._enemy_hp_ratio is not None and self._enemy_hp_ratio < 0.1:
            return True

        if state.phase == DreamPhase.NIGHTMARE and state.time_in_phase_seconds > self._NIGHTMARE_DURATION:
            return True
        if state.phase == DreamPhase.DEEP_DREAM and state.time_in_phase_seconds > self._DEEP_DREAM_DURATION:
            return True
        if state.phase == DreamPhase.LIGHT_DREAM and state.time_in_phase_seconds > self._LIGHT_DREAM_DURATION:
            return True

        return False

    def update_enemy_hp(self, hp_ratio: float) -> None:
        """Update enemy HP ratio for transition decisions."""
        self._enemy_hp_ratio = hp_ratio

    def get_phase_guidance(self, state: DreamState) -> str | None:
        """Get guidance for current phase."""
        if state.phase == DreamPhase.WAKING:
            return "Enter the domain to start dream loop"
        elif state.phase == DreamPhase.LIGHT_DREAM:
            return "Light dream phase - defeat enemies quickly"
        elif state.phase == DreamPhase.DEEP_DREAM:
            return "Deep dream phase - boss damage increased"
        elif state.phase == DreamPhase.NIGHTMARE:
            return "Nightmare phase - stay defensive, wait for phase to end"
        elif state.phase == DreamPhase.AWAKE:
            return "Loop complete - fight the final boss"
        return None

    def is_loop_complete(self) -> bool:
        """Check if dream loop is complete."""
        return self._loop_count >= self._max_loops or self._current_phase == DreamPhase.AWAKE

    def reset(self) -> None:
        """Reset dream handler state."""
        self._current_phase = DreamPhase.WAKING
        self._loop_count = 0
        self._phase_start_time = 0.0
        self._enemy_hp_ratio = None
        log.info("[DreamHandler] Handler reset")