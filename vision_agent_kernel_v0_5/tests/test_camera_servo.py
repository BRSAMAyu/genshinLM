from __future__ import annotations

import math

from core.types import CameraControlError, CameraModel, TargetTrack
from control.camera_servo import CameraServo, CameraServoConfig, genshin_camera_servo_config


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
    camera = CameraModel(viewport_width=1280, viewport_height=720, horizontal_fov_deg=78.0)
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

    assert math.isclose(error.yaw_error_deg, 39.0, abs_tol=1e-9)
    assert intent.yaw_delta == 12.0
    assert intent.pitch_delta == 0.0


def test_camera_servo_coasting_predicts_with_velocity() -> None:
    camera = CameraModel(viewport_width=1280, viewport_height=720, horizontal_fov_deg=78.0)
    servo = CameraServo(CameraServoConfig(dead_zone_deg=0.0, smoothing_alpha=1.0))

    tracked_error = servo.compute_error(_track((640.0, 360.0), state="TRACKED"), camera)
    coasting_error = servo.compute_error(_track((640.0, 360.0), state="COASTING"), camera)

    assert tracked_error.yaw_error_deg == 0.0
    assert coasting_error.yaw_error_deg > 0.0
    assert coasting_error.stale


def test_camera_servo_invert_yaw_and_pitch_config() -> None:
    servo = CameraServo(
        CameraServoConfig(
            dead_zone_deg=0.0,
            kp_yaw=1.0,
            kp_pitch=1.0,
            invert_yaw=True,
            invert_pitch=True,
            smoothing_alpha=1.0,
            max_yaw_delta=12.0,
            max_pitch_delta=8.0,
        )
    )
    error = CameraControlError(
        yaw_error_deg=5.0,
        pitch_error_deg=-4.0,
        angular_distance_deg=math.hypot(5.0, -4.0),
        target_confidence=1.0,
        stale=False,
    )

    intent = servo.step(error, dt=0.05)

    assert intent.yaw_delta == -5.0
    assert intent.pitch_delta == 4.0


def _error(yaw: float, pitch: float, confidence: float = 1.0) -> CameraControlError:
    return CameraControlError(
        yaw_error_deg=yaw,
        pitch_error_deg=pitch,
        angular_distance_deg=math.hypot(yaw, pitch),
        target_confidence=confidence,
        stale=False,
    )


def test_pitch_compensation_reduces_pitch() -> None:
    servo = CameraServo(CameraServoConfig(
        dead_zone_deg=0.0,
        kp_yaw=1.0, kp_pitch=1.0,
        smoothing_alpha=1.0,
        max_yaw_delta=100.0, max_pitch_delta=100.0,
        pitch_compensation_factor=0.75,
    ))
    intent = servo.step(_error(0.0, 10.0), dt=0.05)
    assert math.isclose(intent.pitch_delta, 7.5, abs_tol=1e-9)
    assert intent.yaw_delta == 0.0


def test_default_config_has_no_compensation() -> None:
    servo = CameraServo(CameraServoConfig(smoothing_alpha=1.0))
    intent = servo.step(_error(5.0, 4.0), dt=0.05)
    expected_yaw = 0.65 * 5.0
    expected_pitch = 0.45 * 4.0
    assert math.isclose(intent.yaw_delta, expected_yaw, abs_tol=1e-9)
    assert math.isclose(intent.pitch_delta, expected_pitch, abs_tol=1e-9)


def test_multi_step_decomposition() -> None:
    servo = CameraServo(CameraServoConfig(
        dead_zone_deg=0.0,
        kp_yaw=1.0, kp_pitch=1.0,
        smoothing_alpha=1.0,
        max_yaw_delta=100.0, max_pitch_delta=100.0,
        max_step_deg=3.0,
    ))
    error = _error(5.0, 0.0)
    steps = servo.step_multi(error, dt=0.05)
    assert len(steps) > 1
    total_yaw = sum(s.yaw_delta for s in steps)
    assert math.isclose(total_yaw, 5.0, abs_tol=0.1)


def test_step_queues_substeps() -> None:
    servo = CameraServo(CameraServoConfig(
        dead_zone_deg=0.0,
        kp_yaw=1.0, kp_pitch=1.0,
        smoothing_alpha=1.0,
        max_yaw_delta=100.0, max_pitch_delta=100.0,
        max_step_deg=2.0,
    ))
    first = servo.step(_error(6.0, 0.0), dt=0.05)
    assert abs(first.yaw_delta) <= 2.1
    second = servo.step(_error(0.0, 0.0, confidence=0.0), dt=0.05)
    assert second.yaw_delta != 0.0 or "substep" in second.reason


def test_genshin_preset_has_compensation() -> None:
    config = genshin_camera_servo_config()
    assert config.pitch_compensation_factor == 0.75
    assert config.max_step_deg == 3.0
    assert config.acceleration_compensation == "linear"


def test_acceleration_compensation_reduces_large_moves() -> None:
    servo_none = CameraServo(CameraServoConfig(
        dead_zone_deg=0.0, kp_yaw=1.0, kp_pitch=1.0,
        smoothing_alpha=1.0, max_yaw_delta=100.0, max_pitch_delta=100.0,
        acceleration_compensation="none",
    ))
    servo_linear = CameraServo(CameraServoConfig(
        dead_zone_deg=0.0, kp_yaw=1.0, kp_pitch=1.0,
        smoothing_alpha=1.0, max_yaw_delta=100.0, max_pitch_delta=100.0,
        acceleration_compensation="linear",
    ))
    none_intent = servo_none.step(_error(10.0, 0.0), dt=0.05)
    linear_intent = servo_linear.step(_error(10.0, 0.0), dt=0.05)
    assert linear_intent.yaw_delta < none_intent.yaw_delta


def test_step_multi_single_step_when_no_decomposition() -> None:
    servo = CameraServo(CameraServoConfig(
        dead_zone_deg=0.0, kp_yaw=1.0, kp_pitch=1.0,
        smoothing_alpha=1.0, max_yaw_delta=100.0, max_pitch_delta=100.0,
    ))
    steps = servo.step_multi(_error(3.0, 2.0), dt=0.05)
    assert len(steps) == 1
