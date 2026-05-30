"""Q-33: Cutscene skip handler.

Detects and handles skip options for skippable cutscenes,
tracking which cutscenes have been seen before.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CutsceneInfo:
    """Information about a detected cutscene."""
    cutscene_id: str | None
    title: str | None
    duration_seconds: float | None
    is_skippable: bool
    is_first_time: bool
    skip_available: bool


@dataclass(frozen=True, slots=True)
class SkipAction:
    """Action to take regarding cutscene."""
    action: str  # "watch", "skip", "auto_skip"
    reason: str
    expected_savings_seconds: float


class CutsceneSkipHandler:
    """Handle cutscene detection and skipping."""

    _REF_W = 1920
    _REF_H = 1080

    # Skip button colors (typically white or blue)
    _SKIP_BUTTON_LOW = np.array([0, 0, 200], dtype=np.uint8)
    _SKIP_BUTTON_HIGH = np.array([180, 20, 255], dtype=np.uint8)

    # Skip text colors
    _SKIP_TEXT_LOW = np.array([0, 0, 220], dtype=np.uint8)
    _SKIP_TEXT_HIGH = np.array([180, 10, 255], dtype=np.uint8)

    # Dialogue indicator (cutscenes typically have dialogue)
    _DIALOGUE_LOW = np.array([0, 0, 100], dtype=np.uint8)
    _DIALOGUE_HIGH = np.array([180, 30, 200], dtype=np.uint8)

    def __init__(
        self,
        seen_cutscenes: dict[str, float] | None = None,
        auto_skip_preference: bool = True,
        on_cutscene_start: Any = None,
        on_cutscene_skip: Any = None,
    ) -> None:
        """Initialize cutscene handler.

        Args:
            seen_cutscenes: Dict mapping cutscene ID to last seen timestamp
            auto_skip_preference: Automatically skip known cutscenes
            on_cutscene_start: Callback when cutscene starts
            on_cutscene_skip: Callback when cutscene is skipped
        """
        self._seen_cutscenes = seen_cutscenes or {}
        self._auto_skip = auto_skip_preference
        self._on_cutscene_start = on_cutscene_start
        self._on_cutscene_skip = on_cutscene_skip

        self._current_cutscene: CutsceneInfo | None = None
        self._cutscene_start_time: float = 0.0

    def detect_cutscene(
        self,
        frame: np.ndarray,
        frame_id: int = 0,
    ) -> CutsceneInfo | None:
        """Detect if currently in a cutscene.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            CutsceneInfo if cutscene detected, None otherwise
        """
        if cv2 is None:
            return None

        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Check for dialogue (common in cutscenes)
        dialogue_mask = cv2.inRange(hsv, self._DIALOGUE_LOW, self._DIALOGUE_HIGH)
        dialogue_pixels = cv2.countNonZero(dialogue_mask)
        has_dialogue = dialogue_pixels > 5000

        # Check for skip button
        skip_mask = cv2.inRange(hsv, self._SKIP_BUTTON_LOW, self._SKIP_BUTTON_HIGH)
        skip_pixels = cv2.countNonZero(skip_mask)
        has_skip_button = skip_pixels > 100

        # Check for skip text
        text_mask = cv2.inRange(hsv, self._SKIP_TEXT_LOW, self._SKIP_TEXT_HIGH)
        text_pixels = cv2.countNonZero(text_mask)
        has_skip_text = text_pixels > 50

        skip_available = has_skip_button or has_skip_text

        # Not in cutscene
        if not has_dialogue and not skip_available:
            if self._current_cutscene is not None:
                self._end_cutscene()
            return None

        # Start tracking cutscene
        if self._current_cutscene is None:
            self._start_cutscene()

        # Determine if first time seen
        cutscene_id = self._current_cutscene.cutscene_id if self._current_cutscene else None
        is_first_time = cutscene_id not in self._seen_cutscenes if cutscene_id else True

        # Estimate duration (if not known)
        duration = None
        if cutscene_id in self._seen_cutscenes:
            # Use previous duration as estimate
            duration = 30.0  # Default

        # Check if skippable
        is_skippable = skip_available

        return CutsceneInfo(
            cutscene_id=cutscene_id,
            title=None,
            duration_seconds=duration,
            is_skippable=is_skippable,
            is_first_time=is_first_time,
            skip_available=skip_available,
        )

    def _start_cutscene(self) -> None:
        """Start tracking a cutscene."""
        self._cutscene_start_time = time.perf_counter()
        self._current_cutscene = CutsceneInfo(
            cutscene_id=None,
            title=None,
            duration_seconds=None,
            is_skippable=False,
            is_first_time=True,
            skip_available=False,
        )
        log.info("[CutsceneSkip] Cutscene started")

        if self._on_cutscene_start:
            try:
                self._on_cutscene_start()
            except Exception as exc:
                log.warning("[CutsceneSkip] Start callback failed: %s", exc)

    def _end_cutscene(self) -> None:
        """End cutscene tracking."""
        if self._current_cutscene and self._current_cutscene.cutscene_id:
            self._seen_cutscenes[self._current_cutscene.cutscene_id] = time.perf_counter()
            log.info("[CutsceneSkip] Cutscene ended: %s", self._current_cutscene.cutscene_id)

        self._current_cutscene = None
        self._cutscene_start_time = 0.0

    def register_cutscene(
        self,
        cutscene_id: str,
        title: str | None = None,
        duration_seconds: float | None = None,
        is_skippable: bool = True,
    ) -> None:
        """Register a known cutscene for tracking.

        Args:
            cutscene_id: Unique identifier for the cutscene
            title: Optional display title
            duration_seconds: Known duration
            is_skippable: Whether this cutscene is skippable
        """
        self._current_cutscene = CutsceneInfo(
            cutscene_id=cutscene_id,
            title=title,
            duration_seconds=duration_seconds,
            is_skippable=is_skippable,
            is_first_time=cutscene_id not in self._seen_cutscenes,
            skip_available=is_skippable,
        )
        log.debug("[CutsceneSkip] Registered cutscene: %s", cutscene_id)

    def get_skip_decision(self, cutscene: CutsceneInfo) -> SkipAction:
        """Get decision on whether to skip the cutscene.

        Args:
            cutscene: Cutscene information

        Returns:
            SkipAction with decision and reason
        """
        if not cutscene.is_skippable:
            return SkipAction(
                action="watch",
                reason="Cutscene is not skippable",
                expected_savings_seconds=0.0,
            )

        # First time seeing - watch it
        if cutscene.is_first_time:
            return SkipAction(
                action="watch",
                reason="First time seeing this cutscene",
                expected_savings_seconds=0.0,
            )

        # Auto-skip preference
        if self._auto_skip:
            savings = cutscene.duration_seconds or 30.0
            return SkipAction(
                action="skip",
                reason="Auto-skip known cutscene",
                expected_savings_seconds=savings,
            )

        # Manual preference
        return SkipAction(
            action="watch",
            reason="User preference to watch cutscenes",
            expected_savings_seconds=0.0,
        )

    def record_skip(self, cutscene_id: str) -> None:
        """Record that a cutscene was skipped.

        Args:
            cutscene_id: ID of skipped cutscene
        """
        log.info("[CutsceneSkip] Cutscene skipped: %s", cutscene_id)

        if self._on_cutscene_skip:
            try:
                self._on_cutscene_skip(cutscene_id)
            except Exception as exc:
                log.warning("[CutsceneSkip] Skip callback failed: %s", exc)

    def get_skip_button_position(self, frame: np.ndarray) -> tuple[int, int] | None:
        """Get position of skip button for clicking.

        Args:
            frame: Current frame

        Returns:
            Button center position or None
        """
        if cv2 is None:
            return None

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        skip_mask = cv2.inRange(hsv, self._SKIP_BUTTON_LOW, self._SKIP_BUTTON_HIGH)

        contours, _ = cv2.findContours(skip_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            area = cv2.contourArea(contour)
            if 100 < area < 5000:
                M = cv2.moments(contour)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    return (cx, cy)

        return None

    def get_seen_count(self) -> int:
        """Get number of seen cutscenes."""
        return len(self._seen_cutscenes)

    def reset(self) -> None:
        """Reset handler state."""
        self._current_cutscene = None
        self._cutscene_start_time = 0.0
        log.info("[CutsceneSkipHandler] Handler reset")