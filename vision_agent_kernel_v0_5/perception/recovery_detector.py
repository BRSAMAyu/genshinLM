"""HP recovery state detector for Genshin Impact.

P-51: Detects HP recovery state by analyzing stamina bar green flashing pattern.
Identifies when the character is being healed or using food/items.

The recovery state shows as:
- Green tint in HP bar area
- Stamina bar with green coloration
- Healing particles/effects
- Character portrait glow
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class RecoveryType(Enum):
    """Type of HP recovery detected."""
    HEALING_SKILL = "healing_skill"     # Bennett Q, Qiqi E, etc.
    FOOD = "food"                        # Eating food item
    PICKUP = "pickup"                    # Picking up HP item
    STATUE = "statue"                    # Using statue of seven
    PASSIVE = "passive"                  # Natural regen


@dataclass(frozen=True, slots=True)
class RecoveryDetection:
    """P-51: HP recovery state detection result."""
    is_recovering: bool
    recovery_type: RecoveryType
    intensity: float                     # 0.0-1.0 recovery strength
    duration_frames: int                # Frames since recovery started
    estimated_hp_per_second: float     # Approximate healing rate
    confidence: float
    frame_id: int


@dataclass(frozen=True, slots=True)
class RecoveryStatus:
    """Overall recovery status for character."""
    active_recovery: RecoveryDetection | None
    recent_recovery_count: int         # Recoveries in last minute
    total_healed_estimate: int         # Estimated total HP healed
    is_in_combat_recovery: bool


class RecoveryDetector:
    """Detect HP recovery state and track healing over time.

    Features:
    - Green flashing detection in stamina bar
    - HP bar green tint analysis
    - Recovery type classification
    - Healing rate estimation
    - Recovery pattern tracking

    Primary detection: Green color in HP/stamina bar region
    """

    _REF_W = 1920
    _REF_H = 1080

    # HP/Stamina bar regions
    _HP_BAR_ROI = (50, 960, 250, 1020)    # Main character HP bar
    _STAMINA_ROI = (870, 910, 1050, 940)  # Stamina bar
    _PORTRAIT_ROI = (20, 900, 80, 980)     # Character portrait

    # Recovery color (bright green)
    _RECOVERY_GREEN_LOW = np.array([40, 100, 100])
    _RECOVERY_GREEN_HIGH = np.array([85, 255, 255])

    # Intense healing (food effect)
    _INTENSE_HEAL_LOW = np.array([35, 150, 150])
    _INTENSE_HEAL_HIGH = np.array([90, 255, 255])

    # Parameters
    MIN_RECOVERY_FRAMES = 3              # Minimum frames to confirm recovery
    RECOVERY_FADE_FRAMES = 10            # Frames to fade out detection
    RECOVERY_HISTORY_SIZE = 60            # Keep 60 frames of history

    def __init__(self, now_fn=None) -> None:
        """Initialize recovery detector.

        Args:
            now_fn: Time function (default: time.perf_counter)
        """
        self._now_fn = now_fn or time.perf_counter
        self._recovery_history: list[bool] = []
        self._recovery_intensities: list[float] = []
        self._healed_estimate: int = 0
        self._recovery_count: int = 0
        self._last_detection: RecoveryDetection | None = None
        self._recovery_start_frame: int = 0

    @property
    def last_detection(self) -> RecoveryDetection | None:
        """Get last recovery detection."""
        return self._last_detection

    def detect(
        self,
        frame: np.ndarray,
        frame_id: int,
    ) -> RecoveryDetection:
        """Detect HP recovery state in frame.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID

        Returns:
            RecoveryDetection with recovery state
        """
        # Get regions
        hp_bar = self._get_roi(frame, self._HP_BAR_ROI)
        stamina_bar = self._get_roi(frame, self._STAMINA_ROI)

        # Analyze recovery indicators
        hp_recovery = self._analyze_region(hp_bar)
        stamina_recovery = self._analyze_region(stamina_bar)

        # Combine indicators
        avg_intensity = (hp_recovery + stamina_recovery) / 2
        is_recovering = avg_intensity > 0.1

        # Determine recovery type
        recovery_type = self._classify_recovery(
            hp_recovery,
            stamina_recovery,
            avg_intensity,
        )

        # Track recovery history
        self._recovery_history.append(is_recovering)
        self._recovery_intensities.append(avg_intensity)

        if len(self._recovery_history) > self.RECOVERY_HISTORY_SIZE:
            self._recovery_history.pop(0)
            self._recovery_intensities.pop(0)

        # Calculate duration
        consecutive_recovery = sum(1 for r in reversed(self._recovery_history) if r)
        duration_frames = min(consecutive_recovery, self.RECOVERY_HISTORY_SIZE)

        # Estimate HP per second
        hp_per_sec = self._estimate_healing_rate(avg_intensity, recovery_type)

        # Update tracking
        if is_recovering and not self._last_detection:
            self._recovery_start_frame = frame_id
            self._recovery_count += 1
        elif is_recovering:
            self._healed_estimate += int(hp_per_sec / 60)  # Per frame

        confidence = min(avg_intensity * 2, 1.0) if is_recovering else 0.0

        self._last_detection = RecoveryDetection(
            is_recovering=is_recovering,
            recovery_type=recovery_type,
            intensity=avg_intensity,
            duration_frames=duration_frames,
            estimated_hp_per_second=hp_per_sec,
            confidence=confidence,
            frame_id=frame_id,
        )

        return self._last_detection

    def _analyze_region(self, roi: np.ndarray) -> float:
        """Analyze region for recovery indicators."""
        if roi.size == 0 or cv2 is None:
            return 0.0

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Standard recovery green
        recovery_mask = cv2.inRange(hsv, self._RECOVERY_GREEN_LOW, self._RECOVERY_GREEN_HIGH)
        recovery_ratio = cv2.countNonZero(recovery_mask) / max(recovery_mask.size, 1)

        # Intense healing
        intense_mask = cv2.inRange(hsv, self._INTENSE_HEAL_LOW, self._INTENSE_HEAL_HIGH)
        intense_ratio = cv2.countNonZero(intense_mask) / max(intense_mask.size, 1)

        # Combine
        return min(recovery_ratio * 2 + intense_ratio, 1.0)

    def _classify_recovery(
        self,
        hp_recovery: float,
        stamina_recovery: float,
        avg_intensity: float,
    ) -> RecoveryType:
        """Classify type of recovery based on patterns."""
        if avg_intensity > 0.5:
            return RecoveryType.FOOD  # Food gives intense healing
        elif stamina_recovery > hp_recovery * 2:
            return RecoveryType.HEALING_SKILL  # Skill affects stamina too
        elif avg_intensity > 0.2:
            return RecoveryType.PASSIVE  # Natural regen
        else:
            return RecoveryType.PASSIVE

    def _estimate_healing_rate(
        self,
        intensity: float,
        recovery_type: RecoveryType,
    ) -> float:
        """Estimate HP recovery per second based on type."""
        base_rates = {
            RecoveryType.HEALING_SKILL: 500,
            RecoveryType.FOOD: 1500,
            RecoveryType.PICKUP: 800,
            RecoveryType.STATUE: 2000,
            RecoveryType.PASSIVE: 100,
        }

        base_rate = base_rates.get(recovery_type, 100)
        return base_rate * intensity

    def _get_roi(
        self,
        frame: np.ndarray,
        coords: tuple[int, int, int, int],
    ) -> np.ndarray:
        """Extract region of interest."""
        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1, y1, x2, y2 = coords
        x1, y1, x2, y2 = int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy)

        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        return frame[y1:y2, x1:x2]

    def get_recovery_status(self, frame_id: int) -> RecoveryStatus:
        """Get overall recovery status."""
        return RecoveryStatus(
            active_recovery=self._last_detection,
            recent_recovery_count=self._recovery_count,
            total_healed_estimate=self._healed_estimate,
            is_in_combat_recovery=(
                self._last_detection is not None and
                self._last_detection.is_recovering and
                self._last_detection.recovery_type == RecoveryType.HEALING_SKILL
            ),
        )

    def is_recovering(self) -> bool:
        """Quick check if currently recovering."""
        return self._last_detection.is_recovering if self._last_detection else False

    def reset(self) -> None:
        """Reset detector state."""
        self._recovery_history.clear()
        self._recovery_intensities.clear()
        self._healed_estimate = 0
        self._recovery_count = 0
        self._last_detection = None
        self._recovery_start_frame = 0