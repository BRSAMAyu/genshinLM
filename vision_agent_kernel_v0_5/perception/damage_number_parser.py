"""Damage number parser for Genshin Impact combat.

P-36: Parses damage numbers from combat frames using inter-frame peak detection
and color classification (white/yellow/red/green/blue).

White: Normal hit
Yellow: Crit hit
Red: Enemy damage taken
Green: HP recovery
Blue: Elemental damage (shield-related)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class DamageColor(Enum):
    WHITE = "white"
    YELLOW = "yellow"
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


@dataclass(frozen=True, slots=True)
class DamageEvent:
    value: int
    color: DamageColor
    position: tuple[float, float]
    frame_id: int
    timestamp: float
    is_crit: bool = False


@dataclass(frozen=True, slots=True)
class DamageParseResult:
    total_damage: int
    crit_count: int
    events: tuple[DamageEvent, ...]
    peak_colors: tuple[DamageColor, ...]
    confidence: float
    frame_id: int


class DamageNumberParser:
    """Parse damage numbers from combat frames.

    Features:
    - Inter-frame peak detection to isolate new damage numbers
    - Color classification for damage type identification
    - Crit detection via yellow color + larger size
    - Motion tracking for floating damage numbers
    """

    _REF_W = 1920
    _REF_H = 1080

    # ROI for damage number area (center-screen, above enemies)
    _DAMAGE_ROI = (0.25, 0.20, 0.75, 0.65)

    # Color ranges in HSV (OpenCV: H=0-179, S=0-255, V=0-255)
    _COLOR_RANGES: dict[DamageColor, tuple[np.ndarray, np.ndarray]] = {
        # White: H=0-180 (any hue), high saturation, high value
        DamageColor.WHITE: (
            np.array([0, 30, 200]),
            np.array([180, 255, 255]),
        ),
        # Yellow: H=15-35 (yellow-orange range)
        DamageColor.YELLOW: (
            np.array([15, 100, 200]),
            np.array([35, 255, 255]),
        ),
        # Red: H=0-10 or 170-180
        DamageColor.RED: (
            np.array([0, 150, 150]),
            np.array([10, 255, 255]),
        ),
        # Green: H=40-80 (green range)
        DamageColor.GREEN: (
            np.array([40, 100, 150]),
            np.array([80, 255, 255]),
        ),
        # Blue: H=90-130 (blue range)
        DamageColor.BLUE: (
            np.array([90, 100, 150]),
            np.array([130, 255, 255]),
        ),
    }

    # Peak detection thresholds
    _MIN_PEAK_INTENSITY = 500  # Minimum pixel count for a valid peak
    _PEAK_DISTANCE_THRESHOLD = 30  # Minimum pixel distance between peaks

    def __init__(self, now_fn=None) -> None:
        self._now_fn = now_fn or time.perf_counter
        self._last_frame: np.ndarray | None = None
        self._last_frame_time: float = 0.0
        self._last_frame_id: int = 0
        self._active_damage_events: list[DamageEvent] = []
        self._motion_history: list[tuple[float, float]] = []

    def parse_frame(
        self,
        frame: np.ndarray,
        frame_id: int,
    ) -> DamageParseResult:
        """Parse damage numbers from current frame.

        Uses inter-frame peak detection to isolate new damage numbers.
        Compares with previous frame to find new damage popups.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID

        Returns:
            DamageParseResult with all detected damage events
        """
        if cv2 is None or frame.size == 0:
            return DamageParseResult(0, 0, (), (), 0.0, frame_id)

        now = self._now_fn()

        # Extract ROI
        roi = self._get_roi(frame)
        if roi.size == 0:
            return DamageParseResult(0, 0, (), (), 0.0, frame_id)

        # Compute inter-frame difference if we have a previous frame
        new_peaks: list[tuple[float, float]] = []
        if self._last_frame is not None:
            new_peaks = self._detect_frame_peaks(roi, self._last_frame)

        # Update last frame
        self._last_frame = frame.copy()
        self._last_frame_time = now
        self._last_frame_id = frame_id

        # Parse each detected peak
        events: list[DamageEvent] = []
        peak_colors: list[DamageColor] = []

        for peak_pos in new_peaks:
            # Check color at peak position
            color, intensity = self._get_color_at_position(roi, peak_pos)
            if color is None:
                continue

            peak_colors.append(color)

            # Estimate damage value from intensity
            # (actual OCR would give exact value, this is heuristic)
            estimated_value = self._estimate_damage_value(intensity, color)

            is_crit = color == DamageColor.YELLOW and intensity > 0.5

            # Scale position back to full frame
            scaled_pos = self._scale_position(peak_pos, frame.shape)

            event = DamageEvent(
                value=estimated_value,
                color=color,
                position=scaled_pos,
                frame_id=frame_id,
                timestamp=now,
                is_crit=is_crit,
            )
            events.append(event)

        # Prune old events
        self._prune_old_events(now, events)

        # Compute results
        total_damage = sum(e.value for e in self._active_damage_events if e.color in (DamageColor.WHITE, DamageColor.YELLOW, DamageColor.RED))
        crit_count = sum(1 for e in self._active_damage_events if e.is_crit)
        confidence = min(1.0, len(self._active_damage_events) / 10.0)

        return DamageParseResult(
            total_damage=total_damage,
            crit_count=crit_count,
            events=tuple(self._active_damage_events),
            peak_colors=tuple(peak_colors),
            confidence=confidence,
            frame_id=frame_id,
        )

    def _get_roi(self, frame: np.ndarray) -> np.ndarray:
        """Extract damage number region from frame."""
        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1 = int(self._DAMAGE_ROI[0] * sx * self._REF_W)
        y1 = int(self._DAMAGE_ROI[1] * sy * self._REF_H)
        x2 = int(self._DAMAGE_ROI[2] * sx * self._REF_W)
        y2 = int(self._DAMAGE_ROI[3] * sy * self._REF_H)

        return frame[y1:y2, x1:x2]

    def _detect_frame_peaks(
        self,
        current_roi: np.ndarray,
        previous_frame: np.ndarray,
    ) -> list[tuple[float, float]]:
        """Detect new damage numbers by comparing frames."""
        # Get previous frame ROI
        prev_roi = self._get_roi(previous_frame)

        if prev_roi.size == 0:
            return []

        # Compute difference
        gray_curr = cv2.cvtColor(current_roi, cv2.COLOR_BGR2GRAY) if cv2 else current_roi[:, :, 0]
        gray_prev = cv2.cvtColor(prev_roi, cv2.COLOR_BGR2GRAY) if cv2 else prev_roi[:, :, 0]

        diff = cv2.absdiff(gray_curr, gray_prev) if cv2 else np.abs(gray_curr.astype(int) - gray_prev.astype(int)).astype(np.uint8)

        # Apply threshold
        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY) if cv2 else (None, np.clip(diff, 0, 255).astype(np.uint8))

        # Find contours (peaks)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE) if cv2 else ([], [])

        peaks: list[tuple[float, float]] = []
        for contour in contours:
            area = cv2.contourArea(contour) if cv2 else 0
            if area < self._MIN_PEAK_INTENSITY:
                continue

            # Get centroid
            M = cv2.moments(contour)
            if M["m00"] > 0:
                cx = M["m10"] / M["m00"]
                cy = M["m01"] / M["m00"]
                peaks.append((float(cx), float(cy)))

        return peaks

    def _get_color_at_position(
        self,
        roi: np.ndarray,
        position: tuple[float, float],
    ) -> tuple[DamageColor | None, float]:
        """Determine damage color at a specific position."""
        cx, cy = int(position[0]), int(position[1])

        # Get small region around position
        h, w = roi.shape[:2]
        x1 = max(0, cx - 20)
        y1 = max(0, cy - 20)
        x2 = min(w, cx + 20)
        y2 = min(h, cy + 20)

        region = roi[y1:y2, x1:x2]
        if region.size == 0:
            return None, 0.0

        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV) if cv2 else region

        # Check each color range
        best_color: DamageColor | None = None
        best_intensity = 0.0

        for color, (lower, upper) in self._COLOR_RANGES.items():
            mask = cv2.inRange(hsv, lower, upper)
            pixel_count = cv2.countNonZero(mask)
            intensity = pixel_count / max(mask.size, 1)

            if intensity > best_intensity:
                best_intensity = intensity
                best_color = color

        return best_color, best_intensity

    def _estimate_damage_value(self, intensity: float, color: DamageColor) -> int:
        """Estimate damage value from visual intensity (heuristic)."""
        # This is a rough heuristic - actual value would need OCR
        base_values = {
            DamageColor.WHITE: 100,
            DamageColor.YELLOW: 200,  # Crits are usually larger
            DamageColor.RED: 150,
            DamageColor.GREEN: 50,
            DamageColor.BLUE: 100,
        }
        base = base_values.get(color, 100)
        return int(base * (1 + intensity))

    def _scale_position(
        self,
        roi_pos: tuple[float, float],
        frame_shape: tuple[int, ...],
    ) -> tuple[float, float]:
        """Scale ROI position back to full frame coordinates."""
        h, w = frame_shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1 = int(self._DAMAGE_ROI[0] * sx * self._REF_W)
        y1 = int(self._DAMAGE_ROI[1] * sy * self._REF_H)

        return (roi_pos[0] + x1, roi_pos[1] + y1)

    def _prune_old_events(self, now: float, new_events: list[DamageEvent]) -> None:
        """Remove old damage events and add new ones."""
        # Add new events
        self._active_damage_events.extend(new_events)

        # Remove events older than 2 seconds
        max_age = 2.0
        self._active_damage_events = [
            e for e in self._active_damage_events
            if now - e.timestamp < max_age
        ]

    def reset(self) -> None:
        """Reset parser state."""
        self._last_frame = None
        self._last_frame_time = 0.0
        self._last_frame_id = 0
        self._active_damage_events.clear()
        self._motion_history.clear()