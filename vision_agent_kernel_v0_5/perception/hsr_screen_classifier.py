from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True, slots=True)
class HSRScreenState:
    state: str
    confidence: float
    indicators: dict[str, bool] = field(default_factory=dict)


class HSRScreenClassifier:
    """HSV-based heuristic screen classifier for Honkai: Star Rail."""

    _REF_W = 1920
    _REF_H = 1080

    def __init__(self) -> None:
        self._action_order_roi = (660, 880, 1260, 1080)
        self._sp_indicator_roi = (860, 920, 1060, 960)
        self._team_hp_roi = (100, 880, 400, 920)
        self._dialog_roi = (0, 700, 1920, 1080)
        self._loading_roi = (760, 440, 1160, 640)

    def classify(self, frame: np.ndarray) -> HSRScreenState:
        if frame is None or frame.size == 0:
            return HSRScreenState("unknown", 0.0)

        h, w = frame.shape[:2]
        scale_x = w / self._REF_W
        scale_y = h / self._REF_H

        # Check loading screen first (easiest to detect)
        loading = self._detect_loading(frame, scale_x, scale_y)
        if loading:
            return HSRScreenState("loading_screen", 0.95, {"loading": True})

        # Check combat (action order bar + SP indicator)
        combat_indicators = self._detect_combat(frame, scale_x, scale_y)
        if combat_indicators.get("action_order") and combat_indicators.get("sp_visible"):
            return HSRScreenState("turn_based_combat", 0.9, combat_indicators)

        # Check dialog
        dialog = self._detect_dialog(frame, scale_x, scale_y)
        if dialog:
            return HSRScreenState("dialog", 0.85, {"dialog_box": True})

        # Check map
        map_detected = self._detect_map(frame, scale_x, scale_y)
        if map_detected:
            return HSRScreenState("map_screen", 0.8, {"map_view": True})

        return HSRScreenState("overworld", 0.7, {"overworld": True})

    def _detect_combat(self, frame: np.ndarray, sx: float, sy: float) -> dict[str, bool]:
        indicators: dict[str, bool] = {}
        # Check action order bar region for yellow/white turn indicators
        x1, y1, x2, y2 = self._action_order_roi
        roi = frame[int(y1 * sy):int(y2 * sy), int(x1 * sx):int(x2 * sx)]
        if roi.size > 0:
            hsv = _to_hsv(roi)
            # Yellow-white range: H 0-30 or 170-180, S < 100, V > 150
            yellow_mask = (
                ((hsv[:, :, 0] < 30) | (hsv[:, :, 0] > 170)) &
                (hsv[:, :, 1] < 100) &
                (hsv[:, :, 2] > 150)
            )
            indicators["action_order"] = float(np.mean(yellow_mask)) > 0.15
        else:
            indicators["action_order"] = False

        # Check SP indicator region for cyan/blue dots
        x1, y1, x2, y2 = self._sp_indicator_roi
        roi = frame[int(y1 * sy):int(y2 * sy), int(x1 * sx):int(x2 * sx)]
        if roi.size > 0:
            hsv = _to_hsv(roi)
            cyan_mask = (
                (hsv[:, :, 0] >= 85) & (hsv[:, :, 0] <= 105) &
                (hsv[:, :, 1] > 100) &
                (hsv[:, :, 2] > 150)
            )
            indicators["sp_visible"] = float(np.mean(cyan_mask)) > 0.05
        else:
            indicators["sp_visible"] = False

        # Check team HP bars
        x1, y1, x2, y2 = self._team_hp_roi
        roi = frame[int(y1 * sy):int(y2 * sy), int(x1 * sx):int(x2 * sx)]
        if roi.size > 0:
            hsv = _to_hsv(roi)
            green_mask = (
                (hsv[:, :, 0] >= 35) & (hsv[:, :, 0] <= 85) &
                (hsv[:, :, 1] > 80) &
                (hsv[:, :, 2] > 100)
            )
            indicators["team_hp"] = float(np.mean(green_mask)) > 0.1
        else:
            indicators["team_hp"] = False

        return indicators

    def _detect_dialog(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        x1, y1, x2, y2 = self._dialog_roi
        roi = frame[int(y1 * sy):int(y2 * sy), int(x1 * sx):int(x2 * sx)]
        if roi.size == 0:
            return False
        gray = _to_gray(roi)
        # Dialog areas have semi-transparent overlay with text
        # Check for consistent dark overlay with high-variance text regions
        mean_val = np.mean(gray)
        std_val = np.std(gray)
        return mean_val < 120 and std_val > 30

    def _detect_map(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        # Map screen has distinct blue/green tinted background
        center_roi = frame[
            int(200 * sy):int(800 * sy),
            int(200 * sx):int(1600 * sx)
        ]
        if center_roi.size == 0:
            return False
        hsv = _to_hsv(center_roi)
        # Map background tends to be blue-green
        bg_mask = (
            (hsv[:, :, 0] >= 40) & (hsv[:, :, 0] <= 120) &
            (hsv[:, :, 1] > 30)
        )
        return float(np.mean(bg_mask)) > 0.3

    def _detect_loading(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        x1, y1, x2, y2 = self._loading_roi
        roi = frame[int(y1 * sy):int(y2 * sy), int(x1 * sx):int(x2 * sx)]
        if roi.size == 0:
            return False
        gray = _to_gray(roi)
        return np.mean(gray) < 15


def _to_hsv(roi: np.ndarray) -> np.ndarray:
    try:
        import cv2
        return cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    except ImportError:
        # Fallback: simple RGB to HSV approximation
        return _rgb_to_simple_hsv(roi)


def _to_gray(roi: np.ndarray) -> np.ndarray:
    if roi.ndim == 2:
        return roi
    return np.mean(roi, axis=2).astype(np.uint8)


def _rgb_to_simple_hsv(img: np.ndarray) -> np.ndarray:
    """Approximate HSV conversion without OpenCV."""
    rgb = img.astype(np.float32) / 255.0
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin

    h = np.zeros_like(r)
    mask = delta > 0
    # Simplified hue calculation
    h[mask & (cmax == r)] = 60 * (((g - b) / delta) % 6)[mask & (cmax == r)]
    h[mask & (cmax == g)] = 60 * (((b - r) / delta) + 2)[mask & (cmax == g)]
    h[mask & (cmax == b)] = 60 * (((r - g) / delta) + 4)[mask & (cmax == b)]
    h = h / 2  # Scale to 0-180 like OpenCV

    s = np.zeros_like(r)
    s[cmax > 0] = (delta[cmax > 0] / cmax[cmax > 0]) * 255

    v = cmax * 255

    result = np.stack([h, s, v], axis=2).astype(np.uint8)
    return result
