"""Seven-Star Temple (Statue of Seven) interaction detector.

P-55: Detects Seven-Star Temple interaction prompt and visual elements.
Identifies golden light pillar and statue outline for auto-walk interaction.

Visual indicators:
- Golden pillar of light emanating from statue
- Statue silhouette with glowing aura
- "交互" / "Interact" prompt
- Circular interaction zone
"""
from __future__ import annotations

import logging
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
class StatueDetection:
    """P-55: Seven-Star Temple detection result."""
    is_visible: bool
    position: tuple[float, float]     # Statue position in frame
    distance: Literal["far", "near", "interactable"]
    light_intensity: float            # Golden light pillar intensity
    prompt_visible: bool             # Interaction prompt visible
    confidence: float
    frame_id: int


@dataclass(frozen=True, slots=True)
class StatueStatus:
    """Overall statue interaction status."""
    statue_detected: StatueDetection | None
    is_in_interaction_range: bool
    prompt_required: str              # Action to take


class StatueDetector:
    """Detect Seven-Star Temple interaction opportunities.

    Features:
    - Golden light pillar detection
    - Statue silhouette recognition
    - Distance estimation
    - Interaction prompt detection

    Detection: Golden/yellow color + pillar shape + interaction UI
    """

    _REF_W = 1920
    _REF_H = 1080

    # Golden light pillar colors
    _PILLAR_GOLD_LOW = np.array([15, 100, 200])
    _PILLAR_GOLD_HIGH = np.array([40, 255, 255])

    # Statue glow colors (white/gold aura)
    _AURA_GOLD_LOW = np.array([18, 80, 180])
    _AURA_GOLD_HIGH = np.array([35, 255, 255])

    # Prompt colors (white text on dark background)
    _PROMPT_WHITE_LOW = np.array([0, 0, 200])
    _PROMPT_WHITE_HIGH = np.array([180, 30, 255])

    # Detection parameters
    MIN_PILLAR_PIXELS = 800
    MIN_AURA_PIXELS = 300

    # ROI for statue detection (lower center for ground-level statues)
    _STATUE_SEARCH_ROI = (0.2, 0.3, 0.8, 0.9)

    def __init__(self, now_fn=None) -> None:
        """Initialize statue detector.

        Args:
            now_fn: Time function (default: time.perf_counter)
        """
        self._now_fn = now_fn or time.perf_counter
        self._last_detection: StatueDetection | None = None
        self._frame_count: int = 0

    @property
    def last_detection(self) -> StatueDetection | None:
        """Get last statue detection."""
        return self._last_detection

    def detect(
        self,
        frame: np.ndarray,
        frame_id: int,
    ) -> StatueDetection:
        """Detect Seven-Star Temple in frame.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID

        Returns:
            StatueDetection with statue information
        """
        if cv2 is None or frame.size == 0:
            return StatueDetection(
                is_visible=False,
                position=(0.0, 0.0),
                distance="far",
                light_intensity=0.0,
                prompt_visible=False,
                confidence=0.0,
                frame_id=frame_id,
            )

        self._frame_count = frame_id

        # Get search ROI
        roi = self._get_search_roi(frame)
        if roi.size == 0:
            return self._make_no_detection(frame_id)

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Detect golden light pillar
        pillar_mask = cv2.inRange(hsv, self._PILLAR_GOLD_LOW, self._PILLAR_GOLD_HIGH)
        pillar_pixels = cv2.countNonZero(pillar_mask)

        # Detect statue aura
        aura_mask = cv2.inRange(hsv, self._AURA_GOLD_LOW, self._AURA_GOLD_HIGH)
        aura_pixels = cv2.countNonZero(aura_mask)

        # Check for interaction prompt
        prompt_mask = cv2.inRange(hsv, self._PROMPT_WHITE_LOW, self._PROMPT_WHITE_HIGH)
        prompt_pixels = cv2.countNonZero(prompt_mask)
        prompt_visible = prompt_pixels > 100

        # Calculate presence
        is_visible = (
            pillar_pixels >= self.MIN_PILLAR_PIXELS or
            aura_pixels >= self.MIN_AURA_PIXELS
        )

        if is_visible:
            # Calculate position
            position = self._calculate_statue_position(
                pillar_mask if pillar_pixels > aura_pixels else aura_mask,
            )

            # Estimate distance
            distance = self._estimate_distance(
                pillar_pixels + aura_pixels,
            )

            # Calculate light intensity
            total_pixels = pillar_pixels + aura_pixels
            light_intensity = min(total_pixels / 5000.0, 1.0)

            # Calculate confidence
            confidence = min(light_intensity * 2, 1.0)

            self._last_detection = StatueDetection(
                is_visible=True,
                position=position,
                distance=distance,
                light_intensity=light_intensity,
                prompt_visible=prompt_visible,
                confidence=confidence,
                frame_id=frame_id,
            )
        else:
            self._last_detection = self._make_no_detection(frame_id)

        return self._last_detection

    def _get_search_roi(self, frame: np.ndarray) -> np.ndarray:
        """Get search region for statue detection."""
        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1, y1, x2, y2 = self._STATUE_SEARCH_ROI
        x1 = int(x1 * sx * self._REF_W)
        y1 = int(y1 * sy * self._REF_H)
        x2 = int(x2 * sx * self._REF_W)
        y2 = int(y2 * sy * self._REF_H)

        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        return frame[y1:y2, x1:x2]

    def _calculate_statue_position(self, mask: np.ndarray) -> tuple[float, float]:
        """Calculate statue position from detected mask."""
        moments = cv2.moments(mask)
        if moments["m00"] > 0:
            cx = moments["m10"] / moments["m00"]
            cy = moments["m01"] / moments["m00"]
        else:
            # Fallback to center
            h, w = mask.shape[:2]
            cx, cy = w // 2, h // 2

        return (float(cx), float(cy))

    def _estimate_distance(
        self,
        pixel_count: int,
    ) -> Literal["far", "near", "interactable"]:
        """Estimate distance to statue based on detection size."""
        if pixel_count >= 5000:
            return "interactable"
        elif pixel_count >= 2000:
            return "near"
        else:
            return "far"

    def _make_no_detection(self, frame_id: int) -> StatueDetection:
        """Create a no-detection result."""
        return StatueDetection(
            is_visible=False,
            position=(0.0, 0.0),
            distance="far",
            light_intensity=0.0,
            prompt_visible=False,
            confidence=0.0,
            frame_id=frame_id,
        )

    def get_status(self, frame_id: int) -> StatueStatus:
        """Get overall statue interaction status."""
        detection = self._last_detection

        if detection is None or not detection.is_visible:
            return StatueStatus(
                statue_detected=None,
                is_in_interaction_range=False,
                prompt_required="none",
            )

        is_in_range = detection.distance in ("near", "interactable")

        prompt = "none"
        if detection.prompt_visible:
            prompt = "press_f_to_interact"
        elif detection.distance == "interactable":
            prompt = "approach_statue"
        elif detection.distance == "near":
            prompt = "move_closer"

        return StatueStatus(
            statue_detected=detection,
            is_in_interaction_range=is_in_range,
            prompt_required=prompt,
        )

    def is_statue_visible(self) -> bool:
        """Quick check if statue is visible."""
        return self._last_detection is not None and self._last_detection.is_visible

    def is_in_range(self) -> bool:
        """Check if in interaction range."""
        if self._last_detection is None:
            return False
        return self._last_detection.distance in ("near", "interactable")

    def should_interact(self) -> bool:
        """Check if interaction should happen."""
        if self._last_detection is None:
            return False
        return (
            self._last_detection.prompt_visible and
            self._last_detection.distance == "interactable"
        )

    def reset(self) -> None:
        """Reset detector state."""
        self._last_detection = None
        self._frame_count = 0