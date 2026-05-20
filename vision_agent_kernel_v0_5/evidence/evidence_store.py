from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import IO

from evidence.evidence_graph import EvidenceGraph
from evidence.evidence_nodes import EvidenceNode


class EvidenceStore:
    """Wraps :class:`EvidenceGraph` with optional JSONL persistence.

    Parameters
    ----------
    run_id:
        Logical identifier for the current run (used as sub-directory name).
    persist_dir:
        Directory in which JSONL evidence files are written.  If *None* the
        store operates purely in memory.
    """

    def __init__(
        self,
        run_id: str | None = None,
        persist_dir: str | None = None,
    ) -> None:
        self._run_id = run_id or uuid.uuid4().hex[:12]
        self._persist_dir = persist_dir
        self._graph = EvidenceGraph()
        self._file_handle: IO[str] | None = None
        self._pending_nodes: list[EvidenceNode] = []
        self._pending_edges: list[tuple[str, str, str]] = []

        if self._persist_dir is not None:
            dir_path = Path(self._persist_dir) / self._run_id
            dir_path.mkdir(parents=True, exist_ok=True)
            self._file_path = dir_path / "evidence.jsonl"
            self._file_handle = open(self._file_path, "a", encoding="utf-8")  # noqa: SIM115

    # -- public API ---------------------------------------------------------

    def record_node(self, node_type: str, payload: dict[str, object]) -> EvidenceNode:
        """Create a new :class:`EvidenceNode`, add it to the graph, and return it."""
        node = EvidenceNode(
            node_id=uuid.uuid4().hex,
            node_type=node_type,
            created_at=time.perf_counter(),
            payload=dict(payload),
        )
        self._graph.add_node(node)
        self._pending_nodes.append(node)
        return node

    def record_edge(self, source_id: str, target_id: str, edge_type: str) -> None:
        """Add a directed edge to the evidence graph."""
        self._graph.add_edge(source_id, target_id, edge_type)
        self._pending_edges.append((source_id, target_id, edge_type))

    def query(self) -> EvidenceGraph:
        """Return the underlying :class:`EvidenceGraph`."""
        return self._graph

    def flush(self) -> None:
        """Write pending nodes and edges to the JSONL file (if persist_dir set)."""
        if self._file_handle is None:
            # In-memory only — nothing to flush.
            self._pending_nodes.clear()
            self._pending_edges.clear()
            return

        for node in self._pending_nodes:
            line = json.dumps(
                {
                    "type": "node",
                    "data": {
                        "node_id": node.node_id,
                        "node_type": node.node_type,
                        "created_at": node.created_at,
                        "payload": node.payload,
                    },
                },
                ensure_ascii=False,
            )
            self._file_handle.write(line + "\n")

        for source_id, target_id, edge_type in self._pending_edges:
            line = json.dumps(
                {
                    "type": "edge",
                    "data": {
                        "source_id": source_id,
                        "target_id": target_id,
                        "edge_type": edge_type,
                    },
                },
                ensure_ascii=False,
            )
            self._file_handle.write(line + "\n")

        self._file_handle.flush()
        self._pending_nodes.clear()
        self._pending_edges.clear()

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        """Flush and close the underlying file handle."""
        self.flush()
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def persist_dir(self) -> str | None:
        return self._persist_dir
