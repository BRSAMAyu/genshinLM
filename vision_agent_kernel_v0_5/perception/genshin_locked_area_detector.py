"""Locked area detector for restricted zones in Inazuma.

Q-18: Detects locked/sealed areas like Ritou (离岛) and Kamisato Estate (神里屋敷).

These areas are blocked by Sealed Shutters (眼扉) that require special conditions
or story progression to unlock. Detection uses visual cues from locked UI elements.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


class LockedAreaState(str, Enum):
    UNLOCKED = "unlocked"
    LOCKED_SEALED = "locked_sealed"      # Eye shutter blocks entry
    LOCKED_STORY = "locked_story"        # Requires story progression
    LOCKED_TIME = "locked_time"          # Time-gated (e.g., quest not started)
    UNKNOWN = "unknown"


class LockedArea(str, Enum):
    RITOU = "ritou"                      #离岛 - main locked area in Inazuma
    KAMISATO_ESTATE = "kamisato_estate"  #神里屋敷 - Kamisato estate
    UPPER_WATERSHED = "upper_watershed"  #名椎滩 - near Ritou
    KOMORE_TEA_HOUSE = "komore_tea_house"# 木南居 - Narukami Island


@dataclass(frozen=True, slots=True)
class LockedAreaDetection:
    """Q-18: Detection result for locked area status."""
    area: LockedArea | None
    state: LockedAreaState
    shutter_detected: bool = False
    barrier_color: tuple[int, int, int] | None = None
    required_action: str = ""            # "complete_quest_X", "wait_for_time_gate", "progress_story"
    confidence: float = 0.0
    frame_id: int = 0


class LockedAreaDetector:
    """Q-18: Detect locked/sealed areas in Inazuma.

    Detects eye shutters (眼扉) blocking access to:
    - Ritou (离岛) - locked by Seirō (清�)
    - Kamisato Estate (神里屋敷) - requires Inazuma Archon Quest progress
    - Komore Tea House (木南居) - nighttime only access

    Visual indicators:
    - Red/blue barrier mesh overlay
    - Lock icon in minimap
    - Sealed shutter prompt
    """

    _REF_W = 1280
    _REF_H = 720

    # Eye shutter detection regions (scaled)
    _BARRIER_ROI = (0.2, 0.2, 0.8, 0.8)
    _DIALOG_ROI = (0.1, 0.6, 0.9, 0.9)

    # Color ranges for barriers (HSV)
    _SEALED_RED_LOW = np.array([0, 80, 80])
    _SEALED_RED_HIGH = np.array([10, 255, 255])
    _SEALED_BLUE_LOW = np.array([100, 60, 100])
    _SEALED_BLUE_HIGH = np.array([130, 255, 255])

    # Lock icon detection (grayscale intensity)
    _LOCK_ICON_MIN_AREA = 100
    _LOCK_ICON_MAX_AREA = 2000

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> LockedAreaDetection:
        """Detect locked area status from screen frame.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID for tracking

        Returns:
            LockedAreaDetection with area, state, and confidence
        """
        if frame is None or frame.size == 0:
            return LockedAreaDetection(None, LockedAreaState.UNKNOWN, False, None, "", 0.0, frame_id)

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        # Check for locked dialog (眼扉封锁 prompt)
        locked_dialog = self._detect_locked_dialog(frame, sx, sy)
        if locked_dialog:
            return self._parse_locked_dialog(frame, sx, sy, frame_id)

        # Check for barrier overlay (sealed shutter mesh)
        barrier_color, barrier_strength = self._detect_barrier(frame, sx, sy)
        if barrier_strength > 0.05:
            return LockedAreaDetection(
                area=self._infer_area_from_barrier(barrier_color),
                state=LockedAreaState.LOCKED_SEALED,
                shutter_detected=True,
                barrier_color=tuple(int(c) for c in barrier_color),
                required_action=self._get_unlock_action(barrier_color),
                confidence=min(barrier_strength * 10, 1.0),
                frame_id=frame_id,
            )

        # Check minimap for lock icon
        lock_detected = self._detect_lock_icon(frame, sx, sy)
        if lock_detected:
            return LockedAreaDetection(
                area=LockedArea.RITOU,  # Most common locked area
                state=LockedAreaState.LOCKED_STORY,
                shutter_detected=True,
                required_action="progress_inazuma_archon_quest",
                confidence=0.7,
                frame_id=frame_id,
            )

        # No lock detected - area is accessible
        return LockedAreaDetection(
            area=None,
            state=LockedAreaState.UNLOCKED,
            shutter_detected=False,
            required_action="",
            confidence=1.0,
            frame_id=frame_id,
        )

    def _detect_locked_dialog(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        """Detect locked area dialog prompt (眼扉封锁提示)."""
        if cv2 is None:
            return False

        x1, y1, x2, y2 = self._scale_roi(self._DIALOG_ROI, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        # Look for specific dark dialog box with lock text region
        # Locked dialogs have a distinctive semi-dark box
        dark_mask = gray < 80
        dark_ratio = float(np.sum(dark_mask)) / dark_mask.size

        # Lock text area should have medium brightness
        bright_text = (gray > 150) & (gray < 220)
        text_ratio = float(np.sum(bright_text)) / bright_text.size

        return 0.1 < dark_ratio < 0.4 and text_ratio > 0.02

    def _parse_locked_dialog(self, frame: np.ndarray, sx: float, sy: float, frame_id: int) -> LockedAreaDetection:
        """Parse locked dialog to determine required action."""
        # Default to Ritou lock if dialog detected
        # Could extend with OCR to get specific quest name
        return LockedAreaDetection(
            area=LockedArea.RITOU,
            state=LockedAreaState.LOCKED_STORY,
            shutter_detected=True,
            required_action="complete_seirou_quest_chain",
            confidence=0.75,
            frame_id=frame_id,
        )

    def _detect_barrier(self, frame: np.ndarray, sx: float, sy: float) -> tuple[tuple[int, int, int], float]:
        """Detect barrier mesh overlay color and strength."""
        if cv2 is None:
            return (0, 0, 0), 0.0

        x1, y1, x2, y2 = self._scale_roi(self._BARRIER_ROI, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return (0, 0, 0), 0.0

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Check for red barrier (sealed shutters)
        red_mask_low = cv2.inRange(hsv, self._SEALED_RED_LOW, self._SEALED_RED_HIGH)
        red_mask_high = cv2.inRange(hsv, np.array([170, 80, 80]), np.array([180, 255, 255]))
        red_mask = red_mask_low + red_mask_high
        red_ratio = float(cv2.countNonZero(red_mask)) / max(red_mask.size, 1)

        # Check for blue barrier (alt locked states)
        blue_mask = cv2.inRange(hsv, self._SEALED_BLUE_LOW, self._SEALED_BLUE_HIGH)
        blue_ratio = float(cv2.countNonZero(blue_mask)) / max(blue_mask.size, 1)

        if red_ratio > blue_ratio and red_ratio > 0.01:
            return (255, 50, 50), red_ratio
        elif blue_ratio > 0.01:
            return (50, 50, 255), blue_ratio

        return (0, 0, 0), 0.0

    def _detect_lock_icon(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        """Detect lock icon in minimap region."""
        if cv2 is None:
            return False

        # Minimap region (top-left-ish)
        minimap_roi = frame[0:int(frame.shape[0] * 0.25), 0:int(frame.shape[1] * 0.25)]
        if minimap_roi.size == 0:
            return False

        gray = cv2.cvtColor(minimap_roi, cv2.COLOR_BGR2GRAY)

        # Threshold for bright lock icon
        _, bright = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)

        # Find contours
        contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Check for lock-like shape (rectangular with small body)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if self._LOCK_ICON_MIN_AREA < area < self._LOCK_ICON_MAX_AREA:
                # Approximate to check lock shape
                x, y, w, h = cv2.boundingRect(cnt)
                aspect = float(w) / max(h, 1)
                # Lock icons are roughly square or slightly tall
                if 0.5 < aspect < 2.0:
                    return True

        return False

    def _infer_area_from_barrier(self, color: tuple[int, int, int]) -> LockedArea:
        """Infer which area is blocked based on barrier color."""
        if color[2] > 150:  # Red-dominant
            return LockedArea.RITOU
        elif color[0] > 150:  # Blue-dominant
            return LockedArea.KAMISATO_ESTATE
        return LockedArea.RITOU  # Default

    def _get_unlock_action(self, color: tuple[int, int, int]) -> str:
        """Get required action to unlock based on barrier color."""
        if color[2] > 150:  # Red - Seirō quest
            return "complete_seirou_quest_chain"
        elif color[0] > 150:  # Blue - Story progression
            return "progress_inazuma_archon_quest"
        return "progress_story"

    def _scale_roi(self, roi: tuple[float, float, float, float], sx: float, sy: float) -> tuple[int, int, int, int]:
        """Scale ROI from reference resolution."""
        x1, y1, x2, y2 = roi
        return (
            int(x1 * sx * self._REF_W),
            int(y1 * sy * self._REF_H),
            int(x2 * sx * self._REF_W),
            int(y2 * sy * self._REF_H),
        )