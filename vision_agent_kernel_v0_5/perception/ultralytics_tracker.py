from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import TargetTrack


@dataclass(frozen=True, slots=True)
class UltralyticsTrackerConfig:
    model_path: str
    tracker: str = "botsort.yaml"
    conf_threshold: float = 0.35
    iou_threshold: float = 0.5
    device: str | None = None
    half: bool = False
    persist: bool = True
    coasting_timeout_ms: float = 500.0
    lost_timeout_ms: float = 3000.0


class UltralyticsTracker:
    def __init__(
        self,
        config: UltralyticsTrackerConfig,
        state_bus: StateBus | None = None,
        timebase: Timebase | None = None,
        model: Any | None = None,
    ) -> None:
        self._config = config
        self._state_bus = state_bus
        self._timebase = timebase or Timebase()
        self._model = model
        self._last_track: TargetTrack | None = None
        self._last_timestamp: float | None = None

    def update(self, frame: np.ndarray, frame_id: int, timestamp: float) -> TargetTrack | None:
        try:
            model = self._load_model()
            results = model.track(
                frame,
                tracker=self._config.tracker,
                persist=self._config.persist,
                conf=self._config.conf_threshold,
                iou=self._config.iou_threshold,
                device=self._config.device,
                half=self._config.half,
                verbose=False,
            )
            track = self._results_to_track(results, frame_id=frame_id, timestamp=timestamp)
            if track is not None:
                self._last_track = track
                self._last_timestamp = timestamp
            else:
                track = self._coast_or_lost(frame_id=frame_id, timestamp=timestamp)
            print(
                "[UltralyticsTracker] "
                f"frame_id={frame_id} track_id={track.track_id if track else None} "
                f"state={track.state if track else None}",
                flush=True,
            )
            return track
        except Exception as exc:
            self._publish_error(frame_id=frame_id, exc=exc)
            return self._coast_or_lost(frame_id=frame_id, timestamp=timestamp)

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("ultralytics is not installed") from exc
        self._model = YOLO(self._config.model_path)
        print(
            "[UltralyticsTracker] "
            f"loaded model_path={self._config.model_path} tracker={self._config.tracker}",
            flush=True,
        )
        return self._model

    def _results_to_track(self, results: Any, frame_id: int, timestamp: float) -> TargetTrack | None:
        if not results:
            return None
        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return None
        names = getattr(result, "names", None) or getattr(self._load_model(), "names", {})
        chosen = max(boxes, key=lambda box: float(self._to_float_list(box.conf)[0]))
        xyxy = self._to_float_list(chosen.xyxy[0])
        confidence = float(self._to_float_list(chosen.conf)[0])
        class_index = int(self._to_float_list(chosen.cls)[0])
        class_id = str(names.get(class_index, class_index)) if isinstance(names, dict) else str(class_index)
        track_id = self._extract_track_id(chosen)
        x1, y1, x2, y2 = xyxy
        center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
        velocity = self._estimate_velocity(track_id=track_id, center=center, timestamp=timestamp)
        return TargetTrack(
            track_id=track_id,
            class_id=class_id,
            state="TRACKED",
            bbox_xyxy=(x1, y1, x2, y2),
            smoothed_center_px=center,
            velocity_px_s=velocity,
            confidence=confidence,
            identity_confidence=1.0 if track_id != "untracked" else confidence,
            missing_duration_ms=0.0,
            bearing_deg=None,
            pitch_deg=None,
            estimated_range=None,
            last_seen_frame_id=frame_id,
        )

    def _coast_or_lost(self, frame_id: int, timestamp: float) -> TargetTrack | None:
        if self._last_track is None or self._last_timestamp is None:
            return None
        missing_ms = (timestamp - self._last_timestamp) * 1000.0
        state = "COASTING" if missing_ms <= self._config.lost_timeout_ms else "LOST"
        center = self._last_track.smoothed_center_px
        if center is not None and state == "COASTING":
            dt = min(missing_ms / 1000.0, self._config.coasting_timeout_ms / 1000.0)
            center = (
                center[0] + self._last_track.velocity_px_s[0] * dt,
                center[1] + self._last_track.velocity_px_s[1] * dt,
            )
        return TargetTrack(
            track_id=self._last_track.track_id,
            class_id=self._last_track.class_id,
            state=state,
            bbox_xyxy=self._last_track.bbox_xyxy,
            smoothed_center_px=center,
            velocity_px_s=self._last_track.velocity_px_s,
            confidence=max(0.0, self._last_track.confidence * 0.5),
            identity_confidence=max(0.0, self._last_track.identity_confidence * 0.5),
            missing_duration_ms=missing_ms,
            bearing_deg=self._last_track.bearing_deg,
            pitch_deg=self._last_track.pitch_deg,
            estimated_range=self._last_track.estimated_range,
            last_seen_frame_id=frame_id,
            appearance_signature=self._last_track.appearance_signature,
        )

    def _estimate_velocity(
        self,
        track_id: str,
        center: tuple[float, float],
        timestamp: float,
    ) -> tuple[float, float]:
        if (
            self._last_track is None
            or self._last_timestamp is None
            or self._last_track.track_id != track_id
            or self._last_track.smoothed_center_px is None
        ):
            return (0.0, 0.0)
        dt = max(timestamp - self._last_timestamp, 1e-6)
        previous = self._last_track.smoothed_center_px
        return ((center[0] - previous[0]) / dt, (center[1] - previous[1]) / dt)

    def _extract_track_id(self, box: Any) -> str:
        track_id = getattr(box, "id", None)
        if track_id is None:
            return "untracked"
        values = self._to_float_list(track_id)
        return str(int(values[0])) if values else "untracked"

    def _to_float_list(self, value: Any) -> list[float]:
        if hasattr(value, "detach"):
            value = value.detach()
        if hasattr(value, "cpu"):
            value = value.cpu()
        if hasattr(value, "numpy"):
            value = value.numpy()
        return np.asarray(value, dtype=float).reshape(-1).tolist()

    def _publish_error(self, frame_id: int, exc: Exception) -> None:
        now = self._timebase.now()
        print(
            "[UltralyticsTracker] "
            f"{now:.6f} tracker error frame_id={frame_id} error={exc!r}",
            flush=True,
        )
        if self._state_bus is None:
            return
        self._state_bus.publish_interrupt(
            Interrupt(
                priority=1,
                timestamp=now,
                code="TRACKER_ERROR",
                source="ultralytics_tracker",
                frame_id=frame_id,
                payload={"error": repr(exc)},
                recoverable=True,
            )
        )
