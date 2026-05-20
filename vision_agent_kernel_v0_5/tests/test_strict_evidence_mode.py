"""Tests for evidence/strict_mode.py — Stage 44 strict evidence mode validator."""
from __future__ import annotations

import uuid

from evidence.evidence_graph import EvidenceGraph
from evidence.evidence_nodes import (
    NODE_TYPE_INPUT_LEASE,
    NODE_TYPE_VERIFIER_RESULT,
    EvidenceNode,
)
from evidence.strict_mode import StrictModeConfig, StrictModeValidator


# -- Mock action ---------------------------------------------------------------
class _MockAction:
    """Lightweight mock that mimics ProofCarryingAction attributes."""

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


def _make_node(
    node_type: str,
    payload: dict[str, object] | None = None,
) -> EvidenceNode:
    return EvidenceNode(
        node_id=uuid.uuid4().hex,
        node_type=node_type,
        created_at=0.0,
        payload=payload or {},
    )


# ---------------------------------------------------------------------------
# 1. StrictModeValidator rejects terminal success without verifier result
# ---------------------------------------------------------------------------
def test_rejects_terminal_success_without_verifier_result() -> None:
    graph = EvidenceGraph()
    validator = StrictModeValidator()

    action = _MockAction(
        action_id="act-1",
        status="VERIFIED_SUCCESS",
        verifier_result_id=None,
    )

    violations = validator.validate_action(action, graph)
    assert len(violations) >= 1
    assert any("verifier_result_id" in v for v in violations)


def test_rejects_terminal_success_verifier_not_in_graph() -> None:
    graph = EvidenceGraph()
    validator = StrictModeValidator()

    action = _MockAction(
        action_id="act-2",
        status="VERIFIED_SUCCESS",
        verifier_result_id="vr-nonexistent",
    )

    violations = validator.validate_action(action, graph)
    assert len(violations) >= 1
    assert any("not found" in v for v in violations)


# ---------------------------------------------------------------------------
# 2. StrictModeValidator accepts terminal success with proper evidence chain
# ---------------------------------------------------------------------------
def test_accepts_terminal_success_with_proper_chain() -> None:
    graph = EvidenceGraph()
    validator = StrictModeValidator()

    # Create a verifier result node in the graph
    vr_node = _make_node(NODE_TYPE_VERIFIER_RESULT, {"ok": True})
    graph.add_node(vr_node)

    action = _MockAction(
        action_id="act-3",
        status="VERIFIED_SUCCESS",
        verifier_result_id=vr_node.node_id,
        is_physical=False,
    )

    violations = validator.validate_action(action, graph)
    assert violations == []


# ---------------------------------------------------------------------------
# 3. StrictModeValidator rejects physical action without input lease
# ---------------------------------------------------------------------------
def test_rejects_physical_action_without_input_lease() -> None:
    graph = EvidenceGraph()
    validator = StrictModeValidator()

    action = _MockAction(
        action_id="act-4",
        status="PROPOSED",
        is_physical=True,
        input_lease_id=None,
    )

    violations = validator.validate_action(action, graph)
    assert len(violations) >= 1
    assert any("input_lease_id" in v or "InputLease" in v for v in violations)


def test_rejects_physical_action_lease_not_in_graph() -> None:
    graph = EvidenceGraph()
    validator = StrictModeValidator()

    action = _MockAction(
        action_id="act-5",
        status="PROPOSED",
        is_physical=True,
        input_lease_id="lease-nonexistent",
    )

    violations = validator.validate_action(action, graph)
    assert len(violations) >= 1
    assert any("not found" in v for v in violations)


def test_accepts_physical_action_with_valid_lease() -> None:
    graph = EvidenceGraph()
    validator = StrictModeValidator()

    lease_node = _make_node(NODE_TYPE_INPUT_LEASE, {"owner": "test"})
    graph.add_node(lease_node)

    action = _MockAction(
        action_id="act-6",
        status="PROPOSED",
        is_physical=True,
        input_lease_id=lease_node.node_id,
    )

    violations = validator.validate_action(action, graph)
    assert violations == []


def test_rejects_lease_node_wrong_type() -> None:
    graph = EvidenceGraph()
    validator = StrictModeValidator()

    # A node exists but it's not an input_lease type
    wrong_node = _make_node("frame", {"frame_id": 1})
    graph.add_node(wrong_node)

    action = _MockAction(
        action_id="act-7",
        status="PROPOSED",
        is_physical=True,
        input_lease_id=wrong_node.node_id,
    )

    violations = validator.validate_action(action, graph)
    assert len(violations) >= 1
    assert any("not an InputLease" in v for v in violations)


# ---------------------------------------------------------------------------
# 4. StrictModeValidator can be disabled (config.enabled=False)
# ---------------------------------------------------------------------------
def test_disabled_config_skips_all_validations() -> None:
    graph = EvidenceGraph()
    config = StrictModeConfig(enabled=False)
    validator = StrictModeValidator(config)

    # Action that would fail all checks
    action = _MockAction(
        action_id="act-8",
        status="VERIFIED_SUCCESS",
        verifier_result_id=None,
        is_physical=True,
        input_lease_id=None,
    )

    violations = validator.validate_action(action, graph)
    assert violations == []


def test_disabled_mission_terminal_success() -> None:
    graph = EvidenceGraph()
    config = StrictModeConfig(enabled=False)
    validator = StrictModeValidator(config)

    mission_result = _MockAction(
        verifier_result_id=None,
    )

    violations = validator.validate_mission_terminal_success(mission_result, graph)
    assert violations == []


# ---------------------------------------------------------------------------
# 5. validate_mission_terminal_success catches missing evidence
# ---------------------------------------------------------------------------
def test_mission_terminal_missing_verifier_result_id() -> None:
    graph = EvidenceGraph()
    validator = StrictModeValidator()

    mission_result = _MockAction(
        verifier_result_id=None,
    )

    violations = validator.validate_mission_terminal_success(mission_result, graph)
    assert len(violations) >= 1
    assert any("verifier_result_id" in v for v in violations)


def test_mission_terminal_verifier_node_not_in_graph() -> None:
    graph = EvidenceGraph()
    validator = StrictModeValidator()

    mission_result = _MockAction(
        verifier_result_id="vr-missing",
    )

    violations = validator.validate_mission_terminal_success(mission_result, graph)
    assert len(violations) >= 1
    assert any("not found" in v for v in violations)


def test_mission_terminal_verifier_not_ok() -> None:
    graph = EvidenceGraph()
    validator = StrictModeValidator()

    vr_node = _make_node(NODE_TYPE_VERIFIER_RESULT, {"ok": False})
    graph.add_node(vr_node)

    mission_result = _MockAction(
        verifier_result_id=vr_node.node_id,
    )

    violations = validator.validate_mission_terminal_success(mission_result, graph)
    assert len(violations) >= 1
    assert any("ok=True" in v for v in violations)


def test_mission_terminal_success_with_full_chain() -> None:
    graph = EvidenceGraph()
    validator = StrictModeValidator()

    # Build: frame -> verifier_result (with ok=True, and edge to it)
    frame = _make_node("frame", {"frame_id": 1})
    vr_node = _make_node(NODE_TYPE_VERIFIER_RESULT, {"ok": True})
    graph.add_node(frame)
    graph.add_node(vr_node)
    graph.add_edge(frame.node_id, vr_node.node_id, "VERIFIED_BY")

    mission_result = _MockAction(
        verifier_result_id=vr_node.node_id,
    )

    violations = validator.validate_mission_terminal_success(mission_result, graph)
    assert violations == []
