"""Tests for execution/execution_runtime.py: Phase 2 execution contract."""
from __future__ import annotations

import time
from typing import Any

import pytest

from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import InputLease
from execution.backend_factory import BackendFactory
from execution.console_backend import ConsoleInputBackend
from execution.execution_runtime import ExecutionRuntime, PhysicalReceipt
from execution.input_lease import InputLeaseStore
from execution.semantic_action import (
    ActionContract,
    SemanticAction,
)


class TestBackendFactory:
    def test_create_console(self):
        backend = BackendFactory.create("console")
        assert isinstance(backend, ConsoleInputBackend)
        assert backend.is_target_focused()

    def test_create_background_silent(self):
        backend = BackendFactory.create("background", target_window_title="原神")
        assert hasattr(backend, "mouse_move")
        assert backend._released is True

    def test_create_safe_window_requires_title(self):
        with pytest.raises(ValueError, match="safe_window mode requires"):
            BackendFactory.create("safe_window", target_window_title="")

    def test_create_unknown_mode(self):
        with pytest.raises(ValueError, match="Unknown backend mode"):
            BackendFactory.create("unknown_mode")


class TestPhysicalReceipt:
    def test_pending_receipt_fields(self):
        r = PhysicalReceipt(
            action_id="test_1",
            status="pending",
            submitted_at=time.time(),
        )
        assert r.action_id == "test_1"
        assert r.status == "pending"
        assert not r.success
        assert not r.is_verified

    def test_verified_receipt_success(self):
        from execution.verifier_base import VerifierResult
        vr = VerifierResult(
            ok=True, verifier_id="test", confidence=0.9, reason="ok"
        )
        r = PhysicalReceipt(
            action_id="test_2",
            status="verified",
            submitted_at=time.time(),
            lease_accepted=True,
            focus_ok=True,
            verifier_result=vr,
        )
        assert r.success
        assert r.is_verified

    def test_verified_without_result_not_verified(self):
        r = PhysicalReceipt(
            action_id="test_3",
            status="verified",
            submitted_at=time.time(),
            lease_accepted=True,
            focus_ok=True,
            verifier_result=None,
        )
        assert not r.is_verified

    def test_failed_receipt_not_success(self):
        r = PhysicalReceipt(
            action_id="test_4",
            status="failed",
            submitted_at=time.time(),
            reason="contract_invalid",
        )
        assert not r.success


class TestExecutionRuntime:
    def _make_runtime(self) -> tuple[ExecutionRuntime, StateBus]:
        bus = StateBus()
        tb = Timebase()
        backend = ConsoleInputBackend(timebase=tb)
        runtime = ExecutionRuntime(
            backend=backend,
            state_bus=bus,
            timebase=tb,
        )
        return runtime, bus

    def test_start_stop_lifecycle(self):
        runtime, bus = self._make_runtime()
        assert not runtime.input_worker.is_alive
        runtime.start()
        assert runtime.input_worker.is_alive
        runtime.stop()
        assert not runtime.input_worker.is_alive

    def test_submit_invalid_contract_returns_failed(self):
        runtime, bus = self._make_runtime()
        action = SemanticAction(
            action_id="test_invalid",
            kind="ui",
            intent="click",
            requires_physical_input=True,
        )
        # Empty contract: timeout_ms=0 triggers ActionContractValidator rejection
        contract = ActionContract(
            action_id="test_invalid",
            semantic_action=action,
            timeout_ms=0,
            safety_policy={},
        )
        receipt = runtime.submit(action, contract)
        assert receipt.status == "failed"
        assert "contract_invalid" in receipt.reason

    def test_submit_valid_contract_reaches_executed(self):
        runtime, bus = self._make_runtime()
        runtime.start()
        try:
            action = SemanticAction(
                action_id="test_valid",
                kind="ui",
                intent="wait",
                parameters={"reason": "test"},
            )
            contract = ActionContract(
                action_id="test_valid",
                semantic_action=action,
                timeout_ms=100,
                safety_policy={
                    "require_focus": True,
                    "input_lease_required": True,
                    "max_lease_ms": 250,
                },
                verifier_contract={"verifier_id": "test_verifier"},
            )
            receipt = runtime.submit(action, contract)
            # ConsoleBackend: no OS input, so lease accepted + executed
            assert receipt.status in ("executed", "verified")
            assert receipt.lease_accepted
        finally:
            runtime.stop()

    def test_submit_ui_action_with_adapter(self):
        runtime, bus = self._make_runtime()
        runtime.start()
        try:
            receipt = runtime.submit_ui_action(
                intent="wait",
                parameters={"duration_sec": 0.1},
            )
            # No adapter → failed
            assert receipt.status == "failed"
            assert "no_ui_flow_adapter" in receipt.reason
        finally:
            runtime.stop()

    def test_multiple_submits_sequential(self):
        runtime, bus = self._make_runtime()
        runtime.start()
        try:
            for i in range(3):
                action = SemanticAction(
                    action_id=f"test_seq_{i}",
                    kind="system",
                    intent="wait",
                    parameters={"reason": f"test_{i}"},
                )
                contract = ActionContract(
                    action_id=f"test_seq_{i}",
                    semantic_action=action,
                    timeout_ms=50,
                    safety_policy={
                        "require_focus": True,
                        "input_lease_required": True,
                        "max_lease_ms": 250,
                    },
                    verifier_contract={"verifier_id": f"test_verifier_{i}"},
                )
                receipt = runtime.submit(action, contract)
                assert receipt.status in ("executed", "verified")
        finally:
            runtime.stop()

    def test_waits_only_for_current_lease_keys_not_global_active_keys(self):
        runtime, bus = self._make_runtime()
        runtime.start()
        try:
            # Inject a long-lived unrelated key hold (W) into InputWorker.
            now = runtime.input_worker.lease_store.active_leases_snapshot()
            _ = now  # keep static checkers quiet
            long_hold = InputLease(
                lease_id="unrelated_w_hold",
                owner="test",
                priority=10,
                key_states={"W": "DOWN"},
                mouse_delta=None,
                created_at=time.perf_counter(),
                expires_at=time.perf_counter() + 2.0,
                reason="unrelated hold",
            )
            assert runtime.input_worker.submit_lease(long_hold)

            # Submit action that uses E. Runtime should finish when E is released,
            # without waiting for unrelated W to clear.
            action = SemanticAction(
                action_id="specific_lease_wait",
                kind="system",
                intent="press_e",
                parameters={"key": "E", "reason": "specific key"},
            )
            contract = ActionContract(
                action_id="specific_lease_wait",
                semantic_action=action,
                timeout_ms=50,
                safety_policy={
                    "require_focus": True,
                    "input_lease_required": True,
                    "max_lease_ms": 180,
                },
                verifier_contract={"verifier_id": "test_specific_wait"},
            )
            receipt = runtime.submit(action, contract)
            assert receipt.status in ("executed", "verified")
            assert receipt.duration_ms < 1000.0
        finally:
            runtime.stop()

    def test_receipt_status_transitions(self):
        runtime, bus = self._make_runtime()
        runtime.start()
        try:
            # Step 1: invalid contract → failed
            bad = SemanticAction(action_id="bad", kind="ui", intent="x")
            bad_contract = ActionContract(action_id="bad", semantic_action=bad, timeout_ms=0)
            r1 = runtime.submit(bad, bad_contract)
            assert r1.status == "failed"

            # Step 2: valid contract → executed
            good = SemanticAction(action_id="good", kind="system", intent="wait")
            good_contract = ActionContract(
                action_id="good",
                semantic_action=good,
                timeout_ms=50,
                safety_policy={"require_focus": True, "input_lease_required": True, "max_lease_ms": 250},
                verifier_contract={"verifier_id": "test_verifier_good"},
            )
            r2 = runtime.submit(good, good_contract)
            assert r2.status in ("executed", "verified")
        finally:
            runtime.stop()


class TestExecutionRuntimeWithBackendFactory:
    def test_console_backend_full_flow(self):
        """End-to-end: BackendFactory + ExecutionRuntime"""
        tb = Timebase()
        bus = StateBus()
        backend = BackendFactory.create("console", timebase=tb)
        runtime = ExecutionRuntime(backend=backend, state_bus=bus, timebase=tb)
        runtime.start()
        try:
            action = SemanticAction(
                action_id="e2e_test",
                kind="ui",
                intent="wait",
                parameters={"reason": "e2e"},
            )
            contract = ActionContract(
                action_id="e2e_test",
                semantic_action=action,
                timeout_ms=100,
                safety_policy={
                    "require_focus": True,
                    "input_lease_required": True,
                    "max_lease_ms": 250,
                },
                verifier_contract={"verifier_id": "test_e2e_verifier"},
            )
            receipt = runtime.submit(action, contract)
            assert receipt.status in ("executed", "verified")
            assert receipt.backend_type == "ConsoleInputBackend"
            assert receipt.duration_ms >= 0
        finally:
            runtime.stop()
