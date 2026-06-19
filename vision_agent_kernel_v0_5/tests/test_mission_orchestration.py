"""Tests for mission orchestration — claim-gated graph + chapter completion (Phase 5)."""
from __future__ import annotations

import pytest

from harness.sim.mission_world import (
    ChapterNodeExecutor,
    flaky_map_for,
    make_chapter_graph,
)
from mission.mission_graph import MissionGraph, MissionNode
from mission.mission_orchestrator import (
    MissionOrchestrator,
    NodeOutcome,
)


# --- graph mechanics -------------------------------------------------------


def _linear_graph() -> MissionGraph:
    g = MissionGraph(objective="test")
    g.add(MissionNode(node_id="a", kind="system"))
    g.add(MissionNode(node_id="b", kind="system", dependencies=("a",)))
    g.add(MissionNode(node_id="c", kind="system", dependencies=("b",)))
    return g


def test_next_runnable_respects_dependencies() -> None:
    g = _linear_graph()
    assert g.next_runnable().node_id == "a"
    g.nodes["a"].status = "completed"
    assert g.next_runnable().node_id == "b"
    g.nodes["b"].status = "completed"
    assert g.next_runnable().node_id == "c"


def test_is_complete_only_when_all_done() -> None:
    g = _linear_graph()
    assert not g.is_complete()
    for n in g.nodes.values():
        n.status = "completed"
    assert g.is_complete()


# --- orchestrator: claim-gating, retries, attribution ----------------------


class _ScriptedExecutor:
    """Returns canned outcomes per node_id, recording calls."""

    def __init__(self, outcomes: dict[str, list[NodeOutcome]]) -> None:
        self._outcomes = outcomes
        self.calls: list[str] = []

    def execute(self, node, ctx):
        self.calls.append(node.node_id)
        seq = self._outcomes.get(node.node_id, [NodeOutcome(success=True)])
        idx = min(node.attempts - 1, len(seq) - 1)
        return seq[idx]


def test_orchestrator_completes_linear_mission() -> None:
    g = _linear_graph()
    orch = MissionOrchestrator(g, _ScriptedExecutor({}))
    status = orch.run()
    assert status.success and status.completed == 3


def test_orchestrator_retries_recoverable_failure_then_succeeds() -> None:
    g = MissionGraph(objective="retry")
    g.add(MissionNode(node_id="x", kind="system", max_retries=2))
    exec_ = _ScriptedExecutor({
        "x": [NodeOutcome(success=False, failure_code="transient"),
              NodeOutcome(success=True)],
    })
    status = MissionOrchestrator(g, exec_).run()
    assert status.success
    assert g.nodes["x"].attempts == 2  # failed once, retried, succeeded


def test_orchestrator_blocks_after_retry_budget_exhausted() -> None:
    g = MissionGraph(objective="block")
    g.add(MissionNode(node_id="x", kind="system", max_retries=1))
    exec_ = _ScriptedExecutor({
        "x": [NodeOutcome(success=False, failure_code="hard_fail")],  # always fails
    })
    status = MissionOrchestrator(g, exec_).run()
    assert not status.success
    assert g.nodes["x"].status == "failed"
    assert status.last_failure == "hard_fail"


def test_postcondition_unmet_is_recoverable() -> None:
    g = MissionGraph(objective="postcond", context={})
    g.add(MissionNode(
        node_id="x", kind="system", max_retries=2,
        postcondition=lambda ctx: ctx.get("verified") is True,
    ))
    # First run succeeds execution but ctx lacks 'verified'; second run sets it.
    class _Exec:
        def __init__(self): self.n = 0
        def execute(self, node, ctx):
            self.n += 1
            if self.n == 2:
                return NodeOutcome(success=True, context_updates={"verified": True})
            return NodeOutcome(success=True)  # no verified flag
    status = MissionOrchestrator(g, _Exec()).run()
    assert status.success


def test_quest_context_flows_across_nodes() -> None:
    g = MissionGraph(objective="ctx")
    g.add(MissionNode(node_id="a", kind="interaction"))
    g.add(MissionNode(
        node_id="b", kind="system", dependencies=("a",),
        precondition=lambda ctx: ctx.get("done_a") is True,
    ))
    exec_ = _ScriptedExecutor({
        "a": [NodeOutcome(success=True, context_updates={"done_a": True})],
    })
    status = MissionOrchestrator(g, exec_).run()
    assert status.success  # b's precondition satisfied by a's context update


# --- dogfood: full chapter completion via real sub-stacks ------------------


def test_single_chapter_completes_end_to_end() -> None:
    graph = make_chapter_graph(seed=1, flaky=True)
    executor = ChapterNodeExecutor(flaky_map_for(graph))
    status = MissionOrchestrator(graph, executor).run(max_total_steps=200)
    assert status.success, f"chapter failed at {status.current_node}: {status.last_failure}"
    assert status.completed == status.total
    # the injected transient boss fault was recovered (boss retried)
    assert graph.nodes["boss_fight"].attempts >= 2


def test_chapter_batch_exit_gate() -> None:
    # ROADMAP Phase 5 exit gate: end-to-end chapter completion majority.
    successes = 0
    total = 12
    for seed in range(1, total + 1):
        graph = make_chapter_graph(seed=seed, flaky=True)
        executor = ChapterNodeExecutor(flaky_map_for(graph))
        status = MissionOrchestrator(graph, executor).run(max_total_steps=200)
        successes += 1 if status.success else 0
    rate = successes / total
    assert rate >= 0.75, f"chapter completion rate={rate:.2f} ({successes}/{total})"
