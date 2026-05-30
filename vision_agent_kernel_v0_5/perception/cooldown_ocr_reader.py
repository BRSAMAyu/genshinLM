"""Cooldown OCR reader for Genshin Impact skill icons.

P-38: Reads cooldown numbers below skill icons.
Parses countdown format typically showing seconds remaining.

Located below character skill icons in bottom-left UI area.
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
class CooldownReading:
    """P-38: Cooldown OCR result."""
    skill_slot: int                # 0=normal attack, 1=skill, 2=burst, 3-5=others
    seconds_remaining: float
    is_ready: bool                 # Cooldown complete
    is_critical: bool             # < 1 second remaining
    display_string: str           # Raw number string
    confidence: float
    frame_id: int
    source: Literal["ocr", "color", "none"] = "none"


@dataclass(frozen=True, slots=True)
class AllCooldowns:
    """Status of all skill cooldowns."""
    readings: tuple[CooldownReading, ...]
    ready_count: int
    total_count: int
    any_critical: bool
    frame_id: int


class CooldownOcrReader:
    """Read cooldown numbers from skill icons.

    Features:
    - Reads numbers below skill icons (0-9, possibly 10+)
    - Detects ready state (no cooldown shown)
    - Identifies critical cooldowns (< 1 second)
    - Supports multiple skill slots

    Primary: OCR for exact numbers
    Fallback: Color-based detection for ready/not-ready
    """

    _REF_W = 1920
    _REF_H = 1080

    # Skill bar ROI (bottom-left area)
    _SKILL_BAR_ROI = (80, 900, 500, 1020)

    # Number of skill slots to check
    _NUM_SKILL_SLOTS = 6

    # Slot positions relative to skill bar (normalized)
    _SLOT_POSITIONS: list[tuple[float, float, float, float]] = [
        (0.00, 0.60, 0.12, 0.95),   # Slot 0
        (0.12, 0.60, 0.24, 0.95),   # Slot 1
        (0.24, 0.60, 0.36, 0.95),   # Slot 2
        (0.36, 0.60, 0.48, 0.95),   # Slot 3
        (0.48, 0.60, 0.60, 0.95),   # Slot 4
        (0.60, 0.60, 0.72, 0.95),   # Slot 5
    ]

    # Cooldown overlay color (semi-transparent blue-gray)
    _COOLDOWN_OVERLAY_LOW = np.array([90, 30, 50])
    _COOLDOWN_OVERLAY_HIGH = np.array([130, 100, 200])

    # Ready indicator color (skill icon fully visible, no overlay)
    _READY_BRIGHTNESS_THRESHOLD = 150

    # Cooldown number pattern
    _NUMBER_PATTERN = re.compile(r"(\d+(?:\.\d+)?)")

    def __init__(self, ocr_provider=None, now_fn=None) -> None:
        """Initialize cooldown OCR reader.

        Args:
            ocr_provider: Optional OCR provider for text extraction.
            now_fn: Time function (default: time.perf_counter)
        """
        self._ocr = ocr_provider
        self._now_fn = now_fn or time.perf_counter
        self._last_readings: list[CooldownReading] = []

    @property
    def last_readings(self) -> tuple[CooldownReading, ...]:
        """Get last cooldown readings."""
        return tuple(self._last_readings)

    def read_all_cooldowns(self, frame: np.ndarray, frame_id: int) -> AllCooldowns:
        """Read cooldown status for all skill slots.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID

        Returns:
            AllCooldowns with status of all skill slots
        """
        readings: list[CooldownReading] = []

        for slot in range(self._NUM_SKILL_SLOTS):
            reading = self._read_slot_cooldown(frame, frame_id, slot)
            readings.append(reading)

        self._last_readings = readings

        ready_count = sum(1 for r in readings if r.is_ready)
        any_critical = any(r.is_critical for r in readings)

        return AllCooldowns(
            readings=tuple(readings),
            ready_count=ready_count,
            total_count=self._NUM_SKILL_SLOTS,
            any_critical=any_critical,
            frame_id=frame_id,
        )

    def _read_slot_cooldown(
        self,
        frame: np.ndarray,
        frame_id: int,
        slot: int,
    ) -> CooldownReading:
        """Read cooldown for a specific skill slot."""
        # Get slot region
        slot_roi = self._get_slot_roi(frame, slot)
        if slot_roi.size == 0:
            return CooldownReading(
                skill_slot=slot,
                seconds_remaining=0.0,
                is_ready=True,
                is_critical=False,
                display_string="",
                confidence=0.0,
                frame_id=frame_id,
                source="none",
            )

        # Try OCR for exact number
        if self._ocr is not None:
            ocr_result = self._try_ocr(slot_roi, frame_id, slot)
            if ocr_result is not None:
                return ocr_result

        # Fallback to color-based detection
        return self._detect_cooldown_state(slot_roi, frame_id, slot)

    def _try_ocr(self, roi: np.ndarray, frame_id: int, slot: int) -> CooldownReading | None:
        """Extract cooldown number using OCR."""
        if self._ocr is None:
            return None

        try:
            text = self._ocr.extract_text(roi, lang="eng+digits")
            return self._parse_cooldown_text(text, frame_id, slot)
        except Exception as exc:
            log.debug("[CooldownOcrReader] OCR failed for slot %d: %s", slot, exc)
            return None

    def _parse_cooldown_text(self, text: str, frame_id: int, slot: int) -> CooldownReading | None:
        """Parse OCR text to extract cooldown value."""
        # Clean text
        text = text.strip().replace(" ", "")

        # Try to match numbers
        match = self._NUMBER_PATTERN.search(text)
        if match:
            value_str = match.group(1)
            if "." in value_str:
                seconds = float(value_str)
            else:
                seconds = float(int(value_str))

            is_ready = seconds < 0.5  # Consider ready if < 0.5s

            return CooldownReading(
                skill_slot=slot,
                seconds_remaining=seconds,
                is_ready=is_ready,
                is_critical=0 < seconds < 1.0,
                display_string=value_str,
                confidence=0.9,
                frame_id=frame_id,
                source="ocr",
            )

        # No number found - might be ready
        if not text or text.lower() in ("ready", "ok"):
            return CooldownReading(
                skill_slot=slot,
                seconds_remaining=0.0,
                is_ready=True,
                is_critical=False,
                display_string="0",
                confidence=0.8,
                frame_id=frame_id,
                source="ocr",
            )

        return None

    def _detect_cooldown_state(
        self,
        roi: np.ndarray,
        frame_id: int,
        slot: int,
    ) -> CooldownReading:
        """Detect cooldown state using color analysis."""
        if cv2 is None:
            return CooldownReading(
                skill_slot=slot,
                seconds_remaining=0.0,
                is_ready=True,
                is_critical=False,
                display_string="",
                confidence=0.0,
                frame_id=frame_id,
                source="none",
            )

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Check for cooldown overlay (blue-gray semi-transparent)
        overlay_mask = cv2.inRange(hsv, self._COOLDOWN_OVERLAY_LOW, self._COOLDOWN_OVERLAY_HIGH)
        overlay_ratio = cv2.countNonZero(overlay_mask) / max(overlay_mask.size, 1)

        # Check overall brightness
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        avg_brightness = np.mean(gray)

        if overlay_ratio > 0.15:
            # Has cooldown overlay - skill is on cooldown
            # Estimate seconds from overlay intensity (crude heuristic)
            estimated_seconds = min(overlay_ratio * 30, 15.0)  # Cap at 15s estimate

            return CooldownReading(
                skill_slot=slot,
                seconds_remaining=estimated_seconds,
                is_ready=False,
                is_critical=0 < estimated_seconds < 1.0,
                display_string=str(int(estimated_seconds)) if estimated_seconds >= 1 else f"{estimated_seconds:.1f}",
                confidence=min(overlay_ratio * 3, 0.8),
                frame_id=frame_id,
                source="color",
            )

        # No overlay - check if skill is ready
        if avg_brightness > self._READY_BRIGHTNESS_THRESHOLD:
            return CooldownReading(
                skill_slot=slot,
                seconds_remaining=0.0,
                is_ready=True,
                is_critical=False,
                display_string="",
                confidence=0.7,
                frame_id=frame_id,
                source="color",
            )

        # Unknown state
        return CooldownReading(
            skill_slot=slot,
            seconds_remaining=0.0,
            is_ready=False,
            is_critical=False,
            display_string="",
            confidence=0.3,
            frame_id=frame_id,
            source="color",
        )

    def _get_slot_roi(
        self,
        frame: np.ndarray,
        slot: int,
    ) -> np.ndarray:
        """Get region of interest for a skill slot."""
        h, w = frame.shape[:2]

        # Get skill bar region
        sx, sy = w / self._REF_W, h / self._REF_H
        x1, y1, x2, y2 = self._scale_roi(self._SKILL_BAR_ROI, sx, sy)

        # Calculate slot position within skill bar
        bar_width = x2 - x1
        slot_width = bar_width / self._NUM_SKILL_SLOTS

        slot_x1 = x1 + int(slot * slot_width)
        slot_x2 = slot_x1 + int(slot_width)

        # Clip to frame bounds
        slot_x1 = max(0, slot_x1)
        slot_x2 = min(w, slot_x2)
        y1, y2 = max(0, y1), min(h, y2)

        return frame[y1:y2, slot_x1:slot_x2]

    def _scale_roi(
        self,
        roi: tuple[int, int, int, int],
        sx: float,
        sy: float,
    ) -> tuple[int, int, int, int]:
        """Scale ROI from reference resolution."""
        x1, y1, x2, y2 = roi
        return (
            int(x1 * sx),
            int(y1 * sy),
            int(x2 * sx),
            int(y2 * sy),
        )

    def is_any_skill_ready(self) -> bool:
        """Check if any skill is ready (no cooldown)."""
        return any(r.is_ready for r in self._last_readings)

    def get_burst_ready(self) -> bool:
        """Check if elemental burst (slot 2) is ready."""
        if len(self._last_readings) > 2:
            return self._last_readings[2].is_ready
        return False