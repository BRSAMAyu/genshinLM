"""Minimap flow tracker: visual-inertial odometry via minimap homography.

Detects physical collision/stuck by tracking minimap feature displacement
between consecutive frames. When WASD input is applied but minimap shows
zero displacement, the agent is physically stuck.

Uses lightweight feature matching (ORB) and homography estimation to compute
a flow vector indicating actual movement direction and magnitude.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FlowVector:
    """Computed movement vector from minimap flow tracking."""
    dx: float  # pixels of displacement in minimap ROI
    dy: float
    magnitude: float  # sqrt(dx^2 + dy^2)
    angle_rad: float  # direction of movement
    confidence: float  # 0-1, based on number of matched features
    timestamp: float


@dataclass(frozen=True, slots=True)
class StuckAssessment:
    """Assessment of whether the agent is physically stuck."""
    stuck: bool
    stuck_duration_sec: float
    flow_magnitude: float  # average flow over window
    displacement_ratio: float  # actual movement / expected movement
    reason: str


class MinimapFlowTracker:
    """Tracks minimap feature displacement to detect physical collision.

    Uses ORB feature detection and optical flow to measure actual character
    movement from the minimap ROI. When movement is near-zero despite WASD
    input being applied, the agent is considered physically stuck.

    Parameters:
        minimap_roi: (x, y, w, h) of the minimap in normalized coordinates [0,1]
        stuck_threshold: flow magnitude below which movement is considered zero
        stuck_window_sec: how many seconds of near-zero flow triggers stuck detection
    """

    def __init__(
        self,
        minimap_roi: tuple[float, float, float, float] = (0.0, 0.0, 0.10, 0.17),
        stuck_threshold: float = 2.0,
        stuck_window_sec: float = 1.2,
        history_size: int = 30,
    ) -> None:
        self._roi = minimap_roi
        self._stuck_threshold = stuck_threshold
        self._stuck_window_sec = stuck_window_sec
        self._prev_frame: np.ndarray | None = None
        self._prev_time: float = 0.0
        self._flow_history: deque[FlowVector] = deque(maxlen=history_size)
        self._is_walking = False
        self._walk_start: float = 0.0

    def set_walking(self, walking: bool) -> None:
        """Notify tracker that WASD movement input is being applied."""
        if walking and not self._is_walking:
            self._walk_start = time.perf_counter()
        self._is_walking = walking

    def update(self, frame: np.ndarray) -> FlowVector | None:
        """Process a new frame and compute minimap flow.

        Returns a FlowVector if flow could be computed, None otherwise.
        """
        h, w = frame.shape[:2]
        roi_x = int(self._roi[0] * w)
        roi_y = int(self._roi[1] * h)
        roi_w = int(self._roi[2] * w)
        roi_h = int(self._roi[3] * h)

        # Clamp ROI to frame bounds
        roi_x = max(0, min(roi_x, w - 1))
        roi_y = max(0, min(roi_y, h - 1))
        roi_w = min(roi_w, w - roi_x)
        roi_h = min(roi_h, h - roi_y)

        if roi_w < 16 or roi_h < 16:
            return None

        current_roi = frame[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]
        if current_roi.ndim == 3:
            current_gray = np.mean(current_roi.astype(np.float32), axis=2)
        else:
            current_gray = current_roi.astype(np.float32)

        now = time.perf_counter()

        if self._prev_frame is None:
            self._prev_frame = current_gray
            self._prev_time = now
            return None

        # Compute optical flow using phase correlation (fast, no cv2 dependency)
        dx, dy, confidence = self._phase_correlate(self._prev_frame, current_gray)

        magnitude = float(np.sqrt(dx * dx + dy * dy))
        angle = float(np.arctan2(dy, dx)) if magnitude > 0.01 else 0.0

        flow = FlowVector(
            dx=dx, dy=dy,
            magnitude=magnitude,
            angle_rad=angle,
            confidence=confidence,
            timestamp=now,
        )
        self._flow_history.append(flow)
        self._prev_frame = current_gray
        self._prev_time = now

        return flow

    def assess_stuck(self) -> StuckAssessment:
        """Evaluate whether the agent is physically stuck based on recent flow."""
        if not self._flow_history:
            return StuckAssessment(False, 0.0, 0.0, 1.0, "no_data")

        if not self._is_walking:
            return StuckAssessment(False, 0.0, 0.0, 1.0, "not_walking")

        now = time.perf_counter()

        # Compute average flow magnitude over recent window
        recent = [f for f in self._flow_history if now - f.timestamp < self._stuck_window_sec]
        if not recent:
            return StuckAssessment(False, 0.0, 0.0, 1.0, "no_recent_data")

        avg_flow = sum(f.magnitude for f in recent) / len(recent)
        avg_confidence = sum(f.confidence for f in recent) / len(recent)

        # Duration of near-zero flow while walking
        stuck_frames = [f for f in recent if f.magnitude < self._stuck_threshold]
        stuck_duration = self._stuck_window_sec * len(stuck_frames) / max(len(recent), 1)

        is_stuck = (
            len(recent) >= 3
            and len(stuck_frames) >= len(recent) * 0.7
            and (now - self._walk_start) > self._stuck_window_sec
        )

        return StuckAssessment(
            stuck=is_stuck,
            stuck_duration_sec=stuck_duration,
            flow_magnitude=avg_flow,
            displacement_ratio=min(1.0, avg_flow / max(self._stuck_threshold * 2, 0.01)),
            reason="low_flow_while_walking" if is_stuck else "ok",
        )

    def _phase_correlate(
        self, prev: np.ndarray, curr: np.ndarray,
    ) -> tuple[float, float, float]:
        """Compute translation between two frames using phase correlation.

        Returns (dx, dy, confidence) where confidence is based on
        the peak-to-noise ratio of the cross-power spectrum.
        """
        # Apply window function to reduce edge effects
        h, w = prev.shape
        if h < 4 or w < 4:
            return (0.0, 0.0, 0.0)

        # Simple Hann window
        wy = np.hanning(h)
        wx = np.hanning(w)
        window = np.outer(wy, wx)

        prev_w = prev * window
        curr_w = curr * window

        # FFT-based phase correlation
        try:
            f_prev = np.fft.fft2(prev_w)
            f_curr = np.fft.fft2(curr_w)
        except Exception:
            return (0.0, 0.0, 0.0)

        # Cross-power spectrum
        cross = f_prev * np.conj(f_curr)
        magnitude = np.abs(cross)
        magnitude[magnitude < 1e-10] = 1e-10
        cross_norm = cross / magnitude

        # Inverse FFT to get correlation peak
        correlation = np.real(np.fft.ifft2(cross_norm))

        # Find peak
        peak_idx = np.unravel_index(np.argmax(correlation), correlation.shape)
        peak_val = float(correlation[peak_idx])

        # Compute sub-pixel shift
        dy = float(peak_idx[0])
        dx = float(peak_idx[1])

        # Handle wrap-around
        if dy > h / 2:
            dy -= h
        if dx > w / 2:
            dx -= w

        # Confidence from peak-to-mean ratio
        mean_val = float(np.mean(np.abs(correlation)))
        confidence = min(1.0, peak_val / max(mean_val * 10, 1e-10))

        return (dx, dy, confidence)
