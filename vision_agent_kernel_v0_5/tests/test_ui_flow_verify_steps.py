"""Tests for UIFlow engine OCR verification step primitives."""
from __future__ import annotations

import pytest

from interaction.ui_flow_engine import (
    STEP_VERIFY_OCR_NUMBER,
    STEP_VERIFY_SCREEN_CONTAINS,
    UIStep,
    verify_ocr_number,
    verify_screen_contains,
)


class TestVerifyOcrNumber:
    def test_creates_correct_step_type(self) -> None:
        step = verify_ocr_number(reason="test_level")
        assert step.type == STEP_VERIFY_OCR_NUMBER
        assert step.reason == "test_level"

    def test_sets_expected_min(self) -> None:
        step = verify_ocr_number(expected_min=40)
        assert step.ocr_expected_min == 40
        assert step.ocr_expected_max is None

    def test_sets_expected_range(self) -> None:
        step = verify_ocr_number(expected_min=1, expected_max=90)
        assert step.ocr_expected_min == 1
        assert step.ocr_expected_max == 90

    def test_step_is_frozen(self) -> None:
        step = verify_ocr_number()
        assert isinstance(step, UIStep)
        with pytest.raises(AttributeError):
            step.type = "other"


class TestVerifyScreenContains:
    def test_creates_correct_step_type(self) -> None:
        step = verify_screen_contains("升级成功")
        assert step.type == STEP_VERIFY_SCREEN_CONTAINS
        assert step.expected_text == "升级成功"

    def test_empty_text_allowed(self) -> None:
        step = verify_screen_contains("")
        assert step.expected_text == ""

    def test_reason_passed_through(self) -> None:
        step = verify_screen_contains("test", reason="verify_notification")
        assert step.reason == "verify_notification"
