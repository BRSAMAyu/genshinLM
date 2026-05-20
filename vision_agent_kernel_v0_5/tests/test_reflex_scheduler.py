"""Tests for ReflexScheduler core: preemption, cooldown, clear verification."""
from __future__ import annotations

from core.timebase import Timebase
from reflex.scheduler import (
    DangerClearVerifier,
    PreemptionToken,
    ReflexScheduler,
    ResumeContract,
)


class TestReflexSchedulerDangerTrigger:
    """Danger above threshold triggers PreemptionToken."""

    def test_high_danger_returns_token(self) -> None:
        scheduler = ReflexScheduler(danger_threshold=0.5, cooldown_frames=0)
        token = scheduler.evaluate(danger_score=0.8, danger_type="ground", frame_id=10)
        assert token is not None
        assert isinstance(token, PreemptionToken)
        assert token.danger_score == 0.8
        assert token.danger_type == "ground"
        assert token.frame_id == 10

    def test_very_high_danger_returns_token(self) -> None:
        scheduler = ReflexScheduler(danger_threshold=0.5, cooldown_frames=0)
        token = scheduler.evaluate(danger_score=1.0, danger_type="projectile", frame_id=5)
        assert token is not None
        assert token.danger_score == 1.0


class TestReflexSchedulerCooldown:
    """Cooldown prevents repeated interrupts."""

    def test_cooldown_blocks_second_trigger(self) -> None:
        scheduler = ReflexScheduler(danger_threshold=0.5, cooldown_frames=10)
        token1 = scheduler.evaluate(danger_score=0.8, danger_type="ground", frame_id=1)
        assert token1 is not None

        # Immediate second trigger should be blocked
        token2 = scheduler.evaluate(danger_score=0.8, danger_type="ground", frame_id=2)
        assert token2 is None

    def test_cooldown_allows_after_expiry(self) -> None:
        scheduler = ReflexScheduler(danger_threshold=0.5, cooldown_frames=3)
        scheduler.evaluate(danger_score=0.8, danger_type="ground", frame_id=1)

        # Frames 2,3 are still in cooldown (counter 1,2 < 3).
        # Frame 4 reaches counter=3 which is not < 3, so it triggers again.
        for i in range(2, 4):
            token_blocked = scheduler.evaluate(
                danger_score=0.8, danger_type="ground", frame_id=i
            )
            assert token_blocked is None

        token = scheduler.evaluate(danger_score=0.8, danger_type="ground", frame_id=4)
        assert token is not None

    def test_cooldown_zero_allows_rapid_triggers(self) -> None:
        scheduler = ReflexScheduler(danger_threshold=0.5, cooldown_frames=0)
        t1 = scheduler.evaluate(danger_score=0.9, danger_type="ground", frame_id=1)
        t2 = scheduler.evaluate(danger_score=0.9, danger_type="ground", frame_id=2)
        assert t1 is not None
        assert t2 is not None


class TestReflexSchedulerBelowThreshold:
    """Danger below threshold does not trigger."""

    def test_low_danger_no_token(self) -> None:
        scheduler = ReflexScheduler(danger_threshold=0.5, cooldown_frames=0)
        token = scheduler.evaluate(danger_score=0.3, danger_type="ground", frame_id=1)
        assert token is None

    def test_zero_danger_no_token(self) -> None:
        scheduler = ReflexScheduler(danger_threshold=0.5, cooldown_frames=0)
        token = scheduler.evaluate(danger_score=0.0, danger_type="ground", frame_id=1)
        assert token is None

    def test_exactly_at_threshold_triggers(self) -> None:
        """At exactly threshold, score >= threshold, so it does trigger."""
        scheduler = ReflexScheduler(danger_threshold=0.5, cooldown_frames=0)
        token = scheduler.evaluate(danger_score=0.5, danger_type="ground", frame_id=1)
        assert token is not None
        assert token.danger_score == 0.5


class TestReflexSchedulerVerifyDangerCleared:
    """verify_danger_cleared returns ResumeContract when safe."""

    def test_returns_resume_contract_when_safe(self) -> None:
        scheduler = ReflexScheduler(danger_threshold=0.5, cooldown_frames=0)
        token = scheduler.evaluate(danger_score=0.8, danger_type="ground", frame_id=1)
        assert token is not None

        # Need 3 consecutive safe frames (default DangerClearVerifier)
        contract = None
        for i in range(5):
            contract = scheduler.verify_danger_cleared(token, danger_score=0.1)
        assert contract is not None
        assert isinstance(contract, ResumeContract)
        assert contract.preemption_token_id == token.token_id
        assert contract.safe is True

    def test_returns_none_when_still_dangerous(self) -> None:
        scheduler = ReflexScheduler(danger_threshold=0.5, cooldown_frames=0)
        token = scheduler.evaluate(danger_score=0.8, danger_type="ground", frame_id=1)
        assert token is not None

        contract = scheduler.verify_danger_cleared(token, danger_score=0.9)
        assert contract is None


class TestPreemptionTokenFields:
    """PreemptionToken has correct fields."""

    def test_token_fields_populated(self) -> None:
        tb = Timebase()
        scheduler = ReflexScheduler(
            danger_threshold=0.5, cooldown_frames=0, timebase=tb
        )
        token = scheduler.evaluate(danger_score=0.75, danger_type="hp_drop", frame_id=42)
        assert token is not None
        assert token.token_id == "preempt_1"
        assert token.danger_score == 0.75
        assert token.danger_type == "hp_drop"
        assert token.frame_id == 42
        assert token.timestamp > 0.0

    def test_token_ids_increment(self) -> None:
        scheduler = ReflexScheduler(danger_threshold=0.5, cooldown_frames=0)
        t1 = scheduler.evaluate(danger_score=0.8, danger_type="ground", frame_id=1)
        t2 = scheduler.evaluate(danger_score=0.8, danger_type="ground", frame_id=2)
        assert t1 is not None
        assert t2 is not None
        assert t1.token_id != t2.token_id


class TestDangerClearVerifier:
    """Direct tests for DangerClearVerifier."""

    def test_requires_three_safe_frames(self) -> None:
        v = DangerClearVerifier(safe_frames_required=3, danger_threshold=0.3)
        assert v.check(0.1) is False
        assert v.check(0.1) is False
        assert v.check(0.1) is True

    def test_resets_on_danger(self) -> None:
        v = DangerClearVerifier(safe_frames_required=3, danger_threshold=0.3)
        assert v.check(0.1) is False
        assert v.check(0.1) is False
        # Danger resets counter
        assert v.check(0.5) is False
        assert v.check(0.1) is False
        assert v.check(0.1) is False
        assert v.check(0.1) is True

    def test_false_clear_tracking(self) -> None:
        v = DangerClearVerifier(safe_frames_required=3, danger_threshold=0.3)
        v.check(0.1)  # safe 1
        v.check(0.1)  # safe 2
        # Danger interrupts before we reached 3 safe frames -> false clear
        v.check(0.5)
        assert v.false_clear_count == 1

    def test_reset_clears_state(self) -> None:
        v = DangerClearVerifier(safe_frames_required=3, danger_threshold=0.3)
        v.check(0.1)
        v.check(0.5)
        v.reset()
        assert v.false_clear_count == 0
