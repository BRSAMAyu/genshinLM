"""E-31: Paimon hint OCR reader for dialogue direction extraction.

Paimon (the companion fairy) provides navigation hints during quests.
This module extracts text from Paimon speech bubbles and converts
direction references to navigation commands.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

from perception.genshin_screen_classifier import GenshinScreenClassifier

log = logging.getLogger(__name__)


class DirectionType(str, Enum):
    COMPASS = "compass"       # North, South, East, West
    LANDMARK = "landmark"     # Near the statue, by the tree
    DISTANCE = "distance"     # A short walk, far away
    REGION = "region"         # In Mondstadt, near Liyue


@dataclass(frozen=True, slots=True)
class DirectionHint:
    """Extracted direction from Paimon hint."""
    direction: DirectionType
    value: str                # e.g., "north", "statue", "50m"
    original_text: str
    confidence: float
    position: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class PaimonHintResult:
    """Result of Paimon hint reading."""
    text: str
    directions: list[DirectionHint]
    is_paimon_speaking: bool
    confidence: float
    raw_bboxes: list[tuple[int, int, int, int]]


class PaimonHintReader:
    """Read and parse Paimon hints from screen frames."""

    _REF_W = 1920
    _REF_H = 1080

    # Dialog box region (normalized)
    _DIALOG_ROI = (0, 700, 1920, 1080)

    # Compass directions (case-insensitive patterns)
    _COMPASS_PATTERNS = [
        (re.compile(r"\b(north|n|south|s|east|e|west|w)\b", re.I), DirectionType.COMPASS),
        (re.compile(r"\b(northeast|nw?|southeast|se?|southwest|sw?|northwest|nw?)\b", re.I), DirectionType.COMPASS),
    ]

    # Landmark patterns
    _LANDMARK_PATTERNS = [
        (re.compile(r"\b(near|by|close to|next to|at the)\s+(.+?)(?:\s|$)"), DirectionType.LANDMARK),
        (re.compile(r"\bgo\s+to\s+(.+?)(?:\s|$)"), DirectionType.LANDMARK),
    ]

    # Distance patterns
    _DISTANCE_PATTERNS = [
        (re.compile(r"\b(short|medium|long)\s+(walk|distance|way)\b", re.I), DirectionType.DISTANCE),
        (re.compile(r"\b(\d+)\s*(m|km|meters|kilometers)\b", re.I), DirectionType.DISTANCE),
        (re.compile(r"\b(far|close|near|around)\b", re.I), DirectionType.DISTANCE),
    ]

    # Region patterns
    _REGION_PATTERNS = [
        (re.compile(r"\b(in|near|at)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b"), DirectionType.REGION),
    ]

    def __init__(self, classifier: GenshinScreenClassifier | None = None) -> None:
        self._classifier = classifier or GenshinScreenClassifier()
        self._last_text: str = ""
        self._direction_cache: list[DirectionHint] = []

    def read_hint(self, frame: np.ndarray, frame_id: int = 0) -> PaimonHintResult:
        """Read Paimon hint from frame.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            PaimonHintResult with extracted directions
        """
        if cv2 is None:
            return PaimonHintResult(
                text="",
                directions=[],
                is_paimon_speaking=False,
                confidence=0.0,
                raw_bboxes=[],
            )

        # Check if Paimon is speaking (white speech bubble)
        is_paimon = self._is_paimon_dialog(frame)
        if not is_paimon:
            return PaimonHintResult(
                text="",
                directions=[],
                is_paimon_speaking=False,
                confidence=0.0,
                raw_bboxes=[],
            )

        # Extract dialog text region
        text_region, bboxes = self._extract_dialog_text(frame)

        if text_region is None:
            return PaimonHintResult(
                text="",
                directions=[],
                is_paimon_speaking=True,
                confidence=0.5,
                raw_bboxes=[],
            )

        # OCR placeholder: in production, use GLM OCR or similar
        text = self._simple_text_extraction(text_region)

        # Parse directions from text
        directions = self._parse_directions(text)

        self._last_text = text
        self._direction_cache = directions

        confidence = 0.7 if text else 0.3

        return PaimonHintResult(
            text=text,
            directions=directions,
            is_paimon_speaking=True,
            confidence=confidence,
            raw_bboxes=bboxes,
        )

    def _is_paimon_dialog(self, frame: np.ndarray) -> bool:
        """Check if Paimon dialog box is visible."""
        state = self._classifier.classify(frame)

        # Paimon speech has specific visual markers
        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        # Check for white/silver dialog box (Paimon indicator)
        x1, y1, x2, y2 = self._scale_roi(self._DIALOG_ROI, sx, sy)
        dialog_region = frame[y1:y2, x1:x2]

        if dialog_region.size == 0:
            return False

        # Paimon dialog is typically light-colored
        hsv = cv2.cvtColor(dialog_region, cv2.COLOR_BGR2HSV)
        light_mask = cv2.inRange(hsv, (0, 0, 180), (180, 30, 255))
        light_ratio = cv2.countNonZero(light_mask) / light_mask.size

        return light_ratio > 0.1 or state.state == "dialog"

    def _extract_dialog_text(
        self, frame: np.ndarray
    ) -> tuple[np.ndarray | None, list[tuple[int, int, int, int]]]:
        """Extract text region from dialog box."""
        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        # Scale dialog ROI
        x1, y1, x2, y2 = self._scale_roi(self._DIALOG_ROI, sx, sy)
        text_region = frame[y1:y2, x1:x2]

        # Simple text detection: look for white/lighter regions
        gray = cv2.cvtColor(text_region, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

        # Find text contours (approximate)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        bboxes = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if 50 < area < 5000:  # Text region size
                x, y, cw, ch = cv2.boundingRect(contour)
                bboxes.append((x + x1, y + y1, x + x1 + cw, y + y1 + ch))

        return text_region, bboxes

    def _simple_text_extraction(self, region: np.ndarray) -> str:
        """Simple text extraction placeholder.

        In production, this would call GLM OCR or similar.
        Returns simulated direction hints for now.
        """
        # This is a placeholder - real implementation would use OCR
        # For now, return empty string
        return ""

    def _parse_directions(self, text: str) -> list[DirectionHint]:
        """Parse direction hints from text."""
        directions: list[DirectionHint] = []

        # Compass directions
        for pattern, dtype in self._COMPASS_PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(1).lower()
                directions.append(DirectionHint(
                    direction=dtype,
                    value=value,
                    original_text=match.group(0),
                    confidence=0.85,
                ))

        # Landmark directions
        for pattern, dtype in self._LANDMARK_PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(2) if len(match.groups()) > 1 else match.group(1)
                directions.append(DirectionHint(
                    direction=dtype,
                    value=value.strip(),
                    original_text=match.group(0),
                    confidence=0.75,
                ))

        # Distance directions
        for pattern, dtype in self._DISTANCE_PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(0)
                directions.append(DirectionHint(
                    direction=dtype,
                    value=value,
                    original_text=match.group(0),
                    confidence=0.70,
                ))

        # Region directions
        for pattern, dtype in self._REGION_PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(2)
                directions.append(DirectionHint(
                    direction=dtype,
                    value=value,
                    original_text=match.group(0),
                    confidence=0.80,
                ))

        return directions

    def _scale_roi(self, roi: tuple[int, int, int, int], sx: float, sy: float) -> tuple[int, int, int, int]:
        """Scale ROI by resolution multiplier."""
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))

    def get_navigation_hint(self, result: PaimonHintResult) -> str | None:
        """Convert Paimon hint to navigation command."""
        if not result.directions:
            return None

        # Priority: compass > landmark > region > distance
        for dtype in [DirectionType.COMPASS, DirectionType.LANDMARK, DirectionType.REGION]:
            for hint in result.directions:
                if hint.direction == dtype:
                    if dtype == DirectionType.COMPASS:
                        return f"Navigate {hint.value}"
                    elif dtype == DirectionType.LANDMARK:
                        return f"Go to the {hint.value}"
                    elif dtype == DirectionType.REGION:
                        return f"Head to {hint.value}"

        return None