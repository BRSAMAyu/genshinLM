from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Literal

from runtime.claim_runtime import RiskLevel


UnattendedMode = Literal["conservative", "opportunistic", "supervised"]
ClaimRole = Literal["informational", "local", "dependency", "terminal"]


# --- MissionGraph Node (extends planning/mission_queue MissionNode) ---

@dataclass(frozen=True, slots=True)
class MissionGraphNode:
    node_id: str
    node_type: str
    skill_binding: str = ""
    produces: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    alternative_for: str = ""
    risk_level: RiskLevel = "medium"
    claim_role: ClaimRole = "local"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MissionGraphEdge:
    from_node: str
    to_node: str


# --- UnverifiablePolicy (Section 11.3) ---

@dataclass(frozen=True, slots=True)
class UnverifiableBudget:
    max_count: int = 3
    max_weight: float = 1.0
    allowed_claim_types: list[str] = field(default_factory=list)
    allowed_risk_levels: list[RiskLevel] = field(default_factory=lambda: ["low"])
    terminal_claim_requires_verification: bool = True


@dataclass(frozen=True, slots=True)
class UnverifiableDecision:
    allowed: bool
    reason: str
    budget_remaining: int
    weight_remaining: float


class UnverifiablePolicy:
    def __init__(self, mode: UnattendedMode = "conservative") -> None:
        self.mode = mode

    def check(
        self,
        *,
        claim_role: ClaimRole,
        risk_level: RiskLevel,
        budget: UnverifiableBudget,
        current_count: int,
        current_weight: float,
    ) -> UnverifiableDecision:
        remaining_count = budget.max_count - current_count
        remaining_weight = budget.max_weight - current_weight

        if claim_role == "terminal" and budget.terminal_claim_requires_verification:
            return UnverifiableDecision(False, "terminal_claim_requires_verification", remaining_count, remaining_weight)

        if claim_role == "dependency":
            return self._check_dependency(risk_level, remaining_count, remaining_weight)

        if claim_role == "informational":
            return UnverifiableDecision(True, "informational_claim_can_be_tentative", remaining_count, remaining_weight)

        # local claim
        return self._check_local(risk_level, remaining_count, remaining_weight)

    def _check_dependency(
        self, risk_level: RiskLevel, remaining_count: int, remaining_weight: float,
    ) -> UnverifiableDecision:
        if self.mode == "conservative":
            return UnverifiableDecision(False, "conservative_mode_blocks_dependency_unverifiable", remaining_count, remaining_weight)
        if self.mode == "opportunistic":
            if risk_level == "low" and remaining_count > 0:
                return UnverifiableDecision(True, "opportunistic_allows_low_risk_dependency", remaining_count, remaining_weight)
            return UnverifiableDecision(False, "opportunistic_blocks_non_low_dependency", remaining_count, remaining_weight)
        # supervised
        return UnverifiableDecision(False, "supervised_requires_human_confirm", remaining_count, remaining_weight)

    def _check_local(
        self, risk_level: RiskLevel, remaining_count: int, remaining_weight: float,
    ) -> UnverifiableDecision:
        if remaining_count <= 0:
            return UnverifiableDecision(False, "unverifiable_budget_exhausted", remaining_count, remaining_weight)
        if risk_level == "critical":
            return UnverifiableDecision(False, "critical_risk_cannot_be_unverifiable", remaining_count, remaining_weight)
        if risk_level == "high":
            return UnverifiableDecision(False, "high_risk_local_cannot_be_unverifiable", remaining_count, remaining_weight)
        if self.mode == "conservative" and risk_level in ("medium",):
            return UnverifiableDecision(False, "conservative_blocks_medium_risk_unverifiable", remaining_count, remaining_weight)
        return UnverifiableDecision(True, f"local_{risk_level}_risk_unverifiable_allowed", remaining_count, remaining_weight)


# --- MissionGraph DAG (Section 11) ---

@dataclass(frozen=True, slots=True)
class PathResult:
    path: list[str]
    blocked_nodes: list[str]
    used_alternative: bool


class MissionGraph:
    """DAG-based mission structure with alternative paths.

    Records action dependencies (what to do in what order).
    Complements ClaimGraph (fact dependencies) for planner rerouting.
    """

    def __init__(self, mission_id: str = "", risk_level: RiskLevel = "medium") -> None:
        self.mission_id = mission_id
        self.risk_level = risk_level
        self._nodes: dict[str, MissionGraphNode] = {}
        self._edges: dict[str, set[str]] = defaultdict(set)
        self._alternatives: dict[str, set[str]] = defaultdict(set)
        self._blocked: dict[str, str] = {}

    def add_node(self, node: MissionGraphNode) -> None:
        self._nodes[node.node_id] = node
        for dep in node.depends_on:
            self._edges[dep].add(node.node_id)
        if node.alternative_for:
            self._alternatives[node.alternative_for].add(node.node_id)

    def add_edge(self, from_node: str, to_node: str) -> None:
        self._edges[from_node].add(to_node)

    def get_node(self, node_id: str) -> MissionGraphNode | None:
        return self._nodes.get(node_id)

    def mark_blocked(self, node_id: str, reason: str = "") -> None:
        self._blocked[node_id] = reason

    def is_blocked(self, node_id: str) -> bool:
        return node_id in self._blocked

    def find_path_to(self, target: str, avoid: set[str] | None = None) -> list[str] | None:
        avoid_set = (avoid or set()) | set(self._blocked.keys())
        start = self._find_root()
        if start is None:
            return None
        visited: set[str] = set()
        queue: deque[tuple[str, list[str]]] = deque([(start, [start])])
        while queue:
            current, path = queue.popleft()
            if current == target:
                return path
            if current in visited or current in avoid_set:
                continue
            visited.add(current)
            for neighbor in sorted(self._edges.get(current, set())):
                if neighbor not in visited and neighbor not in avoid_set:
                    queue.append((neighbor, [*path, neighbor]))
        return None

    def find_alternative_path(self, blocked_node: str) -> PathResult | None:
        alternatives = self._alternatives.get(blocked_node, set())
        if not alternatives:
            return None
        for alt in sorted(alternatives):
            if alt in self._blocked:
                continue
            target = self._find_terminal()
            if target is None:
                continue
            avoid = set(self._blocked.keys()) | {blocked_node}
            path = self.find_path_to(target, avoid=avoid)
            if path is not None and alt in path:
                return PathResult(
                    path=path,
                    blocked_nodes=[blocked_node],
                    used_alternative=True,
                )
        return None

    def get_dependents(self, node_id: str) -> list[str]:
        result: list[str] = []
        visited: set[str] = set()
        queue: deque[str] = deque([node_id])
        while queue:
            current = queue.popleft()
            for child in self._edges.get(current, set()):
                if child not in visited:
                    visited.add(child)
                    result.append(child)
                    queue.append(child)
        return sorted(result)

    def validate_dag(self) -> list[str]:
        errors: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> bool:
            if node_id in visiting:
                return True
            if node_id in visited:
                return False
            visiting.add(node_id)
            for child in self._edges.get(node_id, set()):
                if visit(child):
                    return True
            visiting.remove(node_id)
            visited.add(node_id)
            return False

        for node_id in self._nodes:
            if visit(node_id):
                errors.append("cycle_detected")
                break

        for node_id, node in self._nodes.items():
            for dep in node.depends_on:
                if dep not in self._nodes:
                    errors.append(f"missing_dependency:{node_id}->{dep}")

        return errors

    def _find_root(self) -> str | None:
        targets: set[str] = set()
        sources: set[str] = set()
        for src, dsts in self._edges.items():
            sources.add(src)
            targets.update(dsts)
        roots = sources - targets
        for node_id in self._nodes:
            if node_id not in targets:
                return node_id
        return None

    def _find_terminal(self) -> str | None:
        all_sources: set[str] = set()
        for src in self._edges:
            all_sources.add(src)
        for node_id, node in self._nodes.items():
            if node_id not in all_sources:
                return node_id
        return None

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def blocked_count(self) -> int:
        return len(self._blocked)
