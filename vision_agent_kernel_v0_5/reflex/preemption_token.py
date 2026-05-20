from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PreemptionToken:
    """Token created when a danger-triggered preemption interrupts an action.

    Carries context about what was interrupted so that a
    :class:`ResumeContract` can later restore execution.
    """

    token_id: str
    interrupted_action_id: str | None
    interrupted_skill_id: str | None
    checkpoint_id: str | None
    reason: str  # e.g. "DANGER_DETECTED", "EMERGENCY_STOP"
    interrupt_id: str
    created_at: float
    expires_at: float
