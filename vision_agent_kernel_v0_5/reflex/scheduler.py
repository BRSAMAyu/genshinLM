from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.events import Interrupt
from core.timebase import Timebase


@dataclass(slots=True)
class PreemptionToken:
    """Token issued when a danger triggers a preemption."""

    token_id: str
    danger_score: float
    danger_type: str
    timestamp: float
    frame_id: int
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResumeContract:
    """Contract returned when danger is verified as cleared."""

    contract_id: str
    preemption_token_id: str
    verified_at: float
    evidence_ids: list[str] = field(default_factory=list)
    safe: bool = True


class DangerClearVerifier:
    """Verifies whether a danger condition has actually cleared.

    Requires multiple consecutive safe frames (default 3) before
    declaring the danger cleared, to avoid false-clear detections.
    """

    def __init__(self, safe_frames_required: int = 3, danger_threshold: float = 0.3) -> None:
        self._safe_frames_required = safe_frames_required
        self._danger_threshold = danger_threshold
        self._consecutive_safe: int = 0
        self._total_checks: int = 0
        self._false_clears: int = 0

    def check(self, danger_score: float) -> bool:
        """Return True if the danger is verified as cleared."""
        self._total_checks += 1
        if danger_score < self._danger_threshold:
            self._consecutive_safe += 1
        else:
            if self._consecutive_safe > 0 and self._consecutive_safe < self._safe_frames_required:
                self._false_clears += 1
            self._consecutive_safe = 0
        return self._consecutive_safe >= self._safe_frames_required

    def verify(
        self,
        token: PreemptionToken,
        danger_score: float,
        timebase: Timebase,
        evidence_ids: list[str] | None = None,
    ) -> ResumeContract | None:
        """Verify danger is cleared and return a ResumeContract, or None if still unsafe."""
        if not self.check(danger_score):
            return None
        return ResumeContract(
            contract_id=f"resume_{token.token_id}",
            preemption_token_id=token.token_id,
            verified_at=timebase.now(),
            evidence_ids=evidence_ids or [],
            safe=True,
        )

    @property
    def false_clear_count(self) -> int:
        return self._false_clears

    def reset(self) -> None:
        self._consecutive_safe = 0
        self._total_checks = 0
        self._false_clears = 0


class ReflexScheduler:
    """Evaluates danger signals and decides whether to preempt.

    Issues PreemptionToken when danger exceeds threshold. Enforces a
    cooldown between successive preemptions to avoid thrashing.
    """

    def __init__(
        self,
        danger_threshold: float = 0.5,
        cooldown_frames: int = 15,
        timebase: Timebase | None = None,
    ) -> None:
        self._danger_threshold = danger_threshold
        self._cooldown_frames = cooldown_frames
        self._timebase = timebase or Timebase()
        self._frames_since_last: int = cooldown_frames  # start ready
        self._token_counter: int = 0
        self._clear_verifier = DangerClearVerifier()

    @property
    def clear_verifier(self) -> DangerClearVerifier:
        return self._clear_verifier

    def evaluate(
        self,
        danger_score: float,
        danger_type: str,
        frame_id: int,
    ) -> PreemptionToken | None:
        """Evaluate danger and return PreemptionToken if threshold exceeded and not in cooldown."""
        self._frames_since_last += 1
        if danger_score < self._danger_threshold:
            return None
        if self._frames_since_last < self._cooldown_frames:
            return None
        self._token_counter += 1
        self._frames_since_last = 0
        token = PreemptionToken(
            token_id=f"preempt_{self._token_counter}",
            danger_score=danger_score,
            danger_type=danger_type,
            timestamp=self._timebase.now(),
            frame_id=frame_id,
        )
        return token

    def verify_danger_cleared(
        self,
        token: PreemptionToken,
        danger_score: float,
        evidence_ids: list[str] | None = None,
    ) -> ResumeContract | None:
        """Verify that the danger has cleared after a preemption.

        Returns ResumeContract when safe, None otherwise.
        """
        return self._clear_verifier.verify(
            token, danger_score, self._timebase, evidence_ids
        )

    def make_interrupt(self, token: PreemptionToken) -> Interrupt:
        """Convert a PreemptionToken into a StateBus Interrupt."""
        return Interrupt(
            priority=0,
            timestamp=token.timestamp,
            code="REFLEX_PREEMPT",
            source="reflex_scheduler",
            frame_id=token.frame_id,
            payload={
                "token_id": token.token_id,
                "danger_score": token.danger_score,
                "danger_type": token.danger_type,
            },
            recoverable=True,
            requires_input_release=True,
        )

    def reset(self) -> None:
        self._frames_since_last = self._cooldown_frames
        self._token_counter = 0
        self._clear_verifier.reset()
