from __future__ import annotations

import math

from core.types import CameraModel, TargetTrack
from control.camera_model import (
    derive_vertical_fov_deg,
    pixel_to_yaw_pitch_error_deg,
    track_to_camera_error,
)


def test_camera_fov_mapping_center() -> None:
    camera = CameraModel(viewport_width=1280, viewport_height=720, horizontal_fov_deg=78.0)

    yaw, pitch = pixel_to_yaw_pitch_error_deg((640.0, 360.0), camera)

    assert yaw == 0.0
    assert pitch == 0.0


def test_camera_fov_mapping_edge() -> None:
    camera = CameraModel(viewport_width=1280, viewport_height=720, horizontal_fov_deg=78.0)

    right_yaw, _ = pixel_to_yaw_pitch_error_deg((1280.0, 360.0), camera)
    left_yaw, _ = pixel_to_yaw_pitch_error_deg((0.0, 360.0), camera)
    _, bottom_pitch = pixel_to_yaw_pitch_error_deg((640.0, 720.0), camera)

    assert math.isclose(right_yaw, 39.0, abs_tol=1e-9)
    assert math.isclose(left_yaw, -39.0, abs_tol=1e-9)
    assert math.isclose(bottom_pitch, derive_vertical_fov_deg(camera) / 2.0, abs_tol=1e-9)


def test_track_to_camera_error_uses_target_center() -> None:
    camera = CameraModel(viewport_width=1280, viewport_height=720, horizontal_fov_deg=78.0)
    track = TargetTrack(
        track_id="1",
        class_id="target",
        state="TRACKED",
        bbox_xyxy=(1200.0, 300.0, 1280.0, 420.0),
        smoothed_center_px=(1240.0, 360.0),
        velocity_px_s=(0.0, 0.0),
        confidence=0.8,
        identity_confidence=0.9,
        missing_duration_ms=0.0,
        bearing_deg=None,
        pitch_deg=None,
        estimated_range=None,
        last_seen_frame_id=1,
    )

    error = track_to_camera_error(track, camera)

    assert error.yaw_error_deg > 0.0
    assert error.pitch_error_deg == 0.0
    assert error.target_confidence == 0.8
