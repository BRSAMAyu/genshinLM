"""MissionGraph v4 — claim-gated mission nodes with BAGEL belief integration.

Nodes are no longer simple execution steps. Each node is a *fact contract*:
- input_claims: preconditions that must be verified before execution
- output_claims: state changes the node must produce to succeed
- budgets: retry/uncertainty/duration limits
- bagel: required belief commits that must precede action proposal
- fallbacks: recovery recipes and replan policies when execution fails

Validation rules (enforced by mission_graph_validator_v4.py):
- Terminal nodes must have output_claims
- High-risk nodes must have fallbacks
- Graph must be acyclic and deterministic-serializable
"""
from __future__ import annotations

import json
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal

from runtime.claim_runtime import RiskLevel


# -- Types -----------------------------------------------------------------

ClaimContractRole = Literal["informational", "local", "dependency", "terminal"]
_VALID_RISK_LEVELS = frozenset({"low", "medium", "high", "critical"})
_VALID_CLAIM_ROLES = frozenset({"informational", "local", "dependency", "terminal"})


# -- Claim contract (node-level) -------------------------------------------

@dataclass(frozen=True, slots=True)
class ClaimContract:
    """A claim requirement or production declared by a mission node."""
    claim_type: str
    target: str = ""
    required_status: str = "verified"
    claim_role: ClaimContractRole = "local"
    verifier_recipe: str = ""


# -- BAGEL belief template -------------------------------------------------

@dataclass(frozen=True, slots=True)
class BeliefTemplate:
    """Template for a belief that must be committed before node execution."""
    target_object: str
    causal_role: str
    hypothesis: str = ""
    falsification_condition: str = ""


# -- Budgets ---------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class NodeBudget:
    """Execution limits for a mission node."""
    max_retries: int = 2
    max_uncertain: int = 1
    max_duration_sec: float = 120.0


# -- Fallback declaration --------------------------------------------------

@dataclass(frozen=True, slots=True)
class FallbackDecl:
    """A recovery or replan fallback for a node."""
    recovery_recipe: str = ""
    replan_policy: str = ""


# -- Mission node v4 -------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MissionNodeV4:
    """A claim-gated mission node.

    Unlike v1-v3 nodes, this carries explicit claim contracts, BAGEL belief
    templates, budgets, and fallback declarations.
    """
    node_id: str
    node_type: str
    risk_level: RiskLevel = "medium"
    skill_candidates: tuple[str, ...] = ()
    input_claims: tuple[ClaimContract, ...] = ()
    output_claims: tuple[ClaimContract, ...] = ()
    fallbacks: tuple[FallbackDecl, ...] = ()
    budgets: NodeBudget = field(default_factory=NodeBudget)
    belief_templates: tuple[BeliefTemplate, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_terminal(self) -> bool:
        """Whether this node produces output claims (does NOT mean graph leaf)."""
        return bool(self.output_claims)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "risk_level": self.risk_level,
            "skill_candidates": list(self.skill_candidates),
            "input_claims": [_claim_to_dict(c) for c in self.input_claims],
            "output_claims": [_claim_to_dict(c) for c in self.output_claims],
            "fallbacks": [_fallback_to_dict(f) for f in self.fallbacks],
            "budgets": {
                "max_retries": self.budgets.max_retries,
                "max_uncertain": self.budgets.max_uncertain,
                "max_duration_sec": self.budgets.max_duration_sec,
            },
            "belief_templates": [
                {"target_object": bt.target_object, "causal_role": bt.causal_role,
                 "hypothesis": bt.hypothesis, "falsification_condition": bt.falsification_condition}
                for bt in self.belief_templates
            ],
            "metadata": dict(self.metadata),
        }


# -- Edge ------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MissionEdgeV4:
    from_node: str
    to_node: str
    condition: str = "success"


# -- Graph container -------------------------------------------------------

class MissionGraphV4:
    """DAG of claim-gated mission nodes.

    Thread-safe for reads. Mutations should be done during construction
    before the graph is shared across threads.
    """

    def __init__(self, mission_id: str = "", graph_id: str = "") -> None:
        self.mission_id = mission_id
        self.graph_id = graph_id or f"mg4_{uuid.uuid4().hex[:8]}"
        self._nodes: dict[str, MissionNodeV4] = {}
        self._edges: dict[str, set[str]] = {}  # from_node -> {to_nodes}
        self._reverse_edges: dict[str, set[str]] = {}  # to_node -> {from_nodes}
        self._edge_conditions: dict[tuple[str, str], str] = {}  # (from, to) -> condition
        self._node_order: list[str] = []  # insertion order for determinism

    def add_node(self, node: MissionNodeV4) -> None:
        if node.node_id in self._nodes:
            self._node_order = [nid for nid in self._node_order if nid != node.node_id]
        self._nodes[node.node_id] = node
        self._node_order.append(node.node_id)
        self._edges.setdefault(node.node_id, set())
        self._reverse_edges.setdefault(node.node_id, set())

    def add_edge(self, edge: MissionEdgeV4) -> None:
        self._edges.setdefault(edge.from_node, set()).add(edge.to_node)
        self._reverse_edges.setdefault(edge.to_node, set()).add(edge.from_node)
        self._edge_conditions[(edge.from_node, edge.to_node)] = edge.condition

    def get_node(self, node_id: str) -> MissionNodeV4 | None:
        return self._nodes.get(node_id)

    @property
    def nodes(self) -> dict[str, MissionNodeV4]:
        return dict(self._nodes)

    @property
    def node_ids(self) -> list[str]:
        return list(self._node_order)

    def successors(self, node_id: str) -> set[str]:
        return set(self._edges.get(node_id, set()))

    def predecessors(self, node_id: str) -> set[str]:
        return set(self._reverse_edges.get(node_id, set()))

    def root_nodes(self) -> list[str]:
        """Nodes with no predecessors."""
        return [nid for nid in self._node_order if not self._reverse_edges.get(nid)]

    def terminal_nodes(self) -> list[str]:
        """Nodes with no successors."""
        return [nid for nid in self._node_order if not self._edges.get(nid)]

    def has_cycle(self) -> bool:
        """Detect cycles via DFS."""
        white, gray, black = 0, 1, 2
        color: dict[str, int] = {nid: white for nid in self._nodes}

        def dfs(node: str) -> bool:
            color[node] = gray
            for succ in self._edges.get(node, set()):
                if color.get(succ) == gray:
                    return True
                if color.get(succ) == white and dfs(succ):
                    return True
            color[node] = black
            return False

        for nid in self._node_order:
            if color[nid] == white and dfs(nid):
                return True
        return False

    def topological_order(self) -> list[str] | None:
        """Kahn's algorithm. Returns None if cycle exists."""
        in_degree: dict[str, int] = {nid: len(self._reverse_edges.get(nid, set())) for nid in self._nodes}
        queue: deque[str] = deque(nid for nid in self._node_order if in_degree[nid] == 0)
        order: list[str] = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for succ in sorted(self._edges.get(node, set())):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        if len(order) != len(self._nodes):
            return None
        return order

    def to_dict(self) -> dict[str, Any]:
        """Deterministic JSON-serializable export for replay and audit."""
        edges = []
        for src in self._node_order:
            for dst in sorted(self._edges.get(src, set())):
                cond = self._edge_conditions.get((src, dst), "success")
                edges.append({"from": src, "to": dst, "condition": cond})

        return {
            "graph_id": self.graph_id,
            "mission_id": self.mission_id,
            "nodes": [self._nodes[nid].to_dict() for nid in self._node_order],
            "edges": edges,
            "node_count": len(self._nodes),
            "edge_count": len(edges),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MissionGraphV4:
        """Reconstruct graph from deterministic dict."""
        graph = cls(
            mission_id=data.get("mission_id", ""),
            graph_id=data.get("graph_id", ""),
        )
        for nd in data.get("nodes", []):
            budgets_data = nd.get("budgets", {})
            budgets = NodeBudget(
                max_retries=budgets_data.get("max_retries", 2),
                max_uncertain=budgets_data.get("max_uncertain", 1),
                max_duration_sec=budgets_data.get("max_duration_sec", 120.0),
            )
            node = MissionNodeV4(
                node_id=nd["node_id"],
                node_type=nd["node_type"],
                risk_level=nd.get("risk_level", "medium"),
                skill_candidates=tuple(nd.get("skill_candidates", [])),
                input_claims=tuple(
                    ClaimContract(c["claim_type"], c.get("target", ""),
                                  c.get("required_status", "verified"),
                                  c.get("claim_role", "local"),
                                  c.get("verifier_recipe", ""))
                    for c in nd.get("input_claims", [])
                ),
                output_claims=tuple(
                    ClaimContract(c["claim_type"], c.get("target", ""),
                                  c.get("required_status", "verified"),
                                  c.get("claim_role", "local"),
                                  c.get("verifier_recipe", ""))
                    for c in nd.get("output_claims", [])
                ),
                fallbacks=tuple(
                    FallbackDecl(f.get("recovery_recipe", ""), f.get("replan_policy", ""))
                    for f in nd.get("fallbacks", [])
                ),
                budgets=budgets,
                belief_templates=tuple(
                    BeliefTemplate(bt["target_object"], bt["causal_role"],
                                   bt.get("hypothesis", ""), bt.get("falsification_condition", ""))
                    for bt in nd.get("belief_templates", [])
                ),
                metadata=nd.get("metadata", {}),
            )
            graph.add_node(node)
        for ed in data.get("edges", []):
            graph.add_edge(MissionEdgeV4(ed["from"], ed["to"], ed.get("condition", "success")))
        return graph

    @classmethod
    def from_json(cls, json_str: str) -> MissionGraphV4:
        return cls.from_dict(json.loads(json_str))

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return sum(len(succs) for succs in self._edges.values())


# -- Helpers for serialization ---------------------------------------------

def _claim_to_dict(c: ClaimContract) -> dict[str, str]:
    return {
        "claim_type": c.claim_type,
        "target": c.target,
        "required_status": c.required_status,
        "claim_role": c.claim_role,
        "verifier_recipe": c.verifier_recipe,
    }


def _fallback_to_dict(f: FallbackDecl) -> dict[str, str]:
    return {"recovery_recipe": f.recovery_recipe, "replan_policy": f.replan_policy}
