"""Timer OCR reader for timed challenges.

Q-23: Reads countdown timers from limited-time challenge screens.
Used for combat trials, treasure restoration puzzles, and escape sequences.

OCR-based extraction with fallback to color-based detection.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TimerReading:
    """Q-23: Timer OCR result."""
    time_remaining_sec: float
    time_display: str = ""              # Raw display string "MM:SS"
    is_critical: bool = False           # < 30 seconds
    is_warning: bool = False            # < 60 seconds
    confidence: float = 0.0
    frame_id: int = 0
    source: Literal["ocr", "color", "none"] = "none"


class TimerOcrReader:
    """Q-23: Read countdown timers from timed challenge UI.

    Supports:
    - Combat trial timers (e.g., "02:30" countdown)
    - Treasure restoration time limits
    - Escape sequence countdowns
    - Domain challenge timers

    Primary method: OCR with mcp__zai-mcp-server__extract_text_from_screenshot fallback
    Secondary: Color-based detection for emergency/critical states
    """

    _REF_W = 1280
    _REF_H = 720

    # Timer ROI (top-center of screen for combat trials)
    _TIMER_ROI = (0.35, 0.05, 0.65, 0.18)

    # Color thresholds for timer digits
    _CRITICAL_RED_LOW = np.array([0, 150, 150])
    _CRITICAL_RED_HIGH = np.array([10, 255, 255])
    _WARNING_YELLOW_LOW = np.array([15, 100, 150])
    _WARNING_YELLOW_HIGH = np.array([35, 255, 255])
    _NORMAL_GREEN_LOW = np.array([40, 80, 100])
    _NORMAL_GREEN_HIGH = np.array([85, 255, 255])

    # Timer text patterns
    _TIMER_PATTERN = re.compile(r"(\d{1,2}):(\d{2})")
    _TIMER_SECONDS_PATTERN = re.compile(r"^(\d+)$")

    def __init__(self, ocr_provider=None) -> None:
        """Initialize timer OCR reader.

        Args:
            ocr_provider: Optional OCR provider for text extraction.
                         If None, uses color-based fallback detection.
        """
        self._ocr = ocr_provider
        self._last_reading: TimerReading | None = None
        self._consecutive_fails = 0

    def read_timer(self, frame: np.ndarray, frame_id: int = 0) -> TimerReading:
        """Read timer from screen frame.

        Try OCR first, fallback to color detection.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID

        Returns:
            TimerReading with time remaining and confidence
        """
        # Try OCR-based extraction first
        if self._ocr is not None:
            ocr_result = self._try_ocr(frame, frame_id)
            if ocr_result is not None:
                self._last_reading = ocr_result
                self._consecutive_fails = 0
                return ocr_result

        # Fallback to color-based detection
        color_result = self._color_detect_timer(frame, frame_id)
        if color_result.source != "none":
            self._last_reading = color_result
            self._consecutive_fails = 0
            return color_result

        # No timer detected
        self._consecutive_fails += 1
        return TimerReading(
            time_remaining_sec=0.0,
            is_critical=False,
            is_warning=False,
            confidence=0.0,
            frame_id=frame_id,
            source="none",
        )

    def _try_ocr(self, frame: np.ndarray, frame_id: int) -> TimerReading | None:
        """Try OCR-based timer extraction."""
        if self._ocr is None:
            return None

        # Crop timer region
        timer_roi = self._get_timer_roi(frame)
        if timer_roi.size == 0:
            return None

        # Use OCR provider
        try:
            text = self._ocr.extract_text(timer_roi, lang="eng+chi_sim")
            return self._parse_ocr_text(text, frame_id)
        except Exception as exc:
            log.debug("[TimerOcrReader] OCR failed: %s", exc)
            return None

    def _parse_ocr_text(self, text: str, frame_id: int) -> TimerReading | None:
        """Parse OCR text to extract timer value."""
        # Try MM:SS format
        match = self._TIMER_PATTERN.search(text)
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            total_sec = minutes * 60 + seconds
            return TimerReading(
                time_remaining_sec=float(total_sec),
                time_display=f"{minutes:02d}:{seconds:02d}",
                is_critical=total_sec < 30,
                is_warning=total_sec < 60,
                confidence=0.9,
                frame_id=frame_id,
                source="ocr",
            )

        # Try plain seconds
        for line in text.split("\n"):
            match = self._TIMER_SECONDS_PATTERN.match(line.strip())
            if match:
                seconds = int(match.group(1))
                return TimerReading(
                    time_remaining_sec=float(seconds),
                    time_display=f"{seconds}s",
                    is_critical=seconds < 30,
                    is_warning=seconds < 60,
                    confidence=0.8,
                    frame_id=frame_id,
                    source="ocr",
                )

        return None

    def _color_detect_timer(self, frame: np.ndarray, frame_id: int) -> TimerReading:
        """Fallback: Detect timer state via color analysis.

        Cannot get exact time, but can determine:
        - Critical state (bright red timer)
        - Warning state (yellow timer)
        - Normal state (green timer)
        - No timer visible
        """
        if cv2 is None:
            return TimerReading(0.0, "", False, False, 0.0, frame_id, "none")

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._TIMER_ROI, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return TimerReading(0.0, "", False, False, 0.0, frame_id, "none")

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Check for critical red
        red_low = cv2.inRange(hsv, self._CRITICAL_RED_LOW, self._CRITICAL_RED_HIGH)
        red_high = cv2.inRange(hsv, np.array([170, 150, 150]), self._CRITICAL_RED_HIGH)
        red_ratio = (float(cv2.countNonZero(red_low)) + float(cv2.countNonZero(red_high))) / max(red_low.size, 1)

        # Check for warning yellow
        yellow_mask = cv2.inRange(hsv, self._WARNING_YELLOW_LOW, self._WARNING_YELLOW_HIGH)
        yellow_ratio = float(cv2.countNonZero(yellow_mask)) / max(yellow_mask.size, 1)

        # Check for normal green
        green_mask = cv2.inRange(hsv, self._NORMAL_GREEN_LOW, self._NORMAL_GREEN_HIGH)
        green_ratio = float(cv2.countNonZero(green_mask)) / max(green_mask.size, 1)

        # Estimate time based on last known state
        last_time = self._last_reading.time_remaining_sec if self._last_reading else 300.0

        if red_ratio > 0.02:
            # Critical - likely < 30 seconds
            confidence = min(red_ratio * 20, 1.0)
            return TimerReading(
                time_remaining_sec=min(last_time, 30),
                is_critical=True,
                is_warning=False,
                confidence=confidence,
                frame_id=frame_id,
                source="color",
            )

        if yellow_ratio > 0.02:
            # Warning - likely < 60 seconds
            confidence = min(yellow_ratio * 20, 1.0)
            return TimerReading(
                time_remaining_sec=min(last_time, 60),
                is_critical=False,
                is_warning=True,
                confidence=confidence,
                frame_id=frame_id,
                source="color",
            )

        if green_ratio > 0.02:
            # Normal timer state
            confidence = min(green_ratio * 20, 1.0)
            return TimerReading(
                time_remaining_sec=last_time,  # Keep last known time
                is_critical=False,
                is_warning=False,
                confidence=confidence,
                frame_id=frame_id,
                source="color",
            )

        return TimerReading(0.0, "", False, False, 0.0, frame_id, "none")

    def _get_timer_roi(self, frame: np.ndarray) -> np.ndarray:
        """Extract timer region for OCR."""
        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H
        x1, y1, x2, y2 = self._scale_roi(self._TIMER_ROI, sx, sy)
        return frame[y1:y2, x1:x2]

    def _scale_roi(self, roi: tuple[float, float, float, float], sx: float, sy: float) -> tuple[int, int, int, int]:
        """Scale ROI from reference resolution."""
        x1, y1, x2, y2 = roi
        return (
            int(x1 * sx * self._REF_W),
            int(y1 * sy * self._REF_H),
            int(x2 * sx * self._REF_W),
            int(y2 * sy * self._REF_H),
        )