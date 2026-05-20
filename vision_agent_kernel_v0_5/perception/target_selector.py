from __future__ import annotations

import math
from dataclasses import dataclass

from core.types import TargetCandidate, TargetTrack


@dataclass(frozen=True, slots=True)
class TargetSelectorConfig:
    viewport_size: tuple[int, int] = (1280, 720)
    class_allowlist: set[str] | None = None
    confidence_weight: float = 0.55
    center_weight: float = 0.35
    class_weight: float = 0.10


@dataclass(frozen=True, slots=True)
class TargetSelection:
    candidate: TargetCandidate | None
    active_track_id: str | None
    identity_confidence: float
    score: float


class TargetSelector:
    def __init__(self, config: TargetSelectorConfig | None = None) -> None:
        self._config = config or TargetSelectorConfig()
        self._active_track_id: str | None = None

    @property
    def active_track_id(self) -> str | None:
        return self._active_track_id

    def select_candidate(
        self,
        candidates: list[TargetCandidate],
        active_track: TargetTrack | None = None,
    ) -> TargetSelection:
        if active_track is not None and active_track.state != "LOST":
            self._active_track_id = active_track.track_id
        if not candidates:
            return TargetSelection(None, self._active_track_id, 0.0, 0.0)
        scored = [(self._score(candidate), candidate) for candidate in candidates]
        score, candidate = max(scored, key=lambda item: item[0])
        identity = min(1.0, max(0.0, score))
        return TargetSelection(candidate, self._active_track_id, identity, score)

    def select_track(self, tracks: list[TargetTrack]) -> TargetTrack | None:
        if not tracks:
            return None
        if self._active_track_id is not None:
            for track in tracks:
                if track.track_id == self._active_track_id and track.state != "LOST":
                    return track
        track = max(tracks, key=lambda item: self._track_score(item))
        self._active_track_id = track.track_id
        return track

    def _score(self, candidate: TargetCandidate) -> float:
        class_score = self._class_score(candidate.class_id)
        center_score = self._center_score(candidate.center_px)
        return (
            self._config.confidence_weight * candidate.confidence
            + self._config.center_weight * center_score
            + self._config.class_weight * class_score
        )

    def _track_score(self, track: TargetTrack) -> float:
        center_score = self._center_score(track.smoothed_center_px) if track.smoothed_center_px else 0.0
        return 0.5 * track.confidence + 0.3 * track.identity_confidence + 0.2 * center_score

    def _class_score(self, class_id: str) -> float:
        if self._config.class_allowlist is None:
            return 1.0
        return 1.0 if class_id in self._config.class_allowlist else 0.0

    def _center_score(self, center: tuple[float, float]) -> float:
        width, height = self._config.viewport_size
        dx = (center[0] - width / 2.0) / max(width / 2.0, 1.0)
        dy = (center[1] - height / 2.0) / max(height / 2.0, 1.0)
        distance = math.hypot(dx, dy)
        return max(0.0, 1.0 - min(distance, 1.0))
