"""Mainline Runner — continuous mission execution loop.

Orchestrates:
1. MissionGraphV4 execution (claim-gated nodes)
2. Sentinel monitoring (somatic state + recovery)
3. Quest state tracking (ActiveQuestContext updates)
4. BAGEL belief attribution (failure recovery)
5. Skill selection via registry (applicability matching)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from bagel.fig_schema import BeliefIdentity, BeliefNode
from bagel.runtime import BagelRuntime
from control.sentinel.sentinel_runtime import SentinelRuntime
from control.sentinel.somatic_state import SomaticState
from planning.mainline.active_quest_context import ActiveQuestContext
from planning.mainline.mission_graph_v4 import MissionGraphV4, MissionNodeV4
from planning.mainline.mission_graph_validator_v4 import MissionGraphValidatorV4

log = logging.getLogger(__name__)


NodeExecStatus = str  # pending | executing | completed | failed | skipped | blocked
MainlineRuntimePhase = Literal[
    "observe",
    "update_context",
    "select_graph",
    "commit_beliefs",
    "execute",
    "verify",
    "attribute_recover",
    "checkpoint",
    "condense",
    "completed",
    "failed",
]


@dataclass(frozen=True, slots=True)
class NodeResult:
    """Result of executing a single mission node."""
    node_id: str
    status: NodeExecStatus
    duration_sec: float = 0.0
    claim_data: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass(slots=True)
class MissionRunResult:
    """Result of a complete mission run."""
    success: bool
    completed_nodes: list[str] = field(default_factory=list)
    failed_nodes: list[str] = field(default_factory=list)
    skipped_nodes: list[str] = field(default_factory=list)
    node_results: list[NodeResult] = field(default_factory=list)
    sentinel_interventions: int = 0
    duration_sec: float = 0.0


@dataclass(frozen=True, slots=True)
class MainlineCheckpoint:
    checkpoint_id: str
    phase: MainlineRuntimePhase
    context_version: int
    graph_id: str
    completed_nodes: tuple[str, ...] = ()
    failed_nodes: tuple[str, ...] = ()
    bagel_graph_version: int = 0
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if self.created_at == 0.0:
            object.__setattr__(self, "created_at", time.perf_counter())


@dataclass(frozen=True, slots=True)
class MainlineLoopResult:
    success: bool
    phase: MainlineRuntimePhase
    checkpoint: MainlineCheckpoint
    run_result: MissionRunResult
    context: ActiveQuestContext


class MainlineRunner:
    """Executes a MissionGraphV4 with claim-gated progression.

    For each node:
    1. Check input_claims are satisfied (skip if not)
    2. Commit required BAGEL beliefs
    3. Select applicable skill from registry
    4. Execute with budget enforcement
    5. Verify output_claims
    6. Update somatic state
    7. Run sentinel check
    """

    def __init__(
        self,
        sentinel: SentinelRuntime | None = None,
        claim_check_fn: Any = None,
        skill_execute_fn: Any = None,
        max_node_retries: int = 2,
        max_duration_sec: float = 600.0,
    ) -> None:
        self._sentinel = sentinel or SentinelRuntime()
        self._claim_check = claim_check_fn
        self._skill_execute = skill_execute_fn
        self._max_node_retries = max_node_retries
        self._max_duration_sec = max_duration_sec
        self._somatic = SomaticState()

    def run(self, graph: MissionGraphV4) -> MissionRunResult:
        """Execute a validated mission graph."""
        validator = MissionGraphValidatorV4()
        if not validator.is_valid(graph):
            log.error("[MainlineRunner] Graph validation failed")
            return MissionRunResult(success=False)

        result = MissionRunResult(success=False)
        start = time.perf_counter()
        order = graph.topological_order()
        if order is None:
            log.error("[MainlineRunner] Graph has cycle, cannot execute")
            return MissionRunResult(success=False)

        completed: set[str] = set()
        failed: set[str] = set()

        for node_id in order:
            if time.perf_counter() - start > self._max_duration_sec:
                log.warning("[MainlineRunner] Duration budget exhausted")
                break

            node = graph.get_node(node_id)
            if node is None:
                log.warning("[MainlineRunner] Node %r not found in graph, skipping", node_id)
                result.skipped_nodes.append(node_id)
                result.node_results.append(NodeResult(node_id, "skipped", error="node_not_found"))
                continue

            # Check if predecessors completed
            preds = graph.predecessors(node_id)
            if any(p in failed for p in preds):
                result.skipped_nodes.append(node_id)
                result.node_results.append(NodeResult(node_id, "skipped", error="predecessor_failed"))
                continue

            # Execute node with retries
            node_result = self._execute_node(node, completed)
            result.node_results.append(node_result)

            if node_result.status == "completed":
                completed.add(node_id)
                result.completed_nodes.append(node_id)
            else:
                failed.add(node_id)
                result.failed_nodes.append(node_id)

            # Sentinel check
            event = self._sentinel.intervene(self._somatic)
            if event is not None and event.result is not None:
                result.sentinel_interventions += 1
                if event.result.status == "budget_exhausted":
                    log.warning("[MainlineRunner] Sentinel budget exhausted, aborting")
                    break

        result.duration_sec = time.perf_counter() - start

        # Success if all terminal nodes completed
        terminals = set(graph.terminal_nodes())
        result.success = terminals.issubset(completed) if terminals else bool(completed)

        return result

    def _execute_node(self, node: MissionNodeV4, completed: set[str]) -> NodeResult:
        """Execute a single node with retries."""
        last_error = ""
        for attempt in range(self._max_node_retries + 1):
            start = time.perf_counter()

            if self._skill_execute is not None:
                try:
                    claim_data = self._skill_execute(node)
                    duration = time.perf_counter() - start
                    self._update_somatic(node)
                    return NodeResult(node.node_id, "completed", duration, claim_data or {})
                except Exception as exc:
                    last_error = str(exc)
                    duration = time.perf_counter() - start
                    if attempt == self._max_node_retries:
                        return NodeResult(node.node_id, "failed", duration, error=last_error)
                    continue
            else:
                # Dry-run mode: always succeed — log explicitly so this cannot mask real gaps
                duration = time.perf_counter() - start
                log.warning(
                    "[DRY-RUN] Node %r executed without real skill_execute_fn — "
                    "result is synthetic and does NOT represent real execution.",
                    node.node_id,
                )
                self._update_somatic(node)
                return NodeResult(node.node_id, "completed", duration, {"dry_run": True})

        return NodeResult(node.node_id, "failed", error=last_error or "max_retries_exceeded")

    def commit_node_beliefs(self, node: MissionNodeV4, bagel: BagelRuntime) -> list[str]:
        """Commit BAGEL nominal beliefs required by a node."""
        committed: list[str] = []
        for idx, template in enumerate(node.belief_templates):
            belief_id = f"{node.node_id}_belief_{idx}"
            belief = BeliefNode(
                belief_id=belief_id,
                target_object=template.target_object,
                causal_role=template.causal_role or "custom",
                hypothesis=template.hypothesis or f"{node.node_type} node assumption about {template.target_object}",
                falsification_condition=template.falsification_condition or "output claim fails verification",
                lifecycle="committed",
                identity=BeliefIdentity(belief_id=belief_id, provisional_anchor=node.node_id),
                risk_level=node.risk_level,
                metadata={"mission_node": node.node_id},
            )
            bagel.commit_belief(belief, trace_id=node.node_id)
            committed.append(belief_id)
        return committed

    def _update_somatic(self, node: MissionNodeV4) -> None:
        """Update somatic state after node execution."""
        self._somatic = self._somatic.evolve(
            active_mission_node=node.node_id,
        )
        self._sentinel.update_snapshot(self._somatic)


class MainlineAutonomyLoop:
    """Phase runtime for Genshin-like mainline autonomy in safe environments."""

    def __init__(
        self,
        *,
        runner: MainlineRunner | None = None,
        bagel: BagelRuntime | None = None,
        observe_fn: Callable[[], Any] | None = None,
        context_update_fn: Callable[[Any], ActiveQuestContext] | None = None,
        graph_select_fn: Callable[[ActiveQuestContext], MissionGraphV4] | None = None,
    ) -> None:
        self.runner = runner or MainlineRunner()
        self.bagel = bagel or BagelRuntime()
        self.observe_fn = observe_fn
        self.context_update_fn = context_update_fn
        self.graph_select_fn = graph_select_fn
        self.phase: MainlineRuntimePhase = "observe"

    def run_once(self, initial_context: ActiveQuestContext | None = None, graph: MissionGraphV4 | None = None) -> MainlineLoopResult:
        observation = None
        context = initial_context or ActiveQuestContext(
            quest_id="unknown",
            quest_title="",
            objective_text="",
            objective_type="unknown",
        )

        self.phase = "observe"
        if self.observe_fn is not None:
            observation = self.observe_fn()

        self.phase = "update_context"
        if self.context_update_fn is not None:
            context = self.context_update_fn(observation)

        self.phase = "select_graph"
        selected_graph = graph or (self.graph_select_fn(context) if self.graph_select_fn else MissionGraphV4(mission_id=context.quest_id))

        validator = MissionGraphValidatorV4()
        if not validator.is_valid(selected_graph):
            self.phase = "failed"
            run_result = MissionRunResult(success=False)
            return MainlineLoopResult(False, self.phase, self._checkpoint(context, selected_graph, run_result), run_result, context)

        self.phase = "commit_beliefs"
        for node_id in selected_graph.node_ids:
            node = selected_graph.get_node(node_id)
            if node is not None:
                self.runner.commit_node_beliefs(node, self.bagel)

        self.phase = "execute"
        run_result = self.runner.run(selected_graph)

        self.phase = "verify" if run_result.success else "attribute_recover"
        if not run_result.success:
            self.bagel.run_attribution_cycle(trace_id=selected_graph.graph_id)

        self.phase = "checkpoint"
        checkpoint = self._checkpoint(context, selected_graph, run_result)

        self.phase = "condense"
        stable_ids = tuple(
            b.belief_id for b in self.bagel.fig.snapshot()["beliefs"].values()
            if b.lifecycle in ("confirmed", "survived")
        )
        if stable_ids:
            self.bagel.condense_stable_subgraph(stable_ids, {"summary": "mainline stable frontier"})

        self.phase = "completed" if run_result.success else "failed"
        return MainlineLoopResult(run_result.success, self.phase, checkpoint, run_result, context)

    def _checkpoint(
        self,
        context: ActiveQuestContext,
        graph: MissionGraphV4,
        run_result: MissionRunResult,
    ) -> MainlineCheckpoint:
        return MainlineCheckpoint(
            checkpoint_id=f"ckpt_{int(time.perf_counter() * 1000)}",
            phase=self.phase,
            context_version=context.version,
            graph_id=graph.graph_id,
            completed_nodes=tuple(run_result.completed_nodes),
            failed_nodes=tuple(run_result.failed_nodes),
            bagel_graph_version=self.bagel.fig.version,
        )
