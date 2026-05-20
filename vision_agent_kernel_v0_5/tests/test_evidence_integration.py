"""Integration tests for Stage 44 evidence system.

Tests the full evidence chain: EvidenceStore -> StrictModeValidator -> TraceQuery.
"""
from __future__ import annotations

from evidence.evidence_graph import EvidenceGraph
from evidence.evidence_nodes import (
    NODE_TYPE_ACTUATION_RESULT,
    NODE_TYPE_ACTION_INTENT,
    NODE_TYPE_FRAME,
    NODE_TYPE_INPUT_LEASE,
    NODE_TYPE_MISSION_NODE_RESULT,
    NODE_TYPE_OBSERVATION,
    NODE_TYPE_PRECONDITION,
    NODE_TYPE_VERIFIER_RESULT,
    EvidenceNode,
)
from evidence.evidence_store import EvidenceStore
from evidence.strict_mode import StrictModeConfig, StrictModeValidator
from evidence.trace_query import TraceQuery


# -- Mock action ---------------------------------------------------------------
class _MockAction:
    """Lightweight mock that mimics ProofCarryingAction attributes."""

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# 1. Create EvidenceStore, record full chain
# ---------------------------------------------------------------------------
def test_record_full_evidence_chain() -> None:
    store = EvidenceStore()

    # Record: frame -> observation -> action -> lease -> verifier -> mission result
    frame = store.record_node(NODE_TYPE_FRAME, {"frame_id": 1})
    obs = store.record_node(NODE_TYPE_OBSERVATION, {"obs_id": "obs-1"})
    precond = store.record_node(NODE_TYPE_PRECONDITION, {"desc": "target visible"})
    action = store.record_node(NODE_TYPE_ACTION_INTENT, {"kind": "collect", "skill_id": "s1"})
    lease = store.record_node(NODE_TYPE_INPUT_LEASE, {"owner": "mission"})
    actuation = store.record_node(NODE_TYPE_ACTUATION_RESULT, {"keys": ["F"]})
    verifier = store.record_node(NODE_TYPE_VERIFIER_RESULT, {"ok": True})
    mission_result = store.record_node(NODE_TYPE_MISSION_NODE_RESULT, {"status": "success"})

    # Link them
    store.record_edge(frame.node_id, obs.node_id, "DERIVED_FROM")
    store.record_edge(obs.node_id, precond.node_id, "CAUSES")
    store.record_edge(precond.node_id, action.node_id, "SATISFIES")
    store.record_edge(action.node_id, lease.node_id, "LEASED_AS")
    store.record_edge(lease.node_id, actuation.node_id, "RESULTED_IN")
    store.record_edge(actuation.node_id, verifier.node_id, "VERIFIED_BY")
    store.record_edge(verifier.node_id, mission_result.node_id, "RESULTED_IN")

    graph = store.query()
    assert graph.node_count() == 8
    assert graph.edge_count() == 7

    # All node types are present
    assert len(graph.get_nodes_by_type(NODE_TYPE_FRAME)) == 1
    assert len(graph.get_nodes_by_type(NODE_TYPE_OBSERVATION)) == 1
    assert len(graph.get_nodes_by_type(NODE_TYPE_PRECONDITION)) == 1
    assert len(graph.get_nodes_by_type(NODE_TYPE_ACTION_INTENT)) == 1
    assert len(graph.get_nodes_by_type(NODE_TYPE_INPUT_LEASE)) == 1
    assert len(graph.get_nodes_by_type(NODE_TYPE_ACTUATION_RESULT)) == 1
    assert len(graph.get_nodes_by_type(NODE_TYPE_VERIFIER_RESULT)) == 1
    assert len(graph.get_nodes_by_type(NODE_TYPE_MISSION_NODE_RESULT)) == 1


# ---------------------------------------------------------------------------
# 2. Use StrictModeValidator to verify the chain
# ---------------------------------------------------------------------------
def test_strict_mode_validates_full_chain() -> None:
    store = EvidenceStore()
    validator = StrictModeValidator()

    frame = store.record_node(NODE_TYPE_FRAME, {"frame_id": 1})
    obs = store.record_node(NODE_TYPE_OBSERVATION, {"obs_id": "obs-1"})
    action_node = store.record_node(NODE_TYPE_ACTION_INTENT, {"kind": "move"})
    lease = store.record_node(NODE_TYPE_INPUT_LEASE, {"owner": "test"})
    verifier = store.record_node(NODE_TYPE_VERIFIER_RESULT, {"ok": True})

    store.record_edge(frame.node_id, obs.node_id, "DERIVED_FROM")
    store.record_edge(obs.node_id, action_node.node_id, "CAUSES")
    store.record_edge(action_node.node_id, lease.node_id, "LEASED_AS")
    store.record_edge(lease.node_id, verifier.node_id, "VERIFIED_BY")

    graph = store.query()

    # Action mock referencing the graph nodes
    action = _MockAction(
        action_id="act-1",
        status="VERIFIED_SUCCESS",
        verifier_result_id=verifier.node_id,
        is_physical=True,
        input_lease_id=lease.node_id,
        precondition_evidence_ids=[obs.node_id],
    )

    violations = validator.validate_action(action, graph)
    assert violations == []


# ---------------------------------------------------------------------------
# 3. Use TraceQuery to reconstruct the chain
# ---------------------------------------------------------------------------
def test_trace_query_reconstructs_chain() -> None:
    store = EvidenceStore()

    frame = store.record_node(NODE_TYPE_FRAME, {"frame_id": 1})
    obs = store.record_node(NODE_TYPE_OBSERVATION, {"obs_id": "obs-1"})
    precond = store.record_node(NODE_TYPE_PRECONDITION, {"desc": "ready"})
    action = store.record_node(NODE_TYPE_ACTION_INTENT, {"kind": "attack"})
    lease = store.record_node(NODE_TYPE_INPUT_LEASE, {"owner": "combat"})
    actuation = store.record_node(NODE_TYPE_ACTUATION_RESULT, {"result": "ok"})
    verifier = store.record_node(NODE_TYPE_VERIFIER_RESULT, {"ok": True})
    mission_result = store.record_node(NODE_TYPE_MISSION_NODE_RESULT, {"status": "success"})

    store.record_edge(frame.node_id, obs.node_id, "DERIVED_FROM")
    store.record_edge(obs.node_id, precond.node_id, "CAUSES")
    store.record_edge(precond.node_id, action.node_id, "SATISFIES")
    store.record_edge(action.node_id, lease.node_id, "LEASED_AS")
    store.record_edge(lease.node_id, actuation.node_id, "RESULTED_IN")
    store.record_edge(actuation.node_id, verifier.node_id, "VERIFIED_BY")
    store.record_edge(verifier.node_id, mission_result.node_id, "RESULTED_IN")

    graph = store.query()
    tq = TraceQuery(graph)

    # Action chain from the action node
    action_result = tq.action_chain(action.node_id)
    assert action_result["missing_links"] == []
    assert len(action_result["chain"]) >= 4

    # Verifier chain backward
    verifier_result = tq.verifier_chain(verifier.node_id)
    assert verifier_result["missing_links"] == []
    assert len(verifier_result["chain"]) >= 4

    # Mission node chain
    mission_chain_result = tq.mission_node_chain(mission_result.node_id)
    assert mission_chain_result["missing_links"] == []
    assert len(mission_chain_result["chain"]) >= 5


# ---------------------------------------------------------------------------
# 4. Verify evidence coverage (all links present)
# ---------------------------------------------------------------------------
def test_full_coverage_all_links_present() -> None:
    store = EvidenceStore()

    frame = store.record_node(NODE_TYPE_FRAME, {"frame_id": 0})
    obs = store.record_node(NODE_TYPE_OBSERVATION, {"obs": 1})
    precond = store.record_node(NODE_TYPE_PRECONDITION, {"ok": True})
    action = store.record_node(NODE_TYPE_ACTION_INTENT, {"kind": "navigate"})
    lease = store.record_node(NODE_TYPE_INPUT_LEASE, {"owner": "nav"})
    actuation = store.record_node(NODE_TYPE_ACTUATION_RESULT, {"moved": True})
    verifier = store.record_node(NODE_TYPE_VERIFIER_RESULT, {"ok": True})
    mission = store.record_node(NODE_TYPE_MISSION_NODE_RESULT, {"success": True})

    store.record_edge(frame.node_id, obs.node_id, "DERIVED_FROM")
    store.record_edge(obs.node_id, precond.node_id, "CAUSES")
    store.record_edge(precond.node_id, action.node_id, "SATISFIES")
    store.record_edge(action.node_id, lease.node_id, "LEASED_AS")
    store.record_edge(lease.node_id, actuation.node_id, "RESULTED_IN")
    store.record_edge(actuation.node_id, verifier.node_id, "VERIFIED_BY")
    store.record_edge(verifier.node_id, mission.node_id, "RESULTED_IN")

    graph = store.query()
    tq = TraceQuery(graph)

    # Verify every node type is reachable via chains
    action_chain = tq.action_chain(action.node_id)
    assert action_chain["missing_links"] == []

    verifier_chain = tq.verifier_chain(verifier.node_id)
    assert verifier_chain["missing_links"] == []

    mission_chain = tq.mission_node_chain(mission.node_id)
    assert mission_chain["missing_links"] == []


# ---------------------------------------------------------------------------
# 5. Verify removing one node causes strict mode to report violation
# ---------------------------------------------------------------------------
def test_missing_node_causes_strict_mode_violation() -> None:
    """Simulate a missing node by building the chain but omitting one link."""
    graph = EvidenceGraph()

    # Build a partial chain (missing lease node)
    frame_node = EvidenceNode(
        node_id="frame-1", node_type=NODE_TYPE_FRAME,
        created_at=0.0, payload={"frame_id": 1},
    )
    action_node = EvidenceNode(
        node_id="action-1", node_type=NODE_TYPE_ACTION_INTENT,
        created_at=0.0, payload={"kind": "move"},
    )
    verifier_node = EvidenceNode(
        node_id="vr-1", node_type=NODE_TYPE_VERIFIER_RESULT,
        created_at=0.0, payload={"ok": True},
    )

    for n in (frame_node, action_node, verifier_node):
        graph.add_node(n)

    graph.add_edge(frame_node.node_id, action_node.node_id, "CAUSES")
    graph.add_edge(action_node.node_id, verifier_node.node_id, "VERIFIED_BY")

    # Action that claims to have a lease but the lease node doesn't exist
    validator = StrictModeValidator()
    action = _MockAction(
        action_id="act-1",
        status="VERIFIED_SUCCESS",
        verifier_result_id=verifier_node.node_id,
        is_physical=True,
        input_lease_id="lease-nonexistent",
    )

    violations = validator.validate_action(action, graph)
    assert len(violations) >= 1
    assert any("lease" in v.lower() or "input" in v.lower() for v in violations)


def test_missing_verifier_node_causes_violation() -> None:
    """Removing verifier result node causes mission terminal validation failure."""
    graph = EvidenceGraph()

    frame_node = EvidenceNode(
        node_id="frame-1", node_type=NODE_TYPE_FRAME,
        created_at=0.0, payload={"frame_id": 1},
    )
    graph.add_node(frame_node)

    # Mission result references a verifier that was never added
    validator = StrictModeValidator()
    mission_result = _MockAction(
        verifier_result_id="vr-deleted",
    )

    violations = validator.validate_mission_terminal_success(mission_result, graph)
    assert len(violations) >= 1
    assert any("not found" in v for v in violations)
