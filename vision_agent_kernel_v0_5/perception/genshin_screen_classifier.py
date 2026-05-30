from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


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
        self._combat_indicator_roi = (770, 930, 850, 970)
        self._death_roi = (660, 400, 1260, 680)
        self._notification_roi = (1400, 100, 1900, 500)

    def classify(self, frame: np.ndarray) -> ScreenState:
        if cv2 is None:
            return ScreenState(state="unknown", confidence=0.1, indicators={})
        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        dark = self._is_dark_frame(frame)
        death = self._detect_death_screen(frame, sx, sy)
        loading = self._detect_loading_screen(frame, dark)
        dialog = self._detect_dialog_box(frame, sx, sy)
        domain = self._detect_domain_entrance(frame, sx, sy)
        minimap = self._detect_minimap(frame, sx, sy)
        hp_bar, hp_red_ratio = self._detect_hp_bar(frame, sx, sy)
        skill_icons = self._detect_skill_icons(frame, sx, sy)
        combat = self._detect_combat_indicator(frame, sx, sy)
        notification = self._detect_notification(frame, sx, sy)

        indicators: dict[str, bool] = {
            "dark_frame": bool(dark),
            "death_screen": bool(death),
            "loading_screen": bool(loading),
            "dialog_box": bool(dialog),
            "domain_entrance": bool(domain),
            "minimap": bool(minimap),
            "hp_bar": bool(hp_bar),
            "skill_icons": bool(skill_icons),
            "combat": bool(combat),
            "notification": bool(notification),
        }

        # Death screen: checked before loading since both are dark but death has buttons
        if death:
            return ScreenState(state="death_screen", confidence=0.9, indicators=indicators)
        if loading:
            return ScreenState(state="loading_screen", confidence=0.9, indicators=indicators)
        if dialog:
            return ScreenState(state="dialog", confidence=0.85, indicators=indicators)
        if domain:
            return ScreenState(state="domain_entrance", confidence=0.85, indicators=indicators)
        # Combat: minimap + HP bar + red HP damage or combat indicator
        if minimap and hp_bar and (combat or hp_red_ratio > 0.3):
            return ScreenState(state="combat", confidence=0.85, indicators=indicators)
        if minimap and hp_bar:
            return ScreenState(state="world_hud", confidence=0.9, indicators=indicators)
        if minimap:
            return ScreenState(state="world_hud", confidence=0.7, indicators=indicators)
        # Notification: overlaid on HUD, check before no_hud
        if notification:
            return ScreenState(state="notification", confidence=0.8, indicators=indicators)
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

    def _detect_hp_bar(self, frame: np.ndarray, sx: float, sy: float) -> tuple[bool, float]:
        """Detect HP bar and return (detected, red_ratio)."""
        x1, y1, x2, y2 = self._scale_roi(self._hp_bar_roi, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False, 0.0
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        green_mask = cv2.inRange(hsv, (35, 80, 80), (85, 255, 255))
        red_mask_low = cv2.inRange(hsv, (0, 80, 80), (10, 255, 255))
        red_mask_high = cv2.inRange(hsv, (170, 80, 80), (180, 255, 255))
        yellow_mask = cv2.inRange(hsv, (20, 80, 80), (35, 255, 255))
        pixel_count = roi.shape[0] * roi.shape[1]
        green_px = np.count_nonzero(green_mask)
        red_px = np.count_nonzero(red_mask_low) + np.count_nonzero(red_mask_high)
        yellow_px = np.count_nonzero(yellow_mask)
        total_hp_px = green_px + red_px + yellow_px
        has_hp = total_hp_px > pixel_count * 0.05
        red_ratio = red_px / max(total_hp_px, 1)
        return has_hp, red_ratio

    def _detect_combat_indicator(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        """Detect combat indicator (red flash / damage numbers near HP bar)."""
        x1, y1, x2, y2 = self._scale_roi(self._combat_indicator_roi, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        red_mask = cv2.inRange(hsv, (0, 120, 120), (10, 255, 255)) | cv2.inRange(hsv, (170, 120, 120), (180, 255, 255))
        return np.count_nonzero(red_mask) > roi.shape[0] * roi.shape[1] * 0.2

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
        # Tightened thresholds: mean 30-140 (was 30-160), edge_density > 15 (was > 5)
        return 30.0 < mean_val < 140.0 and edge_density > 15.0

    def _is_dark_frame(self, frame: np.ndarray) -> bool:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        return float(np.mean(gray)) < 30.0

    def _detect_death_screen(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        """Detect death screen: gray tones with bright buttons in center, no minimap."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        gray_mean = float(np.mean(gray))
        # Death screen has moderate brightness (not fully dark, not bright)
        if gray_mean < 80 or gray_mean > 160:
            return False
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV) if frame.ndim == 3 else None
        if hsv is None:
            return False
        # Check for low saturation (gray tone) in a large portion of the frame
        low_sat_mask = hsv[:, :, 1] < 40
        if float(np.mean(low_sat_mask)) < 0.5:
            return False
        # Check for bright spots in death ROI (buttons)
        x1, y1, x2, y2 = self._scale_roi(self._death_roi, sx, sy)
        death_roi = gray[y1:y2, x1:x2]
        if death_roi.size == 0:
            return False
        bright_mask = death_roi > 200
        bright_ratio = float(np.sum(bright_mask)) / bright_mask.size
        if bright_ratio < 0.01:
            return False
        # Confirm no minimap present
        minimap = self._detect_minimap(frame, sx, sy)
        return not minimap

    def _detect_notification(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        """Detect notification overlay: bright text on right side of screen."""
        x1, y1, x2, y2 = self._scale_roi(self._notification_roi, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
        # Look for bright pixels (>200) in narrow vertical strips
        bright_mask = gray > 200
        if bright_mask.size == 0:
            return False
        bright_ratio = float(np.sum(bright_mask)) / bright_mask.size
        # Notifications have a modest concentration of bright text on semi-dark bg.
        # All-white/all-bright frames should not trigger.
        if bright_ratio > 0.7:
            return False
        # Check for contrast: notifications have both dark and bright pixels
        dark_mask = gray < 60
        if float(np.sum(dark_mask)) / dark_mask.size < 0.1:
            return False
        return bright_ratio > 0.05

    def _detect_domain_entrance(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        """Detect domain entrance: dark background with bright 'Start' button in center."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        overall_mean = float(np.mean(gray))
        # Domain entrance has a dark background
        if overall_mean > 80:
            return False
        # Check for bright spot in the center (Start button area)
        cx1 = int(frame.shape[1] * 0.35)
        cy1 = int(frame.shape[0] * 0.45)
        cx2 = int(frame.shape[1] * 0.65)
        cy2 = int(frame.shape[0] * 0.65)
        center_roi = gray[cy1:cy2, cx1:cx2]
        if center_roi.size == 0:
            return False
        bright_mask = center_roi > 200
        bright_ratio = float(np.sum(bright_mask)) / bright_mask.size
        if bright_ratio < 0.005:
            return False
        # Confirm no minimap
        minimap = self._detect_minimap(frame, sx, sy)
        return not minimap

    @staticmethod
    def _scale_roi(
        roi: tuple[int, int, int, int], sx: float, sy: float,
    ) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))
