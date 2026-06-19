"""Last-mile visual reacquisition.

When pose-based navigation gets us *near* a target but can no longer place us
precisely (low confidence / high uncertainty, or the target is a specific
on-screen object rather than a coordinate), control switches here. This is a
small visual-servoing state machine driven by the detector's
:class:`~core.types.TargetTrack`:

    SEARCH  — target not visible → sweep the camera yaw until it appears
    SERVO   — target visible but off-centre → rotate to centre it
    APPROACH— target centred → walk forward, keep micro-centred
    ARRIVED — target large enough on screen (close)
    NOT_FOUND — swept the full range without finding it

It reuses the FOV-aware pinhole conversion in :mod:`control.camera_model`, so
pixel error maps to real yaw/pitch degrees rather than raw pixels. Game-agnostic:
the caller supplies whatever TargetTrack its detector produced.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from control.camera_model import pixel_to_yaw_pitch_error_deg
from core.types import CameraIntent, CameraModel, MovementIntent, TargetTrack

ReacquireStatus = Literal["search", "servo", "approach", "arrived", "not_found"]


@dataclass(frozen=True, slots=True)
class ReacquireConfig:
    search_yaw_step_deg: float = 25.0
    search_max_sweep_deg: float = 400.0  # a bit over 360 to cover overlap
    center_tolerance_deg: float = 3.0
    yaw_gain: float = 0.6
    pitch_gain: float = 0.5
    max_yaw_delta_deg: float = 20.0
    max_pitch_delta_deg: float = 12.0
    arrival_area_ratio: float = 0.12  # bbox area / viewport area
    approach_duration_ms: int = 200
    camera_duration_ms: int = 80


@dataclass(frozen=True, slots=True)
class ReacquireDecision:
    status: ReacquireStatus
    reason: str
    movement: MovementIntent | None = None
    camera: CameraIntent | None = None
    yaw_error_deg: float = 0.0
    area_ratio: float = 0.0


class VisualReacquireController:
    def __init__(
        self,
        camera_model: CameraModel | None = None,
        config: ReacquireConfig | None = None,
    ) -> None:
        self._cam = camera_model or CameraModel()
        self._cfg = config or ReacquireConfig()
        self._swept = 0.0

    def reset(self) -> None:
        self._swept = 0.0

    def step(self, track: TargetTrack | None) -> ReacquireDecision:
        cfg = self._cfg
        visible = (
            track is not None
            and track.state != "lost"
            and track.smoothed_center_px is not None
        )

        if not visible:
            if self._swept >= cfg.search_max_sweep_deg:
                return ReacquireDecision("not_found", "swept full range, target not found")
            self._swept += abs(cfg.search_yaw_step_deg)
            return ReacquireDecision(
                "search", "scanning for target",
                camera=CameraIntent(
                    yaw_delta=cfg.search_yaw_step_deg, pitch_delta=0.0,
                    duration_ms=cfg.camera_duration_ms, confidence=0.0,
                    reason="reacquire_search",
                ),
            )

        assert track is not None and track.smoothed_center_px is not None
        self._swept = 0.0

        area_ratio = self._area_ratio(track.bbox_xyxy)
        if area_ratio >= cfg.arrival_area_ratio:
            return ReacquireDecision("arrived", "target close enough", area_ratio=area_ratio)

        yaw_err, pitch_err = pixel_to_yaw_pitch_error_deg(track.smoothed_center_px, self._cam)
        if abs(yaw_err) > cfg.center_tolerance_deg or abs(pitch_err) > cfg.center_tolerance_deg:
            yaw = _clamp(yaw_err * cfg.yaw_gain, -cfg.max_yaw_delta_deg, cfg.max_yaw_delta_deg)
            pitch = _clamp(pitch_err * cfg.pitch_gain, -cfg.max_pitch_delta_deg, cfg.max_pitch_delta_deg)
            return ReacquireDecision(
                "servo", "centering target",
                camera=CameraIntent(
                    yaw_delta=yaw, pitch_delta=pitch, duration_ms=cfg.camera_duration_ms,
                    confidence=track.confidence, reason="reacquire_servo",
                ),
                yaw_error_deg=yaw_err, area_ratio=area_ratio,
            )

        # Centred and still far → approach, holding micro-centring.
        return ReacquireDecision(
            "approach", "approaching centered target",
            movement=MovementIntent(
                move_forward=1.0, move_right=0.0,
                duration_ms=cfg.approach_duration_ms, reason="reacquire_approach",
            ),
            yaw_error_deg=yaw_err, area_ratio=area_ratio,
        )

    def _area_ratio(self, bbox: tuple[float, float, float, float] | None) -> float:
        if bbox is None:
            return 0.0
        x1, y1, x2, y2 = bbox
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        viewport = float(self._cam.viewport_width * self._cam.viewport_height)
        return area / viewport if viewport > 0 else 0.0


def _clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else hi if value > hi else value
