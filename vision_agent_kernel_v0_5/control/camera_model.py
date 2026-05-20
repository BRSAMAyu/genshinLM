from __future__ import annotations

import math

from core.types import CameraControlError, CameraModel, TargetTrack


def derive_vertical_fov_deg(camera: CameraModel) -> float:
    if camera.vertical_fov_deg is not None:
        return camera.vertical_fov_deg
    horizontal_half = math.radians(camera.horizontal_fov_deg) / 2.0
    aspect_inverse = camera.viewport_height / camera.viewport_width
    vertical_half = math.atan(math.tan(horizontal_half) * aspect_inverse)
    return math.degrees(vertical_half * 2.0)


def pixel_to_yaw_pitch_error_deg(
    point_px: tuple[float, float],
    camera: CameraModel,
) -> tuple[float, float]:
    """
    Convert a viewport pixel into angular error inside the camera frustum.

    Mathematical derivation:
    1. Model the camera as a pinhole camera looking down the +Z axis. The image
       plane is one focal length in front of the pinhole.
    2. Let horizontal half-FOV be h/2. At depth z=1, the right edge of the view
       plane sits at x = tan(h/2). The left edge is -tan(h/2).
    3. A pixel coordinate is first normalized into [-1, 1] relative to the image
       center: normalized_x = (target_x - center_x) / center_x.
    4. The corresponding ray direction has x = normalized_x * tan(h/2), z = 1.
       The yaw angle between the center ray (0, 0, 1) and this ray is:
           yaw = atan(x / z) = atan(normalized_x * tan(h/2)).
    5. The same derivation applies vertically with vertical half-FOV. Image Y is
       positive downward, so a target below center produces positive pitch error
       by convention here; the backend can invert via CameraModel.invert_y.

    This is why we do not use mouse_dx = kp * pixel_error. Pixel error is not an
    angular quantity; the same pixel delta means different ray angles depending
    on FOV and viewport size.
    """
    center_x = camera.viewport_width / 2.0
    center_y = camera.viewport_height / 2.0
    target_x, target_y = point_px
    normalized_x = (target_x - center_x) / center_x
    normalized_y = (target_y - center_y) / center_y
    yaw_error = math.degrees(
        math.atan(normalized_x * math.tan(math.radians(camera.horizontal_fov_deg) / 2.0))
    )
    vertical_fov_deg = derive_vertical_fov_deg(camera)
    pitch_error = math.degrees(
        math.atan(normalized_y * math.tan(math.radians(vertical_fov_deg) / 2.0))
    )
    if camera.invert_y:
        pitch_error = -pitch_error
    return (yaw_error, pitch_error)


def track_to_camera_error(track: TargetTrack, camera: CameraModel, stale: bool = False) -> CameraControlError:
    if track.smoothed_center_px is None:
        return CameraControlError(
            yaw_error_deg=0.0,
            pitch_error_deg=0.0,
            angular_distance_deg=0.0,
            target_confidence=track.confidence,
            stale=True,
        )
    yaw_error, pitch_error = pixel_to_yaw_pitch_error_deg(track.smoothed_center_px, camera)
    angular_distance = math.hypot(yaw_error, pitch_error)
    return CameraControlError(
        yaw_error_deg=yaw_error,
        pitch_error_deg=pitch_error,
        angular_distance_deg=angular_distance,
        target_confidence=track.confidence,
        stale=stale or track.state == "LOST",
    )
