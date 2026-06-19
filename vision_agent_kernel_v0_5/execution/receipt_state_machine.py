"""PhysicalReceipt state machine — formalized transition validation.

Ensures that receipt status transitions follow the valid lifecycle:
  PENDING → SUBMITTED → LEASE_ACCEPTED → FOCUS_OK → EXECUTED → VERIFIED
With failure paths to FAILED from any state.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger(__name__)


class ReceiptState(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    LEASE_ACCEPTED = "lease_accepted"
    FOCUS_OK = "focus_ok"
    EXECUTED = "executed"
    VERIFIED = "verified"
    FAILED = "failed"


class InvalidTransition(Exception):
    """Raised when a state transition is not valid."""


# Valid transitions: from_state → set of allowed to_states
_VALID_TRANSITIONS: dict[ReceiptState, set[ReceiptState]] = {
    ReceiptState.PENDING: {ReceiptState.SUBMITTED, ReceiptState.FAILED},
    ReceiptState.SUBMITTED: {ReceiptState.LEASE_ACCEPTED, ReceiptState.FAILED},
    ReceiptState.LEASE_ACCEPTED: {ReceiptState.FOCUS_OK, ReceiptState.FAILED},
    ReceiptState.FOCUS_OK: {ReceiptState.EXECUTED, ReceiptState.FAILED},
    ReceiptState.EXECUTED: {ReceiptState.VERIFIED, ReceiptState.FAILED},
    ReceiptState.VERIFIED: set(),  # Terminal success state
    ReceiptState.FAILED: set(),    # Terminal failure state
}

# Human-readable step names for error messages
_STEP_NAMES: dict[ReceiptState, str] = {
    ReceiptState.PENDING: "submit",
    ReceiptState.SUBMITTED: "lease_accept",
    ReceiptState.LEASE_ACCEPTED: "focus_check",
    ReceiptState.FOCUS_OK: "execute",
    ReceiptState.EXECUTED: "verify",
    ReceiptState.VERIFIED: "complete",
    ReceiptState.FAILED: "fail",
}


@dataclass(slots=True, frozen=True)
class TransitionResult:
    """Result of a state transition attempt."""
    success: bool
    from_state: ReceiptState
    to_state: ReceiptState
    error: str = ""


def validate_transition(current: ReceiptState, target: ReceiptState) -> TransitionResult:
    """Validate whether a transition from current to target state is allowed."""
    allowed = _VALID_TRANSITIONS.get(current, set())

    if target in allowed:
        return TransitionResult(success=True, from_state=current, to_state=target)

    if current in (ReceiptState.VERIFIED, ReceiptState.FAILED):
        error = f"Cannot transition from terminal state {current.value}"
    else:
        expected = _STEP_NAMES.get(current, "unknown")
        error = (
            f"Invalid transition: {current.value} → {target.value}. "
            f"Expected step: {expected}"
        )
    return TransitionResult(success=False, from_state=current, to_state=target, error=error)


def enforce_transition(current: ReceiptState, target: ReceiptState) -> ReceiptState:
    """Validate and enforce a transition. Raises InvalidTransition if invalid.

    Returns the target state on success.
    """
    result = validate_transition(current, target)
    if not result.success:
        raise InvalidTransition(result.error)
    return target


def is_terminal(state: ReceiptState) -> bool:
    """Check if a state is terminal (no further transitions possible)."""
    return state in (ReceiptState.VERIFIED, ReceiptState.FAILED)


def next_expected_step(state: ReceiptState) -> str:
    """Return the human-readable name of the next expected step."""
    return _STEP_NAMES.get(state, "unknown")
