"""Buff duration detector for Genshin Impact status effects.

P-52: Detects BUFF bar icons with countdown rings.
Tracks remaining duration of active buffs/debuffs.

Common buffs detected:
- Elemental resonance bonuses
- Food effects (ATK boost, DEF boost, etc.)
- Character ascension buffs
- Artifact set bonuses
- Enemy debuffs (Pyanodon, etc.)
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BuffInfo:
    """Information about a single buff/debuff."""
    buff_id: str
    name: str
    icon_type: str                    # Icon classification
    remaining_seconds: float         # Time remaining
    total_seconds: float             # Total duration
    progress: float                   # 0.0-1.0 remaining ratio
    is_debuff: bool                  # True if debuff (enemy effect)
    stack_count: int = 1             # Number of stacks


@dataclass(frozen=True, slots=True)
class BuffFieldStatus:
    """Status of all active buffs."""
    buffs: tuple[BuffInfo, ...]
    active_buff_count: int
    active_debuff_count: int
    critical_buffs: tuple[BuffInfo, ...]  # Buffs about to expire
    recommended_action: str


class BuffDurationDetector:
    """Detect and track buff/debuff durations from UI elements.

    Features:
    - Icon recognition for common buffs
    - Countdown ring analysis (circular progress)
    - Duration tracking over time
    - Critical buff warnings (< 3 seconds)
    - Debuff identification

    Detection: Icon shape + countdown ring color/intensity
    """

    _REF_W = 1920
    _REF_H = 1080

    # Buff bar position (top-right of screen)
    _BUFF_BAR_ROI = (0.65, 0.02, 0.98, 0.15)
    _DEBUFF_BAR_ROI = (0.50, 0.02, 0.65, 0.15)

    # Buff icon dimensions
    _ICON_SIZE = 40
    _ICON_SPACING = 45
    _MAX_ICONS = 15

    # Countdown ring colors
    _RING_GREEN_LOW = np.array([40, 100, 100])
    _RING_GREEN_HIGH = np.array([85, 255, 255])
    _RING_YELLOW_LOW = np.array([15, 100, 150])
    _RING_YELLOW_HIGH = np.array([35, 255, 255])
    _RING_RED_LOW = np.array([0, 150, 150])
    _RING_RED_HIGH = np.array([15, 255, 255])

    # Icon background colors for classification
    _ICON_COLORS: dict[str, tuple[np.ndarray, np.ndarray]] = {
        "atk_boost": (np.array([0, 150, 200]), np.array([20, 255, 255])),       # Orange/red
        "def_boost": (np.array([90, 100, 150]), np.array([120, 255, 255])),    # Blue
        "heal": (np.array([40, 150, 150]), np.array([85, 255, 255])),          # Green
        "speed": (np.array([55, 100, 150]), np.array([85, 255, 255])),         # Teal
        "shield": (np.array([15, 100, 150]), np.array([35, 255, 255])),       # Yellow
        "element": (np.array([120, 100, 150]), np.array([160, 255, 255])),    # Purple
    }

    def __init__(self, now_fn=None) -> None:
        """Initialize buff duration detector.

        Args:
            now_fn: Time function (default: time.perf_counter)
        """
        self._now_fn = now_fn or time.perf_counter
        self._active_buffs: dict[str, BuffInfo] = {}
        self._buff_history: dict[str, list[float]] = defaultdict(list)
        self._last_frame_id: int = 0

    @property
    def last_result(self) -> BuffFieldStatus | None:
        """Get last detection result."""
        if not self._active_buffs:
            return None

        return self._build_status()

    def detect(
        self,
        frame: np.ndarray,
        frame_id: int,
    ) -> BuffFieldStatus:
        """Detect buff durations in frame.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID

        Returns:
            BuffFieldStatus with all detected buff durations
        """
        # Get buff bar region
        buff_bar = self._get_roi(frame, self._BUFF_BAR_ROI)
        debuff_bar = self._get_roi(frame, self._DEBUFF_BAR_ROI)

        # Detect icons and their ring progress
        detected_buffs = self._detect_icon_progression(buff_bar, is_debuff=False)
        detected_debuffs = self._detect_icon_progression(debuff_bar, is_debuff=True)

        # Update active buffs
        self._update_buffs(detected_buffs, is_debuff=False)
        self._update_buffs(detected_debuffs, is_debuff=True)

        # Decay buffs that weren't seen
        self._decay_missing_buffs(frame_id)

        self._last_frame_id = frame_id

        return self._build_status()

    def _detect_icon_progression(
        self,
        roi: np.ndarray,
        is_debuff: bool,
    ) -> list[tuple[str, float, int]]:
        """Detect buff icons and their countdown ring progress.

        Returns:
            List of (icon_type, progress_ratio, stack_count)
        """
        if roi.size == 0 or cv2 is None:
            return []

        detections: list[tuple[str, float, int]] = []

        h, w = roi.shape[:2]
        icon_width = self._ICON_SPACING

        num_icons = min(self._MAX_ICONS, w // icon_width)

        for i in range(num_icons):
            x1 = i * icon_width
            x2 = x1 + self._ICON_SIZE
            icon_roi = roi[0:self._ICON_SIZE, x1:x2]

            if icon_roi.size == 0:
                continue

            # Check if icon is present (non-empty)
            gray = cv2.cvtColor(icon_roi, cv2.COLOR_BGR2GRAY)
            icon_pixels = cv2.countNonZero(gray)

            if icon_pixels < 100:
                continue  # No icon here

            # Classify icon type
            icon_type = self._classify_icon(icon_roi)

            # Analyze countdown ring
            progress = self._analyze_ring_progress(icon_roi)

            # Count stacks (based on intensity)
            stacks = self._count_stacks(icon_roi)

            detections.append((icon_type, progress, stacks))

        return detections

    def _classify_icon(self, icon_roi: np.ndarray) -> str:
        """Classify buff icon type by color."""
        if cv2 is None:
            return "unknown"

        hsv = cv2.cvtColor(icon_roi, cv2.COLOR_BGR2HSV)

        best_type = "unknown"
        best_ratio = 0.0

        for icon_type, (lower, upper) in self._ICON_COLORS.items():
            mask = cv2.inRange(hsv, lower, upper)
            ratio = cv2.countNonZero(mask) / max(mask.size, 1)

            if ratio > best_ratio:
                best_ratio = ratio
                best_type = icon_type

        return best_type if best_ratio > 0.02 else "unknown"

    def _analyze_ring_progress(self, icon_roi: np.ndarray) -> float:
        """Analyze countdown ring to estimate remaining time."""
        if cv2 is None:
            return 1.0

        hsv = cv2.cvtColor(icon_roi, cv2.COLOR_BGR2HSV)

        # Check ring colors (green = full, yellow = mid, red = expiring)
        green_mask = cv2.inRange(hsv, self._RING_GREEN_LOW, self._RING_GREEN_HIGH)
        yellow_mask = cv2.inRange(hsv, self._RING_YELLOW_LOW, self._RING_YELLOW_HIGH)
        red_mask = cv2.inRange(hsv, self._RING_RED_LOW, self._RING_RED_HIGH)

        green_ratio = cv2.countNonZero(green_mask) / max(green_mask.size, 1)
        yellow_ratio = cv2.countNonZero(yellow_mask) / max(yellow_mask.size, 1)
        red_ratio = cv2.countNonZero(red_mask) / max(red_mask.size, 1)

        # Estimate progress (green = high, red = low)
        if green_ratio > 0.1:
            return 0.8 + green_ratio * 0.2
        elif yellow_ratio > 0.1:
            return 0.4 + yellow_ratio * 0.3
        elif red_ratio > 0.05:
            return red_ratio * 2  # Expiring soon
        else:
            return 0.5  # Unknown, assume half

    def _count_stacks(self, icon_roi: np.ndarray) -> int:
        """Estimate buff stack count from intensity."""
        if cv2 is None:
            return 1

        gray = cv2.cvtColor(icon_roi, cv2.COLOR_BGR2GRAY)
        avg_intensity = np.mean(gray) / 255.0

        # More intense = more stacks
        if avg_intensity > 200:
            return 3
        elif avg_intensity > 170:
            return 2
        else:
            return 1

    def _update_buffs(
        self,
        detections: list[tuple[str, float, int]],
        is_debuff: bool,
    ) -> None:
        """Update active buff tracking."""
        prefix = "debuff" if is_debuff else "buff"
        now = self._now_fn()

        for i, (icon_type, progress, stacks) in enumerate(detections):
            buff_id = f"{prefix}_{i}"

            # Estimate duration from progress (assume 30s base for short buffs)
            total_seconds = 30.0
            remaining = progress * total_seconds

            buff = BuffInfo(
                buff_id=buff_id,
                name=icon_type,
                icon_type=icon_type,
                remaining_seconds=remaining,
                total_seconds=total_seconds,
                progress=progress,
                is_debuff=is_debuff,
                stack_count=stacks,
            )

            self._active_buffs[buff_id] = buff
            self._buff_history[buff_id].append(remaining)

            # Keep history bounded
            if len(self._buff_history[buff_id]) > 120:
                self._buff_history[buff_id].pop(0)

    def _decay_missing_buffs(self, frame_id: int) -> None:
        """Decay buffs that weren't detected in this frame."""
        if frame_id <= self._last_frame_id + 3:
            return  # Just updated

        for buff_id in list(self._active_buffs.keys()):
            buff = self._active_buffs[buff_id]

            # Estimate decay
            new_remaining = max(0, buff.remaining_seconds - 0.1)

            if new_remaining <= 0:
                del self._active_buffs[buff_id]
            else:
                self._active_buffs[buff_id] = BuffInfo(
                    buff_id=buff.buff_id,
                    name=buff.name,
                    icon_type=buff.icon_type,
                    remaining_seconds=new_remaining,
                    total_seconds=buff.total_seconds,
                    progress=new_remaining / buff.total_seconds,
                    is_debuff=buff.is_debuff,
                    stack_count=buff.stack_count,
                )

    def _build_status(self) -> BuffFieldStatus:
        """Build buff field status."""
        buffs = tuple(self._active_buffs.values())
        active_buffs = [b for b in buffs if not b.is_debuff]
        active_debuffs = [b for b in buffs if b.is_debuff]
        critical = [b for b in buffs if b.remaining_seconds < 3.0]

        # Determine recommended action
        action = "continue_attack"
        if critical:
            action = "refresh_buffs"
        elif any(b.icon_type == "shield" for b in active_buffs):
            action = "maintain_shield"
        elif any(b.icon_type == "atk_boost" for b in active_buffs):
            action = "maximize_dps"

        return BuffFieldStatus(
            buffs=buffs,
            active_buff_count=len(active_buffs),
            active_debuff_count=len(active_debuffs),
            critical_buffs=tuple(critical),
            recommended_action=action,
        )

    def _get_roi(
        self,
        frame: np.ndarray,
        coords: tuple[float, float, float, float],
    ) -> np.ndarray:
        """Extract region of interest."""
        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1, y1, x2, y2 = coords
        x1, y1, x2, y2 = int(x1 * sx * self._REF_W), int(y1 * sy * self._REF_H), int(x2 * sx * self._REF_W), int(y2 * sy * self._REF_H)

        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        return frame[y1:y2, x1:x2]

    def has_buff(self, buff_name: str) -> bool:
        """Check if a specific buff is active."""
        return any(b.name == buff_name for b in self._active_buffs.values())

    def has_critical_buffs(self) -> bool:
        """Check if any buffs are about to expire."""
        return any(b.remaining_seconds < 3.0 for b in self._active_buffs.values())

    def reset(self) -> None:
        """Reset detector state."""
        self._active_buffs.clear()
        self._buff_history.clear()
        self._last_frame_id = 0