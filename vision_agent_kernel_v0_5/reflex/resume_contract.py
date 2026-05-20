from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ResumeContract:
    """Contract that must be satisfied before resuming after a reflex preemption.

    Created once the :class:`DangerClearVerifier` confirms the danger has
    passed. Downstream consumers check ``status`` before resuming execution.
    """

    contract_id: str
    preemption_token_id: str
    checkpoint_id: str
    required_evidence_ids: list[str] = field(default_factory=list)
    reacquire_required: bool = True
    max_resume_delay_ms: int = 2000
    status: str = "PENDING"  # PENDING, SATISFIED, EXPIRED
    satisfied_at: float | None = None
