"""Genshin combat detector: HSV analysis to populate CombatSignal fields.

Detects enemy shields (element), boss phase indicators, incoming attack
telegraphs, and player hitstun/depletion from visual cues.  Designed to be
registered with FusionRuntime via set_combat_detector().
"""
from __future__ import annotations

import logging
import time

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

from perception.fusion_runtime import CombatSignal

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HSV colour ranges (OpenCV H: 0-179, S: 0-255, V: 0-255)
# ---------------------------------------------------------------------------

# Enemy shield auras — appear around shielded enemies
_SHIELD_HYDRO = ((90, 80, 100), (115, 255, 255))
_SHIELD_PYRO = ((0, 80, 100), (10, 255, 255))
_SHIELD_PYRO_HI = ((170, 80, 100), (179, 255, 255))
_SHIELD_CRYO = ((85, 60, 80), (105, 255, 255))  # blue-cyan overlap
_SHIELD_ELECTRO = ((100, 80, 100), (135, 255, 255))

# Boss phase indicators — screen-wide colour washes during phase transitions
_BOSS_GOLD_WASH = ((20, 40, 150), (35, 120, 255))  # gold overlay = phase up
_BOSS_RED_FLASH = ((0, 100, 150), (10, 255, 255))   # red flash = enrage
_BOSS_RED_FLASH_HI = ((170, 100, 150), (179, 255, 255))

# Incoming attack telegraph — bright expanding circle/warning
_TELEGRAPH_BRIGHT = ((0, 0, 200), (180, 60, 255))  # very bright, low saturation
_TELEGRAPH_RED = ((0, 120, 180), (10, 255, 255))

# Player hitstun — screen edge red vignette
_HITSTUN_RED_EDGE = ((0, 100, 100), (10, 200, 200))

# Stamina bar ROI (same as StaminaTracker)
_STAMINA_ROI = (60, 920, 300, 960)
_STAMINA_YELLOW = ((20, 80, 80), (35, 255, 255))

_REF_W = 1920
_REF_H = 1080


class GenshinCombatDetector:
    """Detect combat-relevant visual features from Genshin frames.

    Returns a CombatSignal enriched with shield element, boss phase,
    incoming hitstun, and stamina ratio.
    """

    # Enemy HP bar ROI: top 60% of screen
    _ENEMY_ROI = (100, 50, 1780, 600)

    def __init__(self, viewport: tuple[int, int] = (1920, 1080)) -> None:
        self._viewport = viewport
        self._last_boss_phase = 1
        self._phase_cooldown = 0.0

    def detect(self, frame: np.ndarray) -> CombatSignal:
        """Analyse frame and return enriched CombatSignal."""
        if cv2 is None:
            return CombatSignal()

        h, w = frame.shape[:2]
        sx, sy = w / _REF_W, h / _REF_H

        # 1. Detect enemy shield element
        shield_element = self._detect_shield_element(frame, sx, sy)

        # 2. Detect boss phase transitions
        boss_phase, boss_enraged, mechanic = self._detect_boss_phase(frame)

        # 3. Detect incoming attack telegraphs
        hitstun = self._detect_hitstun(frame, sx, sy)

        # 4. Detect player stamina (for combo_broken inference)
        stamina = self._detect_stamina(frame, sx, sy)

        # 5. Estimate danger score
        danger = self._compute_danger(shield_element, boss_enraged, hitstun, stamina)

        return CombatSignal(
            enemy_shield_element=shield_element,
            boss_phase=boss_phase,
            boss_enraged=boss_enraged,
            boss_mechanic_active=mechanic,
            incoming_hitstun=hitstun,
            player_stamina_ratio=stamina,
            danger_score=danger,
            combo_broken=hitstun and stamina < 0.3,
        )

    # ------------------------------------------------------------------
    # Shield element detection
    # ------------------------------------------------------------------

    def _detect_shield_element(self, frame: np.ndarray, sx: float, sy: float) -> str:
        """Detect elemental shield on enemies (hydro/pyro/cryo/electro)."""
        x1, y1, x2, y2 = self._scale_roi(self._ENEMY_ROI, sx, sy)
        roi = frame[max(0, y1):min(frame.shape[0], y2),
                    max(0, x1):min(frame.shape[1], x2)]
        if roi.size == 0:
            return ""

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        best_element = ""
        best_count = 200  # minimum pixel threshold

        for element, ranges in [
            ("hydro", [_SHIELD_HYDRO]),
            ("pyro", [_SHIELD_PYRO, _SHIELD_PYRO_HI]),
            ("cryo", [_SHIELD_CRYO]),
            ("electro", [_SHIELD_ELECTRO]),
        ]:
            total = 0
            for lower, upper in ranges:
                mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
                total += cv2.countNonZero(mask)
            if total > best_count:
                best_count = total
                best_element = element

        return best_element

    # ------------------------------------------------------------------
    # Boss phase detection
    # ------------------------------------------------------------------

    def _detect_boss_phase(self, frame: np.ndarray) -> tuple[int, bool, str]:
        """Detect boss phase transition effects and enrage state."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Detect gold wash (phase transition)
        gold_mask = cv2.inRange(hsv, np.array(_BOSS_GOLD_WASH[0]), np.array(_BOSS_GOLD_WASH[1]))
        gold_ratio = cv2.countNonZero(gold_mask) / max(frame.shape[0] * frame.shape[1], 1)

        # Detect red flash (enrage)
        red_mask = cv2.inRange(hsv, np.array(_BOSS_RED_FLASH[0]), np.array(_BOSS_RED_FLASH[1]))
        red_mask2 = cv2.inRange(hsv, np.array(_BOSS_RED_FLASH_HI[0]), np.array(_BOSS_RED_FLASH_HI[1]))
        red_ratio = (cv2.countNonZero(red_mask) + cv2.countNonZero(red_mask2)) / max(frame.shape[0] * frame.shape[1], 1)

        now = time.perf_counter()

        # Phase up on gold wash (with cooldown to avoid multi-counting)
        phase = self._last_boss_phase
        mechanic = ""
        if gold_ratio > 0.08 and (now - self._phase_cooldown) > 5.0:
            phase = min(self._last_boss_phase + 1, 4)
            self._last_boss_phase = phase
            self._phase_cooldown = now
            mechanic = "phase_transition"
            log.info("[CombatDetector] boss phase transition → phase %d", phase)

        # Enrage on sustained red
        enraged = red_ratio > 0.10
        if enraged:
            mechanic = mechanic or "enrage"

        return phase, enraged, mechanic

    # ------------------------------------------------------------------
    # Hitstun / incoming attack detection
    # ------------------------------------------------------------------

    def _detect_hitstun(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        """Detect incoming attack telegraphs or player hitstun via edge vignette."""
        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Check screen edges for red vignette (player taking damage)
        edge_thickness = max(int(50 * sy), 10)
        top_edge = hsv[:edge_thickness, :, :]
        bottom_edge = hsv[-edge_thickness:, :, :]
        left_edge = hsv[:, :edge_thickness, :]
        right_edge = hsv[:, -edge_thickness:, :]

        red_edge_count = 0
        for edge in [top_edge, bottom_edge, left_edge, right_edge]:
            mask = cv2.inRange(edge, np.array(_HITSTUN_RED_EDGE[0]), np.array(_HITSTUN_RED_EDGE[1]))
            red_edge_count += cv2.countNonZero(mask)

        total_edge_px = (top_edge.size + bottom_edge.size + left_edge.size + right_edge.size) // 3
        red_ratio = red_edge_count / max(total_edge_px, 1)

        return red_ratio > 0.15

    # ------------------------------------------------------------------
    # Stamina detection (reuses StaminaTracker ROI)
    # ------------------------------------------------------------------

    def _detect_stamina(self, frame: np.ndarray, sx: float, sy: float) -> float:
        """Quick stamina ratio reading from HUD."""
        x1, y1, x2, y2 = self._scale_roi(_STAMINA_ROI, sx, sy)
        roi = frame[max(0, y1):min(frame.shape[0], y2),
                    max(0, x1):min(frame.shape[1], x2)]
        if roi.size == 0:
            return 1.0

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(_STAMINA_YELLOW[0]), np.array(_STAMINA_YELLOW[1]))
        stamina_px = cv2.countNonZero(mask)
        total_px = roi.shape[1]
        return min(stamina_px / max(total_px, 1), 1.0)

    # ------------------------------------------------------------------
    # Danger score computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_danger(
        shield_element: str,
        enraged: bool,
        hitstun: bool,
        stamina: float,
    ) -> float:
        """Compute a 0-1 danger score from detected signals."""
        score = 0.0
        if shield_element:
            score += 0.2
        if enraged:
            score += 0.3
        if hitstun:
            score += 0.3
        if stamina < 0.3:
            score += 0.2
        return min(score, 1.0)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _scale_roi(roi: tuple, sx: float, sy: float) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))


if __name__ == "__main__":
    print("GenshinCombatDetector: HSV combat signal enrichment")
    print("Detects: shield element, boss phase, hitstun, stamina, danger score")
