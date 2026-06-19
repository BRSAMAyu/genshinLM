"""Mission orchestrator — walks the claim-gated graph with attribution + recovery.

Separation of concerns:
* :class:`NodeExecutor` (protocol) runs ONE node's primitive and reports outcome.
* :class:`MissionOrchestrator` owns graph advancement — picks the next runnable
  node, claim-gates it (precondition), executes, checks the postcondition, and on
  failure attributes the cause and either retries (recoverable, within budget) or
  marks the node blocked and stops.

This is the offline preview of MainlineRunner + BAGEL: a node failure doesn't
abort the mission — it's attributed, the node may be retried, and quest context
flows forward across nodes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from mission.mission_graph import MissionGraph, MissionNode, QuestContext


@dataclass(frozen=True, slots=True)
class NodeOutcome:
    success: bool
    failure_code: str = ""
    context_updates: dict[str, object] = field(default_factory=dict)
    reason: str = ""


class NodeExecutor(Protocol):
    """Runs one node's primitive (nav/combat/interaction/puzzle) to completion."""

    def execute(self, node: MissionNode, ctx: QuestContext) -> NodeOutcome:
        ...


@dataclass(frozen=True, slots=True)
class MissionStatus:
    completed: int
    total: int
    current_node: str
    finished: bool
    success: bool
    last_failure: str


class MissionOrchestrator:
    def __init__(self, graph: MissionGraph, executor: NodeExecutor) -> None:
        self._graph = graph
        self._executor = executor

    @property
    def graph(self) -> MissionGraph:
        return self._graph

    def run(self, max_total_steps: int = 4000) -> MissionStatus:
        """Drive the graph to completion or a blocked failure."""
        graph = self._graph
        steps = 0
        while not graph.is_complete() and steps < max_total_steps:
            node = graph.next_runnable()
            if node is None:
                # Nothing runnable and not complete -> a node is blocked/failed
                # beyond its retry budget. Mission cannot advance.
                break
            self._advance(node)
            steps += 1

        success = graph.is_complete()
        current = next((n.node_id for n in graph.nodes.values()
                        if n.status not in ("completed",)), graph.objective)
        return MissionStatus(
            completed=graph.completed_count(), total=len(graph.nodes),
            current_node=current, finished=True, success=success,
            last_failure=self._last_failure(),
        )

    def _advance(self, node: MissionNode) -> None:
        graph = self._graph
        node.status = "running"
        node.attempts += 1
        outcome = self._executor.execute(node, graph.context)

        if outcome.success:
            # The node claims its post-state via context_updates; apply them, then
            # verify the claim (postcondition) holds over the updated context.
            graph.context.update(outcome.context_updates)
            if node.postcondition is not None and not node.postcondition(graph.context):
                # Claim doesn't verify — roll back the claimed updates and treat
                # as a recoverable failure (re-run).
                for key in outcome.context_updates:
                    graph.context.pop(key, None)
                node.status = "failed"
                node.last_failure = "postcondition_unmet"
                self._maybe_retry(node)
                return
            node.status = "completed"
            return

        node.status = "failed"
        node.last_failure = outcome.failure_code or "node_failed"
        self._maybe_retry(node)

    def _maybe_retry(self, node: MissionNode) -> None:
        # Recoverable within budget: reset to pending so next_runnable picks it up.
        if node.attempts <= node.max_retries:
            node.status = "pending"
        # else: leave as failed — next_runnable skips it, mission stalls (blocked).

    def _last_failure(self) -> str:
        failed = [n for n in self._graph.nodes.values() if n.status == "failed"]
        return failed[0].last_failure if failed else ""
