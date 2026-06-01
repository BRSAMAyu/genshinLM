"""Tests for DialogChoiceArbiter — VLM arbitration for dialog branch selection."""
from __future__ import annotations

import pytest

from planning.dialog_choice_arbiter import (
    DialogChoice,
    DialogChoiceArbiter,
    DialogChoiceClaim,
)


def _choice(index: int, text: str = "Option") -> DialogChoice:
    return DialogChoice(
        index=index,
        text=text,
        bbox_norm=(0.1, 0.1, 0.9, 0.9),
    )


def _mock_analyzer_high_conf():
    """Mock analyzer that returns high confidence."""
    class MockAnalyzer:
        def select_choice(self, choices, context):
            return (0, 0.95)
    return MockAnalyzer()


def _mock_analyzer_low_conf():
    """Mock analyzer that returns low confidence."""
    class MockAnalyzer:
        def select_choice(self, choices, context):
            return (1, 0.3)
    return MockAnalyzer()


def _mock_vlm(response_text: str):
    """Create mock VLM function."""
    def vlm_fn(frame, prompt):
        return response_text
    return vlm_fn


class TestDialogChoiceArbiter:
    def test_high_confidence_analyzer_selection(self) -> None:
        arbiter = DialogChoiceArbiter(
            branch_analyzer=_mock_analyzer_high_conf(),
        )
        choices = [_choice(0, "Yes"), _choice(1, "No")]
        claim = arbiter.select_choice(None, choices)
        assert claim.selected_index == 0
        assert claim.confidence >= 0.9

    def test_low_confidence_falls_to_vlm(self) -> None:
        arbiter = DialogChoiceArbiter(
            branch_analyzer=_mock_analyzer_low_conf(),
            vlm_arbiter_fn=_mock_vlm("option 1"),
        )
        choices = [_choice(0, "Yes"), _choice(1, "No")]
        claim = arbiter.select_choice(None, choices)
        assert claim.selected_index == 1
        assert arbiter.vlm_call_count == 1

    def test_no_analyzer_no_vlm_picks_first(self) -> None:
        arbiter = DialogChoiceArbiter()
        choices = [_choice(0, "A"), _choice(1, "B")]
        claim = arbiter.select_choice(None, choices)
        assert claim.selected_index == 0
        assert claim.confidence <= 0.5

    def test_vlm_call_limit(self) -> None:
        arbiter = DialogChoiceArbiter(
            branch_analyzer=_mock_analyzer_low_conf(),
            vlm_arbiter_fn=_mock_vlm("0"),
        )
        # Exhaust VLM limit
        for _ in range(20):
            arbiter.select_choice(None, [_choice(0), _choice(1)])
        assert arbiter.vlm_call_count == 20
        # Next call should fall back to first choice
        claim = arbiter.select_choice(None, [_choice(0), _choice(1)])
        assert claim.confidence <= 0.5

    def test_reset_vlm_counter(self) -> None:
        arbiter = DialogChoiceArbiter(
            branch_analyzer=_mock_analyzer_low_conf(),
            vlm_arbiter_fn=_mock_vlm("0"),
        )
        arbiter.select_choice(None, [_choice(0)])
        assert arbiter.vlm_call_count == 1
        arbiter.reset_vlm_counter()
        assert arbiter.vlm_call_count == 0

    def test_claim_dataclass_fields(self) -> None:
        arbiter = DialogChoiceArbiter()
        choices = [_choice(0, "Test")]
        claim = arbiter.select_choice(None, choices)
        assert isinstance(claim, DialogChoiceClaim)
        assert isinstance(claim.claim_id, str)
        assert isinstance(claim.choices, tuple)
        assert 0.0 <= claim.confidence <= 1.0

    def test_empty_choices_handled(self) -> None:
        arbiter = DialogChoiceArbiter()
        claim = arbiter.select_choice(None, [])
        assert claim.selected_index == -1 or claim.selected_index == 0
