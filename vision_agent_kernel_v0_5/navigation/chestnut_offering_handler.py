"""E-49: Chestnut offering (千来神祠) handler.

Handles the special offering mechanic at the "Thousand Wind Temple" in Mondstadt.
Players need to offer chestnuts to unlock certain treasures or progress quests.
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


class OfferingState(str, Enum):
    IDLE = "idle"                # No offering active
    OFFERING_AVAILABLE = "offering_available"
    OFFERING_IN_PROGRESS = "offering_in_progress"
    OFFERING_COMPLETE = "offering_complete"
    REWARD_READY = "reward_ready"


@dataclass(frozen=True, slots=True)
class ChestnutOffering:
    """Chestnut offering status."""
    state: OfferingState
    chestnuts_needed: int
    chestnuts_offered: int
    reward_available: bool
    confidence: float


class ChestnutOfferingHandler:
    """Handle chestnut offering puzzles at shrines."""

    _REF_W = 1920
    _REF_H = 1080

    # Offering bowl colors (golden/orange)
    _BOWL_GOLD_LOW = np.array([15, 100, 100], dtype=np.uint8)
    _BOWL_GOLD_HIGH = np.array([40, 255, 255], dtype=np.uint8)

    # Chestnut colors (brown)
    _CHESTNUT_BROWN_LOW = np.array([10, 50, 50], dtype=np.uint8)
    _CHESTNUT_BROWN_HIGH = np.array([25, 150, 150], dtype=np.uint8)

    # Offering complete glow (bright white/gold)
    _COMPLETE_GLOW_LOW = np.array([0, 0, 200], dtype=np.uint8)
    _COMPLETE_GLOW_HIGH = np.array([180, 30, 255], dtype=np.uint8)

    def __init__(self) -> None:
        self._offerings_made: int = 0
        self._total_offerings: int = 0
        self._offering_start_time: float = 0.0

    def check_offering_status(
        self, frame: np.ndarray, frame_id: int = 0
    ) -> ChestnutOffering:
        """Check current offering status.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            ChestnutOffering with current status
        """
        if cv2 is None:
            return ChestnutOffering(
                state=OfferingState.IDLE,
                chestnuts_needed=0,
                chestnuts_offered=0,
                reward_available=False,
                confidence=0.0,
            )

        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        # Detect offering bowl
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        bowl_mask = cv2.inRange(hsv, self._BOWL_GOLD_LOW, self._BOWL_GOLD_HIGH)
        bowl_pixels = cv2.countNonZero(bowl_mask)

        # Detect chestnuts in bowl
        chestnut_mask = cv2.inRange(hsv, self._CHESTNUT_BROWN_LOW, self._CHESTNUT_BROWN_HIGH)
        chestnut_pixels = cv2.countNonZero(chestnut_mask)

        # Detect completion glow
        complete_mask = cv2.inRange(hsv, self._COMPLETE_GLOW_LOW, self._COMPLETE_GLOW_HIGH)
        complete_pixels = cv2.countNonZero(complete_mask)

        bowl_present = bowl_pixels > 500
        chestnuts_in_bowl = chestnut_pixels // 100  # Rough estimate

        # Determine state
        if complete_pixels > 200:
            state = OfferingState.REWARD_READY
            reward_available = True
        elif bowl_present and chestnuts_in_bowl > 0:
            state = OfferingState.OFFERING_IN_PROGRESS
            reward_available = False
        elif bowl_present:
            state = OfferingState.OFFERING_AVAILABLE
            reward_available = False
        else:
            state = OfferingState.IDLE
            reward_available = False

        confidence = 0.6 if bowl_present else 0.3

        return ChestnutOffering(
            state=state,
            chestnuts_needed=5,  # Typically 5 chestnuts
            chestnuts_offered=chestnuts_in_bowl,
            reward_available=reward_available,
            confidence=confidence,
        )

    def start_offering(self) -> None:
        """Start tracking an offering sequence."""
        self._offering_start_time = time.perf_counter()
        self._offerings_made = 0
        log.info("[ChestnutOffering] Starting offering sequence")

    def record_offering(self) -> int:
        """Record that a chestnut was offered.

        Returns:
            Number of offerings made so far
        """
        self._offerings_made += 1
        log.info("[ChestnutOffering] Offering %d made", self._offerings_made)
        return self._offerings_made

    def is_complete(self, status: ChestnutOffering) -> bool:
        """Check if offering is complete (all chestnuts given)."""
        return (
            status.state == OfferingState.REWARD_READY or
            status.chestnuts_offered >= status.chestnuts_needed
        )

    def should_claim_reward(self, status: ChestnutOffering) -> bool:
        """Check if reward should be claimed."""
        return status.state == OfferingState.REWARD_READY and status.reward_available

    def get_offering_guidance(self, status: ChestnutOffering) -> str | None:
        """Get guidance on offering progress."""
        if status.state == OfferingState.IDLE:
            return None
        elif status.state == OfferingState.OFFERING_AVAILABLE:
            return "Offer chestnuts to the shrine"
        elif status.state == OfferingState.OFFERING_IN_PROGRESS:
            remaining = status.chestnuts_needed - status.chestnuts_offered
            return f"Continue offering: {remaining} remaining"
        elif status.state == OfferingState.OFFERING_COMPLETE:
            return "Offering complete - claim reward"
        elif status.state == OfferingState.REWARD_READY:
            return "Reward ready - claim it!"
        return None

    def get_offering_statistics(self) -> dict[str, int | float]:
        """Get statistics about offering attempts."""
        elapsed = time.perf_counter() - self._offering_start_time if self._offering_start_time else 0
        return {
            "total_offerings_made": self._offerings_made,
            "total_attempts": self._total_offerings,
            "elapsed_time_seconds": elapsed,
        }

    def reset_statistics(self) -> None:
        """Reset offering statistics."""
        self._offerings_made = 0
        self._total_offerings = 0
        self._offering_start_time = 0.0