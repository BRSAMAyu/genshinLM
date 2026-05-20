"""Core data contracts for proof-carrying visual control.

Completely app-agnostic — no domain-specific imports or assumptions.
Every action that touches the input stream is wrapped in a ProofCarryingAction
that carries its own verification contract, expected state delta, and recovery
policy so the kernel can prove *before* and *after* that the action had the
intended effect.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------
PROPOSED = "PROPOSED"
AUTHORIZED = "AUTHORIZED"
LEASED = "LEASED"
EXECUTED = "EXECUTED"
VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
VERIFIED_FAILED = "VERIFIED_FAILED"
RECOVERED = "RECOVERED"
ABORTED = "ABORTED"


# ---------------------------------------------------------------------------
# Composite dataclasses
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ActionIntent:
    """What the agent intends to do."""

    intent_id: str
    kind: str  # e.g. "move", "dodge", "attack", "interact", "navigate"
    params: dict[str, object]
    reason: str


@dataclass(slots=True)
class ExpectedStateDelta:
    """Observable changes expected after a successful action."""

    delta_id: str
    description: str
    success_triggers: list[str]  # observable state changes that confirm success
    forbidden_regressions: list[str]  # state changes that mean failure
    timeout_ms: int


@dataclass(slots=True)
class VerifierContract:
    """What evidence the verifier needs to confirm or deny the delta."""

    contract_id: str
    verifier_id: str
    required_evidence_types: list[str]  # e.g. ["frame", "roi", "danger_score"]
    min_confidence: float
    roi_ids: list[str]
    timeout_ms: int


@dataclass(slots=True)
class RecoveryPolicyRef:
    """Reference to the recovery strategy if verification fails."""

    policy_id: str
    strategy: str  # "retry", "fallback", "abort", "escalate"
    max_retries: int


@dataclass(slots=True)
class ProofCarryingAction:
    """Top-level envelope: action intent + verification contract + recovery."""

    action_id: str
    mission_id: str | None
    node_id: str | None
    skill_id: str | None
    precondition_evidence_ids: list[str]
    action_intent: ActionIntent
    input_lease_id: str | None
    expected_state_delta: ExpectedStateDelta
    verifier_contract: VerifierContract
    recovery_policy: RecoveryPolicyRef
    telemetry_trace_id: str
    learning_hook_id: str | None
    status: str  # one of the STATUS constants above
    created_at: float
    finished_at: float | None = None
    verifier_result_id: str | None = None


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------
def make_action(
    kind: str,
    params: dict[str, object],
    reason: str,
    verifier_id: str = "default",
    min_confidence: float = 0.8,
    strategy: str = "retry",
    max_retries: int = 2,
    **kwargs: object,
) -> ProofCarryingAction:
    """Create a fully-populated :class:`ProofCarryingAction` with auto-generated IDs.

    Any extra *kwargs* are forwarded to :class:`ProofCarryingAction` fields
    (e.g. ``mission_id``, ``node_id``, ``skill_id``, ``input_lease_id``,
    ``learning_hook_id``, ``precondition_evidence_ids``).
    """
    now = time.perf_counter()

    action_intent = ActionIntent(
        intent_id=uuid.uuid4().hex,
        kind=kind,
        params=params,
        reason=reason,
    )

    expected_state_delta = ExpectedStateDelta(
        delta_id=uuid.uuid4().hex,
        description=reason,
        success_triggers=list(kwargs.get("success_triggers", [])),  # type: ignore[arg-type]
        forbidden_regressions=list(kwargs.get("forbidden_regressions", [])),  # type: ignore[arg-type]
        timeout_ms=int(kwargs.get("timeout_ms", 5000)),  # type: ignore[arg-type]
    )

    verifier_contract = VerifierContract(
        contract_id=uuid.uuid4().hex,
        verifier_id=verifier_id,
        required_evidence_types=list(kwargs.get("required_evidence_types", ["frame"])),  # type: ignore[arg-type]
        min_confidence=min_confidence,
        roi_ids=list(kwargs.get("roi_ids", [])),  # type: ignore[arg-type]
        timeout_ms=int(kwargs.get("timeout_ms", 5000)),  # type: ignore[arg-type]
    )

    recovery_policy = RecoveryPolicyRef(
        policy_id=uuid.uuid4().hex,
        strategy=strategy,
        max_retries=max_retries,
    )

    return ProofCarryingAction(
        action_id=uuid.uuid4().hex,
        mission_id=kwargs.get("mission_id"),  # type: ignore[arg-type]
        node_id=kwargs.get("node_id"),  # type: ignore[arg-type]
        skill_id=kwargs.get("skill_id"),  # type: ignore[arg-type]
        precondition_evidence_ids=list(kwargs.get("precondition_evidence_ids", [])),  # type: ignore[arg-type]
        action_intent=action_intent,
        input_lease_id=kwargs.get("input_lease_id"),  # type: ignore[arg-type]
        expected_state_delta=expected_state_delta,
        verifier_contract=verifier_contract,
        recovery_policy=recovery_policy,
        telemetry_trace_id=uuid.uuid4().hex,
        learning_hook_id=kwargs.get("learning_hook_id"),  # type: ignore[arg-type]
        status=PROPOSED,
        created_at=now,
    )
