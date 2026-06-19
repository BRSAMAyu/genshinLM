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

_MISSING = object()


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
        """Drive the graph to completion or a blocked failure.

        Validates structure first — an invalid graph (dangling deps / cycles)
        fails fast with a diagnostic instead of stalling or KeyError-ing mid-walk.
        """
        graph = self._graph
        errors = graph.validate()
        if errors:
            return MissionStatus(
                completed=0, total=len(graph.nodes),
                current_node=graph.objective, finished=True, success=False,
                last_failure=f"invalid_graph: {errors[0]}",
            )
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
        # Enforce the retry budget BEFORE executing: a node over budget is
        # terminal-blocked, not re-executed. (Without this, run() would loop.)
        if node.attempts > node.max_retries:
            self._block(node)
            return
        node.status = "running"
        node.attempts += 1
        outcome = self._executor.execute(node, graph.context)

        if outcome.success:
            # The node claims its post-state via context_updates; snapshot prior
            # values, apply them, then verify the claim (postcondition) holds.
            prior = {k: graph.context.get(k, _MISSING) for k in outcome.context_updates}
            graph.context.update(outcome.context_updates)
            if node.postcondition is not None and not node.postcondition(graph.context):
                # Claim doesn't verify — roll back to prior values (restore
                # pre-existing keys, don't delete them) and retry/recover.
                self._restore(graph.context, prior)
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
        else:
            # Budget exhausted — terminal. Block it and cascade to dependents.
            self._block(node)

    def _block(self, node: MissionNode) -> None:
        node.status = "blocked"
        self._graph.mark_blocked_descendants(node.node_id)

    @staticmethod
    def _restore(ctx: dict[str, object], prior: dict[str, object]) -> None:
        for key, value in prior.items():
            if value is _MISSING:
                ctx.pop(key, None)
            else:
                ctx[key] = value

    def _last_failure(self) -> str:
        failed = [n for n in self._graph.nodes.values() if n.status == "failed"]
        return failed[0].last_failure if failed else ""
