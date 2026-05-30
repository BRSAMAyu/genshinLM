"""E-42: Mangrove/Mangrowth (芒荒) mechanism detector for Natlan.

Detects Mangrove (芒) and Wilderness (荒) state indicators.
In Natlan's coliseum areas, torches switch between these two states,
requiring specific elements to activate.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


class MangrowthState(str, Enum):
    MAN = "man"      # Bright state (芒)
    HUANG = "huang"  # Dark state (荒)
    NEUTRAL = "neutral"
    TRANSITIONING = "transitioning"


@dataclass(frozen=True, slots=True)
class MangrowthIndicator:
    """Single Mangrowth indicator detection."""
    position: tuple[int, int]
    state: MangrowthState
    confidence: float


@dataclass(frozen=True, slots=True)
class MangrowthDetection:
    """Result of mangrowth mechanism detection."""
    indicators: list[MangrowthIndicator]
    dominant_state: MangrowthState
    requires_element: str | None  # "electro", "pyro", etc.
    all_synced: bool  # All indicators in same state
    confidence: float


class MangrowthDetector:
    """Detect Mangrowth (芒荒) mechanism state in Natlan."""

    _REF_W = 1920
    _REF_H = 1080

    # Bright (芒) indicator - yellow/golden glow
    _MAN_COLOR_LOW = np.array([20, 150, 150], dtype=np.uint8)
    _MAN_COLOR_HIGH = np.array([35, 255, 255], dtype=np.uint8)

    # Dark (荒) indicator - purple/dark glow
    _HUANG_COLOR_LOW = np.array([130, 50, 50], dtype=np.uint8)
    _HUANG_COLOR_HIGH = np.array([170, 150, 150], dtype=np.uint8)

    # Scan center area (where coliseum mechanisms usually appear)
    _SCAN_ROI = (400, 200, 1520, 880)

    def __init__(self) -> None:
        self._last_state: MangrowthState = MangrowthState.NEUTRAL
        self._state_history: list[MangrowthState] = []

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> MangrowthDetection:
        """Detect Mangrowth mechanism state.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            MangrowthDetection with state information
        """
        if cv2 is None:
            return MangrowthDetection(
                indicators=[],
                dominant_state=MangrowthState.NEUTRAL,
                requires_element=None,
                all_synced=False,
                confidence=0.0,
            )

        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._SCAN_ROI, sx, sy)
        scan_region = frame[y1:y2, x1:x2]

        if scan_region.size == 0:
            return MangrowthDetection(
                indicators=[],
                dominant_state=self._last_state,
                requires_element=None,
                all_synced=False,
                confidence=0.3,
            )

        hsv = cv2.cvtColor(scan_region, cv2.COLOR_BGR2HSV)

        # Detect bright (芒) indicators
        man_mask = cv2.inRange(hsv, self._MAN_COLOR_LOW, self._MAN_COLOR_HIGH)
        man_contours, _ = cv2.findContours(man_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Detect dark (荒) indicators
        huang_mask = cv2.inRange(hsv, self._HUANG_COLOR_LOW, self._HUANG_COLOR_HIGH)
        huang_contours, _ = cv2.findContours(huang_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Process bright indicators
        man_indicators = self._process_contours(man_contours, MangrowthState.MAN, x1, y1)

        # Process dark indicators
        huang_indicators = self._process_contours(huang_contours, MangrowthState.HUANG, x1, y1)

        all_indicators = man_indicators + huang_indicators

        if not all_indicators:
            return MangrowthDetection(
                indicators=[],
                dominant_state=MangrowthState.NEUTRAL,
                requires_element=None,
                all_synced=False,
                confidence=0.0,
            )

        # Determine dominant state
        man_count = len(man_indicators)
        huang_count = len(huang_indicators)

        if man_count > huang_count:
            dominant = MangrowthState.MAN
            requires_element = "electro"  # Electro activates bright state
        elif huang_count > man_count:
            dominant = MangrowthState.HUANG
            requires_element = "pyro"  # Pyro activates dark state
        else:
            dominant = MangrowthState.NEUTRAL
            requires_element = None

        # Check if all synchronized
        all_synced = all(ind.state == all_indicators[0].state for ind in all_indicators)

        # Calculate confidence
        confidence = min(0.9, 0.5 + len(all_indicators) * 0.1)

        self._last_state = dominant
        self._state_history.append(dominant)
        if len(self._state_history) > 10:
            self._state_history.pop(0)

        return MangrowthDetection(
            indicators=all_indicators,
            dominant_state=dominant,
            requires_element=requires_element,
            all_synced=all_synced,
            confidence=confidence,
        )

    def _process_contours(
        self,
        contours,
        state: MangrowthState,
        offset_x: int,
        offset_y: int,
    ) -> list[MangrowthIndicator]:
        """Process contours into indicators."""
        indicators = []

        for contour in contours:
            area = cv2.contourArea(contour)
            if 50 < area < 5000:  # Reasonable indicator size
                M = cv2.moments(contour)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"]) + offset_x
                    cy = int(M["m01"] / M["m00"]) + offset_y
                    confidence = min(0.9, area / 1000)

                    indicators.append(MangrowthIndicator(
                        position=(cx, cy),
                        state=state,
                        confidence=confidence,
                    ))

        return indicators

    def get_activation_element(self, detection: MangrowthDetection) -> str | None:
        """Get element needed to activate mechanism."""
        return detection.requires_element

    def is_synchronized(self, detection: MangrowthDetection) -> bool:
        """Check if mechanism is in synchronized state."""
        return detection.all_synced

    def _scale_roi(self, roi: tuple[int, int, int, int], sx: float, sy: float) -> tuple[int, int, int, int]:
        """Scale ROI by resolution multiplier."""
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))