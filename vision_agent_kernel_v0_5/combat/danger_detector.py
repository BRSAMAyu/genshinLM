from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class DangerState:
    score: float
    level: str
    components: dict[str, float]
    dominant_signal: str


class DangerDetector:
    def evaluate(self, signals: dict[str, float], context_priority: float = 0.0) -> DangerState:
        generic_warning = _clamp(signals.get("generic_warning_area", 0.0))
        projectile = _clamp(signals.get("projectile_approaching", 0.0))
        bbox_expand = _clamp(signals.get("target_bbox_fast_expand", 0.0))
        enemy_facing = _clamp(signals.get("enemy_facing_player", 0.0))
        hp_drop = _clamp(signals.get("hp_drop_signal", 0.0))
        scripted = _clamp(signals.get("scripted_testbed_danger", 0.0))
        priority = _clamp(context_priority)

        components = {
            "generic_warning_score": generic_warning * 0.25,
            "projectile_threat_score": projectile * 0.25,
            "distance_closing_score": max(bbox_expand, enemy_facing * 0.75) * 0.20,
            "hp_drop_score": hp_drop * 0.25,
            "scripted_testbed_score": scripted * 0.35,
            "combat_context_priority": priority * 0.20,
        }
        score = _clamp(sum(components.values()))
        level = "HIGH" if score >= 0.8 else "MEDIUM" if score >= 0.45 else "LOW"
        dominant_signal = max(components, key=components.get) if components else "none"
        return DangerState(score=score, level=level, components=components, dominant_signal=dominant_signal)


@dataclass(frozen=True, slots=True)
class DangerSignals:
    ground_danger_zone: float
    projectile_approaching: float
    hp_drop_signal: float
    boss_windup: float
    stamina_critical: float
    overall_danger: float


@dataclass(frozen=True, slots=True)
class DangerThresholds:
    ground_danger: float = 0.15
    hp_drop: float = 0.2
    projectile: float = 0.5
    stamina_low: float = 0.2
    overall_dodge: float = 0.7
    overall_retreat: float = 0.9


_DANGER_WEIGHTS = {
    "ground_danger_zone": 0.35,
    "hp_drop_signal": 0.30,
    "projectile_approaching": 0.20,
    "boss_windup": 0.10,
    "stamina_critical": 0.05,
}


class GenshinDangerSignalExtractor:
    DODGE_PRIORITY: dict[str, int] = {
        "ground_danger_zone": 0,
        "hp_drop_signal": 0,
        "projectile_approaching": 1,
        "stamina_critical": 1,
        "boss_windup": 2,
    }

    def __init__(self, thresholds: DangerThresholds | None = None) -> None:
        self._thresholds = thresholds or DangerThresholds()
        self._prev_char_hp: float = 1.0

    def extract(
        self,
        frame: np.ndarray,
        prev_frame: np.ndarray | None = None,
        rois: dict[str, tuple[int, int, int, int]] | None = None,
    ) -> DangerSignals:
        ground_roi = self._crop(frame, rois, "ground_area") if rois else frame
        char_hp_roi = self._crop(frame, rois, "active_char_hp") if rois else frame
        stamina_roi = self._crop(frame, rois, "stamina_bar") if rois else frame

        ground_danger = self._detect_ground_danger(ground_roi)
        projectile = self._detect_projectile(frame, prev_frame) if prev_frame is not None else 0.0
        hp_drop = self._detect_hp_drop(char_hp_roi)
        stamina_crit = self._detect_stamina(stamina_roi)
        boss_windup = self._detect_boss_windup(frame, prev_frame)

        signals = DangerSignals(
            ground_danger_zone=ground_danger,
            projectile_approaching=projectile,
            hp_drop_signal=hp_drop,
            boss_windup=boss_windup,
            stamina_critical=stamina_crit,
            overall_danger=0.0,
        )
        overall = self._compute_overall_danger(signals)
        return DangerSignals(
            ground_danger_zone=ground_danger,
            projectile_approaching=projectile,
            hp_drop_signal=hp_drop,
            boss_windup=boss_windup,
            stamina_critical=stamina_crit,
            overall_danger=overall,
        )

    def should_dodge(self, signals: DangerSignals) -> tuple[bool, str, int]:
        if signals.ground_danger_zone >= self._thresholds.ground_danger:
            return True, "ground_danger_zone", 0
        if signals.hp_drop_signal >= self._thresholds.hp_drop:
            return True, "hp_drop_signal", 0
        if signals.projectile_approaching >= self._thresholds.projectile:
            return True, "projectile_approaching", 1
        if signals.stamina_critical >= 1.0:
            return True, "stamina_critical", 1
        if signals.overall_danger >= self._thresholds.overall_dodge:
            best = self._dominant_signal(signals)
            priority = self.DODGE_PRIORITY.get(best, 2)
            return True, best, priority
        return False, "", 6

    def should_retreat(self, signals: DangerSignals) -> bool:
        return signals.overall_danger >= self._thresholds.overall_retreat

    def _detect_ground_danger(self, ground_roi: np.ndarray) -> float:
        if ground_roi.size == 0:
            return 0.0
        hsv = _bgr_to_hsv(ground_roi)
        h = hsv[:, :, 0]
        s = hsv[:, :, 1]
        v = hsv[:, :, 2]
        red_mask = ((h <= 18.0) | (h >= 342.0)) & (s >= 0.6) & (v >= 0.5)
        total_pixels = float(ground_roi.shape[0] * ground_roi.shape[1])
        if total_pixels == 0:
            return 0.0
        return _clamp(float(red_mask.sum()) / total_pixels)

    def _detect_projectile(self, frame: np.ndarray, prev_frame: np.ndarray) -> float:
        if frame.shape != prev_frame.shape:
            return 0.0
        diff = np.abs(frame.astype(np.int16) - prev_frame.astype(np.int16))
        gray_diff = diff.max(axis=2)
        motion_mask = gray_diff > 50
        hsv = _bgr_to_hsv(frame)
        bright_mask = hsv[:, :, 2] > 0.6
        combined = motion_mask & bright_mask
        total_pixels = float(frame.shape[0] * frame.shape[1])
        if total_pixels == 0:
            return 0.0
        return _clamp(float(combined.sum()) / total_pixels)

    def _detect_hp_drop(self, char_hp_roi: np.ndarray) -> float:
        current_hp = self._estimate_hp_ratio(char_hp_roi)
        drop = self._prev_char_hp - current_hp
        self._prev_char_hp = current_hp
        return _clamp(drop)

    def _detect_stamina(self, stamina_roi: np.ndarray) -> float:
        if stamina_roi.size == 0:
            return 0.0
        hsv = _bgr_to_hsv(stamina_roi)
        h = hsv[:, :, 0]
        s = hsv[:, :, 1]
        v = hsv[:, :, 2]
        yellow_mask = (h >= 15.0) & (h <= 65.0) & (s >= 0.4) & (v >= 0.6)
        total_pixels = float(stamina_roi.shape[0] * stamina_roi.shape[1])
        if total_pixels == 0:
            return 0.0
        ratio = float(yellow_mask.sum()) / total_pixels
        if ratio < self._thresholds.stamina_low:
            return 1.0
        return 0.0

    def _detect_boss_windup(
        self, frame: np.ndarray, prev_frame: np.ndarray | None
    ) -> float:
        """Detect boss wind-up by measuring bright saturated pixel area expansion."""
        if prev_frame is None:
            return 0.0
        if frame.shape != prev_frame.shape:
            return 0.0

        prev_bright = self._bright_saturated_area(prev_frame)
        curr_bright = self._bright_saturated_area(frame)

        if prev_bright < 1.0:
            # No significant bright area in previous frame — cannot measure growth.
            return 0.0

        growth = (curr_bright - prev_bright) / prev_bright
        if growth <= 0.30:
            return 0.0
        # Proportional score: 30% growth -> 0.0, 130% growth -> ~1.0
        score = (growth - 0.30) / 1.0
        return _clamp(score)

    @staticmethod
    def _bright_saturated_area(frame: np.ndarray) -> float:
        """Return count of bright, saturated pixels in *frame* (0-255 scale HSV)."""
        hsv = _bgr_to_hsv(frame)
        total_pixels = float(frame.shape[0] * frame.shape[1])
        if total_pixels == 0:
            return 0.0
        # The existing _bgr_to_hsv returns H:0-360 deg, S:0-1, V:0-1.
        # Bright & saturated: S >= 0.5 and V >= 0.6
        s = hsv[:, :, 1]
        v = hsv[:, :, 2]
        mask = (s >= 0.5) & (v >= 0.6)
        return float(mask.sum())

    def _estimate_hp_ratio(self, roi: np.ndarray) -> float:
        if roi.size == 0:
            return 1.0
        hsv = _bgr_to_hsv(roi)
        h = hsv[:, :, 0]
        s = hsv[:, :, 1]
        v = hsv[:, :, 2]
        green_mask = (h >= 35.0) & (h <= 130.0) & (s >= 0.2) & (v >= 0.2)
        red_mask = ((h <= 10.0) | (h >= 340.0)) & (s >= 0.2) & (v >= 0.2)
        hp_mask = green_mask | red_mask
        total_pixels = float(roi.shape[0] * roi.shape[1])
        if total_pixels == 0:
            return 1.0
        fill_ratio = float(hp_mask.sum()) / total_pixels
        if fill_ratio < 0.01:
            return 1.0
        return _clamp(fill_ratio)

    def _compute_overall_danger(self, signals: DangerSignals) -> float:
        weighted = (
            signals.ground_danger_zone * _DANGER_WEIGHTS["ground_danger_zone"]
            + signals.hp_drop_signal * _DANGER_WEIGHTS["hp_drop_signal"]
            + signals.projectile_approaching * _DANGER_WEIGHTS["projectile_approaching"]
            + signals.boss_windup * _DANGER_WEIGHTS["boss_windup"]
            + signals.stamina_critical * _DANGER_WEIGHTS["stamina_critical"]
        )
        return _clamp(weighted)

    @staticmethod
    def _dominant_signal(signals: DangerSignals) -> str:
        values = {
            "ground_danger_zone": signals.ground_danger_zone,
            "hp_drop_signal": signals.hp_drop_signal,
            "projectile_approaching": signals.projectile_approaching,
            "boss_windup": signals.boss_windup,
            "stamina_critical": signals.stamina_critical,
        }
        return max(values, key=values.get)

    @staticmethod
    def _crop(
        frame: np.ndarray,
        rois: dict[str, tuple[int, int, int, int]],
        key: str,
    ) -> np.ndarray:
        if key not in rois:
            return frame
        x1, y1, x2, y2 = rois[key]
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        return frame[y1:y2, x1:x2]


def _bgr_to_hsv(frame: np.ndarray) -> np.ndarray:
    bgr = frame.astype(np.float32) / 255.0
    b, g, r = bgr[:, :, 0], bgr[:, :, 1], bgr[:, :, 2]
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    delta = maxc - minc
    hue = np.zeros_like(maxc)
    nonzero = delta > 1e-6
    safe_delta = np.where(nonzero, delta, 1.0)
    hue = np.where((maxc == r) & nonzero, ((g - b) / safe_delta) % 6.0, hue)
    hue = np.where((maxc == g) & nonzero, ((b - r) / safe_delta) + 2.0, hue)
    hue = np.where((maxc == b) & nonzero, ((r - g) / safe_delta) + 4.0, hue)
    hue_deg = hue * 60.0
    saturation = np.divide(delta, maxc, out=np.zeros_like(delta), where=maxc > 1e-6)
    value = maxc
    hsv = np.stack([hue_deg, saturation, value], axis=-1)
    return hsv


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
