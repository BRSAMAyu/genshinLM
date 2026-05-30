"""Hangout affinity OCR reader for Genshin Impact relationship events.

P-57: Reads hangout affinity levels from character hangout screens.
Parses heart icons and percentage display for relationship progress.

Visual elements:
- Heart icons (filled/empty) for affinity level
- Percentage text "75%" or "好感度 +15"
- Character portrait
- "邀约" / "Hangout" banner
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AffinityReading:
    """P-57: Hangout affinity OCR result."""
    level: int                         # Affinity level (1-10)
    percentage: float                  # Progress to next level (0.0-1.0)
    total_hearts: int                 # Total hearts displayed
    filled_hearts: int                # Filled hearts
    display_string: str               # Raw "75%" or "3/10" format
    character_name: str | None        # Detected character
    confidence: float
    frame_id: int
    source: Literal["ocr", "hearts", "none"] = "none"


@dataclass(frozen=True, slots=True)
class HangoutStatus:
    """Overall hangout session status."""
    affinity: AffinityReading | None
    in_hangout: bool
    is_max_affinity: bool
    hearts_to_next_level: int


class HangoutAffinityReader:
    """Read affinity levels from hangout event screens.

    Features:
    - Heart icon counting (filled vs empty)
    - Percentage display parsing
    - Character name detection
    - Level progression tracking

    Primary: OCR for exact values
    Fallback: Heart counting via color analysis
    """

    _REF_W = 1920
    _REF_H = 1080

    # Affinity display regions
    _HEARTS_ROI = (0.35, 0.15, 0.65, 0.30)  # Heart icons row
    _PERCENTAGE_ROI = (0.40, 0.10, 0.60, 0.20)  # Percentage text

    # Heart colors (red/pink for filled, gray for empty)
    _HEART_RED_LOW = np.array([0, 100, 150])
    _HEART_RED_HIGH = np.array([15, 255, 255])

    _HEART_GRAY_LOW = np.array([0, 0, 100])
    _HEART_GRAY_HIGH = np.array([180, 50, 180])

    # Percentage pattern
    _PERCENTAGE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%")
    _FRACTION_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)")

    # Max affinity threshold
    MAX_AFFINITY_LEVEL = 10

    def __init__(self, ocr_provider=None, now_fn=None) -> None:
        """Initialize hangout affinity reader.

        Args:
            ocr_provider: Optional OCR provider for text extraction.
            now_fn: Time function (default: time.perf_counter)
        """
        self._ocr = ocr_provider
        self._now_fn = now_fn or time.perf_counter
        self._last_reading: AffinityReading | None = None

    @property
    def last_reading(self) -> AffinityReading | None:
        """Get last affinity reading."""
        return self._last_reading

    def read_affinity(
        self,
        frame: np.ndarray,
        frame_id: int,
    ) -> AffinityReading:
        """Read affinity level from current frame.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID

        Returns:
            AffinityReading with affinity information
        """
        # Try OCR first
        if self._ocr is not None:
            ocr_result = self._try_ocr(frame, frame_id)
            if ocr_result is not None:
                self._last_reading = ocr_result
                return ocr_result

        # Fallback to heart counting
        heart_result = self._count_hearts(frame, frame_id)
        self._last_reading = heart_result
        return heart_result

    def _try_ocr(self, frame: np.ndarray, frame_id: int) -> AffinityReading | None:
        """Extract affinity using OCR."""
        if self._ocr is None:
            return None

        # Try percentage region
        percentage_roi = self._get_roi(frame, self._PERCENTAGE_ROI)
        if percentage_roi.size == 0:
            return None

        try:
            text = self._ocr.extract_text(percentage_roi, lang="eng+chi_sim")
            return self._parse_ocr_text(text, frame_id)
        except Exception as exc:
            log.debug("[HangoutAffinityReader] OCR failed: %s", exc)
            return None

    def _parse_ocr_text(self, text: str, frame_id: int) -> AffinityReading | None:
        """Parse OCR text to extract affinity values."""
        # Clean text
        text = text.replace(" ", "").replace("%", "")

        # Try percentage format "75%"
        match = self._PERCENTAGE_PATTERN.search(text)
        if match:
            percentage = float(match.group(1)) / 100.0
            # Estimate level from percentage
            level = self._percentage_to_level(percentage)

            return AffinityReading(
                level=level,
                percentage=percentage,
                total_hearts=self.MAX_AFFINITY_LEVEL,
                filled_hearts=level,
                display_string=f"{int(percentage * 100)}%",
                character_name=None,
                confidence=0.9,
                frame_id=frame_id,
                source="ocr",
            )

        # Try fraction format "3/10"
        match = self._FRACTION_PATTERN.search(text)
        if match:
            filled = int(match.group(1))
            total = int(match.group(2))

            percentage = filled / total if total > 0 else 0.0

            return AffinityReading(
                level=filled,
                percentage=percentage,
                total_hearts=total,
                filled_hearts=filled,
                display_string=f"{filled}/{total}",
                character_name=None,
                confidence=0.95,
                frame_id=frame_id,
                source="ocr",
            )

        return None

    def _count_hearts(self, frame: np.ndarray, frame_id: int) -> AffinityReading:
        """Count heart icons to determine affinity level."""
        if cv2 is None:
            return AffinityReading(
                level=0,
                percentage=0.0,
                total_hearts=0,
                filled_hearts=0,
                display_string="",
                character_name=None,
                confidence=0.0,
                frame_id=frame_id,
                source="none",
            )

        # Get hearts ROI
        hearts_roi = self._get_roi(frame, self._HEARTS_ROI)
        if hearts_roi.size == 0:
            return AffinityReading(
                level=0,
                percentage=0.0,
                total_hearts=0,
                filled_hearts=0,
                display_string="",
                character_name=None,
                confidence=0.0,
                frame_id=frame_id,
                source="none",
            )

        hsv = cv2.cvtColor(hearts_roi, cv2.COLOR_BGR2HSV)

        # Count filled hearts (red/pink)
        filled_mask = cv2.inRange(hsv, self._HEART_RED_LOW, self._HEART_RED_HIGH)
        filled_pixels = cv2.countNonZero(filled_mask)

        # Count empty hearts (gray)
        empty_mask = cv2.inRange(hsv, self._HEART_GRAY_LOW, self._HEART_GRAY_HIGH)
        empty_pixels = cv2.countNonZero(empty_mask)

        # Estimate heart counts (assume ~200 pixels per filled heart)
        PIXELS_PER_HEART = 200

        filled_hearts = max(1, filled_pixels // PIXELS_PER_HEART)
        empty_hearts = max(1, empty_pixels // PIXELS_PER_HEART)
        total_hearts = filled_hearts + empty_hearts

        # Clamp to reasonable values
        total_hearts = min(total_hearts, self.MAX_AFFINITY_LEVEL)
        filled_hearts = min(filled_hearts, total_hearts)

        # Calculate percentage
        percentage = filled_hearts / total_hearts if total_hearts > 0 else 0.0

        return AffinityReading(
            level=filled_hearts,
            percentage=percentage,
            total_hearts=total_hearts,
            filled_hearts=filled_hearts,
            display_string=f"{filled_hearts}/{total_hearts}",
            character_name=None,
            confidence=min(0.6 + filled_hearts * 0.05, 0.9),
            frame_id=frame_id,
            source="hearts",
        )

    def _percentage_to_level(self, percentage: float) -> int:
        """Convert percentage to affinity level."""
        if percentage >= 0.95:
            return self.MAX_AFFINITY_LEVEL
        return int(percentage * self.MAX_AFFINITY_LEVEL) + 1

    def _get_roi(
        self,
        frame: np.ndarray,
        coords: tuple[float, float, float, float],
    ) -> np.ndarray:
        """Extract region of interest."""
        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1, y1, x2, y2 = coords
        x1 = int(x1 * sx * self._REF_W)
        y1 = int(y1 * sy * self._REF_H)
        x2 = int(x2 * sx * self._REF_W)
        y2 = int(y2 * sy * self._REF_H)

        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        return frame[y1:y2, x1:x2]

    def get_status(self, frame_id: int) -> HangoutStatus:
        """Get overall hangout status."""
        if self._last_reading is None:
            return HangoutStatus(
                affinity=None,
                in_hangout=False,
                is_max_affinity=False,
                hearts_to_next_level=0,
            )

        is_max = self._last_reading.level >= self.MAX_AFFINITY_LEVEL
        hearts_to_next = max(0, self.MAX_AFFINITY_LEVEL - self._last_reading.level)

        return HangoutStatus(
            affinity=self._last_reading,
            in_hangout=True,
            is_max_affinity=is_max,
            hearts_to_next_level=hearts_to_next,
        )

    def is_max_affinity(self) -> bool:
        """Check if character is at max affinity."""
        if self._last_reading is None:
            return False
        return self._last_reading.level >= self.MAX_AFFINITY_LEVEL

    def needs_more_affinity(self, target_level: int) -> bool:
        """Check if more affinity is needed to reach target."""
        if self._last_reading is None:
            return True
        return self._last_reading.level < target_level