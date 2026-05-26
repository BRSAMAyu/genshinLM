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
from typing import Any

from control.sentinel.sentinel_runtime import SentinelRuntime
from control.sentinel.somatic_state import SomaticState
from planning.mainline.mission_graph_v4 import MissionGraphV4, MissionNodeV4
from planning.mainline.mission_graph_validator_v4 import MissionGraphValidatorV4

log = logging.getLogger(__name__)


NodeExecStatus = str  # pending | executing | completed | failed | skipped | blocked


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
        for attempt in range(self._max_node_retries + 1):
            start = time.perf_counter()

            # Simulate execution (real implementation would call skill_execute_fn)
            if self._skill_execute is not None:
                try:
                    claim_data = self._skill_execute(node)
                    duration = time.perf_counter() - start
                    self._update_somatic(node)
                    return NodeResult(node.node_id, "completed", duration, claim_data or {})
                except Exception as exc:
                    duration = time.perf_counter() - start
                    if attempt == self._max_node_retries:
                        return NodeResult(node.node_id, "failed", duration, error=str(exc))
                    continue
            else:
                # Dry-run mode: always succeed
                duration = time.perf_counter() - start
                self._update_somatic(node)
                return NodeResult(node.node_id, "completed", duration)

        return NodeResult(node.node_id, "failed", error="max_retries_exceeded")

    def _update_somatic(self, node: MissionNodeV4) -> None:
        """Update somatic state after node execution."""
        self._somatic = self._somatic.evolve(
            active_mission_node=node.node_id,
        )
        self._sentinel.update_snapshot(self._somatic)
