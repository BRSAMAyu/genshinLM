from __future__ import annotations

import math

from core.types import CameraControlError, CameraModel, TargetTrack
from control.camera_servo import CameraServo, CameraServoConfig


def _track(center: tuple[float, float], state: str = "TRACKED") -> TargetTrack:
    return TargetTrack(
        track_id="1",
        class_id="target",
        state=state,
        bbox_xyxy=None,
        smoothed_center_px=center,
        velocity_px_s=(100.0, 0.0),
        confidence=1.0,
        identity_confidence=1.0,
        missing_duration_ms=100.0 if state == "COASTING" else 0.0,
        bearing_deg=None,
        pitch_deg=None,
        estimated_range=None,
        last_seen_frame_id=1,
    )


def test_camera_servo_dead_zone_outputs_zero() -> None:
    servo = CameraServo(CameraServoConfig(dead_zone_deg=1.5, smoothing_alpha=1.0))
    error = CameraControlError(
        yaw_error_deg=1.0,
        pitch_error_deg=-1.0,
        angular_distance_deg=math.sqrt(2.0),
        target_confidence=1.0,
        stale=False,
    )

    intent = servo.step(error, dt=0.05)

    assert intent.yaw_delta == 0.0
    assert intent.pitch_delta == 0.0


def test_camera_servo_uses_angular_error_not_pixel_error() -> None:
    camera = CameraModel(viewport_width=1280, viewport_height=720, horizontal_fov_deg=90.0)
    servo = CameraServo(
        CameraServoConfig(
            dead_zone_deg=0.0,
            kp_yaw=1.0,
            kp_pitch=1.0,
            smoothing_alpha=1.0,
            max_yaw_delta=12.0,
            max_pitch_delta=8.0,
        )
    )

    error = servo.compute_error(_track((1280.0, 360.0)), camera)
    intent = servo.step(error, dt=0.05)

    assert math.isclose(error.yaw_error_deg, 45.0, abs_tol=1e-9)
    assert intent.yaw_delta == 12.0
    assert intent.pitch_delta == 0.0


def test_camera_servo_coasting_predicts_with_velocity() -> None:
    camera = CameraModel(viewport_width=1280, viewport_height=720, horizontal_fov_deg=90.0)
    servo = CameraServo(CameraServoConfig(dead_zone_deg=0.0, smoothing_alpha=1.0))

    tracked_error = servo.compute_error(_track((640.0, 360.0), state="TRACKED"), camera)
    coasting_error = servo.compute_error(_track((640.0, 360.0), state="COASTING"), camera)

    assert tracked_error.yaw_error_deg == 0.0
    assert coasting_error.yaw_error_deg > 0.0
    assert coasting_error.stale
