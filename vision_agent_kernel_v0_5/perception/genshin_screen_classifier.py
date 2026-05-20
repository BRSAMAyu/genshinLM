from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class ScreenState:
    state: str
    confidence: float
    indicators: dict[str, bool]


class GenshinScreenClassifier:
    """Classify Genshin Impact screen state using HSV/color analysis."""

    _REF_W = 1920
    _REF_H = 1080

    def __init__(self) -> None:
        self._minimap_roi = (0, 0, 220, 220)
        self._hp_bar_roi = (610, 970, 1310, 1010)
        self._skill_icon_roi = (1490, 940, 1890, 1070)
        self._dialog_roi = (0, 756, 1920, 1080)

    def classify(self, frame: np.ndarray) -> ScreenState:
        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        dark = self._is_dark_frame(frame)
        loading = self._detect_loading_screen(frame, dark)
        dialog = self._detect_dialog_box(frame, sx, sy)
        minimap = self._detect_minimap(frame, sx, sy)
        hp_bar = self._detect_hp_bar(frame, sx, sy)
        skill_icons = self._detect_skill_icons(frame, sx, sy)

        indicators: dict[str, bool] = {
            "dark_frame": bool(dark),
            "loading_screen": bool(loading),
            "dialog_box": bool(dialog),
            "minimap": bool(minimap),
            "hp_bar": bool(hp_bar),
            "skill_icons": bool(skill_icons),
        }

        if loading:
            return ScreenState(state="loading_screen", confidence=0.9, indicators=indicators)
        if dialog:
            return ScreenState(state="dialog", confidence=0.85, indicators=indicators)
        if minimap and hp_bar:
            return ScreenState(state="world_hud", confidence=0.9, indicators=indicators)
        if minimap:
            return ScreenState(state="world_hud", confidence=0.7, indicators=indicators)
        if hp_bar or skill_icons:
            return ScreenState(state="full_menu", confidence=0.6, indicators=indicators)
        if dark:
            return ScreenState(state="paimon_menu", confidence=0.5, indicators=indicators)
        return ScreenState(state="no_hud", confidence=0.6, indicators=indicators)

    def _detect_minimap(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        x1, y1, x2, y2 = self._scale_roi(self._minimap_roi, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=100,
            param1=50,
            param2=30,
            minRadius=20,
            maxRadius=int(min(x2 - x1, y2 - y1) / 2),
        )
        return circles is not None and len(circles) > 0

    def _detect_hp_bar(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        x1, y1, x2, y2 = self._scale_roi(self._hp_bar_roi, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        green_mask = cv2.inRange(hsv, (35, 80, 80), (85, 255, 255))
        red_mask_low = cv2.inRange(hsv, (0, 80, 80), (10, 255, 255))
        red_mask_high = cv2.inRange(hsv, (170, 80, 80), (180, 255, 255))
        yellow_mask = cv2.inRange(hsv, (20, 80, 80), (35, 255, 255))
        total = green_mask.sum() + red_mask_low.sum() + red_mask_high.sum() + yellow_mask.sum()
        threshold = roi.shape[0] * roi.shape[1] * 0.15
        return total > threshold

    def _detect_skill_icons(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        x1, y1, x2, y2 = self._scale_roi(self._skill_icon_roi, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        saturated_mask = (hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 100)
        ratio = saturated_mask.sum() / saturated_mask.size
        return ratio > 0.1

    def _detect_loading_screen(self, frame: np.ndarray, is_dark: bool) -> bool:
        if not is_dark:
            return False
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        std = float(np.std(gray))
        return std < 20.0

    def _detect_dialog_box(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        x1, y1, x2, y2 = self._scale_roi(self._dialog_roi, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
        mean_val = float(np.mean(gray))
        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(edges.sum()) / edges.size
        return 30.0 < mean_val < 160.0 and edge_density > 5.0

    def _is_dark_frame(self, frame: np.ndarray) -> bool:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        return float(np.mean(gray)) < 30.0

    @staticmethod
    def _scale_roi(
        roi: tuple[int, int, int, int], sx: float, sy: float
    ) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))
