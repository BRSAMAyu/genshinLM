from __future__ import annotations

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
)

# Ordered chain types for action-oriented traces.
_ACTION_CHAIN_TYPES: list[str] = [
    NODE_TYPE_PRECONDITION,
    NODE_TYPE_ACTION_INTENT,
    NODE_TYPE_INPUT_LEASE,
    NODE_TYPE_ACTUATION_RESULT,
    NODE_TYPE_VERIFIER_RESULT,
]


def _walk_bidirectional(
    graph: EvidenceGraph,
    start_id: str,
    target_types: list[str],
) -> tuple[list[dict[str, object]], list[str]]:
    """BFS in both edge directions from *start_id*, collecting one node per
    *target_types* slot.

    Evidence graphs have mixed edge directions (e.g. ``LEASED_AS`` points from
    lease to action, ``VERIFIED_BY`` from verifier to actuation).  A
    bidirectional walk ensures the full chain is discovered regardless of edge
    orientation.

    Returns ``(collected, missing)`` where *collected* preserves the ordering of
    *target_types* and *missing* lists the type names for which no node was
    found.
    """
    collected: list[dict[str, object] | None] = [None] * len(target_types)
    visited: set[str] = set()
    frontier: list[str] = [start_id]

    while frontier:
        current = frontier.pop(0)
        if current in visited:
            continue
        visited.add(current)
        node = graph.get_node(current)
        if node is not None and node.node_type in target_types:
            idx = target_types.index(node.node_type)
            if collected[idx] is None:
                collected[idx] = {
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "payload": node.payload,
                }
        # Follow edges in both directions.
        for _s, t, _et in graph.get_edges_from(current):
            if t not in visited:
                frontier.append(t)
        for s, _t, _et in graph.get_edges_to(current):
            if s not in visited:
                frontier.append(s)

    missing = [
        target_types[i]
        for i in range(len(target_types))
        if collected[i] is None
    ]
    result: list[dict[str, object]] = [c for c in collected if c is not None]
    return result, missing


class TraceQuery:
    """High-level queries over an :class:`EvidenceGraph`."""

    def __init__(self, graph: EvidenceGraph) -> None:
        self._graph = graph

    # -- queries ------------------------------------------------------------

    def action_chain(self, action_id: str) -> dict[str, object]:
        """Given an action intent node id, walk the full action chain.

        Chain: precondition -> action_intent -> input_lease -> actuation_result
               -> verifier_result

        Returns ``{"chain": [...nodes...], "missing_links": [...type names...]}``.
        """
        node = self._graph.get_node(action_id)
        if node is None:
            return {
                "chain": [],
                "missing_links": list(_ACTION_CHAIN_TYPES),
            }

        chain, missing = _walk_bidirectional(
            self._graph, action_id, _ACTION_CHAIN_TYPES,
        )
        return {"chain": chain, "missing_links": missing}

    def verifier_chain(self, verifier_result_id: str) -> dict[str, object]:
        """Walk backward from a verifier result.

        Chain: precondition <- action_intent <- input_lease <-
               actuation_result <- verifier_result
        """
        reverse_chain: list[str] = [
            NODE_TYPE_PRECONDITION,
            NODE_TYPE_ACTION_INTENT,
            NODE_TYPE_INPUT_LEASE,
            NODE_TYPE_ACTUATION_RESULT,
            NODE_TYPE_VERIFIER_RESULT,
        ]

        chain, missing = _walk_bidirectional(
            self._graph, verifier_result_id, reverse_chain,
        )
        return {"chain": chain, "missing_links": missing}

    def mission_node_chain(self, node_result_id: str) -> dict[str, object]:
        """Walk from frames/observations through to mission result.

        Chain: frame -> observation -> action -> lease -> verifier -> mission result
        """
        node = self._graph.get_node(node_result_id)
        if node is None:
            return {"chain": [], "missing_links": [
                NODE_TYPE_FRAME,
                NODE_TYPE_OBSERVATION,
                NODE_TYPE_ACTION_INTENT,
                NODE_TYPE_INPUT_LEASE,
                NODE_TYPE_VERIFIER_RESULT,
                NODE_TYPE_MISSION_NODE_RESULT,
            ]}

        mission_chain_types: list[str] = [
            NODE_TYPE_FRAME,
            NODE_TYPE_OBSERVATION,
            NODE_TYPE_ACTION_INTENT,
            NODE_TYPE_INPUT_LEASE,
            NODE_TYPE_VERIFIER_RESULT,
            NODE_TYPE_MISSION_NODE_RESULT,
        ]

        chain, missing = _walk_bidirectional(
            self._graph, node_result_id, mission_chain_types,
        )
        return {"chain": chain, "missing_links": missing}

    def failures_for_skill(self, skill_id: str) -> list[dict[str, object]]:
        """Find all failure signatures for *skill_id* and their linked patches."""
        failures: list[dict[str, object]] = []
        failure_nodes = self._graph.get_nodes_by_type(NODE_TYPE_FAILURE_SIGNATURE)

        for fnode in failure_nodes:
            if fnode.payload.get("skill_id") != skill_id:
                continue

            patches: list[dict[str, object]] = []
            for _s, target_id, _et in self._graph.get_edges_from(fnode.node_id):
                patch_node = self._graph.get_node(target_id)
                if patch_node is not None and patch_node.node_type == NODE_TYPE_PATCH_PROPOSAL:
                    patches.append({
                        "node_id": patch_node.node_id,
                        "payload": patch_node.payload,
                    })

            failures.append({
                "failure": {
                    "node_id": fnode.node_id,
                    "payload": fnode.payload,
                },
                "patches": patches,
            })

        return failures
