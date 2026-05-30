"""Visual detectors for Genshin Impact gameplay elements.

Extends the base screen classifier with specialized detectors for:
- P-10: Boss phase transition detection (visual glow/aura changes)
- P-12: Elemental aura on enemies (Pyro/Hydro/Electro/Cryo/Dendro glow)
- P-14: Weather/environment gauges (Sheer Cold, Balethunder)
- P-15: Stamina bar detection (climbing/swimming/gliding)
- P-16: Countdown timer detection (timed challenges)
- P-17: Chest quality identification (common/exquisite/precious/luxurious)

All detectors use HSV color analysis consistent with genshin_screen_classifier.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


class BossPhaseIndicator(str, Enum):
    IDLE = "idle"
    AGGRESSIVE = "aggressive"
    INVULNERABLE = "invulnerable"
    STUNNED = "stunned"
    TRANSITIONING = "transitioning"
    ENRAGED = "enraged"


class ChestQuality(str, Enum):
    COMMON = "common"          # Brown/wood
    EXQUISITE = "exquisite"    # Blue glow
    PRECIOUS = "precious"      # Purple glow
    LUXURIOUS = "luxurious"    # Gold glow
    REMARKABLE = "remarkable"  # Red/rainbow (event)


class ElementType(str, Enum):
    PYRO = "Pyro"
    HYDRO = "Hydro"
    ELECTRO = "Electro"
    CRYO = "Cryo"
    ANEMO = "Anemo"
    GEO = "Geo"
    DENDRO = "Dendro"


@dataclass(frozen=True, slots=True)
class BossPhaseDetection:
    phase: BossPhaseIndicator
    confidence: float
    glow_intensity: float         # 0.0-1.0
    shield_visible: bool = False


@dataclass(frozen=True, slots=True)
class ElementalAuraDetection:
    element: ElementType | None
    intensity: float              # 0.0-1.0
    position: tuple[int, int]     # center pixel coords
    radius: int = 0


@dataclass(frozen=True, slots=True)
class EnvironmentGauge:
    gauge_type: str               # "sheer_cold", "balethunder", "phlogiston"
    level: float                  # 0.0-1.0 (1.0 = critical)
    is_active: bool = False


@dataclass(frozen=True, slots=True)
class StaminaBarState:
    ratio: float                  # 0.0-1.0
    is_visible: bool = False
    is_recovering: bool = False


@dataclass(frozen=True, slots=True)
class CountdownTimer:
    seconds_remaining: float
    is_active: bool = False
    position: tuple[int, int] = (0, 0)


@dataclass(frozen=True, slots=True)
class ChestDetection:
    quality: ChestQuality
    position: tuple[int, int]     # center pixel coords
    is_locked: bool = False
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Color ranges in HSV (OpenCV: H=0-179, S=0-255, V=0-255)
# ---------------------------------------------------------------------------

_ELEMENT_HSV: dict[ElementType, tuple[np.ndarray, np.ndarray]] = {
    ElementType.PYRO: (
        np.array([0, 150, 150]),
        np.array([15, 255, 255]),
    ),
    ElementType.HYDRO: (
        np.array([95, 100, 100]),
        np.array([130, 255, 255]),
    ),
    ElementType.ELECTRO: (
        np.array([130, 100, 100]),
        np.array([160, 255, 255]),
    ),
    ElementType.CRYO: (
        np.array([85, 50, 150]),
        np.array([110, 200, 255]),
    ),
    ElementType.DENDRO: (
        np.array([35, 100, 100]),
        np.array([80, 255, 255]),
    ),
    ElementType.ANEMO: (
        np.array([65, 50, 150]),
        np.array([90, 200, 255]),
    ),
    ElementType.GEO: (
        np.array([15, 100, 100]),
        np.array([35, 255, 255]),
    ),
}

# Chest quality HSV glow colors (the aura around the chest)
_CHEST_HSV: dict[ChestQuality, tuple[np.ndarray, np.ndarray]] = {
    ChestQuality.COMMON: (
        np.array([10, 30, 80]),
        np.array([25, 255, 220]),
    ),
    ChestQuality.EXQUISITE: (
        np.array([90, 80, 120]),
        np.array([120, 255, 255]),
    ),
    ChestQuality.PRECIOUS: (
        np.array([120, 80, 120]),
        np.array([150, 255, 255]),
    ),
    ChestQuality.LUXURIOUS: (
        np.array([15, 80, 160]),
        np.array([40, 255, 255]),
    ),
}


class GenshinVisualDetector:
    """Specialized visual detectors for Genshin gameplay elements.

    All methods accept BGR numpy frames and return structured detection results.
    Uses HSV color analysis + contour detection consistent with existing classifier.
    """

    _REF_W = 1920
    _REF_H = 1080

    # ROI regions (reference coordinates at 1920x1080)
    _STAMINA_ROI = (870, 910, 1050, 940)
    _TIMER_ROI = (800, 50, 1120, 130)
    _ENV_GAUGE_ROI = (10, 700, 60, 900)
    _BOSS_HP_ROI = (400, 30, 1520, 80)

    def detect_boss_phase(self, frame: np.ndarray) -> BossPhaseDetection:
        """Detect boss phase from visual indicators (P-10).

        Uses boss HP bar color and surrounding aura to determine phase.
        """
        if cv2 is None:
            return BossPhaseDetection(BossPhaseIndicator.IDLE, 0.0, 0.0)

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        # Check boss HP bar region for phase indicators
        x1, y1, x2, y2 = self._scale_roi(self._BOSS_HP_ROI, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return BossPhaseDetection(BossPhaseIndicator.IDLE, 0.0, 0.0)

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Check for invulnerable indicator (bright golden glow — much more saturated than HP bar)
        invul_mask = cv2.inRange(
            hsv,
            np.array([18, 200, 220]),
            np.array([28, 255, 255]),
        )
        invul_ratio = cv2.countNonZero(invul_mask) / max(invul_mask.size, 1)

        # Check for enraged indicator (deep red pulsing aura)
        red_mask = cv2.inRange(
            hsv,
            np.array([0, 180, 180]),
            np.array([8, 255, 255]),
        )
        red_ratio = cv2.countNonZero(red_mask) / max(red_mask.size, 1)

        # Boss HP bar presence (white/yellow bar at top)
        hp_bar_mask = cv2.inRange(
            hsv,
            np.array([10, 20, 150]),
            np.array([45, 255, 255]),
        )
        hp_visible = cv2.countNonZero(hp_bar_mask) / max(hp_bar_mask.size, 1) > 0.05

        glow = max(invul_ratio, red_ratio)

        if not hp_visible:
            return BossPhaseDetection(BossPhaseIndicator.IDLE, 0.5, 0.0)

        if invul_ratio > 0.15:
            return BossPhaseDetection(BossPhaseIndicator.INVULNERABLE, 0.8,
                                      glow, shield_visible=True)
        if red_ratio > 0.15:
            return BossPhaseDetection(BossPhaseIndicator.ENRAGED, 0.75, glow)

        if glow > 0.05:
            return BossPhaseDetection(BossPhaseIndicator.TRANSITIONING, 0.6, glow)

        return BossPhaseDetection(BossPhaseIndicator.AGGRESSIVE, 0.7, glow)

    def detect_elemental_auras(self, frame: np.ndarray,
                               target_roi: tuple[int, int, int, int] | None = None,
                               ) -> list[ElementalAuraDetection]:
        """Detect elemental auras on enemies in frame (P-12).

        Scans for colored glows matching element types.
        """
        if cv2 is None:
            return []

        if target_roi:
            x1, y1, x2, y2 = target_roi
            roi = frame[y1:y2, x1:x2]
        else:
            roi = frame
            x1, y1 = 0, 0

        if roi.size == 0:
            return []

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        detections: list[ElementalAuraDetection] = []

        for element, (lower, upper) in _ELEMENT_HSV.items():
            mask = cv2.inRange(hsv, lower, upper)
            pixel_count = cv2.countNonZero(mask)

            if pixel_count < 50:
                continue

            intensity = min(pixel_count / 5000.0, 1.0)

            # Find center of the detected region
            moments = cv2.moments(mask)
            if moments["m00"] > 0:
                cx = int(moments["m10"] / moments["m00"]) + x1
                cy = int(moments["m01"] / moments["m00"]) + y1
            else:
                cx, cy = x1 + roi.shape[1] // 2, y1 + roi.shape[0] // 2

            detections.append(ElementalAuraDetection(
                element=element,
                intensity=intensity,
                position=(cx, cy),
            ))

        # Return strongest detection per element
        return sorted(detections, key=lambda d: d.intensity, reverse=True)

    def detect_environment_gauge(self, frame: np.ndarray) -> EnvironmentGauge:
        """Detect environment hazard gauges (P-14).

        Detects Sheer Cold (Dragonspine), Balethunder (Inazuma), Phlogiston (Natlan).
        """
        if cv2 is None:
            return EnvironmentGauge("none", 0.0)

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._ENV_GAUGE_ROI, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return EnvironmentGauge("none", 0.0)

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Sheer Cold: blue/white gauge on left side
        cold_mask = cv2.inRange(
            hsv,
            np.array([90, 30, 100]),
            np.array([125, 255, 255]),
        )
        cold_ratio = cv2.countNonZero(cold_mask) / max(cold_mask.size, 1)

        # Balethunder: purple/electric gauge
        bale_mask = cv2.inRange(
            hsv,
            np.array([130, 80, 100]),
            np.array([155, 255, 255]),
        )
        bale_ratio = cv2.countNonZero(bale_mask) / max(bale_mask.size, 1)

        # Phlogiston: orange/red gauge
        phlog_mask = cv2.inRange(
            hsv,
            np.array([5, 100, 150]),
            np.array([20, 255, 255]),
        )
        phlog_ratio = cv2.countNonZero(phlog_mask) / max(phlog_mask.size, 1)

        if cold_ratio > 0.05:
            return EnvironmentGauge("sheer_cold", cold_ratio, is_active=True)
        if bale_ratio > 0.05:
            return EnvironmentGauge("balethunder", bale_ratio, is_active=True)
        if phlog_ratio > 0.05:
            return EnvironmentGauge("phlogiston", phlog_ratio, is_active=True)

        return EnvironmentGauge("none", 0.0)

    def detect_stamina_bar(self, frame: np.ndarray) -> StaminaBarState:
        """Detect stamina bar state (P-15).

        The stamina bar appears during climbing, swimming, gliding, and sprinting.
        It's a thin bar near the bottom-center of screen.
        """
        if cv2 is None:
            return StaminaBarState(0.0)

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._STAMINA_ROI, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return StaminaBarState(0.0)

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Stamina bar is yellow when full, orange when low
        stamina_mask = cv2.inRange(
            hsv,
            np.array([15, 100, 150]),
            np.array([35, 255, 255]),
        )

        # Background of stamina area is dark
        dark_mask = cv2.inRange(
            hsv,
            np.array([0, 0, 0]),
            np.array([180, 50, 80]),
        )

        total_pixels = stamina_mask.size
        stamina_pixels = cv2.countNonZero(stamina_mask)
        dark_pixels = cv2.countNonZero(dark_mask)

        if stamina_pixels < 10 and dark_pixels < total_pixels * 0.3:
            return StaminaBarState(0.0, is_visible=False)

        # Stamina bar must have actual yellow/orange pixels to be visible
        is_visible = stamina_pixels > total_pixels * 0.03
        if not is_visible:
            return StaminaBarState(0.0, is_visible=False)

        ratio = stamina_pixels / max(stamina_pixels + dark_pixels, 1)
        return StaminaBarState(ratio, is_visible=True)

    def detect_countdown_timer(self, frame: np.ndarray) -> CountdownTimer:
        """Detect countdown timer for timed challenges (P-16).

        Timed challenges show a countdown in the upper-center of the screen.
        Returns detected time or 0 if no timer found.
        """
        if cv2 is None:
            return CountdownTimer(0.0)

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._TIMER_ROI, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return CountdownTimer(0.0)

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Timer text is white/yellow on semi-transparent dark background
        timer_mask = cv2.inRange(
            hsv,
            np.array([10, 20, 150]),
            np.array([40, 255, 255]),
        )

        # Red urgent timer (below 30 seconds)
        urgent_mask = cv2.inRange(
            hsv,
            np.array([0, 150, 150]),
            np.array([10, 255, 255]),
        )

        timer_pixels = cv2.countNonZero(timer_mask)
        urgent_pixels = cv2.countNonZero(urgent_mask)

        total_signal = timer_pixels + urgent_pixels
        if total_signal < 20:
            return CountdownTimer(0.0)

        # Estimate time from color (urgent = less than 30s)
        is_urgent = urgent_pixels > timer_pixels * 0.3

        return CountdownTimer(
            seconds_remaining=15.0 if is_urgent else 120.0,
            is_active=True,
            position=((x1 + x2) // 2, (y1 + y2) // 2),
        )

    def detect_chest_quality(self, frame: np.ndarray,
                             chest_roi: tuple[int, int, int, int],
                             ) -> ChestDetection | None:
        """Identify chest quality from the glow color (P-17).

        Args:
            frame: Full BGR frame.
            chest_roi: Region of interest around the detected chest.
        """
        if cv2 is None:
            return None

        x1, y1, x2, y2 = chest_roi
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return None

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        best_quality = ChestQuality.COMMON
        best_ratio = 0.0

        for quality, (lower, upper) in _CHEST_HSV.items():
            mask = cv2.inRange(hsv, lower, upper)
            ratio = cv2.countNonZero(mask) / max(mask.size, 1)
            if ratio > best_ratio:
                best_ratio = ratio
                best_quality = quality

        if best_ratio < 0.02:
            return None

        return ChestDetection(
            quality=best_quality,
            position=((x1 + x2) // 2, (y1 + y2) // 2),
            confidence=min(best_ratio * 5, 1.0),
        )

    def _scale_roi(self, roi: tuple[int, int, int, int],
                   sx: float, sy: float) -> tuple[int, int, int, int]:
        return (
            int(roi[0] * sx), int(roi[1] * sy),
            int(roi[2] * sx), int(roi[3] * sy),
        )
