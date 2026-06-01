"""Tests for QuestMarkerFollower — mock-only, dry-run compatible."""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, call

import numpy as np
import pytest

from control.camera_servo import CameraServo, genshin_camera_servo_config
from core.types import CameraControlError, CameraIntent, InputLease
from navigation.minimap_quest_reader import MinimapQuestReader
from navigation.quest_marker_follower import QuestMarkerFollower


# ---------------------------------------------------------------------------
# Helper / mock components
# ---------------------------------------------------------------------------

class _CountingFrameSource:
    """Callable that yields a fixed frame N times, then returns None."""

    def __init__(self, frame: np.ndarray, count: int = 999) -> None:
        self._frame = frame
        self._remaining = count
        self.call_count = 0

    def __call__(self) -> np.ndarray | None:
        if self._remaining <= 0:
            return None
        self._remaining -= 1
        self.call_count += 1
        return self._frame


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def dummy_frame() -> np.ndarray:
    return np.zeros((1080, 1920, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# Basic initialization
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Test _angle_to_keys
# ---------------------------------------------------------------------------

class TestAngleToKeys:
    """Test WASD key selection from quest marker angle."""

    def test_angle_0_forward_w(self) -> None:
        backend = MagicMock()
        reader = MagicMock()
        follower = QuestMarkerFollower(backend, reader)
        keys = follower._angle_to_keys(0.0)
        assert keys == ["w"]

    def test_angle_pi_2_right_d(self) -> None:
        backend = MagicMock()
        reader = MagicMock()
        follower = QuestMarkerFollower(backend, reader)
        keys = follower._angle_to_keys(math.pi / 2)
        assert keys == ["d"]

    def test_angle_neg_pi_2_left_a(self) -> None:
        backend = MagicMock()
        reader = MagicMock()
        follower = QuestMarkerFollower(backend, reader)
        keys = follower._angle_to_keys(-math.pi / 2)
        assert keys == ["a"]

    def test_angle_pi_backward_s(self) -> None:
        backend = MagicMock()
        reader = MagicMock()
        follower = QuestMarkerFollower(backend, reader)
        keys = follower._angle_to_keys(math.pi)
        # π (3.14) normalizes to -π, which is NOT > π - threshold
        # so forward is NOT triggered; it falls through to backward check
        assert "s" in keys

    def test_angle_0_3_within_threshold_forward(self) -> None:
        """0.3 rad (≈17°) is within ~67° forward threshold → 'w'."""
        backend = MagicMock()
        reader = MagicMock()
        follower = QuestMarkerFollower(backend, reader)
        keys = follower._angle_to_keys(0.3)
        assert "w" in keys
        assert "d" not in keys
        assert "a" not in keys

    def test_angle_pi_4_diagonal_wd(self) -> None:
        """π/4 (45°) → forward+right ('wd')."""
        backend = MagicMock()
        reader = MagicMock()
        follower = QuestMarkerFollower(backend, reader)
        keys = follower._angle_to_keys(math.pi / 4)
        assert "w" in keys
        assert "d" in keys

    def test_angle_neg_pi_4_diagonal_wa(self) -> None:
        """-π/4 (-45°) → forward+left ('wa')."""
        backend = MagicMock()
        reader = MagicMock()
        follower = QuestMarkerFollower(backend, reader)
        keys = follower._angle_to_keys(-math.pi / 4)
        assert "w" in keys
        assert "a" in keys


# ---------------------------------------------------------------------------
# Test navigate_to_marker
# ---------------------------------------------------------------------------

class TestNavigateToMarker:
    """Full integration tests for navigate_to_marker."""

    def test_returns_true_when_at_destination(self, dummy_frame: np.ndarray) -> None:
        """is_at_destination=True → return True on first step."""
        backend = MagicMock()
        reader = MagicMock()
        reader.is_at_destination.return_value = True
        follower = QuestMarkerFollower(backend, reader)
        frame_source = _CountingFrameSource(dummy_frame)
        result = follower.navigate_to_marker(frame_source, max_steps=10)
        assert result is True
        assert frame_source.call_count == 1  # stopped after first check

    def test_returns_false_after_max_steps(self, dummy_frame: np.ndarray) -> None:
        """max_steps exhausted → False."""
        backend = MagicMock()
        reader = MagicMock()
        reader.is_at_destination.return_value = False
        reader.read_quest_direction.return_value = 0.0
        servo = MagicMock()
        servo.step_multi.return_value = [
            CameraIntent(yaw_delta=0.0, pitch_delta=0.0, duration_ms=50, confidence=1.0, reason="ok"),
        ]
        follower = QuestMarkerFollower(backend, reader, servo=servo)
        frame_source = _CountingFrameSource(dummy_frame)
        result = follower.navigate_to_marker(frame_source, max_steps=3)
        assert result is False
        assert frame_source.call_count == 3

    def test_key_press_release_cycles_match(self, dummy_frame: np.ndarray) -> None:
        """Every key_down must be followed by a key_up."""
        backend = MagicMock()
        reader = MagicMock()
        reader.is_at_destination.return_value = False
        reader.read_quest_direction.return_value = 0.0
        servo = MagicMock()
        servo.step_multi.return_value = [
            CameraIntent(yaw_delta=0.0, pitch_delta=0.0, duration_ms=50, confidence=1.0, reason="ok"),
        ]
        follower = QuestMarkerFollower(backend, reader, servo=servo)
        frame_source = _CountingFrameSource(dummy_frame)
        follower.navigate_to_marker(frame_source, max_steps=1)

        down_keys = [c[0][0] for c in backend.key_down.call_args_list]
        up_keys = [c[0][0] for c in backend.key_up.call_args_list]
        assert set(down_keys) == set(up_keys)

    def test_shutdown_event_interrupts(self, dummy_frame: np.ndarray) -> None:
        """shutdown_event.set() → return False mid-loop."""
        backend = MagicMock()
        reader = MagicMock()
        reader.is_at_destination.return_value = False
        reader.read_quest_direction.return_value = 0.0
        servo = MagicMock()
        servo.step_multi.return_value = [
            CameraIntent(yaw_delta=0.0, pitch_delta=0.0, duration_ms=50, confidence=1.0, reason="ok"),
        ]
        follower = QuestMarkerFollower(backend, reader, servo=servo)
        shutdown = threading.Event()
        call_count = [0]

        def frame_with_shutdown() -> np.ndarray | None:
            call_count[0] += 1
            if call_count[0] > 1:
                shutdown.set()
            return dummy_frame

        result = follower.navigate_to_marker(frame_with_shutdown, max_steps=50, shutdown_event=shutdown)
        assert result is False

    def test_read_quest_direction_called_each_step(self, dummy_frame: np.ndarray) -> None:
        """Each iteration calls read_quest_direction."""
        backend = MagicMock()
        reader = MagicMock()
        reader.is_at_destination.return_value = False
        reader.read_quest_direction.return_value = 0.0
        servo = MagicMock()
        servo.step_multi.return_value = [
            CameraIntent(yaw_delta=0.0, pitch_delta=0.0, duration_ms=50, confidence=1.0, reason="ok"),
        ]
        follower = QuestMarkerFollower(backend, reader, servo=servo)
        frame_source = _CountingFrameSource(dummy_frame)
        follower.navigate_to_marker(frame_source, max_steps=5)
        assert len(reader.read_quest_direction.call_args_list) == 5

    def test_skips_step_when_frame_is_none(self) -> None:
        """frame_source() returning None does not crash."""
        backend = MagicMock()
        reader = MagicMock()
        reader.is_at_destination.return_value = False
        reader.read_quest_direction.return_value = 0.0
        servo = MagicMock()
        servo.step_multi.return_value = [
            CameraIntent(yaw_delta=0.0, pitch_delta=0.0, duration_ms=50, confidence=1.0, reason="ok"),
        ]
        follower = QuestMarkerFollower(backend, reader, servo=servo)
        call_count = [0]

        def frame_or_none() -> np.ndarray | None:
            call_count[0] += 1
            if call_count[0] <= 2:
                return None
            return np.zeros((1080, 1920, 3), dtype=np.uint8)

        reader.is_at_destination.side_effect = lambda *_: call_count[0] > 2
        result = follower.navigate_to_marker(frame_or_none, max_steps=5)
        assert result is True

    def test_skips_step_when_no_marker(self, dummy_frame: np.ndarray) -> None:
        """read_quest_direction returns None → no key press."""
        backend = MagicMock()
        reader = MagicMock()
        reader.is_at_destination.return_value = False
        reader.read_quest_direction.return_value = None
        servo = MagicMock()
        servo.step_multi.return_value = [
            CameraIntent(yaw_delta=0.0, pitch_delta=0.0, duration_ms=50, confidence=1.0, reason="ok"),
        ]
        follower = QuestMarkerFollower(backend, reader, servo=servo)
        frame_source = _CountingFrameSource(dummy_frame)
        follower.navigate_to_marker(frame_source, max_steps=3)
        backend.key_down.assert_not_called()


# ---------------------------------------------------------------------------
# Integration with real MinimapQuestReader + synthetic frame
# ---------------------------------------------------------------------------

class TestNavigateWithRealMinimapeQuestReader:
    """Test using real MinimapQuestReader with synthetic frames."""

    def test_with_real_reader_and_synthetic_dot(self, dummy_frame: np.ndarray) -> None:
        """Real reader on frame with a synthetic red dot."""
        reader = MinimapQuestReader(viewport=(1920, 1080))
        servo = CameraServo(genshin_camera_servo_config())
        backend = MagicMock()
        follower = QuestMarkerFollower(backend, reader, servo)

        # Create a frame with a red dot on the minimap
        # Red HSV (H=5, S=200, V=200) → correct BGR so detection works
        import cv2 as _cv2
        arr = np.uint8([[[5, 200, 200]]])
        bgr = _cv2.cvtColor(arr, _cv2.COLOR_HSV2BGR)[0, 0]
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        dot_x = int(150)  # right side of minimap
        dot_y = int(110)
        r = 5
        frame[max(0, dot_y - r):dot_y + r, max(0, dot_x - r):dot_x + r] = bgr

        frame_source = _CountingFrameSource(frame)
        result = follower.navigate_to_marker(frame_source, max_steps=3)
        # Not at destination, max_steps exhausted
        assert result is False
        assert frame_source.call_count == 3
        # Should have pressed some keys
        assert len(backend.key_down.call_args_list) > 0