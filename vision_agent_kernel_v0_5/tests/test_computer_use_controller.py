"""Tests for ComputerUseController — all dry-run, no real hardware."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from execution.computer_use_controller import (
    ComputerUseController,
    _best_candidate,
    _frame_to_image_input,
)
from llm.vision_provider import ImageInput, UIGroundingResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_backend() -> MagicMock:
    backend = MagicMock()
    backend.mouse_move_to = MagicMock(return_value=None)
    backend.left_click = MagicMock(return_value=None)
    return backend


@pytest.fixture
def mock_vlm() -> MagicMock:
    return MagicMock()


@pytest.fixture
def controller(mock_backend: MagicMock, mock_vlm: MagicMock) -> ComputerUseController:
    return ComputerUseController(mock_backend, mock_vlm, screen_width=1920, screen_height=1080)


@pytest.fixture
def dummy_frame() -> np.ndarray:
    return np.zeros((1080, 1920, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# find_target tests
# ---------------------------------------------------------------------------


class TestFindTarget:
    def test_returns_none_when_no_candidates(self, controller: ComputerUseController, dummy_frame: np.ndarray) -> None:
        controller._vlm.ground_ui = MagicMock(return_value=UIGroundingResult("local_vlm", "test", [], 10.0))
        assert controller.find_target(dummy_frame, "test") is None

    def test_returns_best_candidate(self, controller: ComputerUseController, dummy_frame: np.ndarray) -> None:
        candidates = [
            {"label": "b", "bbox_norm": [0.0, 0.0, 0.1, 0.1], "confidence": 0.5, "reason": "low"},
            {"label": "a", "bbox_norm": [0.2, 0.3, 0.1, 0.1], "confidence": 0.9, "reason": "high"},
        ]
        controller._vlm.ground_ui = MagicMock(
            return_value=UIGroundingResult("local_vlm", "test", candidates, 10.0),
        )
        x, y, conf = controller.find_target(dummy_frame, "test")
        assert conf == 0.9
        # bbox_norm [0.2, 0.3, 0.1, 0.1]  centre_x = 0.2*1920 + 0.1*1920/2 = 384 + 96 = 480
        # centre_y = 0.3*1080 + 0.1*1080/2 = 324 + 54 = 378
        assert x == 480
        assert y == 378

    def test_ignores_missing_bbox(self, controller: ComputerUseController, dummy_frame: np.ndarray) -> None:
        candidates = [
            {"label": "a", "confidence": 0.8, "reason": "no bbox"},
        ]
        controller._vlm.ground_ui = MagicMock(
            return_value=UIGroundingResult("local_vlm", "test", candidates, 10.0),
        )
        assert controller.find_target(dummy_frame, "test") is None


# ---------------------------------------------------------------------------
# Coordinate conversion tests
# ---------------------------------------------------------------------------


class TestCoordinateConversion:
    def test_centre_at_screen_centre(self) -> None:
        """Normalized [0.5, 0.5, 0.1, 0.1] → x=1056, y=594 per formula."""
        result = UIGroundingResult(
            "local_vlm", "test",
            [{"label": "c", "bbox_norm": [0.5, 0.5, 0.1, 0.1], "confidence": 0.9, "reason": "centre"}],
            10.0,
        )
        x, y, conf = _best_candidate(result, screen_w=1920, screen_h=1080)
        # centre_x = 0.5*1920 + 0.1*1920/2 = 960 + 96 = 1056
        # centre_y = 0.5*1080 + 0.1*1080/2 = 540 + 54 = 594
        assert x == 1056
        assert y == 594
        assert conf == 0.9

    def test_top_left_corner(self) -> None:
        result = UIGroundingResult(
            "local_vlm", "test",
            [{"label": "tl", "bbox_norm": [0.0, 0.0, 0.1, 0.1], "confidence": 1.0, "reason": "tl"}],
            10.0,
        )
        x, y, _ = _best_candidate(result, screen_w=1920, screen_h=1080)
        # x = 0*1920 + 0.1*1920/2 = 96
        # y = 0*1080 + 0.1*1080/2 = 54
        assert x == 96
        assert y == 54

    def test_bottom_right_corner(self) -> None:
        result = UIGroundingResult(
            "local_vlm", "test",
            [{"label": "br", "bbox_norm": [0.9, 0.9, 0.1, 0.1], "confidence": 1.0, "reason": "br"}],
            10.0,
        )
        x, y, _ = _best_candidate(result, screen_w=1920, screen_h=1080)
        # x = 0.9*1920 + 0.1*1920/2 = 1728 + 96 = 1824
        # y = 0.9*1080 + 0.1*1080/2 = 972 + 54 = 1026
        assert x == 1824
        assert y == 1026

    def test_empty_candidates_returns_none(self) -> None:
        result = UIGroundingResult("local_vlm", "test", [], 10.0)
        assert _best_candidate(result, 1920, 1080) is None

    def test_defaults_to_1920x1080_when_screen_size_not_provided(self) -> None:
        result = UIGroundingResult(
            "local_vlm", "test",
            [{"label": "c", "bbox_norm": [0.25, 0.25, 0.5, 0.5], "confidence": 0.9, "reason": "large"}],
            10.0,
        )
        x, y, _ = _best_candidate(result, screen_w=None, screen_h=None)
        # x = 0.25*1920 + 0.5*1920/2 = 480 + 480 = 960
        # y = 0.25*1080 + 0.5*1080/2 = 270 + 270 = 540
        assert x == 960
        assert y == 540


# ---------------------------------------------------------------------------
# move_to_target tests
# ---------------------------------------------------------------------------


class TestMoveToTarget:
    def test_calls_mouse_move_to_with_correct_coords(
        self,
        controller: ComputerUseController,
        dummy_frame: np.ndarray,
    ) -> None:
        candidates = [
            {"label": "x", "bbox_norm": [0.1, 0.2, 0.05, 0.05], "confidence": 0.8, "reason": "target"},
        ]
        controller._vlm.ground_ui = MagicMock(
            return_value=UIGroundingResult("local_vlm", "test", candidates, 10.0),
        )
        ok = controller.move_to_target(dummy_frame, "test", reason="click start button")
        assert ok is True
        # screen_x = 0.1*1920 + 0.05*1920/2 = 192 + 48 = 240
        # screen_y = 0.2*1080 + 0.05*1080/2 = 216 + 27 = 243
        controller._backend.mouse_move_to.assert_called_once_with(240, 243, "click start button")

    def test_returns_false_when_no_candidates(
        self,
        controller: ComputerUseController,
        dummy_frame: np.ndarray,
    ) -> None:
        controller._vlm.ground_ui = MagicMock(
            return_value=UIGroundingResult("local_vlm", "test", [], 10.0),
        )
        assert controller.move_to_target(dummy_frame, "test") is False

    def test_returns_false_when_backend_raises(
        self,
        controller: ComputerUseController,
        dummy_frame: np.ndarray,
    ) -> None:
        candidates = [
            {"label": "x", "bbox_norm": [0.1, 0.2, 0.05, 0.05], "confidence": 0.8, "reason": "err"},
        ]
        controller._vlm.ground_ui = MagicMock(
            return_value=UIGroundingResult("local_vlm", "test", candidates, 10.0),
        )
        controller._backend.mouse_move_to = MagicMock(side_effect=RuntimeError("focus lost"))
        assert controller.move_to_target(dummy_frame, "test") is False


# ---------------------------------------------------------------------------
# click_target tests
# ---------------------------------------------------------------------------


class TestClickTarget:
    def test_calls_mouse_move_to_then_left_click(
        self,
        controller: ComputerUseController,
        dummy_frame: np.ndarray,
    ) -> None:
        candidates = [
            {"label": "x", "bbox_norm": [0.5, 0.5, 0.1, 0.1], "confidence": 0.9, "reason": "btn"},
        ]
        controller._vlm.ground_ui = MagicMock(
            return_value=UIGroundingResult("local_vlm", "test", candidates, 10.0),
        )
        ok = controller.click_target(dummy_frame, "test", reason="confirm")
        assert ok is True
        controller._backend.mouse_move_to.assert_called_once()
        controller._backend.left_click.assert_called_once_with("confirm")

    def test_returns_false_when_move_fails(
        self,
        controller: ComputerUseController,
        dummy_frame: np.ndarray,
    ) -> None:
        controller._vlm.ground_ui = MagicMock(
            return_value=UIGroundingResult("local_vlm", "test", [], 10.0),
        )
        assert controller.click_target(dummy_frame, "test") is False
        controller._backend.left_click.assert_not_called()

    def test_returns_false_when_click_raises(
        self,
        controller: ComputerUseController,
        dummy_frame: np.ndarray,
    ) -> None:
        candidates = [
            {"label": "x", "bbox_norm": [0.5, 0.5, 0.1, 0.1], "confidence": 0.9, "reason": "err"},
        ]
        controller._vlm.ground_ui = MagicMock(
            return_value=UIGroundingResult("local_vlm", "test", candidates, 10.0),
        )
        controller._backend.left_click = MagicMock(side_effect=RuntimeError("click failed"))
        assert controller.click_target(dummy_frame, "test") is False


# ---------------------------------------------------------------------------
# interact_with_query tests
# ---------------------------------------------------------------------------


class TestInteractWithQuery:
    def test_includes_settle_delay(self, controller: ComputerUseController, dummy_frame: np.ndarray) -> None:
        candidates = [
            {"label": "x", "bbox_norm": [0.5, 0.5, 0.1, 0.1], "confidence": 0.9, "reason": "btn"},
        ]
        controller._vlm.ground_ui = MagicMock(
            return_value=UIGroundingResult("local_vlm", "test", candidates, 10.0),
        )
        with patch("execution.computer_use_controller.time.sleep") as mock_sleep:
            controller.interact_with_query(dummy_frame, "test", reason="dialog confirm")
            mock_sleep.assert_called_once_with(0.3)

    def test_propagates_sleep_error(self, controller: ComputerUseController, dummy_frame: np.ndarray) -> None:
        """InterruptedError from sleep is not caught — it propagates (unusual interruption)."""
        candidates = [
            {"label": "x", "bbox_norm": [0.5, 0.5, 0.1, 0.1], "confidence": 0.9, "reason": "err"},
        ]
        controller._vlm.ground_ui = MagicMock(
            return_value=UIGroundingResult("local_vlm", "test", candidates, 10.0),
        )
        with patch("execution.computer_use_controller.time.sleep", side_effect=InterruptedError("sleep err")):
            with pytest.raises(InterruptedError):
                controller.interact_with_query(dummy_frame, "test", reason="err")


# ---------------------------------------------------------------------------
# execute_until_success tests
# ---------------------------------------------------------------------------


class TestExecuteUntilSuccess:
    def test_succeeds_on_first_attempt(self, controller: ComputerUseController, dummy_frame: np.ndarray) -> None:
        candidates = [
            {"label": "x", "bbox_norm": [0.5, 0.5, 0.1, 0.1], "confidence": 0.9, "reason": "ok"},
        ]
        controller._vlm.ground_ui = MagicMock(
            return_value=UIGroundingResult("local_vlm", "test", candidates, 10.0),
        )
        with patch("execution.computer_use_controller.time.sleep") as mock_sleep:
            ok = controller.execute_until_success(dummy_frame, "test", action="click")
        assert ok is True
        # interact_with_query always calls time.sleep(0.3) as settle delay; no retries needed
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(0.3)

    def test_retries_on_failure(self, controller: ComputerUseController, dummy_frame: np.ndarray) -> None:
        candidates = [
            {"label": "x", "bbox_norm": [0.5, 0.5, 0.1, 0.1], "confidence": 0.9, "reason": "ok"},
        ]
        controller._vlm.ground_ui = MagicMock(
            return_value=UIGroundingResult("local_vlm", "test", candidates, 10.0),
        )
        controller._backend.mouse_move_to = MagicMock(side_effect=[RuntimeError("first"), None])

        with patch("execution.computer_use_controller.time.sleep") as mock_sleep:
            ok = controller.execute_until_success(dummy_frame, "test", action="click", max_retries=3, retry_delay=1.5)

        assert ok is True
        # Each attempt calls sleep(0.3) for settle delay; retries call sleep(retry_delay)
        # Attempt 1 fails → retry_delay sleep; attempt 2 succeeds (no retry_delay after last)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.5)  # retry_delay between attempts
        mock_sleep.assert_any_call(0.3)  # settle delay

    def test_returns_false_when_all_retries_fail(self, controller: ComputerUseController, dummy_frame: np.ndarray) -> None:
        controller._vlm.ground_ui = MagicMock(
            return_value=UIGroundingResult("local_vlm", "test", [], 10.0),
        )
        with patch("execution.computer_use_controller.time.sleep") as mock_sleep:
            ok = controller.execute_until_success(dummy_frame, "test", max_retries=3, retry_delay=0.5)
        assert ok is False
        # 3 attempts all fail on move_to_target (no candidates).
        # retry_delay=0.5 is called after each of the 3 attempts (including last one).
        assert mock_sleep.call_count == 3
        for call in mock_sleep.call_args_list:
            assert call[0][0] == 0.5

    def test_hover_action_only_moves(self, controller: ComputerUseController, dummy_frame: np.ndarray) -> None:
        candidates = [
            {"label": "x", "bbox_norm": [0.5, 0.5, 0.1, 0.1], "confidence": 0.9, "reason": "ok"},
        ]
        controller._vlm.ground_ui = MagicMock(
            return_value=UIGroundingResult("local_vlm", "test", candidates, 10.0),
        )
        with patch("execution.computer_use_controller.time.sleep"):
            ok = controller.execute_until_success(dummy_frame, "test", action="hover")
        assert ok is True
        controller._backend.mouse_move_to.assert_called_once()
        controller._backend.left_click.assert_not_called()


# ---------------------------------------------------------------------------
# _frame_to_image_input tests
# ---------------------------------------------------------------------------


class TestFrameToImageInput:
    def test_converts_rgb_frame(self) -> None:
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        img = _frame_to_image_input(frame)
        assert isinstance(img, ImageInput)
        assert img.mime_type == "image/png"
        assert len(img.data) > 0

    def test_converts_grayscale_frame(self) -> None:
        frame = np.zeros((1080, 1920), dtype=np.uint8)
        img = _frame_to_image_input(frame)
        assert isinstance(img, ImageInput)
        assert len(img.data) > 0

    def test_accepts_float_frame_by_normalizing(self) -> None:
        frame = np.zeros((100, 100, 3), dtype=np.float32)
        img = _frame_to_image_input(frame)
        assert isinstance(img, ImageInput)