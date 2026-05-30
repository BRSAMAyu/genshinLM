"""HP OCR reader for Genshin Impact character health bars.

P-37: Reads precise HP values from character HP bars in format "32000/45000".
Uses slash separator detection for numerator/denominator parsing.

Typically displayed below the character portrait in co-op or when viewing details.
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
class HPReading:
    """P-37: HP OCR result."""
    current_hp: int
    max_hp: int
    ratio: float                   # current_hp / max_hp
    display_string: str           # Raw "32000/45000" format
    confidence: float
    frame_id: int
    source: Literal["ocr", "bar", "none"] = "none"


class HPOcrReader:
    """Read HP values from character HP bars.

    Supports:
    - Character detail view HP (format: "32000/45000")
    - Co-op HP bars at top of screen
    - Bar-based fallback when OCR unavailable

    Primary: OCR with number parsing
    Fallback: HP bar fill ratio estimation
    """

    _REF_W = 1920
    _REF_H = 1080

    # Character HP bar regions
    _MAIN_CHAR_HP_ROI = (50, 960, 250, 1020)  # Main character HP bottom-left
    _COOP_HP_ROI = (200, 30, 500, 70)         # Co-op HP bar top area
    _DETAIL_HP_ROI = (60, 680, 200, 730)      # Detail view HP

    # Bar color (green HP bar)
    _HP_BAR_LOW = np.array([40, 100, 100])
    _HP_BAR_HIGH = np.array([85, 255, 255])

    # HP text pattern: numbers with optional slash
    _HP_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)")

    def __init__(self, ocr_provider=None, now_fn=None) -> None:
        """Initialize HP OCR reader.

        Args:
            ocr_provider: Optional OCR provider for text extraction.
            now_fn: Time function (default: time.perf_counter)
        """
        self._ocr = ocr_provider
        self._now_fn = now_fn or time.perf_counter
        self._last_reading: HPReading | None = None

    @property
    def last_reading(self) -> HPReading | None:
        """Get last successful HP reading."""
        return self._last_reading

    def read_hp(
        self,
        frame: np.ndarray,
        frame_id: int,
        region: Literal["main", "coop", "detail"] = "main",
    ) -> HPReading:
        """Read HP value from specified region.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID
            region: Which HP bar to read

        Returns:
            HPReading with current/max HP and confidence
        """
        # Try OCR first
        if self._ocr is not None:
            ocr_result = self._try_ocr(frame, frame_id, region)
            if ocr_result is not None:
                self._last_reading = ocr_result
                return ocr_result

        # Fallback to bar-based estimation
        bar_result = self._estimate_hp_from_bar(frame, frame_id, region)
        self._last_reading = bar_result
        return bar_result

    def _try_ocr(
        self,
        frame: np.ndarray,
        frame_id: int,
        region: Literal["main", "coop", "detail"],
    ) -> HPReading | None:
        """Extract HP value using OCR."""
        if self._ocr is None:
            return None

        roi = self._get_roi(frame, region)
        if roi.size == 0:
            return None

        try:
            text = self._ocr.extract_text(roi, lang="eng+digits")
            return self._parse_ocr_text(text, frame_id)
        except Exception as exc:
            log.debug("[HPOcrReader] OCR failed: %s", exc)
            return None

    def _parse_ocr_text(self, text: str, frame_id: int) -> HPReading | None:
        """Parse OCR text to extract HP values."""
        # Clean text
        text = text.replace(" ", "").replace(",", "")

        # Try pattern matching for "32000/45000" format
        match = self._HP_PATTERN.search(text)
        if match:
            current = int(match.group(1))
            max_hp = int(match.group(2))

            if max_hp > 0:
                ratio = current / max_hp
                return HPReading(
                    current_hp=current,
                    max_hp=max_hp,
                    ratio=ratio,
                    display_string=f"{current}/{max_hp}",
                    confidence=0.95,
                    frame_id=frame_id,
                    source="ocr",
                )

        # Try single number (might be current HP only)
        single_match = re.search(r"(\d{4,6})", text)
        if single_match:
            value = int(single_match.group(1))
            # Use last known max HP if available
            if self._last_reading and self._last_reading.max_hp > 0:
                ratio = value / self._last_reading.max_hp
                return HPReading(
                    current_hp=value,
                    max_hp=self._last_reading.max_hp,
                    ratio=ratio,
                    display_string=f"{value}/{self._last_reading.max_hp}",
                    confidence=0.7,
                    frame_id=frame_id,
                    source="ocr",
                )

        return None

    def _estimate_hp_from_bar(
        self,
        frame: np.ndarray,
        frame_id: int,
        region: Literal["main", "coop", "detail"],
    ) -> HPReading:
        """Fallback: Estimate HP from bar fill ratio."""
        if cv2 is None:
            return HPReading(0, 0, 0.0, "", 0.0, frame_id, "none")

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        roi = self._get_roi(frame, region)
        if roi.size == 0:
            return HPReading(0, 0, 0.0, "", 0.0, frame_id, "none")

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Green HP bar pixels
        hp_mask = cv2.inRange(hsv, self._HP_BAR_LOW, self._HP_BAR_HIGH)
        hp_pixels = cv2.countNonZero(hp_mask)

        # Total bar area (estimate as ROI width)
        bar_width = roi.shape[1]
        bar_height = roi.shape[0]
        total_bar_pixels = bar_width * bar_height

        if total_bar_pixels == 0:
            return HPReading(0, 0, 0.0, "", 0.0, frame_id, "none")

        # Calculate fill ratio
        fill_ratio = hp_pixels / total_bar_pixels

        # Estimate values (assume max HP is 45000 for main character)
        if region == "main":
            estimated_max = 45000
        elif region == "coop":
            estimated_max = 30000
        else:
            estimated_max = 50000

        current_hp = int(fill_ratio * estimated_max)
        ratio = fill_ratio

        # Add small threshold for visible bars
        is_visible = hp_pixels > (bar_width * bar_height * 0.01)
        if not is_visible:
            return HPReading(0, 0, 0.0, "", 0.0, frame_id, "none")

        return HPReading(
            current_hp=current_hp,
            max_hp=estimated_max,
            ratio=ratio,
            display_string=f"{current_hp}/{estimated_max}",
            confidence=min(fill_ratio * 2, 1.0) * 0.8,  # Lower confidence for bar estimation
            frame_id=frame_id,
            source="bar",
        )

    def _get_roi(
        self,
        frame: np.ndarray,
        region: Literal["main", "coop", "detail"],
    ) -> np.ndarray:
        """Get region of interest for HP bar."""
        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        roi_coords = {
            "main": self._MAIN_CHAR_HP_ROI,
            "coop": self._COOP_HP_ROI,
            "detail": self._DETAIL_HP_ROI,
        }

        x1, y1, x2, y2 = roi_coords[region]
        x1, y1, x2, y2 = int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy)

        # Clip to frame bounds
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        return frame[y1:y2, x1:x2]

    def is_critical(self, reading: HPReading | None = None) -> bool:
        """Check if HP is in critical state (<20%)."""
        if reading is None:
            reading = self._last_reading

        if reading is None:
            return False

        return reading.ratio < 0.2

    def is_low(self, reading: HPReading | None = None) -> bool:
        """Check if HP is low (<50%)."""
        if reading is None:
            reading = self._last_reading

        if reading is None:
            return False

        return reading.ratio < 0.5