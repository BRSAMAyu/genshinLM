"""ExecutionRuntime: orchestrator for the Phase 2 execution contract.

Per AUTONOMY_RUNTIME_CONTRACT.md §5:
    SemanticAction
        ↓ ActionContractValidator
    ActionContract (validated)
        ↓ InputWorker.submit_lease()
    PhysicalReceipt (PENDING → SUBMITTED → LEASE_ACCEPTED → FOCUS_OK → EXECUTED)
        ↓ post-action ScreenStateClaimBuilder
    verifier_result = Verifier.verify(post_claim, contract)
    PhysicalReceipt (status=VERIFIED or status=FAILED)
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import InputLease
from execution.claim_adapter import ClaimProducingAdapter
from execution.input_lease import InputLeaseStore
from execution.input_worker import InputWorker
from execution.semantic_action import (
    ActionContract,
    ActionContractValidator,
    SemanticAction,
)
from execution.verifier_base import VerifierContext, VerifierResult
from planning.screen_state_claim_builder import ScreenStateClaimBuilder

if TYPE_CHECKING:
    from execution.input_backend_base import InputBackend
    from execution.ui_flow_skill_adapter import UIFlowSkillAdapter


ReceiptStatus = Literal[
    "pending", "submitted", "lease_accepted", "focus_ok",
    "executed", "verified", "failed", "expired",
]


@dataclass(frozen=True, slots=True)
class PhysicalReceipt:
    """Proof-of-execution record. Matches AUTONOMY_RUNTIME_CONTRACT.md §1.5."""

    action_id: str
    status: ReceiptStatus
    submitted_at: float
    lease_accepted: bool = False
    focus_ok: bool = False
    duration_ms: float = 0.0
    post_state_claim_id: str = ""
    verifier_result: VerifierResult | None = None
    reason: str = ""
    failed_step: str = ""
    backend_type: str = ""

    @property
    def is_verified(self) -> bool:
        return self.status == "verified" and self.verifier_result is not None and self.verifier_result.ok

    @property
    def success(self) -> bool:
        return self.status in ("executed", "verified") and self.lease_accepted and self.focus_ok


class ExecutionRuntime:
    """Orchestrates physical action execution following AUTONOMY_RUNTIME_CONTRACT.md §5."""

    __slots__ = (
        "_backend", "_state_bus", "_timebase", "_ui_flow_adapter",
        "_claim_builder", "_lease_store", "_worker",
        "_contract_validator", "_claim_adapter", "_started",
    )

    def __init__(
        self,
        backend: InputBackend,
        state_bus: StateBus,
        timebase: Timebase | None = None,
        ui_flow_adapter: UIFlowSkillAdapter | None = None,
        claim_builder: ScreenStateClaimBuilder | None = None,
        lease_store: InputLeaseStore | None = None,
    ) -> None:
        self._backend = backend
        self._state_bus = state_bus
        self._timebase = timebase or Timebase()
        self._ui_flow_adapter = ui_flow_adapter
        self._claim_builder = claim_builder or ScreenStateClaimBuilder()
        self._lease_store = lease_store or InputLeaseStore()
        self._worker = InputWorker(
            backend=backend,
            timebase=self._timebase,
            state_bus=state_bus,
        )
        self._contract_validator = ActionContractValidator()
        self._claim_adapter = ClaimProducingAdapter()
        self._started = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the InputWorker background thread."""
        if self._started:
            return
        self._worker.start()
        self._started = True

    def stop(self, timeout: float = 2.0) -> None:
        self._worker.stop(timeout=timeout)
        self._started = False

    def submit(
        self,
        semantic_action: SemanticAction,
        contract: ActionContract,
        post_action_frame: Any = None,
        verifier_fn: Any = None,
    ) -> PhysicalReceipt:
        """Execute a semantic action and return a PhysicalReceipt.

        Follows the contract flow:
            validated → lease requested → submitted → executed → verified/failed
        """
        action_id = semantic_action.action_id
        start_time = self._timebase.now()
        reason = semantic_action.parameters.get("reason", semantic_action.intent)

        # ---- Step 1: Validate contract ----
        validation = self._contract_validator.validate(contract)
        if not validation.ok:
            return self._make_receipt(
                action_id=action_id,
                status="failed",
                submitted_at=start_time,
                reason=f"contract_invalid: {validation.errors}",
                failed_step="contract_validation",
                backend_type=self._backend.__class__.__name__,
            )

        # ---- Step 2: Build InputLease from contract ----
        lease = self._build_lease(semantic_action, contract, action_id, start_time)
        if lease is None:
            return self._make_receipt(
                action_id=action_id,
                status="expired",
                submitted_at=start_time,
                reason="lease_request_rejected",
                failed_step="lease_request",
                backend_type=self._backend.__class__.__name__,
            )

        # ---- Step 3: Submit lease to InputWorker ----
        submitted = self._worker.submit_lease(lease)
        if not submitted:
            return self._make_receipt(
                action_id=action_id,
                status="expired",
                submitted_at=start_time,
                reason="input_worker_queue_full",
                failed_step="lease_submission",
                backend_type=self._backend.__class__.__name__,
            )

        # ---- Step 4: Wait for execution (chunked polling) ----
        receipt = self._wait_for_execution(action_id, lease, start_time)

        # ---- Step 5: Post-action verification ----
        if receipt.status == "executed":
            receipt = self._verify(action_id, lease, receipt, post_action_frame, verifier_fn)

        return receipt

    def submit_ui_action(
        self,
        intent: str,
        target: str = "",
        parameters: dict[str, Any] | None = None,
        timeout_ms: int = 1500,
    ) -> PhysicalReceipt:
        """Convenience method for UI actions via UIFlowSkillAdapter.

        Delegates to UIFlowSkillAdapter.execute_semantic() and wraps result
        as a PhysicalReceipt.
        """
        if self._ui_flow_adapter is None:
            return self._make_receipt(
                action_id=intent,
                status="failed",
                submitted_at=self._timebase.now(),
                reason="no_ui_flow_adapter",
                failed_step="adapter_lookup",
            )

        action_id = f"ui_{intent}_{int(time.time() * 1000)}"
        semantic_action = SemanticAction(
            action_id=action_id,
            kind="ui",
            intent=intent,
            target=target,
            parameters=parameters or {},
            requires_physical_input=True,
        )
        contract = ActionContract(
            action_id=action_id,
            semantic_action=semantic_action,
            safety_policy={
                "require_focus": True,
                "input_lease_required": True,
                "max_lease_ms": timeout_ms,
            },
            timeout_ms=timeout_ms,
            risk_level="medium",
        )
        return self.submit(semantic_action, contract)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_lease(
        self,
        semantic_action: SemanticAction,
        contract: ActionContract,
        action_id: str,
        start_time: float,
    ) -> Any | None:
        """Build an InputLease from semantic action + contract safety policy."""
        now = self._timebase.now()
        max_lease_ms = contract.safety_policy.get("max_lease_ms", 250)
        expires_at = start_time + max_lease_ms / 1000.0

        key_states: dict[str, str] = {}
        mouse_delta: tuple[float, float] | None = None

        params = semantic_action.parameters
        if "key" in params:
            key_states[params["key"]] = "DOWN"
        if "keys" in params:
            for k in params["keys"]:
                key_states[k] = "DOWN"
        if "mouse_dx" in params and "mouse_dy" in params:
            mouse_delta = (float(params["mouse_dx"]), float(params["mouse_dy"]))

        if not key_states and mouse_delta is None:
            key_states["left"] = "DOWN"

        lease = InputLease(
            lease_id=f"lease:{action_id}",
            owner="ExecutionRuntime",
            priority=contract.risk_level in ("high", "human_confirm") and 5 or 10,
            key_states=key_states,
            mouse_delta=mouse_delta,
            created_at=start_time,
            expires_at=expires_at,
            reason=semantic_action.parameters.get("reason", semantic_action.intent),
        )

        validation = self._lease_store.validate(lease, now)
        if not validation.valid:
            return None

        self._lease_store.add(lease)
        return lease

    def _wait_for_execution(
        self,
        action_id: str,
        lease: Any,
        start_time: float,
    ) -> PhysicalReceipt:
        """Poll InputWorker until execution completes or times out."""
        timeout_sec = 5.0
        chunk = 0.05
        elapsed = 0.0

        while elapsed < timeout_sec:
            time.sleep(chunk)
            elapsed += chunk

            active = self._worker.active_keys_snapshot()
            if not active:
                duration_ms = elapsed * 1000
                return PhysicalReceipt(
                    action_id=action_id,
                    status="executed",
                    submitted_at=start_time,
                    lease_accepted=True,
                    focus_ok=True,
                    duration_ms=duration_ms,
                    reason=f"executed_in_{duration_ms:.1f}ms",
                    backend_type=self._backend.__class__.__name__,
                )

        return self._make_receipt(
            action_id=action_id,
            status="executed",
            submitted_at=start_time,
            lease_accepted=True,
            focus_ok=True,
            duration_ms=elapsed * 1000,
            reason="timeout_waiting_for_release",
            backend_type=self._backend.__class__.__name__,
        )

    def _verify(
        self,
        action_id: str,
        lease: Any,
        receipt: PhysicalReceipt,
        post_frame: Any,
        verifier_fn: Any,
    ) -> PhysicalReceipt:
        """Post-action verification: resample + verifier."""
        try:
            obs = self._state_bus.latest_observation.get()
            claim = self._claim_builder.build(post_frame, obs)

            if verifier_fn is not None:
                ctx = VerifierContext(
                    state={},
                    observation=obs,
                    frame=post_frame,
                )
                vr = verifier_fn(ctx)
            else:
                vr = None

            return PhysicalReceipt(
                action_id=receipt.action_id,
                status="verified" if vr is None or vr.ok else "failed",
                submitted_at=receipt.submitted_at,
                lease_accepted=receipt.lease_accepted,
                focus_ok=receipt.focus_ok,
                duration_ms=receipt.duration_ms,
                post_state_claim_id=claim.claim_id if hasattr(claim, "claim_id") else "",
                verifier_result=vr,
                reason=receipt.reason,
                backend_type=receipt.backend_type,
            )
        except Exception as exc:
            return PhysicalReceipt(
                action_id=action_id,
                status="failed",
                submitted_at=receipt.submitted_at,
                lease_accepted=receipt.lease_accepted,
                focus_ok=receipt.focus_ok,
                duration_ms=receipt.duration_ms,
                reason=f"verification_error: {exc}",
                failed_step="verification",
                backend_type=receipt.backend_type,
            )

    def _make_receipt(
        self,
        action_id: str,
        status: ReceiptStatus,
        submitted_at: float,
        reason: str,
        failed_step: str = "",
        backend_type: str = "",
        duration_ms: float = 0.0,
        verifier_result: VerifierResult | None = None,
    ) -> PhysicalReceipt:
        return PhysicalReceipt(
            action_id=action_id,
            status=status,
            submitted_at=submitted_at,
            lease_accepted=status in ("lease_accepted", "focus_ok", "executed", "verified"),
            focus_ok=status in ("focus_ok", "executed", "verified"),
            duration_ms=duration_ms,
            verifier_result=verifier_result,
            reason=reason,
            failed_step=failed_step,
            backend_type=backend_type,
        )

    @property
    def input_worker(self) -> InputWorker:
        return self._worker

    @property
    def backend(self) -> InputBackend:
        return self._backend