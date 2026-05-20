"""Tests for evidence/trace_query.py — Stage 44 evidence trace queries."""
from __future__ import annotations

import uuid

from evidence.evidence_graph import EvidenceGraph
from evidence.evidence_nodes import (
    NODE_TYPE_ACTION_INTENT,
    NODE_TYPE_ACTUATION_RESULT,
    NODE_TYPE_FAILURE_SIGNATURE,
    NODE_TYPE_FRAME,
    NODE_TYPE_INPUT_LEASE,
    NODE_TYPE_MISSION_NODE_RESULT,
    NODE_TYPE_OBSERVATION,
    NODE_TYPE_PATCH_PROPOSAL,
    NODE_TYPE_PRECONDITION,
    NODE_TYPE_VERIFIER_RESULT,
    EvidenceNode,
)
from evidence.trace_query import TraceQuery


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
# 1. TraceQuery.action_chain walks precondition -> action -> lease -> verifier
# ---------------------------------------------------------------------------
def test_action_chain_full() -> None:
    graph = EvidenceGraph()

    precond = _make_node(NODE_TYPE_PRECONDITION, {"desc": "target visible"})
    action = _make_node(NODE_TYPE_ACTION_INTENT, {"kind": "attack"})
    lease = _make_node(NODE_TYPE_INPUT_LEASE, {"owner": "combat"})
    actuation = _make_node(NODE_TYPE_ACTUATION_RESULT, {"keys_pressed": ["W"]})
    verifier = _make_node(NODE_TYPE_VERIFIER_RESULT, {"ok": True})

    for n in (precond, action, lease, actuation, verifier):
        graph.add_node(n)

    # Link them: precond -> action -> lease -> actuation -> verifier
    graph.add_edge(precond.node_id, action.node_id, "SATISFIES")
    graph.add_edge(action.node_id, lease.node_id, "LEASED_AS")
    graph.add_edge(lease.node_id, actuation.node_id, "RESULTED_IN")
    graph.add_edge(actuation.node_id, verifier.node_id, "VERIFIED_BY")

    tq = TraceQuery(graph)
    result = tq.action_chain(action.node_id)

    chain = result["chain"]
    missing = result["missing_links"]

    # All chain types should be present
    assert len(missing) == 0, f"Missing links: {missing}"
    assert len(chain) == 5

    chain_types = [e.get("node_type") for e in chain]
    assert NODE_TYPE_PRECONDITION in chain_types
    assert NODE_TYPE_ACTION_INTENT in chain_types
    assert NODE_TYPE_INPUT_LEASE in chain_types
    assert NODE_TYPE_ACTUATION_RESULT in chain_types
    assert NODE_TYPE_VERIFIER_RESULT in chain_types


def test_action_chain_missing_action_id() -> None:
    graph = EvidenceGraph()
    tq = TraceQuery(graph)

    result = tq.action_chain("nonexistent-id")
    assert result["chain"] == []
    assert len(result["missing_links"]) > 0


# ---------------------------------------------------------------------------
# 2. TraceQuery.verifier_chain walks backward from verifier result
# ---------------------------------------------------------------------------
def test_verifier_chain_full() -> None:
    graph = EvidenceGraph()

    precond = _make_node(NODE_TYPE_PRECONDITION, {"desc": "pre"})
    action = _make_node(NODE_TYPE_ACTION_INTENT, {"kind": "move"})
    lease = _make_node(NODE_TYPE_INPUT_LEASE, {"owner": "test"})
    actuation = _make_node(NODE_TYPE_ACTUATION_RESULT, {"result": "ok"})
    verifier = _make_node(NODE_TYPE_VERIFIER_RESULT, {"ok": True})

    for n in (precond, action, lease, actuation, verifier):
        graph.add_node(n)

    graph.add_edge(precond.node_id, action.node_id, "SATISFIES")
    graph.add_edge(action.node_id, lease.node_id, "LEASED_AS")
    graph.add_edge(lease.node_id, actuation.node_id, "RESULTED_IN")
    graph.add_edge(actuation.node_id, verifier.node_id, "VERIFIED_BY")

    tq = TraceQuery(graph)
    result = tq.verifier_chain(verifier.node_id)

    chain = result["chain"]
    missing = result["missing_links"]

    assert len(missing) == 0, f"Missing links: {missing}"
    assert len(chain) == 5

    chain_types = [e.get("node_type") for e in chain]
    assert NODE_TYPE_PRECONDITION in chain_types
    assert NODE_TYPE_ACTION_INTENT in chain_types
    assert NODE_TYPE_INPUT_LEASE in chain_types
    assert NODE_TYPE_ACTUATION_RESULT in chain_types
    assert NODE_TYPE_VERIFIER_RESULT in chain_types


def test_verifier_chain_partial() -> None:
    graph = EvidenceGraph()

    # Only action -> verifier, missing precondition, lease, actuation
    action = _make_node(NODE_TYPE_ACTION_INTENT)
    verifier = _make_node(NODE_TYPE_VERIFIER_RESULT)

    for n in (action, verifier):
        graph.add_node(n)

    graph.add_edge(action.node_id, verifier.node_id, "VERIFIED_BY")

    tq = TraceQuery(graph)
    result = tq.verifier_chain(verifier.node_id)

    missing = result["missing_links"]
    assert NODE_TYPE_PRECONDITION in missing
    assert NODE_TYPE_INPUT_LEASE in missing
    assert NODE_TYPE_ACTUATION_RESULT in missing

    # Action and verifier should be found
    chain_types = [e.get("node_type") for e in result["chain"]]
    assert NODE_TYPE_ACTION_INTENT in chain_types
    assert NODE_TYPE_VERIFIER_RESULT in chain_types


# ---------------------------------------------------------------------------
# 3. TraceQuery.mission_node_chain reconstructs full frame -> ... -> mission result
# ---------------------------------------------------------------------------
def test_mission_node_chain_full() -> None:
    graph = EvidenceGraph()

    frame = _make_node(NODE_TYPE_FRAME, {"frame_id": 1})
    obs = _make_node(NODE_TYPE_OBSERVATION, {"obs_id": "obs1"})
    action = _make_node(NODE_TYPE_ACTION_INTENT, {"kind": "collect"})
    lease = _make_node(NODE_TYPE_INPUT_LEASE, {"owner": "mission"})
    verifier = _make_node(NODE_TYPE_VERIFIER_RESULT, {"ok": True})
    mission_result = _make_node(NODE_TYPE_MISSION_NODE_RESULT, {"status": "success"})

    for n in (frame, obs, action, lease, verifier, mission_result):
        graph.add_node(n)

    graph.add_edge(frame.node_id, obs.node_id, "DERIVED_FROM")
    graph.add_edge(obs.node_id, action.node_id, "CAUSES")
    graph.add_edge(action.node_id, lease.node_id, "LEASED_AS")
    graph.add_edge(lease.node_id, verifier.node_id, "VERIFIED_BY")
    graph.add_edge(verifier.node_id, mission_result.node_id, "RESULTED_IN")

    tq = TraceQuery(graph)
    result = tq.mission_node_chain(mission_result.node_id)

    chain = result["chain"]
    missing = result["missing_links"]

    assert len(missing) == 0, f"Missing links: {missing}"
    assert len(chain) >= 5

    chain_types = [e.get("node_type") for e in chain]
    assert NODE_TYPE_FRAME in chain_types
    assert NODE_TYPE_OBSERVATION in chain_types
    assert NODE_TYPE_ACTION_INTENT in chain_types
    assert NODE_TYPE_INPUT_LEASE in chain_types
    assert NODE_TYPE_VERIFIER_RESULT in chain_types
    assert NODE_TYPE_MISSION_NODE_RESULT in chain_types


def test_mission_node_chain_missing_node() -> None:
    graph = EvidenceGraph()
    tq = TraceQuery(graph)

    result = tq.mission_node_chain("nonexistent-id")
    assert result["chain"] == []
    assert len(result["missing_links"]) > 0


# ---------------------------------------------------------------------------
# 4. TraceQuery reports missing_links when graph is incomplete
# ---------------------------------------------------------------------------
def test_missing_links_incomplete_action_chain() -> None:
    graph = EvidenceGraph()

    # Only precondition and action, missing lease/actuation/verifier
    precond = _make_node(NODE_TYPE_PRECONDITION)
    action = _make_node(NODE_TYPE_ACTION_INTENT)

    for n in (precond, action):
        graph.add_node(n)

    graph.add_edge(precond.node_id, action.node_id, "SATISFIES")

    tq = TraceQuery(graph)
    result = tq.action_chain(action.node_id)

    missing = result["missing_links"]
    assert NODE_TYPE_INPUT_LEASE in missing
    assert NODE_TYPE_ACTUATION_RESULT in missing
    assert NODE_TYPE_VERIFIER_RESULT in missing


# ---------------------------------------------------------------------------
# 5. TraceQuery.failures_for_skill filters by skill_id
# ---------------------------------------------------------------------------
def test_failures_for_skill_with_patches() -> None:
    graph = EvidenceGraph()

    skill_id = "skill-combat-v1"

    # Create a failure signature node
    failure = _make_node(NODE_TYPE_FAILURE_SIGNATURE, {
        "skill_id": skill_id,
        "error": "dodge_missed",
    })
    graph.add_node(failure)

    # Create a patch proposal linked to the failure
    patch = _make_node(NODE_TYPE_PATCH_PROPOSAL, {
        "patch_type": "timing_adjustment",
        "delta_ms": 50,
    })
    graph.add_node(patch)
    graph.add_edge(failure.node_id, patch.node_id, "PATCHED_BY")

    # Create an unrelated failure
    other_failure = _make_node(NODE_TYPE_FAILURE_SIGNATURE, {
        "skill_id": "skill-navigate-v1",
        "error": "stuck_on_terrain",
    })
    graph.add_node(other_failure)

    tq = TraceQuery(graph)
    results = tq.failures_for_skill(skill_id)

    assert len(results) == 1
    assert results[0]["failure"]["payload"]["skill_id"] == skill_id
    assert len(results[0]["patches"]) == 1
    assert results[0]["patches"][0]["payload"]["patch_type"] == "timing_adjustment"


def test_failures_for_skill_no_matches() -> None:
    graph = EvidenceGraph()

    failure = _make_node(NODE_TYPE_FAILURE_SIGNATURE, {
        "skill_id": "other-skill",
        "error": "timeout",
    })
    graph.add_node(failure)

    tq = TraceQuery(graph)
    results = tq.failures_for_skill("skill-nonexistent")

    assert results == []


def test_failures_for_skill_multiple_failures() -> None:
    graph = EvidenceGraph()

    skill_id = "skill-collect-v1"

    f1 = _make_node(NODE_TYPE_FAILURE_SIGNATURE, {"skill_id": skill_id, "error": "miss_1"})
    f2 = _make_node(NODE_TYPE_FAILURE_SIGNATURE, {"skill_id": skill_id, "error": "miss_2"})
    graph.add_node(f1)
    graph.add_node(f2)

    tq = TraceQuery(graph)
    results = tq.failures_for_skill(skill_id)

    assert len(results) == 2
    errors = {r["failure"]["payload"]["error"] for r in results}
    assert errors == {"miss_1", "miss_2"}
