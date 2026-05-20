from __future__ import annotations

import math
from dataclasses import dataclass

from core.types import CameraControlError, CameraIntent, CameraModel, TargetTrack
from control.camera_model import pixel_to_yaw_pitch_error_deg, track_to_camera_error


@dataclass(frozen=True, slots=True)
class CameraServoConfig:
    dead_zone_deg: float = 1.5
    kp_yaw: float = 0.65
    kp_pitch: float = 0.45
    invert_yaw: bool = False
    invert_pitch: bool = False
    smoothing_alpha: float = 0.35
    max_yaw_delta: float = 12.0
    max_pitch_delta: float = 8.0
    default_duration_ms: int = 50
    coasting_prediction_limit_ms: float = 500.0


class CameraServo:
    def __init__(self, config: CameraServoConfig | None = None) -> None:
        self._config = config or CameraServoConfig()
        self._last_yaw_delta = 0.0
        self._last_pitch_delta = 0.0

    def compute_error(self, track: TargetTrack, camera: CameraModel) -> CameraControlError:
        center = self._predicted_center(track)
        if center is None:
            return track_to_camera_error(track, camera, stale=True)
        yaw_error, pitch_error = pixel_to_yaw_pitch_error_deg(center, camera)
        stale = track.state in {"COASTING", "LOST"}
        return CameraControlError(
            yaw_error_deg=yaw_error,
            pitch_error_deg=pitch_error,
            angular_distance_deg=math.hypot(yaw_error, pitch_error),
            target_confidence=track.confidence,
            stale=stale,
        )

    def step(self, error: CameraControlError, dt: float) -> CameraIntent:
        if error.stale and error.target_confidence <= 0.0:
            return CameraIntent(
                yaw_delta=0.0,
                pitch_delta=0.0,
                duration_ms=self._duration_ms(dt),
                confidence=0.0,
                reason="stale_or_missing_target",
            )

        yaw_error = self._apply_dead_zone(error.yaw_error_deg)
        pitch_error = self._apply_dead_zone(error.pitch_error_deg)
        if self._config.invert_yaw:
            yaw_error = -yaw_error
        if self._config.invert_pitch:
            pitch_error = -pitch_error
        raw_yaw = self._clamp(
            self._config.kp_yaw * yaw_error,
            -self._config.max_yaw_delta,
            self._config.max_yaw_delta,
        )
        raw_pitch = self._clamp(
            self._config.kp_pitch * pitch_error,
            -self._config.max_pitch_delta,
            self._config.max_pitch_delta,
        )
        yaw_delta = self._smooth(raw_yaw, self._last_yaw_delta)
        pitch_delta = self._smooth(raw_pitch, self._last_pitch_delta)
        self._last_yaw_delta = yaw_delta
        self._last_pitch_delta = pitch_delta
        return CameraIntent(
            yaw_delta=yaw_delta,
            pitch_delta=pitch_delta,
            duration_ms=self._duration_ms(dt),
            confidence=error.target_confidence,
            reason=(
                f"fov_servo yaw_error={error.yaw_error_deg:.3f} "
                f"pitch_error={error.pitch_error_deg:.3f} "
                f"angular_distance={error.angular_distance_deg:.3f}"
            ),
        )

    def reset(self) -> None:
        self._last_yaw_delta = 0.0
        self._last_pitch_delta = 0.0

    def _predicted_center(self, track: TargetTrack) -> tuple[float, float] | None:
        center = track.smoothed_center_px
        if center is None:
            return None
        if track.state != "COASTING":
            return center
        dt = min(track.missing_duration_ms, self._config.coasting_prediction_limit_ms) / 1000.0
        return (
            center[0] + track.velocity_px_s[0] * dt,
            center[1] + track.velocity_px_s[1] * dt,
        )

    def _apply_dead_zone(self, value: float) -> float:
        return 0.0 if abs(value) < self._config.dead_zone_deg else value

    def _smooth(self, current: float, previous: float) -> float:
        alpha = self._config.smoothing_alpha
        return alpha * current + (1.0 - alpha) * previous

    def _duration_ms(self, dt: float) -> int:
        if dt <= 0.0:
            return self._config.default_duration_ms
        return max(1, int(round(dt * 1000.0)))

    def _clamp(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))
