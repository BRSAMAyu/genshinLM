from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.types import TargetTrack


@dataclass(frozen=True, slots=True)
class VisualTriggerDetectorConfig:
    viewport_size: tuple[int, int] = (1280, 720)
    centered_threshold_px: float = 320.0
    min_component_area_px: int = 200
    nominal_target_area_px: float = 64.0 * 64.0
    in_range_min_area_px: float = 36.0 * 36.0


@dataclass(frozen=True, slots=True)
class ColorTargetRegion:
    color_state: str
    bbox_xyxy: tuple[float, float, float, float]
    center_px: tuple[float, float]
    area_px: float
    confidence: float


class VisualTriggerDetector:
    """Detects visual trigger conditions from the current normalized frame."""

    def __init__(self, config: VisualTriggerDetectorConfig | None = None) -> None:
        self._config = config or VisualTriggerDetectorConfig()

    def detect_target(self, frame: np.ndarray, frame_id: int, timestamp: float) -> TargetTrack | None:
        tracks = self.detect_targets(frame, frame_id, timestamp)
        if not tracks:
            return None
        return tracks[0]

    def detect_targets(self, frame: np.ndarray, frame_id: int, timestamp: float) -> list[TargetTrack]:
        del timestamp
        regions = self.detect_color_regions(frame)
        tracks: list[TargetTrack] = []
        for index, region in enumerate(regions):
            tracks.append(self._region_to_track(region, frame_id, index))
        return tracks

    def _region_to_track(self, region: ColorTargetRegion, frame_id: int, index: int) -> TargetTrack:
        return TargetTrack(
            track_id="color-target" if index == 0 else f"color-target-candidate-{index}",
            class_id=f"{region.color_state.lower()}_block",
            state="TRACKED",
            bbox_xyxy=region.bbox_xyxy,
            smoothed_center_px=region.center_px,
            velocity_px_s=(0.0, 0.0),
            confidence=region.confidence,
            identity_confidence=region.confidence,
            missing_duration_ms=0.0,
            bearing_deg=None,
            pitch_deg=None,
            estimated_range=self._estimated_range(region.area_px),
            last_seen_frame_id=frame_id,
            appearance_signature={"color_state": region.color_state},
        )

    def detect_color_region(self, frame: np.ndarray) -> ColorTargetRegion | None:
        regions = self.detect_color_regions(frame)
        return regions[0] if regions else None

    def detect_color_regions(self, frame: np.ndarray) -> list[ColorTargetRegion]:
        if frame.ndim != 3 or frame.shape[2] < 3:
            return []
        regions = self._regions(frame, "GREEN") + self._regions(frame, "RED")
        return sorted(regions, key=lambda region: region.area_px, reverse=True)

    def detect_triggers(
        self,
        frame: np.ndarray | None,
        track: TargetTrack | None,
    ) -> dict[str, bool]:
        region = self.detect_color_region(frame) if frame is not None else None
        effective_track = track
        if effective_track is None and region is not None:
            effective_track = TargetTrack(
                track_id="color-target",
                class_id=f"{region.color_state.lower()}_block",
                state="TRACKED",
                bbox_xyxy=region.bbox_xyxy,
                smoothed_center_px=region.center_px,
                velocity_px_s=(0.0, 0.0),
                confidence=region.confidence,
                identity_confidence=region.confidence,
                missing_duration_ms=0.0,
                bearing_deg=None,
                pitch_deg=None,
                estimated_range=self._estimated_range(region.area_px),
                last_seen_frame_id=0,
                appearance_signature={"color_state": region.color_state},
            )

        green = self._is_green(effective_track, region)
        visible = (
            green
            or effective_track is not None
            and effective_track.state in {"TRACKED", "COASTING"}
        )
        # In the pseudo3d testbed, GREEN is an authoritative visual state emitted
        # only after the target has stayed near center long enough.
        centered = green or self._is_centered(effective_track)
        in_range = self._in_range_estimated(effective_track)
        return {
            "target_visible": visible,
            "target_centered": centered,
            "target_visible_and_centered": visible and centered,
            "target_color_green": green,
            "in_range_estimated": in_range,
            "visual_action_completed": green,
        }

    def _largest_region(self, frame: np.ndarray, color_state: str) -> ColorTargetRegion | None:
        regions = self._regions(frame, color_state)
        return regions[0] if regions else None

    def _regions(self, frame: np.ndarray, color_state: str) -> list[ColorTargetRegion]:
        mask = self._color_mask(frame, color_state)
        if int(mask.sum()) < self._config.min_component_area_px:
            return []
        regions: list[ColorTargetRegion] = []
        for x1, y1, x2, y2, area in self._connected_component_bboxes(mask):
            if area < self._config.min_component_area_px:
                continue
            center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
            confidence = min(1.0, area / max(self._config.nominal_target_area_px, 1.0))
            regions.append(
                ColorTargetRegion(
                    color_state=color_state,
                    bbox_xyxy=(float(x1), float(y1), float(x2), float(y2)),
                    center_px=center,
                    area_px=float(area),
                    confidence=confidence,
                )
            )
        return sorted(regions, key=lambda region: region.area_px, reverse=True)

    def _color_mask(self, frame: np.ndarray, color_state: str) -> np.ndarray:
        c0 = frame[:, :, 0].astype(np.int16)
        c1 = frame[:, :, 1].astype(np.int16)
        c2 = frame[:, :, 2].astype(np.int16)
        if color_state == "GREEN":
            return (c1 > 110) & (c1 > c0 + 50) & (c1 > c2 + 50)
        rgb_red = (c0 > 110) & (c0 > c1 + 50) & (c0 > c2 + 50)
        bgr_red = (c2 > 110) & (c2 > c1 + 50) & (c2 > c0 + 50)
        return rgb_red if int(rgb_red.sum()) >= int(bgr_red.sum()) else bgr_red

    def _connected_component_bbox(self, mask: np.ndarray) -> tuple[int, int, int, int, int] | None:
        bboxes = self._connected_component_bboxes(mask)
        return bboxes[0] if bboxes else None

    def _connected_component_bboxes(self, mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
        try:
            import cv2  # type: ignore[import-not-found]
        except ImportError:
            y_indices, x_indices = np.where(mask)
            if len(x_indices) == 0:
                return []
            return [(
                int(x_indices.min()),
                int(y_indices.min()),
                int(x_indices.max()),
                int(y_indices.max()),
                int(len(x_indices)),
            )]

        labels_count, labels, stats, _ = cv2.connectedComponentsWithStats(
            mask.astype(np.uint8),
            connectivity=8,
        )
        if labels_count <= 1:
            return []
        bboxes: list[tuple[int, int, int, int, int]] = []
        for index in range(1, labels_count):
            area = int(stats[index, cv2.CC_STAT_AREA])
            if area < self._config.min_component_area_px:
                continue
            x = int(stats[index, cv2.CC_STAT_LEFT])
            y = int(stats[index, cv2.CC_STAT_TOP])
            width = int(stats[index, cv2.CC_STAT_WIDTH])
            height = int(stats[index, cv2.CC_STAT_HEIGHT])
            bboxes.append((x, y, x + width - 1, y + height - 1, area))
        del labels
        return sorted(bboxes, key=lambda item: item[4], reverse=True)

    def _is_centered(self, track: TargetTrack | None) -> bool:
        if track is None or track.smoothed_center_px is None:
            return False
        width, height = self._config.viewport_size
        dx = track.smoothed_center_px[0] - width / 2.0
        dy = track.smoothed_center_px[1] - height / 2.0
        return float(np.hypot(dx, dy)) <= self._config.centered_threshold_px

    def _is_green(self, track: TargetTrack | None, region: ColorTargetRegion | None) -> bool:
        if region is not None and region.color_state == "GREEN":
            return True
        if track is None or track.appearance_signature is None:
            return False
        return track.appearance_signature.get("color_state") == "GREEN"

    def _in_range_estimated(self, track: TargetTrack | None) -> bool:
        if track is None or track.bbox_xyxy is None:
            return False
        x1, y1, x2, y2 = track.bbox_xyxy
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        return area >= self._config.in_range_min_area_px and self._is_centered(track)

    def _estimated_range(self, area_px: float) -> float | None:
        if area_px <= 0.0:
            return None
        return max(1.0, self._config.nominal_target_area_px / area_px)


class ColorTargetTracker:
    def __init__(
        self,
        short_coast_ms: float = 500.0,
        lost_timeout_ms: float = 3000.0,
        ambiguity_distance_px: float = 180.0,
    ) -> None:
        self._last_track: TargetTrack | None = None
        self._last_timestamp: float | None = None
        self._short_coast_ms = short_coast_ms
        self._lost_timeout_ms = lost_timeout_ms
        self._ambiguity_distance_px = ambiguity_distance_px

    def update(
        self,
        detection: TargetTrack | list[TargetTrack] | None,
        frame_id: int,
        timestamp: float,
    ) -> TargetTrack | None:
        detections = detection if isinstance(detection, list) else [detection] if detection is not None else []
        selected, ambiguous = self._select_detection(detections, timestamp)
        if selected is not None:
            velocity = self._velocity(selected.smoothed_center_px, timestamp)
            identity_confidence = selected.identity_confidence
            if ambiguous:
                identity_confidence = min(identity_confidence, 0.55)
            track = TargetTrack(
                track_id="color-target",
                class_id=selected.class_id,
                state="TRACKED",
                bbox_xyxy=selected.bbox_xyxy,
                smoothed_center_px=selected.smoothed_center_px,
                velocity_px_s=velocity,
                confidence=selected.confidence,
                identity_confidence=identity_confidence,
                missing_duration_ms=0.0,
                bearing_deg=selected.bearing_deg,
                pitch_deg=selected.pitch_deg,
                estimated_range=selected.estimated_range,
                last_seen_frame_id=frame_id,
                appearance_signature={
                    **(selected.appearance_signature or {}),
                    "ambiguous": ambiguous,
                    "candidate_count": len(detections),
                },
            )
            self._last_track = track
            self._last_timestamp = timestamp
            return track
        if self._last_track is None or self._last_timestamp is None:
            return None
        missing_ms = (timestamp - self._last_timestamp) * 1000.0
        state = "COASTING" if missing_ms <= self._lost_timeout_ms else "LOST"
        center = self._last_track.smoothed_center_px
        if center is not None and state == "COASTING":
            dt = missing_ms / 1000.0
            center = (
                center[0] + self._last_track.velocity_px_s[0] * dt,
                center[1] + self._last_track.velocity_px_s[1] * dt,
            )
        identity_factor = 0.0 if state == "LOST" else max(0.1, 1.0 - missing_ms / self._lost_timeout_ms)
        return TargetTrack(
            track_id=self._last_track.track_id,
            class_id=self._last_track.class_id,
            state=state,
            bbox_xyxy=self._last_track.bbox_xyxy,
            smoothed_center_px=center,
            velocity_px_s=self._last_track.velocity_px_s,
            confidence=max(0.0, self._last_track.confidence * identity_factor),
            identity_confidence=max(0.0, self._last_track.identity_confidence * identity_factor),
            missing_duration_ms=missing_ms,
            bearing_deg=self._last_track.bearing_deg,
            pitch_deg=self._last_track.pitch_deg,
            estimated_range=self._last_track.estimated_range,
            last_seen_frame_id=frame_id,
            appearance_signature=self._last_track.appearance_signature,
        )

    def _select_detection(
        self,
        detections: list[TargetTrack],
        timestamp: float,
    ) -> tuple[TargetTrack | None, bool]:
        if not detections:
            return (None, False)
        if self._last_track is None or self._last_track.smoothed_center_px is None:
            return (detections[0], len(detections) > 1)
        predicted = self._predicted_center(timestamp)
        if predicted is None:
            return (detections[0], len(detections) > 1)
        scored = [
            (
                self._distance(detection.smoothed_center_px, predicted),
                detection,
            )
            for detection in detections
            if detection.smoothed_center_px is not None
        ]
        if not scored:
            return (detections[0], len(detections) > 1)
        scored.sort(key=lambda item: item[0])
        best_distance, best = scored[0]
        ambiguous = (
            len(scored) > 1
            and scored[1][0] - best_distance < self._ambiguity_distance_px
        )
        return (best, ambiguous)

    def _predicted_center(self, timestamp: float) -> tuple[float, float] | None:
        if self._last_track is None or self._last_track.smoothed_center_px is None:
            return None
        if self._last_timestamp is None:
            return self._last_track.smoothed_center_px
        dt = max(timestamp - self._last_timestamp, 0.0)
        center = self._last_track.smoothed_center_px
        return (
            center[0] + self._last_track.velocity_px_s[0] * dt,
            center[1] + self._last_track.velocity_px_s[1] * dt,
        )

    def _distance(
        self,
        center: tuple[float, float] | None,
        predicted: tuple[float, float],
    ) -> float:
        if center is None:
            return float("inf")
        return float(np.hypot(center[0] - predicted[0], center[1] - predicted[1]))

    def _velocity(self, center: tuple[float, float] | None, timestamp: float) -> tuple[float, float]:
        if (
            center is None
            or self._last_track is None
            or self._last_track.smoothed_center_px is None
            or self._last_timestamp is None
        ):
            return (0.0, 0.0)
        dt = max(timestamp - self._last_timestamp, 1e-6)
        previous = self._last_track.smoothed_center_px
        return ((center[0] - previous[0]) / dt, (center[1] - previous[1]) / dt)
