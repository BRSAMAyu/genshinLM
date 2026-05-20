from __future__ import annotations

import threading
from typing import Sequence

from evidence.evidence_nodes import EvidenceNode


class EvidenceGraph:
    """In-memory directed graph of evidence nodes and edges.

    Thread-safe via an internal ``RLock``.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, EvidenceNode] = {}
        self._edges: list[tuple[str, str, str]] = []  # (source_id, target_id, edge_type)
        self._lock = threading.RLock()

    # -- mutation -----------------------------------------------------------

    def add_node(self, node: EvidenceNode) -> None:
        """Insert *node*, replacing any existing node with the same id."""
        with self._lock:
            self._nodes[node.node_id] = node

    def add_edge(self, source_id: str, target_id: str, edge_type: str) -> None:
        """Add a directed edge *source_id* -> *target_id* with *edge_type*."""
        with self._lock:
            self._edges.append((source_id, target_id, edge_type))

    # -- queries ------------------------------------------------------------

    def get_node(self, node_id: str) -> EvidenceNode | None:
        with self._lock:
            return self._nodes.get(node_id)

    def get_edges_from(self, node_id: str) -> list[tuple[str, str, str]]:
        """Return all edges originating from *node_id*."""
        with self._lock:
            return [(s, t, et) for s, t, et in self._edges if s == node_id]

    def get_edges_to(self, node_id: str) -> list[tuple[str, str, str]]:
        """Return all edges pointing at *node_id*."""
        with self._lock:
            return [(s, t, et) for s, t, et in self._edges if t == node_id]

    def get_nodes_by_type(self, node_type: str) -> list[EvidenceNode]:
        with self._lock:
            return [n for n in self._nodes.values() if n.node_type == node_type]

    # -- counts -------------------------------------------------------------

    def node_count(self) -> int:
        with self._lock:
            return len(self._nodes)

    def edge_count(self) -> int:
        with self._lock:
            return len(self._edges)

    # -- bulk access (for persistence / query) ------------------------------

    def all_nodes(self) -> Sequence[EvidenceNode]:
        """Return a snapshot of all nodes."""
        with self._lock:
            return list(self._nodes.values())

    def all_edges(self) -> Sequence[tuple[str, str, str]]:
        """Return a snapshot of all edges."""
        with self._lock:
            return list(self._edges)
