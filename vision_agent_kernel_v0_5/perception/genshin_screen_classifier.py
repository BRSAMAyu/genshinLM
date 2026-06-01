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
        self._letterbox_top_roi = (0, 0, 1920, 60)
        self._letterbox_bottom_roi = (0, 1020, 1920, 1080)
        self._skip_button_roi = (1650, 900, 1900, 1000)
        self._history: list[str] = []

    def classify(self, frame: np.ndarray) -> ScreenState:
        if cv2 is None:
            return ScreenState(state="unknown", confidence=0.1, indicators={})
        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        gray_full = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        overall_mean = float(np.mean(gray_full))

        dark = self._is_dark_frame(frame)
        death = self._detect_death_screen(frame, sx, sy)
        loading = self._detect_loading_screen(frame, dark)
        dialog = self._detect_dialog_box(frame, sx, sy, overall_mean)
        domain = self._detect_domain_entrance(frame, sx, sy)
        minimap = self._detect_minimap(frame, sx, sy, overall_mean)
        hp_bar, hp_red_ratio = self._detect_hp_bar(frame, sx, sy, overall_mean)
        skill_icons = self._detect_skill_icons(frame, sx, sy, overall_mean)
        combat = self._detect_combat_indicator(frame, sx, sy)
        notification = self._detect_notification(frame, sx, sy)
        cutscene = self._detect_cutscene(frame, sx, sy, minimap, hp_bar)

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
            "cutscene": bool(cutscene),
        }

        # Determine raw classified state
        if death:
            raw_state = "death_screen"
            conf = 0.9
        elif loading:
            raw_state = "loading_screen"
            conf = 0.9
        elif cutscene:
            raw_state = "cutscene"
            conf = 0.8
        elif dialog:
            raw_state = "dialog"
            conf = 0.85
        elif domain:
            raw_state = "domain_entrance"
            conf = 0.85
        elif minimap and hp_bar and (combat or hp_red_ratio > 0.3):
            raw_state = "combat"
            conf = 0.85
        elif minimap and hp_bar:
            raw_state = "world_hud"
            conf = 0.9
        elif minimap:
            raw_state = "world_hud"
            conf = 0.7
        elif notification:
            raw_state = "notification"
            conf = 0.8
        elif hp_bar or skill_icons:
            raw_state = "full_menu"
            conf = 0.6
        elif dark:
            raw_state = "paimon_menu"
            conf = 0.5
        else:
            raw_state = "no_hud"
            conf = 0.6

        # Intermittent blank/flash frame filter (Gap 16):
        # If raw_state is loading_screen or no_hud but recent history is solidly overworld/combat/dialog,
        # smooth the state to the previous healthy state.
        filtered_state = raw_state
        if raw_state in ("loading_screen", "no_hud") and len(self._history) >= 2:
            recent = self._history[-2:]
            if all(s in ("world_hud", "combat", "dialog") for s in recent):
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
                std = float(np.std(gray))
                mean = float(np.mean(gray))
                # Confirm it is an extremely flat frame (DirectX blackout std < 5.0 or flash mean > 250.0)
                if std < 5.0 or mean > 250.0:
                    filtered_state = self._history[-1]
                    conf = 0.95

        self._history.append(filtered_state)
        if len(self._history) > 10:
            self._history.pop(0)

        return ScreenState(state=filtered_state, confidence=conf, indicators=indicators)

    def _detect_minimap(self, frame: np.ndarray, sx: float, sy: float, overall_mean: float | None = None) -> bool:
        x1, y1, x2, y2 = self._scale_roi(self._minimap_roi, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Apply dynamic contrast stretching to combat glare/low contrast under extreme lighting
        if overall_mean is not None and (overall_mean < 80.0 or overall_mean > 180.0):
            min_val, max_val, _, _ = cv2.minMaxLoc(blurred)
            if max_val - min_val > 10.0:
                blurred = np.uint8((blurred - min_val) * (255.0 / (max_val - min_val)))

        # Relax param2 slightly in dark or glare environments for circle detection stability
        param2 = 30
        if overall_mean is not None and (overall_mean < 80.0 or overall_mean > 180.0):
            param2 = 20

        circles = cv2.HOUGH_GRADIENT if cv2 is not None else 3  # type: ignore
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=100,
            param1=50,
            param2=param2,
            minRadius=20,
            maxRadius=int(min(x2 - x1, y2 - y1) / 2),
        )
        return circles is not None and len(circles) > 0

    def _detect_hp_bar(self, frame: np.ndarray, sx: float, sy: float, overall_mean: float | None = None) -> tuple[bool, float]:
        """Detect HP bar and return (detected, red_ratio)."""
        x1, y1, x2, y2 = self._scale_roi(self._hp_bar_roi, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False, 0.0
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Adaptive HSV limits for HP bar under dynamic lighting
        lower_sat = 80
        lower_val = 80
        if overall_mean is not None:
            if overall_mean < 80.0:
                lower_sat = 40
                lower_val = 40
            elif overall_mean > 200.0:
                lower_sat = 50

        green_mask = cv2.inRange(hsv, (35, lower_sat, lower_val), (85, 255, 255))
        red_mask_low = cv2.inRange(hsv, (0, lower_sat, lower_val), (10, 255, 255))
        red_mask_high = cv2.inRange(hsv, (170, lower_sat, lower_val), (180, 255, 255))
        yellow_mask = cv2.inRange(hsv, (20, lower_sat, lower_val), (35, 255, 255))
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

    def _detect_skill_icons(self, frame: np.ndarray, sx: float, sy: float, overall_mean: float | None = None) -> bool:
        x1, y1, x2, y2 = self._scale_roi(self._skill_icon_roi, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        sat_thresh = 100
        val_thresh = 100
        if overall_mean is not None:
            if overall_mean < 80.0:
                sat_thresh = 60
                val_thresh = 60
            elif overall_mean > 200.0:
                sat_thresh = 70

        saturated_mask = (hsv[:, :, 1] > sat_thresh) & (hsv[:, :, 2] > val_thresh)
        ratio = saturated_mask.sum() / saturated_mask.size
        return ratio > 0.1

    def _detect_loading_screen(self, frame: np.ndarray, is_dark: bool) -> bool:
        if not is_dark:
            return False
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        std = float(np.std(gray))
        return std < 20.0

    def _detect_dialog_box(self, frame: np.ndarray, sx: float, sy: float, overall_mean: float | None = None) -> bool:
        x1, y1, x2, y2 = self._scale_roi(self._dialog_roi, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
        mean_val = float(np.mean(gray))
        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(edges.sum()) / edges.size

        # Adaptive dialog detection thresholds based on overall screen brightness to accommodate bleed-through
        min_mean = 30.0
        max_mean = 140.0
        if overall_mean is not None:
            if overall_mean < 80.0:
                min_mean = max(15.0, 30.0 - (80.0 - overall_mean) * 0.25)
            elif overall_mean > 180.0:
                max_mean = min(180.0, 140.0 + (overall_mean - 180.0) * 0.4)

        return min_mean < mean_val < max_mean and edge_density > 15.0

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

    def _detect_cutscene(
        self, frame: np.ndarray, sx: float, sy: float,
        has_minimap: bool, has_hp: bool,
    ) -> bool:
        """Detect cinematic cutscene: letterbox bars, no HUD, skip button."""
        # Must have no minimap and no HP bar (cinematic hides HUD)
        if has_minimap or has_hp:
            return False
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        overall_std = float(np.std(gray))
        # Reject uniform frames (solid color, all-white, all-black)
        if overall_std < 30.0:
            return False
        h, w = frame.shape[:2]
        # Check for letterbox (top + bottom black bars)
        x1t, y1t, x2t, y2t = self._scale_roi(self._letterbox_top_roi, sx, sy)
        top_bar = gray[y1t:y2t, x1t:x2t]
        x1b, y1b, x2b, y2b = self._scale_roi(self._letterbox_bottom_roi, sx, sy)
        bot_bar = gray[y1b:y2b, x1b:x2b]
        if top_bar.size > 0 and bot_bar.size > 0:
            top_dark = float(np.mean(top_bar)) < 30.0
            bot_dark = float(np.mean(bot_bar)) < 30.0
            if top_dark and bot_dark:
                return True
        # Alternative: check for skip button even without letterbox
        x1s, y1s, x2s, y2s = self._scale_roi(self._skip_button_roi, sx, sy)
        skip_roi = frame[y1s:y2s, x1s:x2s]
        if skip_roi.size == 0:
            return False
        hsv = cv2.cvtColor(skip_roi, cv2.COLOR_BGR2HSV)
        # Skip button: bright white/blue text on dark
        bright_mask = cv2.inRange(hsv, (0, 0, 200), (180, 30, 255))
        bright_ratio = float(np.count_nonzero(bright_mask)) / bright_mask.size
        return bright_ratio > 0.05

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
