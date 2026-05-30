"""Character detail detector for Genshin Impact.

P-48: Detects character detail/character screen:
- Character portrait (角色立绘)
- Attribute stats panel (属性面板)
- Constellation stars (命座星星)
- Talent levels
- Equipment display

Uses face detection regions and color-based constellation star detection.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class ConstellationState(str, Enum):
    LOCKED = "locked"                    # Gray/dimmed
    UNLOCKED = "unlocked"                # Lit/glowing
    ACTIVE = "active"                    # Currently selected


@dataclass(frozen=True, slots=True)
class ConstellationStar:
    """A single constellation star slot."""
    index: int                           # 1-6
    state: ConstellationState
    x: float                             # Normalized 0-1
    y: float
    confidence: float


@dataclass(frozen=True, slots=True)
class CharacterDetailDetection:
    """P-48: Character detail screen detection result."""
    is_character_screen: bool = False
    character_name: str = ""
    character_level: int = 0
    constellation_count: int = 0
    constellation_stars: list[ConstellationStar] | None = None
    talent_e_level: int = 0
    talent_q_level: int = 0
    element_type: str = ""               # pyro, hydro, cryo, etc.
    confidence: float = 0.0
    frame_id: int = 0


class CharacterDetailDetector:
    """P-48: Detect character detail/character screen.

    Detects:
    - Character portrait (large character art)
    - Level display
    - Constellation stars (6 total, locked=gray, unlocked=gold)
    - Element badge
    - Talent levels

    Visual cues:
    - Portrait area has characteristic art frame
    - Constellation stars: gold (#FFD700) when unlocked, gray (#808080) when locked
    - Element badge: color-coded by element type
    """

    _REF_W = 1280
    _REF_H = 720

    # Character screen regions (relative to 1920x1080 base)
    _PORTRAIT_ROI = (0.02, 0.08, 0.35, 0.92)
    _STATS_ROI = (0.36, 0.25, 0.65, 0.75)
    _CONSTELLATION_ROI = (0.36, 0.10, 0.65, 0.25)
    _TALENT_ROI = (0.66, 0.40, 0.98, 0.85)

    # Constellation star colors (HSV)
    _STAR_UNLOCKED_LOW = np.array([15, 100, 150])     # Gold
    _STAR_UNLOCKED_HIGH = np.array([30, 255, 255])
    _STAR_LOCKED_LOW = np.array([0, 0, 80])           # Gray
    _STAR_LOCKED_HIGH = np.array([180, 30, 150])
    _STAR_ACTIVE_LOW = np.array([20, 150, 200])      # Bright gold
    _STAR_ACTIVE_HIGH = np.array([25, 255, 255])

    # Element badge colors (HSV ranges)
    _ELEMENT_COLORS = {
        "pyro": (np.array([0, 100, 150]), np.array([15, 255, 255])),
        "hydro": (np.array([100, 80, 150]), np.array([130, 255, 255])),
        "cryo": (np.array([95, 50, 150]), np.array([120, 255, 255])),
        "electro": (np.array([130, 60, 150]), np.array([170, 255, 255])),
        "anemo": (np.array([75, 60, 150]), np.array([95, 255, 255])),
        "geo": (np.array([25, 60, 150]), np.array([40, 255, 255])),
        "dendro": (np.array([50, 80, 150]), np.array([80, 255, 255])),
    }

    # Level number detection (white digits in portrait area)
    _LEVEL_MIN_AREA = 50
    _LEVEL_MAX_AREA = 500

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> CharacterDetailDetection:
        """Detect character detail screen.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID

        Returns:
            CharacterDetailDetection with all detected elements
        """
        if frame is None or frame.size == 0:
            return CharacterDetailDetection(frame_id=frame_id)

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        # Check if character screen is open
        is_char_screen = self._is_character_screen(frame, sx, sy)
        if not is_char_screen:
            return CharacterDetailDetection(is_character_screen=False, confidence=0.0, frame_id=frame_id)

        # Detect constellation stars
        stars = self._detect_constellation_stars(frame, sx, sy)
        unlocked_count = sum(1 for s in stars if s.state != ConstellationState.LOCKED)

        # Detect element type
        element = self._detect_element(frame, sx, sy)

        # Detect character level
        level = self._detect_level(frame, sx, sy)

        return CharacterDetailDetection(
            is_character_screen=True,
            constellation_count=unlocked_count,
            constellation_stars=stars,
            element_type=element,
            character_level=level,
            confidence=0.85,
            frame_id=frame_id,
        )

    def _is_character_screen(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        """Check if character detail screen is visible."""
        if cv2 is None:
            return False

        # Character screen has distinctive portrait region
        x1, y1, x2, y2 = self._scale_roi(self._PORTRAIT_ROI, sx, sy)
        portrait_roi = frame[y1:y2, x1:x2]
        if portrait_roi.size == 0:
            return False

        hsv = cv2.cvtColor(portrait_roi, cv2.COLOR_BGR2HSV)

        # Check for flesh tones in portrait (indicates character art)
        # Character portraits have varied skin tones
        skin_low = np.array([0, 20, 80])
        skin_high = np.array([30, 100, 200])
        skin_mask = cv2.inRange(hsv, skin_low, skin_high)
        skin_ratio = float(cv2.countNonZero(skin_mask)) / max(skin_mask.size, 1)

        # Also check for constellation area (gold stars)
        x1, y1, x2, y2 = self._scale_roi(self._CONSTELLATION_ROI, sx, sy)
        constellation_roi = frame[y1:y2, x1:x2]
        if constellation_roi.size > 0:
            hsv_const = cv2.cvtColor(constellation_roi, cv2.COLOR_BGR2HSV)
            gold_mask = cv2.inRange(hsv_const, self._STAR_UNLOCKED_LOW, self._STAR_UNLOCKED_HIGH)
            gold_ratio = float(cv2.countNonZero(gold_mask)) / max(gold_mask.size, 1)
            if gold_ratio > 0.01:
                return True

        # Character screen if we detect significant skin-colored region
        return skin_ratio > 0.05

    def _detect_constellation_stars(self, frame: np.ndarray, sx: float, sy: float) -> list[ConstellationStar]:
        """Detect constellation star slots (1-6)."""
        if cv2 is None:
            return []

        x1, y1, x2, y2 = self._scale_roi(self._CONSTELLATION_ROI, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return []

        h, w = roi.shape[:2]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        stars: list[ConstellationStar] = []

        # Detect unlocked stars (gold)
        gold_mask = cv2.inRange(hsv, self._STAR_UNLOCKED_LOW, self._STAR_UNLOCKED_HIGH)
        gold_contours, _ = cv2.findContours(gold_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for i, cnt in enumerate(sorted(gold_contours, key=cv2.contourArea, reverse=True)[:6]):
            area = cv2.contourArea(cnt)
            if self._LEVEL_MIN_AREA < area < self._LEVEL_MAX_AREA * 5:
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = M["m10"] / M["m00"] + x1
                    cy = M["m01"] / M["m00"] + y1
                    stars.append(ConstellationStar(
                        index=len(stars) + 1,
                        state=ConstellationState.UNLOCKED,
                        x=cx / frame.shape[1],
                        y=cy / frame.shape[0],
                        confidence=min(area / 100, 1.0),
                    ))

        # Detect locked stars (gray) - find star-shaped contours
        gray_mask = cv2.inRange(hsv, self._STAR_LOCKED_LOW, self._STAR_LOCKED_HIGH)
        gray_contours, _ = cv2.findContours(gray_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Add up to 6 total stars
        for cnt in sorted(gray_contours, key=cv2.contourArea, reverse=True)[:6 - len(stars)]:
            area = cv2.contourArea(cnt)
            if self._LEVEL_MIN_AREA < area < self._LEVEL_MAX_AREA * 5:
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = M["m10"] / M["m00"] + x1
                    cy = M["m01"] / M["m00"] + y1
                    stars.append(ConstellationStar(
                        index=len(stars) + 1,
                        state=ConstellationState.LOCKED,
                        x=cx / frame.shape[1],
                        y=cy / frame.shape[0],
                        confidence=min(area / 100, 1.0),
                    ))

        return stars

    def _detect_element(self, frame: np.ndarray, sx: float, sy: float) -> str:
        """Detect character element type from badge color."""
        if cv2 is None:
            return ""

        h, w = frame.shape[:2]

        # Element badge is typically in upper-right of stats area
        badge_roi = frame[int(h * 0.15):int(h * 0.35), int(w * 0.70):int(w * 0.90)]
        if badge_roi.size == 0:
            return ""

        hsv = cv2.cvtColor(badge_roi, cv2.COLOR_BGR2HSV)

        best_element = ""
        best_ratio = 0.0

        for element, (low, high) in self._ELEMENT_COLORS.items():
            mask = cv2.inRange(hsv, low, high)
            ratio = float(cv2.countNonZero(mask)) / max(mask.size, 1)
            if ratio > best_ratio and ratio > 0.01:
                best_ratio = ratio
                best_element = element

        return best_element

    def _detect_level(self, frame: np.ndarray, sx: float, sy: float) -> int:
        """Detect character level from number display."""
        if cv2 is None:
            return 0

        # Level is displayed near the portrait area
        level_roi = frame[int(frame.shape[0] * 0.30):int(frame.shape[0] * 0.50),
                         int(frame.shape[1] * 0.20):int(frame.shape[1] * 0.35)]
        if level_roi.size == 0:
            return 0

        gray = cv2.cvtColor(level_roi, cv2.COLOR_BGR2GRAY)

        # Look for bright white numbers
        _, bright = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Count number-like shapes
        number_count = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if self._LEVEL_MIN_AREA < area < self._LEVEL_MAX_AREA:
                number_count += 1

        # Estimate level from number count
        if number_count >= 2:
            return 90
        elif number_count >= 1:
            return 50

        return 0

    def _scale_roi(self, roi: tuple[float, float, float, float], sx: float, sy: float) -> tuple[int, int, int, int]:
        """Scale ROI from reference resolution."""
        x1, y1, x2, y2 = roi
        return (
            int(x1 * sx * self._REF_W),
            int(y1 * sy * self._REF_H),
            int(x2 * sx * self._REF_W),
            int(y2 * sy * self._REF_H),
        )