"""Q-32: Memory scene detector (回忆场景).

Detects memory/recall scenes that require specific interactions
or puzzle-solving to progress (common in Inazuma and other regions).
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


class MemoryState(str, Enum):
    NOT_IN_MEMORY = "not_in_memory"
    MEMORY_STARTING = "memory_starting"
    MEMORY_ACTIVE = "memory_active"
    MEMORY_PUZZLE = "memory_puzzle"
    MEMORY_COMPLETE = "memory_complete"
    MEMORY_EXITING = "memory_exiting"


@dataclass(frozen=True, slots=True)
class MemorySceneDetection:
    """Detected memory scene state."""
    is_in_memory: bool
    memory_state: MemoryState
    progress_ratio: float  # 0.0-1.0
    interaction_needed: bool
    puzzle_active: bool
    confidence: float


class MemorySceneDetector:
    """Detect memory/recall scenes in Genshin."""

    _REF_W = 1920
    _REF_H = 1080

    # Memory scene indicators
    # Blur/vignette effect (memory scenes have distinct visual style)
    _VIGNETTE_THRESHOLD = 0.3

    # Memory-specific colors (cyan/teal glow)
    _MEMORY_CYAN_LOW = np.array([80, 50, 50], dtype=np.uint8)
    _MEMORY_CYAN_HIGH = np.array([100, 150, 200], dtype=np.uint8)

    # Puzzle UI elements (memory puzzles have specific style)
    _PUZZLE_UI_LOW = np.array([0, 0, 200], dtype=np.uint8)
    _PUZZLE_UI_HIGH = np.array([180, 20, 255], dtype=np.uint8)

    # Memory progress indicator (bright particles)
    _PROGRESS_GLOW_LOW = np.array([0, 100, 200], dtype=np.uint8)
    _PROGRESS_GLOW_HIGH = np.array([180, 200, 255], dtype=np.uint8)

    def __init__(self) -> None:
        self._memory_start_time: float | None = None
        self._puzzle_start_time: float | None = None
        self._last_state = MemoryState.NOT_IN_MEMORY

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> MemorySceneDetection:
        """Detect memory scene state.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            MemorySceneDetection with memory state
        """
        if cv2 is None:
            return MemorySceneDetection(
                is_in_memory=False,
                memory_state=MemoryState.NOT_IN_MEMORY,
                progress_ratio=0.0,
                interaction_needed=False,
                puzzle_active=False,
                confidence=0.0,
            )

        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Check for memory cyan glow
        cyan_mask = cv2.inRange(hsv, self._MEMORY_CYAN_LOW, self._MEMORY_CYAN_HIGH)
        cyan_pixels = cv2.countNonZero(cyan_mask)
        cyan_ratio = cyan_pixels / cyan_mask.size

        # Check for vignette effect (darker corners)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        vignette_ratio = self._calculate_vignette(gray)

        # Check for puzzle UI
        puzzle_mask = cv2.inRange(hsv, self._PUZZLE_UI_LOW, self._PUZZLE_UI_HIGH)
        puzzle_pixels = cv2.countNonZero(puzzle_mask)
        has_puzzle = puzzle_pixels > 1000

        # Check for progress glow
        progress_mask = cv2.inRange(hsv, self._PROGRESS_GLOW_LOW, self._PROGRESS_GLOW_HIGH)
        progress_pixels = cv2.countNonZero(progress_mask)
        progress_ratio = min(1.0, progress_pixels / 5000)

        # Determine memory state
        is_in_memory = cyan_ratio > 0.05 or vignette_ratio > self._VIGNETTE_THRESHOLD

        if not is_in_memory:
            self._memory_start_time = None
            self._puzzle_start_time = None
            self._last_state = MemoryState.NOT_IN_MEMORY
            return MemorySceneDetection(
                is_in_memory=False,
                memory_state=MemoryState.NOT_IN_MEMORY,
                progress_ratio=0.0,
                interaction_needed=False,
                puzzle_active=False,
                confidence=0.0,
            )

        # Track memory entry
        if self._memory_start_time is None:
            self._memory_start_time = time.perf_counter()
            self._last_state = MemoryState.MEMORY_STARTING
            log.info("[MemoryScene] Memory scene detected")

        memory_duration = time.perf_counter() - self._memory_start_time

        # Determine specific memory state
        if has_puzzle:
            if self._puzzle_start_time is None:
                self._puzzle_start_time = time.perf_counter()
            self._last_state = MemoryState.MEMORY_PUZZLE
            interaction_needed = True
        elif progress_ratio > 0.8:
            self._last_state = MemoryState.MEMORY_COMPLETE
            interaction_needed = False
        elif memory_duration < 5.0:
            self._last_state = MemoryState.MEMORY_STARTING
            interaction_needed = False
        else:
            self._last_state = MemoryState.MEMORY_ACTIVE
            interaction_needed = True

        confidence = min(0.9, 0.5 + cyan_ratio * 10)

        return MemorySceneDetection(
            is_in_memory=True,
            memory_state=self._last_state,
            progress_ratio=progress_ratio,
            interaction_needed=interaction_needed,
            puzzle_active=has_puzzle,
            confidence=confidence,
        )

    def _calculate_vignette(self, gray: np.ndarray) -> float:
        """Calculate vignette ratio (dark corners indicate memory scene)."""
        h, w = gray.shape
        center_x, center_y = w // 2, h // 2
        radius = min(w, h) // 2

        # Sample corners
        corners = [
            gray[0, 0],
            gray[0, -1],
            gray[-1, 0],
            gray[-1, -1],
        ]
        corner_avg = sum(corners) / len(corners)

        # Sample center
        center_region = gray[
            center_y - h // 8:center_y + h // 8,
            center_x - w // 8:center_x + w // 8,
        ]
        center_avg = np.mean(center_region)

        # Vignette ratio
        if center_avg > 0:
            vignette = 1.0 - (corner_avg / center_avg)
        else:
            vignette = 0.0

        return max(0.0, vignette)

    def should_wait_for_interaction(self, detection: MemorySceneDetection) -> bool:
        """Check if should wait for automatic interaction."""
        return detection.memory_state == MemoryState.MEMORY_STARTING

    def is_puzzle_complete(self, detection: MemorySceneDetection) -> bool:
        """Check if memory puzzle appears complete."""
        return detection.memory_state == MemoryState.MEMORY_COMPLETE

    def get_memory_guidance(self, detection: MemorySceneDetection) -> str | None:
        """Get guidance for current memory scene state."""
        if detection.memory_state == MemoryState.MEMORY_STARTING:
            return "Memory scene loading - please wait"
        elif detection.memory_state == MemoryState.MEMORY_ACTIVE:
            return "Interact with memory objects"
        elif detection.memory_state == MemoryState.MEMORY_PUZZLE:
            return "Solve the memory puzzle"
        elif detection.memory_state == MemoryState.MEMORY_COMPLETE:
            return "Memory complete - exit or continue"
        elif detection.memory_state == MemoryState.MEMORY_EXITING:
            return "Exiting memory scene"
        return None

    def estimate_remaining_time(self, detection: MemorySceneDetection) -> float | None:
        """Estimate remaining time in memory scene."""
        if not detection.is_in_memory:
            return None

        if detection.memory_state == MemoryState.MEMORY_COMPLETE:
            return 5.0

        # Estimate based on progress
        if detection.progress_ratio > 0:
            remaining = (1.0 - detection.progress_ratio) * 60.0  # ~60s total typical
            return max(0, remaining)

        return None

    def reset(self) -> None:
        """Reset detector state."""
        self._memory_start_time = None
        self._puzzle_start_time = None
        self._last_state = MemoryState.NOT_IN_MEMORY
        log.info("[MemorySceneDetector] Detector reset")