"""Tests for core/proof_carrying_action.py — Stage 44 proof-carrying action model."""
from __future__ import annotations

import dataclasses
import uuid

from core.proof_carrying_action import (
    ABORTED,
    AUTHORIZED,
    EXECUTED,
    LEASED,
    PROPOSED,
    RECOVERED,
    VERIFIED_FAILED,
    VERIFIED_SUCCESS,
    ActionIntent,
    ExpectedStateDelta,
    ProofCarryingAction,
    RecoveryPolicyRef,
    VerifierContract,
    make_action,
)


# ---------------------------------------------------------------------------
# 1. ProofCarryingAction can be created with all fields
# ---------------------------------------------------------------------------
def test_proof_carrying_action_create_all_fields() -> None:
    intent = ActionIntent(
        intent_id="int-001",
        kind="move",
        params={"dx": 10, "dy": 5},
        reason="approach target",
    )
    delta = ExpectedStateDelta(
        delta_id="delta-001",
        description="character moves 10px right",
        success_triggers=["position_changed"],
        forbidden_regressions=["collision"],
        timeout_ms=3000,
    )
    contract = VerifierContract(
        contract_id="vc-001",
        verifier_id="visual_verifier",
        required_evidence_types=["frame"],
        min_confidence=0.9,
        roi_ids=["roi-center"],
        timeout_ms=3000,
    )
    recovery = RecoveryPolicyRef(
        policy_id="rp-001",
        strategy="retry",
        max_retries=2,
    )

    action = ProofCarryingAction(
        action_id="act-001",
        mission_id="mis-001",
        node_id="node-001",
        skill_id="skill-navigate",
        precondition_evidence_ids=["ev-1", "ev-2"],
        action_intent=intent,
        input_lease_id="lease-001",
        expected_state_delta=delta,
        verifier_contract=contract,
        recovery_policy=recovery,
        telemetry_trace_id="trace-001",
        learning_hook_id="hook-001",
        status=PROPOSED,
        created_at=100.0,
        finished_at=None,
        verifier_result_id=None,
    )

    assert action.action_id == "act-001"
    assert action.mission_id == "mis-001"
    assert action.node_id == "node-001"
    assert action.skill_id == "skill-navigate"
    assert action.precondition_evidence_ids == ["ev-1", "ev-2"]
    assert action.action_intent is intent
    assert action.input_lease_id == "lease-001"
    assert action.expected_state_delta is delta
    assert action.verifier_contract is contract
    assert action.recovery_policy is recovery
    assert action.telemetry_trace_id == "trace-001"
    assert action.learning_hook_id == "hook-001"
    assert action.status == PROPOSED
    assert action.created_at == 100.0
    assert action.finished_at is None
    assert action.verifier_result_id is None


# ---------------------------------------------------------------------------
# 2. make_action() factory creates a valid action with auto-generated IDs
# ---------------------------------------------------------------------------
def test_make_action_factory() -> None:
    action = make_action(
        kind="attack",
        params={"target": "enemy_01"},
        reason="eliminate hostile",
        mission_id="mis-002",
        skill_id="skill-combat",
        input_lease_id="lease-002",
        precondition_evidence_ids=["ev-10"],
    )

    # Auto-generated IDs should be non-empty hex strings
    assert len(action.action_id) > 0
    assert action.action_id != ""

    # Sub-object IDs also auto-generated
    assert len(action.action_intent.intent_id) > 0
    assert len(action.expected_state_delta.delta_id) > 0
    assert len(action.verifier_contract.contract_id) > 0
    assert len(action.recovery_policy.policy_id) > 0
    assert len(action.telemetry_trace_id) > 0

    # Intent carries the requested data
    assert action.action_intent.kind == "attack"
    assert action.action_intent.params == {"target": "enemy_01"}
    assert action.action_intent.reason == "eliminate hostile"

    # Kwargs forwarded correctly
    assert action.mission_id == "mis-002"
    assert action.skill_id == "skill-combat"
    assert action.input_lease_id == "lease-002"
    assert action.precondition_evidence_ids == ["ev-10"]

    # Status defaults to PROPOSED
    assert action.status == PROPOSED

    # created_at is set (non-zero)
    assert action.created_at > 0


def test_make_action_unique_ids() -> None:
    """Each call to make_action should produce unique IDs."""
    a1 = make_action(kind="move", params={}, reason="test1")
    a2 = make_action(kind="move", params={}, reason="test2")
    assert a1.action_id != a2.action_id
    assert a1.action_intent.intent_id != a2.action_intent.intent_id
    assert a1.telemetry_trace_id != a2.telemetry_trace_id


# ---------------------------------------------------------------------------
# 3. Action status transitions are valid
# ---------------------------------------------------------------------------
def test_valid_status_transitions() -> None:
    action = make_action(kind="move", params={}, reason="test transition")

    # PROPOSED -> AUTHORIZED
    action.status = AUTHORIZED
    assert action.status == AUTHORIZED

    # AUTHORIZED -> LEASED
    action.status = LEASED
    assert action.status == LEASED

    # LEASED -> EXECUTED
    action.status = EXECUTED
    assert action.status == EXECUTED

    # EXECUTED -> VERIFIED_SUCCESS
    action.status = VERIFIED_SUCCESS
    assert action.status == VERIFIED_SUCCESS


def test_valid_failure_and_recovery_transitions() -> None:
    action = make_action(kind="move", params={}, reason="test failure")
    action.status = AUTHORIZED
    action.status = LEASED
    action.status = EXECUTED

    # EXECUTED -> VERIFIED_FAILED
    action.status = VERIFIED_FAILED
    assert action.status == VERIFIED_FAILED

    # VERIFIED_FAILED -> RECOVERED
    action.status = RECOVERED
    assert action.status == RECOVERED


def test_abort_from_proposed() -> None:
    action = make_action(kind="move", params={}, reason="abort test")
    action.status = ABORTED
    assert action.status == ABORTED


# ---------------------------------------------------------------------------
# 4. JSON serialization works (dataclasses.asdict)
# ---------------------------------------------------------------------------
def test_json_serialization() -> None:
    action = make_action(
        kind="dodge",
        params={"direction": "left"},
        reason="avoid attack",
    )

    d = dataclasses.asdict(action)

    # Top-level keys
    assert "action_id" in d
    assert "action_intent" in d
    assert "expected_state_delta" in d
    assert "verifier_contract" in d
    assert "recovery_policy" in d
    assert "status" in d
    assert "precondition_evidence_ids" in d
    assert "created_at" in d

    # Nested structures are dicts too
    assert isinstance(d["action_intent"], dict)
    assert d["action_intent"]["kind"] == "dodge"
    assert d["action_intent"]["params"] == {"direction": "left"}

    assert isinstance(d["expected_state_delta"], dict)
    assert isinstance(d["verifier_contract"], dict)
    assert isinstance(d["recovery_policy"], dict)

    # Status is serialized as string
    assert d["status"] == PROPOSED


def test_serialization_roundtrip_identity() -> None:
    """Serialized dict can be used to reconstruct key fields."""
    action = make_action(kind="interact", params={"target": "chest"}, reason="loot")
    d = dataclasses.asdict(action)

    assert d["action_intent"]["kind"] == "interact"
    assert d["action_intent"]["reason"] == "loot"
    assert d["recovery_policy"]["strategy"] == "retry"
    assert d["recovery_policy"]["max_retries"] == 2


# ---------------------------------------------------------------------------
# 5. Action can link to evidence IDs
# ---------------------------------------------------------------------------
def test_precondition_evidence_ids() -> None:
    action = make_action(
        kind="navigate",
        params={"waypoint": "A"},
        reason="go to A",
        precondition_evidence_ids=["ev-frame-1", "ev-obs-1"],
    )
    assert action.precondition_evidence_ids == ["ev-frame-1", "ev-obs-1"]


def test_verifier_result_id_linkage() -> None:
    action = make_action(kind="attack", params={}, reason="strike")
    assert action.verifier_result_id is None

    # Simulate post-execution: set verifier result
    action.verifier_result_id = "vr-001"
    assert action.verifier_result_id == "vr-001"


def test_input_lease_id_linkage() -> None:
    action = make_action(
        kind="click",
        params={"x": 100, "y": 200},
        reason="interact with NPC",
        input_lease_id="lease-abc",
    )
    assert action.input_lease_id == "lease-abc"
