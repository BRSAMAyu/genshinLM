"""Tests for Phase 8: DialogChoiceExecutionBridge.

Verifies:
- Arbiter claim triggers actual click execution
- Click produces physical receipt
- Invalid selected_index returns clicked=False
- Verify callback is called after click
"""
from __future__ import annotations

from planning.dialog_choice_arbiter import DialogChoice, DialogChoiceClaim
from planning.dialog_choice_execution_bridge import (
    DialogChoiceExecutionBridge,
    DialogExecutionReceipt,
)


def _make_claim(selected: int = 0, count: int = 3) -> DialogChoiceClaim:
    choices = tuple(
        DialogChoice(
            index=i,
            text=f"Option {i}",
            bbox_norm=(0.1 * i, 0.8, 0.15, 0.05),
        )
        for i in range(count)
    )
    return DialogChoiceClaim(
        claim_id="test_claim_1",
        frame_id=1,
        timestamp=0.0,
        choices=choices,
        selected_index=selected,
        confidence=0.8,
    )


class _FakeClickExecutor:
    def __init__(self, success: bool = True):
        self.clicked: list[tuple[int, tuple[float, ...]]] = []
        self._success = success

    def click_choice(self, choice_index: int, bbox_norm: tuple[float, ...]) -> bool:
        self.clicked.append((choice_index, bbox_norm))
        return self._success


class TestDialogChoiceExecutionBridge:
    """Test DialogChoiceExecutionBridge execution path."""

    def test_valid_claim_triggers_click(self):
        executor = _FakeClickExecutor()
        bridge = DialogChoiceExecutionBridge(click_executor=executor, verify_fn=lambda idx: True)
        claim = _make_claim(selected=1)
        receipt = bridge.execute_claim(claim)

        assert receipt.clicked is True
        assert receipt.verified is True
        assert executor.clicked[0][0] == 1  # clicked choice index 1

    def test_click_uses_correct_bbox(self):
        executor = _FakeClickExecutor()
        bridge = DialogChoiceExecutionBridge(click_executor=executor)
        claim = _make_claim(selected=2)
        bridge.execute_claim(claim)

        assert executor.clicked[0][1] == (0.2, 0.8, 0.15, 0.05)

    def test_invalid_selected_index_returns_not_clicked(self):
        executor = _FakeClickExecutor()
        bridge = DialogChoiceExecutionBridge(click_executor=executor)
        claim = _make_claim(selected=99)
        receipt = bridge.execute_claim(claim)

        assert receipt.clicked is False
        assert receipt.verified is False
        assert "invalid" in receipt.error
        assert len(executor.clicked) == 0

    def test_negative_selected_index_returns_not_clicked(self):
        executor = _FakeClickExecutor()
        bridge = DialogChoiceExecutionBridge(click_executor=executor)
        claim = _make_claim(selected=-1)
        receipt = bridge.execute_claim(claim)

        assert receipt.clicked is False

    def test_click_failure_returns_receipt(self):
        executor = _FakeClickExecutor(success=False)
        bridge = DialogChoiceExecutionBridge(click_executor=executor)
        claim = _make_claim(selected=0)
        receipt = bridge.execute_claim(claim)

        assert receipt.clicked is False
        assert receipt.error == "click_rejected"

    def test_verify_callback_checked(self):
        executor = _FakeClickExecutor()
        verify_calls: list[int] = []
        bridge = DialogChoiceExecutionBridge(
            click_executor=executor,
            verify_fn=lambda idx: (verify_calls.append(idx) or True),
        )
        claim = _make_claim(selected=0)
        receipt = bridge.execute_claim(claim)

        assert receipt.verified is True
        assert verify_calls == [0]

    def test_verify_failure_returns_not_verified(self):
        executor = _FakeClickExecutor()
        bridge = DialogChoiceExecutionBridge(
            click_executor=executor,
            verify_fn=lambda idx: False,
        )
        claim = _make_claim(selected=0)
        receipt = bridge.execute_claim(claim)

        assert receipt.clicked is True
        assert receipt.verified is False

    def test_no_executor_returns_not_clicked(self):
        bridge = DialogChoiceExecutionBridge(click_executor=None)
        claim = _make_claim(selected=0)
        receipt = bridge.execute_claim(claim)

        assert receipt.clicked is False
        assert receipt.verified is False
        assert receipt.error == "no_click_executor"

    def test_allow_unverified_is_explicit_test_mode(self):
        executor = _FakeClickExecutor()
        bridge = DialogChoiceExecutionBridge(click_executor=executor, allow_unverified=True)
        claim = _make_claim(selected=0)
        receipt = bridge.execute_claim(claim)

        assert receipt.clicked is True
        assert receipt.verified is True

    def test_receipt_contains_claim_id(self):
        bridge = DialogChoiceExecutionBridge()
        claim = _make_claim(selected=0)
        receipt = bridge.execute_claim(claim)

        assert receipt.claim_id == "test_claim_1"
        assert receipt.selected_index == 0

    def test_call_count_increments(self):
        bridge = DialogChoiceExecutionBridge()
        assert bridge.call_count == 0
        bridge.execute_claim(_make_claim())
        assert bridge.call_count == 1
        bridge.execute_claim(_make_claim())
        assert bridge.call_count == 2
