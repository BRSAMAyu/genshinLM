from __future__ import annotations

import math
from unittest.mock import MagicMock, call

import numpy as np
import pytest

from control.camera_servo import CameraServo
from core.types import CameraControlError, CameraIntent
from navigation.minimap_quest_reader import MinimapQuestReader
from navigation.quest_marker_follower import QuestMarkerFollower


def test_quest_marker_follower_initialization() -> None:
    backend = MagicMock()
    reader = MagicMock()
    follower = QuestMarkerFollower(backend, reader)
    assert follower._backend is backend
    assert follower._reader is reader
    assert isinstance(follower._servo, CameraServo)


def test_quest_marker_follower_navigation_arrived() -> None:
    backend = MagicMock()
    reader = MagicMock()
    reader.is_at_destination.return_value = True

    follower = QuestMarkerFollower(backend, reader)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame_source = lambda: frame

    assert follower.navigate_to_marker(frame_source, max_steps=1) is True
    reader.is_at_destination.assert_called_once_with(frame)
    backend.key_down.assert_not_called()


def test_quest_marker_follower_navigation_yaw_servo() -> None:
    backend = MagicMock()
    reader = MagicMock()
    # First step: not at destination, angle is pi/4 (45 degrees, to the right)
    # Second step: arrived at destination
    reader.is_at_destination.side_effect = [False, True]
    reader.read_quest_direction.return_value = math.pi / 4  # 45 degrees

    servo = MagicMock()
    # Mock step_multi to return two camera intents
    servo.step_multi.return_value = [
        CameraIntent(yaw_delta=1.5, pitch_delta=0.0, duration_ms=50, confidence=1.0, reason="sub1"),
        CameraIntent(yaw_delta=1.5, pitch_delta=0.0, duration_ms=50, confidence=1.0, reason="sub2"),
    ]

    follower = QuestMarkerFollower(backend, reader, servo=servo)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame_source = lambda: frame

    # Should finish on the second step because is_at_destination becomes True
    assert follower.navigate_to_marker(frame_source, max_steps=2, step_interval=0.1) is True

    # Check key down/up sequences
    # For angle = pi/4, WASD mapping:
    # 45 degrees is between -pi/8 * 3 and pi/8 * 3, so 'w' is pressed.
    # 45 degrees is positive (> pi/8), so 'd' is also pressed.
    # So 'w' and 'd' are pressed.
    backend.key_down.assert_has_calls([call("w", reason="quest_follow"), call("d", reason="quest_follow")], any_order=True)
    backend.key_up.assert_has_calls([call("w", reason="quest_follow_done"), call("d", reason="quest_follow_done")], any_order=True)

    # Check that mouse_move was called for the camera servo intents
    backend.mouse_move.assert_has_calls([
        call(1.5, 0.0, reason="quest_camera_servo"),
        call(1.5, 0.0, reason="quest_camera_servo"),
    ])

    # Check that servo.step_multi was called with correct error and interval
    servo.step_multi.assert_called_once()
    args, kwargs = servo.step_multi.call_args
    error_arg = args[0]
    assert isinstance(error_arg, CameraControlError)
    assert math.isclose(error_arg.yaw_error_deg, 45.0, abs_tol=1e-5)
    assert error_arg.pitch_error_deg == 0.0
    assert math.isclose(kwargs.get("dt"), 0.1)
