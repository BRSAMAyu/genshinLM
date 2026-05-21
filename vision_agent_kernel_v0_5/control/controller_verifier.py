from __future__ import annotations

from dataclasses import dataclass, field

from control.controller_protocol import ControllerResult


@dataclass(frozen=True, slots=True)
class ControllerResultVerification:
    ok: bool
    errors: list[str] = field(default_factory=list)


class ControllerResultVerifier:
    """Verify controller self-reports before upper layers trust them."""

    def verify(self, result: ControllerResult) -> ControllerResultVerification:
        errors: list[str] = []
        normalized_status = result.status.lower()
        if normalized_status in {"ok", "success", "executed"}:
            if not result.evidence_refs and not result.verifier_request:
                errors.append("success_without_evidence_or_verifier")
            for receipt in result.receipts:
                if not receipt.bounded:
                    errors.append(f"unbounded_receipt:{receipt.receipt_id}")
        elif normalized_status in {"failed", "blocked", "error"}:
            if not result.failure_code:
                errors.append("failure_without_failure_code")
        else:
            errors.append(f"unknown_controller_status:{result.status}")
        return ControllerResultVerification(ok=not errors, errors=errors)
