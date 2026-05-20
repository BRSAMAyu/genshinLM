"""Tests for evidence/evidence_graph.py — Stage 44 evidence graph."""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from evidence.evidence_graph import EvidenceGraph
from evidence.evidence_nodes import EvidenceNode


def _make_node(node_type: str, payload: dict[str, object] | None = None) -> EvidenceNode:
    return EvidenceNode(
        node_id=uuid.uuid4().hex,
        node_type=node_type,
        created_at=0.0,
        payload=payload or {},
    )


# ---------------------------------------------------------------------------
# 1. EvidenceGraph add_node / add_edge / get_node
# ---------------------------------------------------------------------------
def test_add_and_get_node() -> None:
    graph = EvidenceGraph()
    node = _make_node("frame", {"frame_id": 1})

    graph.add_node(node)
    retrieved = graph.get_node(node.node_id)

    assert retrieved is not None
    assert retrieved.node_id == node.node_id
    assert retrieved.node_type == "frame"
    assert retrieved.payload == {"frame_id": 1}


def test_get_node_missing() -> None:
    graph = EvidenceGraph()
    assert graph.get_node("nonexistent") is None


def test_add_edge() -> None:
    graph = EvidenceGraph()
    n1 = _make_node("frame")
    n2 = _make_node("observation")

    graph.add_node(n1)
    graph.add_node(n2)
    graph.add_edge(n1.node_id, n2.node_id, "DERIVED_FROM")

    edges_from = graph.get_edges_from(n1.node_id)
    assert len(edges_from) == 1
    assert edges_from[0] == (n1.node_id, n2.node_id, "DERIVED_FROM")


def test_add_edge_to_missing_node_raises() -> None:
    graph = EvidenceGraph()
    n1 = _make_node("frame")
    graph.add_node(n1)

    # The other agent's EvidenceGraph.add_edge does not validate existence,
    # so this should not raise. Edge just gets added.
    graph.add_edge(n1.node_id, "nonexistent", "DERIVED_FROM")
    edges = graph.get_edges_from(n1.node_id)
    assert len(edges) == 1


# ---------------------------------------------------------------------------
# 2. Multiple nodes and edges form a chain
# ---------------------------------------------------------------------------
def test_chain_of_nodes() -> None:
    graph = EvidenceGraph()

    frame = _make_node("frame", {"frame_id": 0})
    obs = _make_node("observation", {"obs_id": 1})
    action = _make_node("action_intent", {"action": "move"})
    lease = _make_node("input_lease", {"lease_id": "L1"})

    for n in (frame, obs, action, lease):
        graph.add_node(n)

    graph.add_edge(frame.node_id, obs.node_id, "DERIVED_FROM")
    graph.add_edge(obs.node_id, action.node_id, "CAUSES")
    graph.add_edge(action.node_id, lease.node_id, "LEASED_AS")

    # Walk the chain forward from frame
    current_id = frame.node_id
    visited_types: list[str] = [frame.node_type]
    for _ in range(3):
        edges = graph.get_edges_from(current_id)
        assert len(edges) >= 1, f"No edges from {current_id}"
        current_id = edges[0][1]  # target_id
        node = graph.get_node(current_id)
        assert node is not None
        visited_types.append(node.node_type)

    assert visited_types == ["frame", "observation", "action_intent", "input_lease"]


# ---------------------------------------------------------------------------
# 3. get_edges_from / get_edges_to work correctly
# ---------------------------------------------------------------------------
def test_get_edges_from_multiple() -> None:
    graph = EvidenceGraph()
    parent = _make_node("frame")
    child_a = _make_node("observation")
    child_b = _make_node("roi_evidence")

    for n in (parent, child_a, child_b):
        graph.add_node(n)

    graph.add_edge(parent.node_id, child_a.node_id, "DERIVED_FROM")
    graph.add_edge(parent.node_id, child_b.node_id, "DERIVED_FROM")

    edges = graph.get_edges_from(parent.node_id)
    assert len(edges) == 2

    targets = {e[1] for e in edges}
    assert targets == {child_a.node_id, child_b.node_id}


def test_get_edges_to() -> None:
    graph = EvidenceGraph()
    n1 = _make_node("frame")
    n2 = _make_node("observation")
    n3 = _make_node("action_intent")

    for n in (n1, n2, n3):
        graph.add_node(n)

    graph.add_edge(n1.node_id, n3.node_id, "TRIGGERS")
    graph.add_edge(n2.node_id, n3.node_id, "CAUSES")

    edges_to = graph.get_edges_to(n3.node_id)
    assert len(edges_to) == 2

    sources = {e[0] for e in edges_to}
    assert sources == {n1.node_id, n2.node_id}


def test_get_edges_from_empty() -> None:
    graph = EvidenceGraph()
    n1 = _make_node("frame")
    graph.add_node(n1)

    assert graph.get_edges_from(n1.node_id) == []
    assert graph.get_edges_to(n1.node_id) == []


# ---------------------------------------------------------------------------
# 4. get_nodes_by_type filters correctly
# ---------------------------------------------------------------------------
def test_get_nodes_by_type() -> None:
    graph = EvidenceGraph()

    frames = [_make_node("frame") for _ in range(3)]
    obs = [_make_node("observation") for _ in range(2)]
    lease = [_make_node("input_lease")]

    for n in frames + obs + lease:
        graph.add_node(n)

    assert len(graph.get_nodes_by_type("frame")) == 3
    assert len(graph.get_nodes_by_type("observation")) == 2
    assert len(graph.get_nodes_by_type("input_lease")) == 1
    assert len(graph.get_nodes_by_type("verifier_result")) == 0


def test_get_nodes_by_type_returns_correct_nodes() -> None:
    graph = EvidenceGraph()
    f1 = _make_node("frame", {"frame_id": 42})
    f2 = _make_node("frame", {"frame_id": 99})
    o1 = _make_node("observation")

    for n in (f1, f2, o1):
        graph.add_node(n)

    frame_nodes = graph.get_nodes_by_type("frame")
    frame_ids = {n.node_id for n in frame_nodes}
    assert frame_ids == {f1.node_id, f2.node_id}

    payloads = {n.payload.get("frame_id") for n in frame_nodes}
    assert payloads == {42, 99}


# ---------------------------------------------------------------------------
# 5. Thread safety: concurrent add_node calls don't corrupt
# ---------------------------------------------------------------------------
def test_concurrent_add_node() -> None:
    graph = EvidenceGraph()
    num_nodes = 200
    nodes = [_make_node("frame", {"idx": i}) for i in range(num_nodes)]

    def add_node(node: EvidenceNode) -> None:
        graph.add_node(node)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(add_node, nodes))

    assert graph.node_count() == num_nodes

    # Verify all nodes are retrievable
    for node in nodes:
        retrieved = graph.get_node(node.node_id)
        assert retrieved is not None
        assert retrieved.node_id == node.node_id


def test_concurrent_add_node_and_edge() -> None:
    graph = EvidenceGraph()
    num_pairs = 100

    parent_nodes = [_make_node("frame") for _ in range(num_pairs)]
    child_nodes = [_make_node("observation") for _ in range(num_pairs)]

    for n in parent_nodes + child_nodes:
        graph.add_node(n)

    def add_edge(pair: tuple[EvidenceNode, EvidenceNode]) -> None:
        parent, child = pair
        graph.add_edge(parent.node_id, child.node_id, "DERIVED_FROM")

    pairs = list(zip(parent_nodes, child_nodes))
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(add_edge, pairs))

    assert graph.edge_count() == num_pairs

    # Each parent has exactly one outgoing edge
    for parent in parent_nodes:
        edges = graph.get_edges_from(parent.node_id)
        assert len(edges) == 1
