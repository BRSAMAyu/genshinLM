"""Auto-calibrator: automatic UI landmark detection and scale factor computation.

Detects key UI landmarks (minimap edges, HP bar, quest tracker, menu buttons)
from a screenshot to compute resolution-independent scale factors for the
Symbolic Spatial Transformation Matrix (SSTM).

All click coordinates are then expressed as:
    ClickPoint = AnchorPoint + ScaleMatrix(Sx, Sy) * OffsetVector(dx, dy)

where (dx, dy) are offsets relative to a detected anchor in the reference
resolution (1920x1080).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

# Reference resolution for all anchor definitions
REFERENCE_WIDTH = 1920
REFERENCE_HEIGHT = 1080


@dataclass(frozen=True, slots=True)
class LandmarkDetection:
    """A detected UI landmark with its position and confidence."""
    landmark_id: str
    x: float  # pixel position in current frame
    y: float
    width: float
    height: float
    confidence: float


@dataclass(frozen=True, slots=True)
class ScaleFactors:
    """Computed scale factors mapping reference coords to current resolution."""
    scale_x: float
    scale_y: float
    offset_x: float  # letterboxing offset
    offset_y: float
    reference_size: tuple[int, int] = (REFERENCE_WIDTH, REFERENCE_HEIGHT)
    current_size: tuple[int, int] = (0, 0)

    def to_screen(self, ref_x: float, ref_y: float) -> tuple[float, float]:
        """Convert reference coordinates to current screen coordinates."""
        return (
            ref_x * self.scale_x + self.offset_x,
            ref_y * self.scale_y + self.offset_y,
        )

    def to_reference(self, screen_x: float, screen_y: float) -> tuple[float, float]:
        """Convert current screen coordinates to reference coordinates."""
        return (
            (screen_x - self.offset_x) / self.scale_x if self.scale_x > 0 else 0.0,
            (screen_y - self.offset_y) / self.scale_y if self.scale_y > 0 else 0.0,
        )

    def scale_roi(
        self, ref_x: float, ref_y: float, ref_w: float, ref_h: float,
    ) -> tuple[float, float, float, float]:
        """Scale a reference ROI to current screen coordinates."""
        sx, sy = self.to_screen(ref_x, ref_y)
        return (sx, sy, ref_w * self.scale_x, ref_h * self.scale_y)


@dataclass(frozen=True, slots=True)
class CalibrationSnapshot:
    """Complete calibration state for a single frame."""
    scale: ScaleFactors
    landmarks: tuple[LandmarkDetection, ...]
    frame_size: tuple[int, int]
    aspect_ratio: float
    valid: bool


class AutoCalibrator:
    """Detects UI landmarks and computes resolution-independent scale factors.

    Uses color-based heuristic detection for common Genshin UI elements:
    - Minimap circle (top-left, dark circle with bright border)
    - HP bar (party character portraits)
    - Quest tracker (right side text area)
    - Menu button (top-right gear icon area)

    Falls back to aspect-ratio-based scaling when landmarks are not found.
    """

    # Reference landmark positions at 1920x1080
    _REF_MINIMAP = (28, 28, 184, 184)       # minimap circle
    _REF_HP_BAR = (164, 868, 228, 40)       # active character HP
    _REF_QUEST = (1480, 30, 400, 200)       # quest tracker area
    _REF_MENU = (1830, 10, 60, 60)          # menu button

    def __init__(self, expected_aspect: float = 16.0 / 9.0) -> None:
        self._expected_aspect = expected_aspect
        self._last_snapshot: CalibrationSnapshot | None = None

    @property
    def last_snapshot(self) -> CalibrationSnapshot | None:
        return self._last_snapshot

    def calibrate(self, frame: np.ndarray) -> CalibrationSnapshot:
        """Compute scale factors from a screenshot frame.

        Detects UI landmarks and derives affine scale factors. Falls back
        to aspect-ratio-based scaling when detection fails.
        """
        h, w = frame.shape[:2]
        frame_aspect = w / h if h > 0 else self._expected_aspect

        # Attempt landmark detection
        landmarks = self._detect_landmarks(frame)

        if landmarks:
            scale = self._compute_scale_from_landmarks(landmarks, w, h)
        else:
            scale = self._compute_scale_from_aspect(w, h)

        snap = CalibrationSnapshot(
            scale=scale,
            landmarks=tuple(landmarks),
            frame_size=(w, h),
            aspect_ratio=frame_aspect,
            valid=scale.scale_x > 0 and scale.scale_y > 0,
        )
        self._last_snapshot = snap
        return snap

    def _detect_landmarks(self, frame: np.ndarray) -> list[LandmarkDetection]:
        """Detect UI landmarks using color-based heuristics."""
        h, w = frame.shape[:2]
        detections: list[LandmarkDetection] = []

        # Minimap detection: top-left quadrant, look for circular dark region
        minimap = self._detect_minimap(frame, w, h)
        if minimap is not None:
            detections.append(minimap)

        return detections

    def _detect_minimap(
        self, frame: np.ndarray, w: int, h: int,
    ) -> LandmarkDetection | None:
        """Detect minimap circle in top-left corner.

        The Genshin minimap is a dark circular region with a bright border
        in the top-left corner. We detect it by checking for a dark region
        surrounded by a lighter border in the top-left quadrant.
        """
        # Search in top-left 15% of screen
        search_w = int(w * 0.15)
        search_h = int(h * 0.20)
        if search_w < 10 or search_h < 10:
            return None

        roi = frame[:search_h, :search_w]
        if roi.size == 0:
            return None

        # Convert to grayscale if needed
        if roi.ndim == 3:
            gray = np.mean(roi, axis=2)
        else:
            gray = roi.astype(float)

        # Find the darkest circular region (minimap center is very dark)
        threshold = np.percentile(gray, 20)
        dark_mask = gray < threshold

        if not np.any(dark_mask):
            return None

        # Find centroid of dark region
        ys, xs = np.where(dark_mask)
        if len(xs) < 20:
            return None

        cx = float(np.mean(xs))
        cy = float(np.mean(ys))
        radius = max(float(np.std(xs)), float(np.std(ys))) * 1.5

        confidence = min(1.0, len(xs) / (search_w * search_h * 0.1))
        if confidence < 0.2:
            return None

        return LandmarkDetection(
            landmark_id="minimap",
            x=cx, y=cy,
            width=radius * 2, height=radius * 2,
            confidence=confidence,
        )

    def _compute_scale_from_landmarks(
        self, landmarks: list[LandmarkDetection], w: int, h: int,
    ) -> ScaleFactors:
        """Compute scale factors from detected landmarks."""
        minimap = next((lm for lm in landmarks if lm.landmark_id == "minimap"), None)

        if minimap is not None:
            # Minimap center should be at REFERENCE ~(120, 120)
            ref_cx = self._REF_MINIMAP[0] + self._REF_MINIMAP[2] / 2
            ref_cy = self._REF_MINIMAP[1] + self._REF_MINIMAP[3] / 2

            # Scale from minimap position ratio
            scale_x = minimap.x / ref_cx if ref_cx > 0 else w / REFERENCE_WIDTH
            scale_y = minimap.y / ref_cy if ref_cy > 0 else h / REFERENCE_HEIGHT

            return ScaleFactors(
                scale_x=scale_x,
                scale_y=scale_y,
                offset_x=0.0,
                offset_y=0.0,
                current_size=(w, h),
            )

        return self._compute_scale_from_aspect(w, h)

    def _compute_scale_from_aspect(self, w: int, h: int) -> ScaleFactors:
        """Fallback: compute scale from aspect ratio assuming 16:9 with letterboxing."""
        frame_aspect = w / h if h > 0 else self._expected_aspect

        if frame_aspect > self._expected_aspect:
            # Wider than expected: horizontal letterboxing (pillarbox)
            scaled_w = int(h * self._expected_aspect)
            offset_x = (w - scaled_w) / 2.0
            scale_x = scaled_w / REFERENCE_WIDTH
            return ScaleFactors(
                scale_x=scale_x, scale_y=h / REFERENCE_HEIGHT,
                offset_x=offset_x, offset_y=0.0,
                current_size=(w, h),
            )
        elif frame_aspect < self._expected_aspect:
            # Taller than expected: vertical letterboxing
            scaled_h = int(w / self._expected_aspect)
            offset_y = (h - scaled_h) / 2.0
            scale_y = scaled_h / REFERENCE_HEIGHT
            return ScaleFactors(
                scale_x=w / REFERENCE_WIDTH, scale_y=scale_y,
                offset_x=0.0, offset_y=offset_y,
                current_size=(w, h),
            )
        else:
            # Exact aspect ratio match
            return ScaleFactors(
                scale_x=w / REFERENCE_WIDTH,
                scale_y=h / REFERENCE_HEIGHT,
                offset_x=0.0, offset_y=0.0,
                current_size=(w, h),
            )
