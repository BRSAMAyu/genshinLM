"""Claim-gated mission graph (game-agnostic).

A mission is a DAG of :class:`MissionNode`s. Each node has a kind (mapped by the
orchestrator to a primitive controller: nav / combat / interaction / puzzle), a
set of dependencies (nodes that must be completed first), and claim-style
pre/post conditions expressed as simple predicates over a quest-context dict.

Status advances: ``pending`` -> ``ready`` (deps satisfied) -> ``running`` ->
``completed`` (postcondition holds) | ``failed`` (recoverable) | ``blocked``
(unrecoverable). The graph is pure data — the orchestrator drives transitions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

QuestContext = dict[str, object]
Predicate = Callable[[QuestContext], bool]

NodeKind = Literal["nav", "combat", "interaction", "puzzle", "system"]
NodeStatus = Literal["pending", "ready", "running", "completed", "failed", "blocked"]


@dataclass(slots=True)
class MissionNode:
    node_id: str
    kind: NodeKind
    setup: dict[str, object] = field(default_factory=dict)
    dependencies: tuple[str, ...] = ()
    # Claim-style conditions over the quest context (default: always satisfied).
    precondition: Predicate | None = None
    postcondition: Predicate | None = None
    # How many times this node may be retried after a recoverable failure.
    max_retries: int = 1
    status: NodeStatus = "pending"
    attempts: int = 0
    last_failure: str = ""

    def ready(self, ctx: QuestContext) -> bool:
        if self.status in ("completed", "running"):
            return False
        if self.status == "blocked":
            return False
        if self.precondition is not None and not self.precondition(ctx):
            return False
        return True


@dataclass(slots=True)
class MissionGraph:
    objective: str
    nodes: dict[str, MissionNode] = field(default_factory=dict)
    # Quest context persists across nodes (flags, item counts, phase, ...).
    context: QuestContext = field(default_factory=dict)

    def add(self, node: MissionNode) -> None:
        self.nodes[node.node_id] = node

    def validate(self) -> list[str]:
        """Return a list of structural errors (empty == valid).

        Catches the two failure modes that otherwise corrupt a run silently:
        dangling dependencies (a dep id with no node — would KeyError mid-walk)
        and dependency cycles (would stall with no runnable node and no diagnosis).
        Call after construction, before running.
        """
        errors: list[str] = []
        # Dangling dependencies.
        for nid, node in self.nodes.items():
            for dep in node.dependencies:
                if dep not in self.nodes:
                    errors.append(f"node '{nid}' depends on unknown node '{dep}'")
        # Cycle detection (DFS over the dependency edges).
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {nid: WHITE for nid in self.nodes}

        def visit(nid: str, stack: list[str]) -> None:
            color[nid] = GRAY
            for dep in self.nodes[nid].dependencies:
                if dep not in self.nodes:
                    continue  # already reported as dangling
                if color[dep] == GRAY:
                    cycle = " -> ".join([*stack, nid, dep])
                    errors.append(f"dependency cycle: {cycle}")
                elif color[dep] == WHITE:
                    visit(dep, [*stack, nid])
            color[nid] = BLACK

        for nid in self.nodes:
            if color[nid] == WHITE:
                visit(nid, [])
        return errors

    def is_complete(self) -> bool:
        return all(n.status == "completed" for n in self.nodes.values())

    def next_runnable(self) -> MissionNode | None:
        """A node ready to execute: pending, or failed-but-still-within-retry-budget,
        whose dependencies are all completed. A node whose retry budget is
        exhausted is terminal (not returned) — it must be marked ``blocked`` so
        its dependents don't stall silently.
        """
        for node in self.nodes.values():
            if node.status in ("completed", "running", "blocked"):
                continue
            if node.status == "failed" and node.attempts > node.max_retries:
                # Budget exhausted — terminal. Caller marks it blocked + propagates.
                continue
            # A dangling dep (unknown id) can never be "completed", so the node is
            # never runnable — surfaced as a stall, not a KeyError.
            if not all(
                d in self.nodes and self.nodes[d].status == "completed"
                for d in node.dependencies
            ):
                continue
            # Claim-gate: a node only becomes runnable once its precondition holds
            # over the (flowing) quest context.
            if node.precondition is not None and not node.precondition(self.context):
                continue
            return node
        return None

    def mark_blocked_descendants(self, node_id: str) -> list[str]:
        """Cascade ``blocked`` to every transitive dependent of ``node_id``.

        Returns the ids of all nodes newly marked blocked. Use when a node
        exhausts its retry budget so successors reflect that they can't run.
        """
        newly_blocked: list[str] = []
        # BFS over the dependents graph (reverse of dependencies).
        queue = [node_id]
        seen: set[str] = {node_id}
        dependents: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for nid, n in self.nodes.items():
            for dep in n.dependencies:
                dependents.setdefault(dep, []).append(nid)
        while queue:
            current = queue.pop()
            for child in dependents.get(current, []):
                if child in seen:
                    continue
                seen.add(child)
                child_node = self.nodes.get(child)
                if child_node is not None and child_node.status not in ("completed",):
                    if child_node.status != "blocked":
                        child_node.status = "blocked"
                        newly_blocked.append(child)
                    queue.append(child)
        return newly_blocked

    def any_recoverable(self) -> bool:
        return any(n.status == "failed" and n.attempts <= n.max_retries for n in self.nodes.values())

    def completed_count(self) -> int:
        return sum(1 for n in self.nodes.values() if n.status == "completed")
