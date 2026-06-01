"""Enemy HP bar and stamina tracking for Genshin Impact.

P2.1: Enemy HP bar detection (HSV color analysis + optional OCR)
P2.2: Character switching UI detection
P2.3: Real-time stamina continuous tracking
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Literal

import numpy as np

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import cv2
except ImportError:
    cv2 = None

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enemy HP Bar Detection
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EnemyHPBar:
    """Detected enemy HP bar with normalized position."""
    screen_x: float  # normalized 0-1
    screen_y: float  # normalized 0-1
    width_px: float
    height_px: float
    fill_ratio: float  # 0.0-1.0 (current HP / max HP)
    bar_color: Literal["red", "yellow", "shield"] = "red"
    confidence: float = 0.0
    frame_id: int = 0


@dataclass(frozen=True, slots=True)
class EnemyHPReading:
    """Aggregate enemy HP read result."""
    bars: tuple[EnemyHPBar, ...] = ()
    lowest_ratio: float = 1.0  # most critical enemy HP
    highest_ratio: float = 1.0
    count: int = 0
    has_shield: bool = False
    frame_id: int = 0
    timestamp: float = 0.0


class EnemyHPBarDetector:
    """Detect enemy HP bars above enemies.

    Enemy HP bars in Genshin appear above enemy heads.
    Uses HSV color detection for red/yellow HP bars and shield indicators.
    """

    _REF_W = 1920
    _REF_H = 1080

    # Enemy HP bar colors (HSV ranges)
    _ENEMY_HP_RED = ((0, 80, 80), (10, 255, 255))
    _ENEMY_HP_RED_HI = ((170, 80, 80), (180, 255, 255))
    _ENEMY_HP_YELLOW = ((20, 80, 80), (35, 255, 255))
    _ENEMY_SHIELD_BLUE = ((100, 60, 60), (130, 255, 255))
    _ENEMY_SHIELD_PURPLE = ((130, 60, 60), (160, 255, 255))

    # Enemy HP bar ROI: top 60% of screen (where HP bars appear above enemies)
    _ENEMY_HP_ROI = (100, 50, 1780, 600)

    def __init__(self, viewport: tuple[int, int] = (1920, 1080)) -> None:
        self._viewport = viewport
        self._last_reading: EnemyHPReading | None = None

    def detect(self, frame: np.ndarray, frame_id: int) -> EnemyHPReading:
        if cv2 is None:
            return EnemyHPReading(frame_id=frame_id, timestamp=time.perf_counter())

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._ENEMY_HP_ROI, sx, sy)
        roi = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if roi.size == 0:
            return EnemyHPReading(frame_id=frame_id, timestamp=time.perf_counter())

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        bars: list[EnemyHPBar] = []
        bar_height_threshold = 6  # px, minimum bar height
        bar_width_threshold = 20  # px, minimum bar width

        for (lower, upper, color) in [
            (self._ENEMY_HP_RED[0], self._ENEMY_HP_RED[1], "red"),
            (self._ENEMY_HP_RED_HI[0], self._ENEMY_HP_RED_HI[1], "red"),
            (self._ENEMY_HP_YELLOW[0], self._ENEMY_HP_YELLOW[1], "yellow"),
        ]:
            mask = cv2.inRange(hsv, np.array(lower[0]), np.array(upper[1]))
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                x, y, cw, ch = cv2.boundingRect(contour)
                if cw < bar_width_threshold or ch < bar_height_threshold:
                    continue
                fill = self._estimate_fill(mask[y:y + ch, x:x + cw])
                bar = EnemyHPBar(
                    screen_x=(x1 + x + cw / 2) / w,
                    screen_y=(y1 + y) / h,
                    width_px=float(cw),
                    height_px=float(ch),
                    fill_ratio=fill,
                    bar_color=color,
                    confidence=0.8 if fill > 0.5 else 0.6,
                    frame_id=frame_id,
                )
                bars.append(bar)

        ratios = [b.fill_ratio for b in bars] if bars else [1.0]
        reading = EnemyHPReading(
            bars=tuple(bars),
            lowest_ratio=min(ratios) if ratios else 1.0,
            highest_ratio=max(ratios) if ratios else 1.0,
            count=len(bars),
            has_shield=self._detect_shield(hsv),
            frame_id=frame_id,
            timestamp=time.perf_counter(),
        )
        self._last_reading = reading
        return reading

    def _detect_shield(self, hsv: np.ndarray) -> bool:
        for (lower, upper) in [
            (self._ENEMY_SHIELD_BLUE[0], self._ENEMY_SHIELD_BLUE[1]),
            (self._ENEMY_SHIELD_PURPLE[0], self._ENEMY_SHIELD_PURPLE[1]),
        ]:
            mask = cv2.inRange(hsv, np.array(lower[0]), np.array(upper[1]))
            if cv2.countNonZero(mask) > 200:
                return True
        return False

    def _estimate_fill(self, bar_mask: np.ndarray) -> float:
        """Estimate how full the HP bar is (left side = current, right = empty)."""
        if bar_mask.size == 0:
            return 1.0
        col_sums = bar_mask.sum(axis=0)
        total = float(col_sums.max()) if col_sums.max() > 0 else 1.0
        filled = 0
        for col in col_sums:
            if col > total * 0.1:
                filled += 1
            else:
                break
        return min(filled / max(len(col_sums), 1), 1.0)

    @staticmethod
    def _scale_roi(roi: tuple, sx: float, sy: float) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))


# ---------------------------------------------------------------------------
# Character Switching UI Detection
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CharacterSwitchState:
    """State of the character switching UI."""
    visible: bool = False
    slot_count: int = 0  # 1-4 visible
    selected_slot: int = 0  # 0=none, 1-4
    slot_hp_pcts: tuple[float, ...] = ()  # HP ratio for each slot
    frame_id: int = 0


class CharacterSwitchDetector:
    """Detect character switching UI (Tab menu in Genshin).

    The character switch UI appears when pressing Tab.
    Shows 4 character portraits with HP/stamina indicators.
    """

    _REF_W = 1920
    _REF_H = 1080

    # Character portrait grid regions (4 slots)
    _SLOT_ROIS = [
        (150, 600, 350, 850),   # Slot 1 (left)
        (500, 600, 700, 850),   # Slot 2
        (850, 600, 1050, 850),  # Slot 3
        (1200, 600, 1400, 850), # Slot 4
    ]

    _HP_GREEN = ((35, 80, 80), (85, 255, 255))
    _HP_YELLOW = ((20, 80, 80), (35, 255, 255))
    _HP_RED = ((0, 80, 80), (10, 255, 255))
    _HP_RED_HI = ((170, 80, 80), (180, 255, 255))

    def detect(self, frame: np.ndarray, frame_id: int) -> CharacterSwitchState:
        if cv2 is None:
            return CharacterSwitchState(frame_id=frame_id)

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        # Check if character switch UI is visible by looking for portrait regions
        visible_slots = 0
        hp_pcts: list[float] = []

        for slot_idx, roi in enumerate(self._SLOT_ROIS, 1):
            x1, y1, x2, y2 = self._scale_roi(roi, sx, sy)
            roi_frame = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
            if roi_frame.size == 0:
                continue

            # Check if slot has a portrait (non-dark area)
            gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
            mean_brightness = float(np.mean(gray))
            if mean_brightness > 30:
                visible_slots += 1
                hp_pct = self._read_slot_hp(roi_frame)
                hp_pcts.append(hp_pct)

        return CharacterSwitchState(
            visible=visible_slots >= 2,
            slot_count=visible_slots,
            selected_slot=0,  # Will be set by VLM if needed
            slot_hp_pcts=tuple(hp_pcts),
            frame_id=frame_id,
        )

    def _read_slot_hp(self, slot_roi: np.ndarray) -> float:
        """Read HP bar fill ratio for a character slot."""
        h, w = slot_roi.shape[:2]
        # HP bar is typically in lower portion of portrait slot
        hp_region = slot_roi[int(h * 0.7):, :]
        if hp_region.size == 0:
            return 1.0

        hsv = cv2.cvtColor(hp_region, cv2.COLOR_BGR2HSV)
        total_px = hp_region.shape[1]
        hp_px = 0

        for lower, upper in [
            (self._HP_GREEN[0], self._HP_GREEN[1]),
            (self._HP_YELLOW[0], self._HP_YELLOW[1]),
            (self._HP_RED[0], self._HP_RED[1]),
            (self._HP_RED_HI[0], self._HP_RED_HI[1]),
        ]:
            mask = cv2.inRange(hsv, np.array(lower[0]), np.array(upper[1]))
            hp_px += cv2.countNonZero(mask)

        return min(hp_px / max(total_px, 1), 1.0)

    @staticmethod
    def _scale_roi(roi: tuple, sx: float, sy: float) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))


# ---------------------------------------------------------------------------
# Real-time Stamina Tracking
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class StaminaReading:
    """Continuous stamina reading with history."""
    ratio: float  # 0.0-1.0
    activity: Literal["idle", "climbing", "swimming", "gliding", "running", "sprinting"] = "idle"
    critical: bool = False
    depleted: bool = False
    frame_id: int = 0
    timestamp: float = 0.0


class StaminaTracker:
    """Real-time stamina bar tracking with activity inference.

    Reads stamina bar from screen and tracks temporal patterns
    to infer current activity (climbing/swimming/gliding/running).
    """

    _REF_W = 1920
    _REF_H = 1080

    # Stamina bar ROI (below minimap, in HUD area)
    _STAMINA_ROI = (60, 920, 300, 960)

    # Stamina bar color (yellow)
    _STAMINA_YELLOW = ((20, 80, 80), (35, 255, 255))
    _STAMINA_ORANGE = ((10, 80, 80), (25, 255, 255))
    _STAMINA_LOW = ((0, 60, 60), (20, 255, 255))

    def __init__(self, history_size: int = 30) -> None:
        self._history: list[StaminaReading] = []
        self._max_history = history_size
        self._last_reading: StaminaReading | None = None

    def detect(self, frame: np.ndarray, frame_id: int) -> StaminaReading:
        if cv2 is None:
            return StaminaReading(ratio=1.0, frame_id=frame_id, timestamp=time.perf_counter())

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._STAMINA_ROI, sx, sy)
        roi = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if roi.size == 0:
            reading = StaminaReading(ratio=1.0, activity="idle", frame_id=frame_id, timestamp=time.perf_counter())
        else:
            ratio = self._read_stamina_ratio(roi)
            activity = self._infer_activity(ratio)
            reading = StaminaReading(
                ratio=ratio,
                activity=activity,
                critical=ratio < 0.2,
                depleted=ratio < 0.05,
                frame_id=frame_id,
                timestamp=time.perf_counter(),
            )

        self._history.append(reading)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        self._last_reading = reading
        return reading

    def _read_stamina_ratio(self, roi: np.ndarray) -> float:
        """Read stamina bar fill ratio."""
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        total_px = roi.shape[1]
        stamina_px = 0

        for lower, upper in [
            (self._STAMINA_YELLOW[0], self._STAMINA_YELLOW[1]),
            (self._STAMINA_ORANGE[0], self._STAMINA_ORANGE[1]),
        ]:
            mask = cv2.inRange(hsv, np.array(lower[0]), np.array(upper[1]))
            stamina_px += cv2.countNonZero(mask)

        # Also check for low stamina (red tint when depleted)
        if stamina_px == 0:
            mask = cv2.inRange(hsv, np.array(self._STAMINA_LOW[0]), np.array(self._STAMINA_LOW[1]))
            stamina_px = cv2.countNonZero(mask)

        return min(stamina_px / max(total_px, 1), 1.0)

    def _infer_activity(self, current_ratio: float) -> Literal["idle", "climbing", "swimming", "gliding", "running", "sprinting"]:
        """Infer current activity from stamina depletion rate."""
        if len(self._history) < 3:
            return "idle"

        recent = self._history[-5:]
        ratios = [r.ratio for r in recent]

        # Calculate depletion rate
        if ratios[0] > ratios[-1]:
            delta = ratios[0] - ratios[-1]
            if delta > 0.05:
                # Fast depletion = active activity
                if delta > 0.15:
                    return "sprinting"
                return "running"
            elif delta < 0.02 and current_ratio < 0.5:
                return "climbing" if self._last_reading and self._last_reading.activity in ("climbing", "swimming", "gliding") else "idle"

        # Check last known activity
        if self._last_reading:
            return self._last_reading.activity
        return "idle"

    @staticmethod
    def _scale_roi(roi: tuple, sx: float, sy: float) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))

    def is_critical(self) -> bool:
        if self._last_reading is None:
            return False
        return self._last_reading.critical

    def is_depleted(self) -> bool:
        if self._last_reading is None:
            return False
        return self._last_reading.depleted


if __name__ == "__main__":
    print("Enemy HP Bar Detector: detects enemy HP bars above enemies")
    print("Character Switch Detector: detects Tab character switch UI")
    print("Stamina Tracker: real-time stamina bar tracking")