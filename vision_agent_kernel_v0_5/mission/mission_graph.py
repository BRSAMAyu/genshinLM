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

    def is_complete(self) -> bool:
        return all(n.status == "completed" for n in self.nodes.values())

    def next_runnable(self) -> MissionNode | None:
        """A pending node whose dependencies are all completed."""
        for node in self.nodes.values():
            if node.status not in ("pending", "failed"):
                continue
            if not all(self.nodes[d].status == "completed" for d in node.dependencies):
                continue
            return node
        return None

    def any_recoverable(self) -> bool:
        return any(n.status == "failed" and n.attempts <= n.max_retries for n in self.nodes.values())

    def completed_count(self) -> int:
        return sum(1 for n in self.nodes.values() if n.status == "completed")
