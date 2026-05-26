from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

MissionNodeStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]
MissionNodeType = Literal[
    "goal",
    "subtask",
    "action",
    "verify",
    "condition",
    "loop",
    "fallback",
]


@dataclass(slots=True)
class MissionNode:
    node_id: str
    node_type: MissionNodeType
    label: str
    semantic_action: str = ""
    target: str = ""
    precondition: str = ""
    expected_state: str = ""
    verifier: str = ""
    children: list[str] = field(default_factory=list)
    parent_id: str | None = None
    alternative_for: str | None = None
    risk_level: str = "low"
    status: MissionNodeStatus = "pending"
    attempts: int = 0
    max_attempts: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_terminal(self) -> bool:
        return self.status in ("completed", "failed", "skipped")


@dataclass(frozen=True, slots=True)
class MissionEdge:
    source: str
    target: str
    condition: str = ""
    edge_type: str = "sequential"


@dataclass(slots=True)
class MissionGraph:
    graph_id: str
    goal: str
    capsule_id: str
    root_node_id: str
    nodes: dict[str, MissionNode] = field(default_factory=dict)
    edges: list[MissionEdge] = field(default_factory=list)
    created_at: float = field(default_factory=time.perf_counter)
    status: str = "planned"

    def add_node(self, node: MissionNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, source: str, target: str, condition: str = "", edge_type: str = "sequential") -> None:
        self.edges.append(MissionEdge(source=source, target=target, condition=condition, edge_type=edge_type))

    def node(self, node_id: str) -> MissionNode:
        return self.nodes[node_id]

    def children_of(self, node_id: str) -> list[MissionNode]:
        node = self.nodes[node_id]
        return [self.nodes[cid] for cid in node.children if cid in self.nodes]

    def next_pending(self) -> MissionNode | None:
        for node in self.nodes.values():
            if node.node_type in ("goal", "subtask"):
                continue
            if not node.is_terminal() and self._predecessors_complete(node.node_id):
                return node
        return None

    def _predecessors_complete(self, node_id: str) -> bool:
        predecessors = [e.source for e in self.edges if e.target == node_id]
        if not predecessors:
            return True
        for pid in predecessors:
            pred = self.nodes.get(pid)
            if pred is None:
                continue
            if pred.node_type in ("goal", "subtask") and pred.status in ("in_progress", "completed"):
                continue
            if pred.status != "completed":
                return False
        return True

    def progress(self) -> tuple[int, int]:
        total = len(self.nodes)
        done = sum(1 for n in self.nodes.values() if n.status == "completed")
        return (done, total)

    def executable_progress(self) -> tuple[int, int]:
        executable = [n for n in self.nodes.values() if n.node_type not in ("goal", "subtask")]
        total = len(executable)
        done = sum(1 for n in executable if n.status == "completed")
        return (done, total)

    def is_complete(self) -> bool:
        executable = [n for n in self.nodes.values() if n.node_type not in ("goal", "subtask")]
        return bool(executable) and all(n.is_terminal() for n in executable)

    def failed_nodes(self) -> list[MissionNode]:
        return [n for n in self.nodes.values() if n.status == "failed"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "goal": self.goal,
            "capsule_id": self.capsule_id,
            "root_node_id": self.root_node_id,
            "status": self.status,
            "progress": self.progress(),
            "nodes": {
                nid: {
                    "node_id": n.node_id,
                    "node_type": n.node_type,
                    "label": n.label,
                    "semantic_action": n.semantic_action,
                    "status": n.status,
                    "attempts": n.attempts,
                }
                for nid, n in self.nodes.items()
            },
            "edges": [{"source": e.source, "target": e.target, "condition": e.condition} for e in self.edges],
        }


class MissionGraphBuilder:
    """Builds a MissionGraph from a hierarchical plan specification."""

    @staticmethod
    def _next_id(prefix: str = "node") -> str:
        import uuid
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    @classmethod
    def from_decomposition(
        cls,
        goal: str,
        capsule_id: str,
        steps: list[dict[str, Any]],
    ) -> MissionGraph:
        root_id = cls._next_id("root")
        graph = MissionGraph(
            graph_id=f"mission_{uuid.uuid4().hex[:12]}",
            goal=goal,
            capsule_id=capsule_id,
            root_node_id=root_id,
        )

        root = MissionNode(
            node_id=root_id,
            node_type="goal",
            label=goal,
            status="in_progress",
        )
        graph.add_node(root)

        prev_id = root_id
        for step in steps:
            node_id = cls._build_node(graph, step, parent_id=root_id)
            graph.add_edge(prev_id, node_id)
            root.children.append(node_id)
            prev_id = node_id

        verify_id = cls._next_id("verify")
        verify_node = MissionNode(
            node_id=verify_id,
            node_type="verify",
            label=f"Verify: {goal}",
            verifier="goal_achieved",
            parent_id=root_id,
        )
        graph.add_node(verify_node)
        graph.add_edge(prev_id, verify_id)
        root.children.append(verify_id)

        return graph

    @classmethod
    def _build_node(
        cls,
        graph: MissionGraph,
        step: dict[str, Any],
        parent_id: str | None = None,
    ) -> str:
        node_id = cls._next_id(step.get("type", "action"))
        children = step.get("children", [])

        node = MissionNode(
            node_id=node_id,
            node_type=step.get("node_type", "action" if not children else "subtask"),
            label=step.get("label", ""),
            semantic_action=step.get("semantic_action", ""),
            target=step.get("target", ""),
            precondition=step.get("precondition", ""),
            expected_state=step.get("expected_state", ""),
            verifier=step.get("verifier", ""),
            parent_id=parent_id,
            risk_level=step.get("risk_level", "low"),
            max_attempts=step.get("max_attempts", 3),
        )
        graph.add_node(node)

        if children:
            prev = node_id
            for child_spec in children:
                child_id = cls._build_node(graph, child_spec, parent_id=node_id)
                graph.add_edge(prev, child_id)
                node.children.append(child_id)
                prev = child_id

        fallback = step.get("fallback")
        if fallback:
            fallback_id = cls._build_node(graph, fallback, parent_id=parent_id)
            fallback_node = graph.node(fallback_id)
            fallback_node.alternative_for = node_id
            graph.add_edge(parent_id or node_id, fallback_id, condition=f"failed:{node_id}", edge_type="fallback")

        return node_id
