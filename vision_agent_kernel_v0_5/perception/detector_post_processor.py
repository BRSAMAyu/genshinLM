"""Detector post-processor: wires YOLO detection + tracking into PerceptionPipeline.

Implements the FramePostProcessor protocol so that PerceptionPipeline
automatically populates observation.target_track on every frame.
"""
from __future__ import annotations

import logging

import numpy as np

from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import Observation, TargetTrack
from perception.ultralytics_tracker import UltralyticsTracker, UltralyticsTrackerConfig
from perception.yolo_detector import YoloDetector, YoloDetectorConfig

log = logging.getLogger(__name__)


class DetectionTrackingPostProcessor:
    """Runs YOLO detection + BoT-SORT tracking on each frame.

    Populates observation.target_track with the best-confidence tracked target.
    Falls back gracefully if ultralytics is not installed.
    """

    def __init__(
        self,
        detector_config: YoloDetectorConfig | None = None,
        tracker_config: UltralyticsTrackerConfig | None = None,
        timebase: Timebase | None = None,
        fallback_to_color: bool = True,
    ) -> None:
        self._detector_config = detector_config
        self._tracker_config = tracker_config
        self._timebase = timebase or Timebase()
        self._fallback_to_color = fallback_to_color

        # Lazy initialization — only create when first frame arrives
        self._detector: YoloDetector | None = None
        self._tracker: UltralyticsTracker | None = None
        self._initialized = False
        self._init_failed = False

    def process(self, frame: np.ndarray, observation: Observation, state_bus: StateBus) -> None:
        if self._init_failed:
            return

        if not self._initialized:
            self._initialized = True
            try:
                if self._tracker_config is not None:
                    self._tracker = UltralyticsTracker(
                        self._tracker_config, state_bus=state_bus, timebase=self._timebase,
                    )
                elif self._detector_config is not None:
                    self._detector = YoloDetector(
                        self._detector_config, state_bus=state_bus, timebase=self._timebase,
                    )
                log.info(
                    "[DetectionPostProcessor] initialized tracker=%s detector=%s",
                    self._tracker is not None, self._detector is not None,
                )
            except Exception as exc:
                self._init_failed = True
                log.warning("[DetectionPostProcessor] init failed: %s — target_track will be None", exc)
                return

        # Use tracker (preferred — does detection + tracking in one call)
        if self._tracker is not None:
            track = self._tracker.update(
                frame, frame_id=observation.frame_id, timestamp=observation.t_processed,
            )
            if track is not None:
                observation.target_track = track
            return

        # Fallback: detector only (no tracking persistence)
        if self._detector is not None:
            candidates = self._detector.safe_detect(frame, frame_id=observation.frame_id)
            if candidates:
                best = max(candidates, key=lambda c: c.confidence)
                observation.target_track = TargetTrack(
                    track_id="det_only",
                    class_id=best.class_id,
                    state="TRACKED",
                    bbox_xyxy=best.bbox_xyxy,
                    smoothed_center_px=best.center_px,
                    velocity_px_s=(0.0, 0.0),
                    confidence=best.confidence,
                    identity_confidence=best.confidence,
                    missing_duration_ms=0.0,
                    bearing_deg=None,
                    pitch_deg=None,
                    estimated_range=None,
                    last_seen_frame_id=best.frame_id,
                )
