"""Item count parser for Genshin Impact inventory and shop counts.

P-39: Parses item quantity display in format "x999/99/999".
Handles single count, dual count (current/max), and triple count formats.

Common displays:
- Material count in inventory ("x999")
- Artifact substats ("x9" style)
- Shop quantities with limits ("5/99")
- Material usage counts in crafting ("3/4")
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ItemCountReading:
    """P-39: Item count OCR result."""
    count: int                     # Primary count value
    max_count: int | None          # Optional max count (e.g., "5/99")
    secondary_count: int | None    # Optional second count (e.g., "3/4/10")
    format_type: Literal["single", "ratio", "triple"]  # Format detected
    display_string: str            # Raw "x999" or "5/99" format
    position: tuple[int, int]     # Center position in frame
    confidence: float
    frame_id: int
    source: Literal["ocr", "color", "none"] = "none"


@dataclass(frozen=True, slots=True)
class MultiItemCount:
    """Result for scanning multiple item locations."""
    items: tuple[ItemCountReading, ...]
    total_items: int
    frame_id: int


class ItemCountParser:
    """Parse item counts from UI elements.

    Supports multiple formats:
    - "x999" - single count (inventory materials)
    - "5/99" - ratio format (crafting materials with max)
    - "3/4/10" - triple format (e.g., enhancement ore count)
    - "99" - plain number

    Primary: OCR with pattern matching
    Fallback: Color-based detection for high/low states
    """

    _REF_W = 1920
    _REF_H = 1080

    # Common item count display regions
    _INVENTORY_COUNT_ROI = (0.70, 0.10, 0.95, 0.50)  # Right side of inventory
    _CRAFTING_COUNT_ROI = (0.30, 0.40, 0.50, 0.60)  # Crafting material count
    _SHOP_COUNT_ROI = (0.60, 0.30, 0.85, 0.70)      # Shop quantity display

    # Color for count display (white/yellow text)
    _COUNT_TEXT_LOW = np.array([0, 0, 180])
    _COUNT_TEXT_HIGH = np.array([180, 60, 255])

    # Low stock indicator colors
    _LOW_STOCK_YELLOW = np.array([20, 150, 200])
    _LOW_STOCK_YELLOW_HIGH = np.array([35, 255, 255])
    _OUT_OF_STOCK_RED = np.array([0, 150, 150])
    _OUT_OF_STOCK_RED_HIGH = np.array([10, 255, 255])

    # Count patterns
    _SINGLE_PATTERN = re.compile(r"x?\s*(\d+)")
    _RATIO_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)")
    _TRIPLE_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)\s*/\s*(\d+)")

    def __init__(self, ocr_provider=None, now_fn=None) -> None:
        """Initialize item count parser.

        Args:
            ocr_provider: Optional OCR provider for text extraction.
            now_fn: Time function (default: time.perf_counter)
        """
        self._ocr = ocr_provider
        self._now_fn = now_fn or time.perf_counter
        self._last_readings: list[ItemCountReading] = []

    @property
    def last_readings(self) -> tuple[ItemCountReading, ...]:
        """Get last item count readings."""
        return tuple(self._last_readings)

    def parse_count(
        self,
        frame: np.ndarray,
        frame_id: int,
        region: Literal["inventory", "crafting", "shop"] | tuple[int, int, int, int] = "inventory",
        position: tuple[int, int] | None = None,
    ) -> ItemCountReading:
        """Parse item count from specified region.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID
            region: Named region or custom ROI tuple
            position: Optional specific position to check

        Returns:
            ItemCountReading with count values
        """
        # Get ROI
        if isinstance(region, tuple):
            roi_coords = region
            roi = self._get_custom_roi(frame, roi_coords)
        else:
            roi = self._get_named_roi(frame, region)

        if position is not None:
            # Adjust ROI to focus on specific position
            pass  # Use position if provided

        # Try OCR
        if self._ocr is not None:
            ocr_result = self._try_ocr(roi, frame_id)
            if ocr_result is not None:
                self._last_readings.append(ocr_result)
                return ocr_result

        # Fallback to color-based
        return self._detect_from_color(roi, frame_id)

    def parse_multiple_counts(
        self,
        frame: np.ndarray,
        frame_id: int,
        positions: list[tuple[int, int, int, int]],
    ) -> MultiItemCount:
        """Parse item counts at multiple positions.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID
            positions: List of (x1, y1, x2, y2) ROIs to scan

        Returns:
            MultiItemCount with all detected counts
        """
        items: list[ItemCountReading] = []

        for i, coords in enumerate(positions):
            roi = self._get_custom_roi(frame, coords)
            if roi.size == 0:
                continue

            if self._ocr is not None:
                result = self._try_ocr(roi, frame_id)
                if result is not None:
                    items.append(result)
                    continue

            # Fallback color detection
            result = self._detect_from_color(roi, frame_id)
            items.append(result)

        self._last_readings.extend(items)

        return MultiItemCount(
            items=tuple(items),
            total_items=len(items),
            frame_id=frame_id,
        )

    def _try_ocr(self, roi: np.ndarray, frame_id: int) -> ItemCountReading | None:
        """Extract item count using OCR."""
        if self._ocr is None:
            return None

        try:
            text = self._ocr.extract_text(roi, lang="eng+digits")
            return self._parse_ocr_text(text, frame_id, roi)
        except Exception as exc:
            log.debug("[ItemCountParser] OCR failed: %s", exc)
            return None

    def _parse_ocr_text(
        self,
        text: str,
        frame_id: int,
        roi: np.ndarray,
    ) -> ItemCountReading | None:
        """Parse OCR text to extract count values."""
        # Clean text
        text = text.replace(" ", "").replace(",", "").replace("X", "x")

        # Try triple format first (e.g., "3/4/10")
        triple_match = self._TRIPLE_PATTERN.search(text)
        if triple_match:
            count = int(triple_match.group(1))
            secondary = int(triple_match.group(2))
            max_count = int(triple_match.group(3))

            return ItemCountReading(
                count=count,
                max_count=max_count,
                secondary_count=secondary,
                format_type="triple",
                display_string=text,
                position=self._get_roi_center(roi),
                confidence=0.85,
                frame_id=frame_id,
                source="ocr",
            )

        # Try ratio format (e.g., "5/99")
        ratio_match = self._RATIO_PATTERN.search(text)
        if ratio_match:
            count = int(ratio_match.group(1))
            max_count = int(ratio_match.group(2))

            return ItemCountReading(
                count=count,
                max_count=max_count,
                secondary_count=None,
                format_type="ratio",
                display_string=text,
                position=self._get_roi_center(roi),
                confidence=0.9,
                frame_id=frame_id,
                source="ocr",
            )

        # Try single format (e.g., "x999" or "999")
        single_match = self._SINGLE_PATTERN.search(text)
        if single_match:
            count = int(single_match.group(1))

            return ItemCountReading(
                count=count,
                max_count=None,
                secondary_count=None,
                format_type="single",
                display_string=text,
                position=self._get_roi_center(roi),
                confidence=0.85,
                frame_id=frame_id,
                source="ocr",
            )

        return None

    def _detect_from_color(
        self,
        roi: np.ndarray,
        frame_id: int,
    ) -> ItemCountReading:
        """Fallback: Detect item count state from color."""
        if cv2 is None:
            return ItemCountReading(
                count=0,
                max_count=None,
                secondary_count=None,
                format_type="single",
                display_string="",
                position=(0, 0),
                confidence=0.0,
                frame_id=frame_id,
                source="none",
            )

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Check for count text (white/yellow)
        text_mask = cv2.inRange(hsv, self._COUNT_TEXT_LOW, self._COUNT_TEXT_HIGH)
        text_ratio = cv2.countNonZero(text_mask) / max(text_mask.size, 1)

        # Check for low stock warning (yellow)
        yellow_mask = cv2.inRange(hsv, self._LOW_STOCK_YELLOW, self._LOW_STOCK_YELLOW_HIGH)
        yellow_ratio = cv2.countNonZero(yellow_mask) / max(yellow_mask.size, 1)

        # Check for out of stock (red)
        red_mask = cv2.inRange(hsv, self._OUT_OF_STOCK_RED, self._OUT_OF_STOCK_RED_HIGH)
        red_ratio = cv2.countNonZero(red_mask) / max(red_mask.size, 1)

        # Determine state
        if red_ratio > 0.02:
            # Out of stock - red indicator
            confidence = min(red_ratio * 20, 1.0)
            return ItemCountReading(
                count=0,
                max_count=None,
                secondary_count=None,
                format_type="single",
                display_string="0",
                position=self._get_roi_center(roi),
                confidence=confidence * 0.7,
                frame_id=frame_id,
                source="color",
            )

        if yellow_ratio > 0.02:
            # Low stock - yellow indicator
            confidence = min(yellow_ratio * 20, 1.0)
            return ItemCountReading(
                count=1,  # Estimate low
                max_count=None,
                secondary_count=None,
                format_type="single",
                display_string="1",
                position=self._get_roi_center(roi),
                confidence=confidence * 0.6,
                frame_id=frame_id,
                source="color",
            )

        if text_ratio > 0.05:
            # Has count text visible
            confidence = min(text_ratio * 10, 0.8)
            return ItemCountReading(
                count=99,  # Estimate moderate
                max_count=None,
                secondary_count=None,
                format_type="single",
                display_string="99",
                position=self._get_roi_center(roi),
                confidence=confidence,
                frame_id=frame_id,
                source="color",
            )

        return ItemCountReading(
            count=0,
            max_count=None,
            secondary_count=None,
            format_type="single",
            display_string="",
            position=(0, 0),
            confidence=0.0,
            frame_id=frame_id,
            source="color",
        )

    def _get_named_roi(
        self,
        frame: np.ndarray,
        region: Literal["inventory", "crafting", "shop"],
    ) -> np.ndarray:
        """Get region of interest by name."""
        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        roi_map = {
            "inventory": self._INVENTORY_COUNT_ROI,
            "crafting": self._CRAFTING_COUNT_ROI,
            "shop": self._SHOP_COUNT_ROI,
        }

        x1, y1, x2, y2 = roi_map[region]
        x1, y1, x2, y2 = int(x1 * sx * self._REF_W), int(y1 * sy * self._REF_H), int(x2 * sx * self._REF_W), int(y2 * sy * self._REF_H)

        return frame[y1:y2, x1:x2]

    def _get_custom_roi(
        self,
        frame: np.ndarray,
        coords: tuple[int, int, int, int],
    ) -> np.ndarray:
        """Get custom region of interest."""
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = coords

        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        return frame[y1:y2, x1:x2]

    def _get_roi_center(self, roi: np.ndarray) -> tuple[int, int]:
        """Get center of ROI."""
        if roi.size == 0:
            return (0, 0)

        h, w = roi.shape[:2]
        return (w // 2, h // 2)

    def is_sufficient(self, reading: ItemCountReading, required: int) -> bool:
        """Check if item count is sufficient for an action."""
        return reading.count >= required

    def is_low_stock(self, reading: ItemCountReading) -> bool:
        """Check if item is low on stock."""
        if reading.max_count is not None and reading.max_count > 0:
            return reading.count <= reading.max_count * 0.2

        return reading.count <= 5