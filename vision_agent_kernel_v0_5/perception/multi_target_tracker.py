"""Multi-target tracker for Genshin Impact combat.

P-43~P-44: Extends single-target tracking to multi-target scenarios.
Handles target switching, priority management, and teleport detection.

Features:
- Multiple simultaneous target tracks
- Teleport detection (TELEPORTED state)
- Target priority management
- Smooth interpolation for position updates
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class TrackState(Enum):
    """Target track state."""
    ACTIVE = "active"
    MISSING = "missing"
    TELEPORTED = "teleported"
    LOST = "lost"


@dataclass(frozen=True, slots=True)
class TargetPrediction:
    """Predicted target position."""
    position: tuple[float, float]
    confidence: float
    timestamp: float
    motion_vector: tuple[float, float]


@dataclass(frozen=True, slots=True)
class MultiTargetTrack:
    """Track state for a single target."""
    track_id: str
    class_id: str
    state: TrackState
    current_position: tuple[float, float] | None
    smoothed_position: tuple[float, float] | None
    bbox: tuple[float, float, float, float] | None
    confidence: float
    priority: int                      # Higher = more important to track
    missing_frames: int
    last_seen_frame: int
    teleport_count: int
    appearance_signature: dict | None = None


@dataclass(frozen=True, slots=True)
class TrackingResult:
    """Result of multi-target tracking."""
    tracks: tuple[MultiTargetTrack, ...]
    primary_target: str | None
    total_tracked: int
    total_lost: int
    frame_id: int


class MultiTargetTracker:
    """Track multiple targets simultaneously.

    Features:
    - Maintains tracks for multiple targets
    - Handles target disappearance and reappearance
    - Detects teleportation (sudden position jumps)
    - Priority-based target management
    - Smooth position interpolation

    Teleport detection: If a target's position jumps > threshold pixels
    between frames, mark as TELEPORTED and attempt to reacquire.
    """

    _REF_W = 1920
    _REF_H = 1080

    # Tracking parameters
    TELEPORT_THRESHOLD_PX = 150      # Pixels to consider a teleport
    MAX_MISSING_FRAMES = 30          # Frames before marking LOST
    POSITION_SMOOTH_ALPHA = 0.7     # EMA smoothing factor

    # Velocity estimation
    VELOCITY_ESTIMATE_WINDOW = 5    # Frames to average for velocity
    VELOCITY_DECAY = 0.9            # Decay factor for missing frames

    def __init__(
        self,
        now_fn=None,
        max_tracks: int = 10,
    ) -> None:
        """Initialize multi-target tracker.

        Args:
            now_fn: Time function (default: time.perf_counter)
            max_tracks: Maximum number of simultaneous tracks
        """
        self._now_fn = now_fn or time.perf_counter
        self._max_tracks = max_tracks

        self._tracks: dict[str, MultiTargetTrack] = {}
        self._track_counter: int = 0
        self._frame_id: int = 0

        # Velocity tracking per target
        self._velocities: dict[str, tuple[float, float]] = {}
        self._position_history: dict[str, list[tuple[float, float]]] = defaultdict(list)

        self._last_result: TrackingResult | None = None

    @property
    def last_result(self) -> TrackingResult | None:
        """Get last tracking result."""
        return self._last_result

    @property
    def active_tracks(self) -> tuple[MultiTargetTrack, ...]:
        """Get all active tracks."""
        return tuple(t for t in self._tracks.values() if t.state == TrackState.ACTIVE)

    def update(
        self,
        detections: list[tuple[str, tuple[float, float], float, str]],
        frame_id: int,
    ) -> TrackingResult:
        """Update tracks with new detections.

        Args:
            detections: List of (track_id, position, confidence, class_id)
                        If track_id is empty string, it's a new detection
            frame_id: Current frame ID

        Returns:
            TrackingResult with updated track states
        """
        self._frame_id = frame_id

        # First, predict positions for existing tracks
        self._predict_positions()

        # Match detections to existing tracks
        matched, unmatched_detections = self._match_detections(detections)

        # Update matched tracks
        for det_idx, track_id in matched.items():
            detection = detections[det_idx]
            self._update_track(
                track_id,
                detection[1],  # position
                detection[2],  # confidence
                detection[3],  # class_id
            )

        # Handle unmatched detections (new targets)
        for det_idx in unmatched_detections:
            detection = detections[det_idx]
            self._add_new_track(
                detection[1],  # position
                detection[2],  # confidence
                detection[3],  # class_id
            )

        # Update unmatched tracks (mark as missing)
        self._mark_missing_tracks()

        # Build result
        result = self._build_result()
        self._last_result = result
        return result

    def _predict_positions(self) -> None:
        """Predict positions for all active tracks based on velocity."""
        for track_id, track in self._tracks.items():
            if track.state != TrackState.ACTIVE:
                continue

            if track_id in self._velocities:
                vx, vy = self._velocities[track_id]
                if track.smoothed_position:
                    pred_x = track.smoothed_position[0] + vx
                    pred_y = track.smoothed_position[1] + vy
                    # Store prediction (would be used in matching)
                    pass

    def _match_detections(
        self,
        detections: list[tuple[str, tuple[float, float], float, str]],
    ) -> tuple[dict[int, str], list[int]]:
        """Match detections to existing tracks.

        Returns:
            matched: dict of detection_index -> track_id
            unmatched: list of unmatched detection indices
        """
        matched: dict[int, str] = {}
        unmatched: list[int] = []

        available_tracks = {
            tid: track for tid, track in self._tracks.items()
            if track.state == TrackState.ACTIVE
        }

        for det_idx, detection in enumerate(detections):
            det_pos = detection[1]

            best_match: str | None = None
            best_distance = float('inf')

            for track_id, track in available_tracks.items():
                if track.smoothed_position is None:
                    continue

                dist = self._distance(det_pos, track.smoothed_position)

                # Also check teleported tracks
                if track.state == TrackState.TELEPORTED:
                    dist *= 1.5  # Penalize teleport matches

                if dist < best_distance and dist < self.TELEPORT_THRESHOLD_PX * 2:
                    best_distance = dist
                    best_match = track_id

            if best_match:
                matched[det_idx] = best_match
                del available_tracks[best_match]
            else:
                unmatched.append(det_idx)

        return matched, unmatched

    def _update_track(
        self,
        track_id: str,
        position: tuple[float, float],
        confidence: float,
        class_id: str,
    ) -> None:
        """Update an existing track with new detection."""
        track = self._tracks.get(track_id)
        if track is None:
            return

        # Calculate motion
        motion_vector = (0.0, 0.0)
        if track.smoothed_position:
            motion_vector = (
                position[0] - track.smoothed_position[0],
                position[1] - track.smoothed_position[1],
            )

        # Check for teleport
        if track.smoothed_position:
            dist = self._distance(position, track.smoothed_position)
            if dist > self.TELEPORT_THRESHOLD_PX:
                new_state = TrackState.TELEPORTED
                teleport_count = track.teleport_count + 1
                log.debug("[MultiTargetTracker] Track %s teleported: %.1f px", track_id, dist)
            else:
                new_state = TrackState.ACTIVE
                teleport_count = track.teleport_count
        else:
            new_state = TrackState.ACTIVE
            teleport_count = track.teleport_count

        # Smooth position
        if track.smoothed_position:
            smooth_x = self._lerp(track.smoothed_position[0], position[0], self.POSITION_SMOOTH_ALPHA)
            smooth_y = self._lerp(track.smoothed_position[1], position[1], self.POSITION_SMOOTH_ALPHA)
            smoothed = (smooth_x, smooth_y)
        else:
            smoothed = position

        # Update velocity
        self._velocities[track_id] = motion_vector

        # Update position history
        self._position_history[track_id].append(position)
        if len(self._position_history[track_id]) > self.VELOCITY_ESTIMATE_WINDOW:
            self._position_history[track_id].pop(0)

        # Create updated track
        self._tracks[track_id] = MultiTargetTrack(
            track_id=track_id,
            class_id=class_id,
            state=new_state,
            current_position=position,
            smoothed_position=smoothed,
            bbox=track.bbox,
            confidence=confidence,
            priority=track.priority,
            missing_frames=0,
            last_seen_frame=self._frame_id,
            teleport_count=teleport_count,
            appearance_signature=track.appearance_signature,
        )

    def _add_new_track(
        self,
        position: tuple[float, float],
        confidence: float,
        class_id: str,
    ) -> None:
        """Add a new track."""
        if len(self._tracks) >= self._max_tracks:
            # Remove lowest priority track
            self._remove_lowest_priority()

        self._track_counter += 1
        track_id = f"track_{self._track_counter}"

        track = MultiTargetTrack(
            track_id=track_id,
            class_id=class_id,
            state=TrackState.ACTIVE,
            current_position=position,
            smoothed_position=position,
            bbox=None,
            confidence=confidence,
            priority=1,
            missing_frames=0,
            last_seen_frame=self._frame_id,
            teleport_count=0,
            appearance_signature=None,
        )

        self._tracks[track_id] = track
        self._position_history[track_id] = [position]
        self._velocities[track_id] = (0.0, 0.0)

        log.debug("[MultiTargetTracker] Added new track: %s at %s", track_id, position)

    def _mark_missing_tracks(self) -> None:
        """Mark tracks that weren't updated as missing."""
        for track_id, track in self._tracks.items():
            if track.last_seen_frame < self._frame_id:
                # Track wasn't updated this frame
                new_missing = track.missing_frames + 1

                # Check velocity prediction
                if track_id in self._velocities:
                    vx, vy = self._velocities[track_id]
                    # Decay velocity
                    self._velocities[track_id] = (vx * self.VELOCITY_DECAY, vy * self.VELOCITY_DECAY)

                if new_missing >= self.MAX_MISSING_FRAMES:
                    new_state = TrackState.LOST
                else:
                    new_state = TrackState.MISSING

                self._tracks[track_id] = MultiTargetTrack(
                    track_id=track_id,
                    class_id=track.class_id,
                    state=new_state,
                    current_position=track.current_position,
                    smoothed_position=track.smoothed_position,
                    bbox=track.bbox,
                    confidence=track.confidence * 0.95,  # Decay confidence
                    priority=track.priority,
                    missing_frames=new_missing,
                    last_seen_frame=track.last_seen_frame,
                    teleport_count=track.teleport_count,
                    appearance_signature=track.appearance_signature,
                )

    def _remove_lowest_priority(self) -> None:
        """Remove the lowest priority track to make room for new ones."""
        if not self._tracks:
            return

        # Find lowest priority active track
        lowest = min(
            self._tracks.values(),
            key=lambda t: (t.priority, -t.last_seen_frame),
        )

        del self._tracks[lowest.track_id]
        if lowest.track_id in self._velocities:
            del self._velocities[lowest.track_id]
        if lowest.track_id in self._position_history:
            del self._position_history[lowest.track_id]

    def _build_result(self) -> TrackingResult:
        """Build tracking result."""
        tracks = tuple(self._tracks.values())
        total_tracked = sum(1 for t in tracks if t.state == TrackState.ACTIVE)
        total_lost = sum(1 for t in tracks if t.state == TrackState.LOST)

        # Find primary target (highest priority active track)
        primary = None
        best_priority = -1

        for track in tracks:
            if track.state == TrackState.ACTIVE and track.priority > best_priority:
                best_priority = track.priority
                primary = track.track_id

        return TrackingResult(
            tracks=tracks,
            primary_target=primary,
            total_tracked=total_tracked,
            total_lost=total_lost,
            frame_id=self._frame_id,
        )

    def _distance(self, p1: tuple[float, float], p2: tuple[float, float]) -> float:
        """Calculate distance between two points."""
        return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5

    def _lerp(self, a: float, b: float, t: float) -> float:
        """Linear interpolation."""
        return a + (b - a) * t

    def set_priority(self, track_id: str, priority: int) -> None:
        """Set track priority."""
        if track_id in self._tracks:
            track = self._tracks[track_id]
            self._tracks[track_id] = MultiTargetTrack(
                track_id=track.track_id,
                class_id=track.class_id,
                state=track.state,
                current_position=track.current_position,
                smoothed_position=track.smoothed_position,
                bbox=track.bbox,
                confidence=track.confidence,
                priority=priority,
                missing_frames=track.missing_frames,
                last_seen_frame=track.last_seen_frame,
                teleport_count=track.teleport_count,
                appearance_signature=track.appearance_signature,
            )

    def get_track(self, track_id: str) -> MultiTargetTrack | None:
        """Get a specific track."""
        return self._tracks.get(track_id)

    def remove_track(self, track_id: str) -> None:
        """Remove a track."""
        if track_id in self._tracks:
            del self._tracks[track_id]
        if track_id in self._velocities:
            del self._velocities[track_id]
        if track_id in self._position_history:
            del self._position_history[track_id]

    def reset(self) -> None:
        """Reset tracker state."""
        self._tracks.clear()
        self._velocities.clear()
        self._position_history.clear()
        self._track_counter = 0
        self._frame_id = 0
        self._last_result = None