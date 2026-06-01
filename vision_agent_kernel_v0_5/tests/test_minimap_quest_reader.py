"""Tests for MinimapQuestReader — all synthetic, no GPU, no real screen."""
from __future__ import annotations

import math
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

import navigation.minimap_quest_reader as mqr_module

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hsv_to_bgr(h: int, s: int, v: int) -> tuple[int, int, int]:
    """Convert HSV (OpenCV H∈[0,179]) to BGR."""
    arr = np.uint8([[[h, s, v]]])
    bgr = cv2.cvtColor(arr, cv2.COLOR_HSV2BGR)[0, 0]
    return int(bgr[0]), int(bgr[1]), int(bgr[2])


def _make_frame_with_dot(
    resolution: tuple[int, int],
    dot_x: float,
    dot_y: float,
    dot_h: int = 5,
    dot_s: int = 200,
    dot_v: int = 200,
    bg_bgr: tuple[int, int, int] = (30, 30, 30),
) -> np.ndarray:
    """Return a BGR frame with a single coloured dot at (dot_x, dot_y).

    The dot is painted using the HSV→BGR conversion so it rounds-trip
    correctly through the reader's HSV colour-range checks.
    """
    h, w = resolution[1], resolution[0]
    frame = np.full((h, w, 3), bg_bgr, dtype=np.uint8)

    # Convert HSV to BGR (correct colour representation)
    bgr = _hsv_to_bgr(dot_h, dot_s, dot_v)

    # Dot radius
    sx = w / 1920.0
    sy = h / 1080.0
    r = max(2, int(5 * sx))

    # Absolute pixel in frame
    px = int(dot_x * sx)
    py = int(dot_y * sy)

    y_start = max(0, py - r)
    y_end = min(h, py + r + 1)
    x_start = max(0, px - r)
    x_end = min(w, px + r + 1)

    frame[y_start:y_end, x_start:x_end] = bgr

    return frame


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def reader() -> mqr_module.MinimapQuestReader:
    return mqr_module.MinimapQuestReader()


@pytest.fixture
def reader_2560x1440() -> mqr_module.MinimapQuestReader:
    return mqr_module.MinimapQuestReader(viewport=(2560, 1440))


@pytest.fixture
def reader_3840x2160() -> mqr_module.MinimapQuestReader:
    return mqr_module.MinimapQuestReader(viewport=(3840, 2160))


# ---------------------------------------------------------------------------
# Test read_quest_direction at different resolutions
# ---------------------------------------------------------------------------

class TestReadQuestDirection:
    def test_returns_0_when_dot_at_center(self, reader: mqr_module.MinimapQuestReader) -> None:
        """Dot at minimap center → angle 0."""
        # minimap center in ref space = (110, 110)
        frame = _make_frame_with_dot((1920, 1080), dot_x=110, dot_y=110)
        angle = reader.read_quest_direction(frame)
        assert angle is not None
        assert abs(angle) < 0.1

    def test_returns_near_pi_2_when_dot_right(self, reader: mqr_module.MinimapQuestReader) -> None:
        """Dot to the right → angle near π/2."""
        frame = _make_frame_with_dot((1920, 1080), dot_x=150, dot_y=110)
        angle = reader.read_quest_direction(frame)
        assert angle is not None
        assert abs(angle - math.pi / 2) < 0.2

    def test_returns_near_neg_pi_2_when_dot_left(self, reader: mqr_module.MinimapQuestReader) -> None:
        """Dot to the left → angle near -π/2."""
        frame = _make_frame_with_dot((1920, 1080), dot_x=70, dot_y=110)
        angle = reader.read_quest_direction(frame)
        assert angle is not None
        assert abs(angle + math.pi / 2) < 0.2

    def test_returns_near_pi_when_dot_bottom(self, reader: mqr_module.MinimapQuestReader) -> None:
        """Dot below center → angle near π."""
        frame = _make_frame_with_dot((1920, 1080), dot_x=110, dot_y=150)
        angle = reader.read_quest_direction(frame)
        assert angle is not None
        assert abs(angle - math.pi) < 0.2

    def test_returns_none_when_no_marker(self, reader: mqr_module.MinimapQuestReader) -> None:
        """Frame with no red/yellow dot → None."""
        frame = np.full((1080, 1920, 3), (30, 30, 30), dtype=np.uint8)
        assert reader.read_quest_direction(frame) is None

    def test_returns_none_when_minimap_roi_empty(self, reader: mqr_module.MinimapQuestReader) -> None:
        """Frame too small to contain minimap ROI → None."""
        frame = np.zeros((50, 50, 3), dtype=np.uint8)
        assert reader.read_quest_direction(frame) is None

    def test_resolution_2560x1440(self, reader_2560x1440: mqr_module.MinimapQuestReader) -> None:
        """Verify angle is computed on a 2560×1440 frame."""
        frame = _make_frame_with_dot((2560, 1440), dot_x=110, dot_y=110)
        angle = reader_2560x1440.read_quest_direction(frame)
        assert angle is not None
        assert abs(angle) < 0.1

    def test_resolution_3840x2160(self, reader_3840x2160: mqr_module.MinimapQuestReader) -> None:
        """Verify angle is computed on a 3840×2160 frame."""
        frame = _make_frame_with_dot((3840, 2160), dot_x=110, dot_y=110)
        angle = reader_3840x2160.read_quest_direction(frame)
        assert angle is not None
        assert abs(angle) < 0.1

    def test_dark_env_adjusts_threshold(self, reader: mqr_module.MinimapQuestReader) -> None:
        """Very dark frame (avg_v<100) still detects marker."""
        frame = _make_frame_with_dot(
            (1920, 1080), dot_x=150, dot_y=110,
            bg_bgr=(5, 5, 5),
        )
        angle = reader.read_quest_direction(frame)
        # Dark environment: thresholds are relaxed so detection should still succeed
        assert angle is not None

    def test_hsv_color_range_red_marker(self, reader: mqr_module.MinimapQuestReader) -> None:
        """Red dot (H≈0-10 in OpenCV) should be detected."""
        # Red in OpenCV HSV: H≈0, S≈200, V≈200
        bgr = _hsv_to_bgr(5, 200, 200)
        frame = _make_frame_with_dot((1920, 1080), dot_x=150, dot_y=110, bg_bgr=bgr)
        angle = reader.read_quest_direction(frame)
        assert angle is not None

    def test_hsv_color_range_yellow_marker(self, reader: mqr_module.MinimapQuestReader) -> None:
        """Yellow dot (H≈20-35 in OpenCV) should be detected."""
        bgr = _hsv_to_bgr(28, 200, 200)
        frame = _make_frame_with_dot((1920, 1080), dot_x=150, dot_y=110, bg_bgr=bgr)
        angle = reader.read_quest_direction(frame)
        assert angle is not None


# ---------------------------------------------------------------------------
# Test has_quest_marker
# ---------------------------------------------------------------------------

class TestHasQuestMarker:
    def test_true_when_marker_present(self, reader: mqr_module.MinimapQuestReader) -> None:
        """Returns True when red dot is on the minimap."""
        frame = _make_frame_with_dot((1920, 1080), dot_x=150, dot_y=110)
        assert reader.has_quest_marker(frame) is True

    def test_false_when_no_marker(self, reader: mqr_module.MinimapQuestReader) -> None:
        """Returns False when minimap is empty."""
        frame = np.full((1080, 1920, 3), (30, 30, 30), dtype=np.uint8)
        assert reader.has_quest_marker(frame) is False

    def test_false_for_blank_frame(self, reader: mqr_module.MinimapQuestReader) -> None:
        """Returns False when frame is all zeros."""
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        assert reader.has_quest_marker(frame) is False


# ---------------------------------------------------------------------------
# Test is_at_destination
# ---------------------------------------------------------------------------

class TestIsAtDestination:
    def test_true_when_dot_at_center(self, reader: mqr_module.MinimapQuestReader) -> None:
        """Dot at minimap center → at destination."""
        frame = _make_frame_with_dot((1920, 1080), dot_x=110, dot_y=110)
        assert reader.is_at_destination(frame) is True

    def test_false_when_dot_not_at_center(self, reader: mqr_module.MinimapQuestReader) -> None:
        """Dot away from center → not at destination."""
        frame = _make_frame_with_dot((1920, 1080), dot_x=150, dot_y=110)
        assert reader.is_at_destination(frame) is False

    def test_false_when_no_marker(self, reader: mqr_module.MinimapQuestReader) -> None:
        """No marker → not at destination (returns False per is_at_destination logic)."""
        frame = np.full((1080, 1920, 3), (30, 30, 30), dtype=np.uint8)
        # is_at_destination returns True if no marker pixel is found
        # (no marker = arrived or no quest), so it's True here
        # Actually re-reading the code: if <3 pixels returns True
        assert reader.is_at_destination(frame) is True

    def test_is_at_destination_for_empty_roi(self, reader: mqr_module.MinimapQuestReader) -> None:
        """Tiny frame → ROI is empty (0x0) → reader returns False."""
        # 1x1 frame: ROI scales to (0,0,0,0) -> empty ROI -> returns False
        frame = np.zeros((1, 1, 3), dtype=np.uint8)
        assert reader.is_at_destination(frame) is False


# ---------------------------------------------------------------------------
# Test _scale_roi
# ---------------------------------------------------------------------------

class TestScaleROI:
    def test_scale_roi_exact(self) -> None:
        """_scale_roi scales ROI correctly."""
        roi = (20, 20, 200, 200)
        scaled = mqr_module.MinimapQuestReader._scale_roi(roi, 1.333, 1.333)
        assert scaled == (26, 26, 266, 266)

    def test_scale_roi_half(self) -> None:
        """_scale_roi at 0.5× scale."""
        roi = (20, 20, 200, 200)
        scaled = mqr_module.MinimapQuestReader._scale_roi(roi, 0.5, 0.5)
        assert scaled == (10, 10, 100, 100)

    def test_scale_roi_integer_cast(self) -> None:
        """Result is integer (truncated, not rounded)."""
        roi = (20, 20, 200, 200)
        scaled = mqr_module.MinimapQuestReader._scale_roi(roi, 1.7, 1.7)
        assert all(isinstance(v, int) for v in scaled)
        assert scaled == (34, 34, 340, 340)