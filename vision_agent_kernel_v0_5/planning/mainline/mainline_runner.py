"""Mainline Runner — continuous mission execution loop.

Orchestrates:
1. MissionGraphV4 execution (claim-gated nodes)
2. Sentinel monitoring (somatic state + recovery)
3. Quest state tracking (ActiveQuestContext updates)
4. BAGEL belief attribution (failure recovery)
5. Skill selection via registry (applicability matching)

Phase 8 closure: every node must satisfy:
  input claim verified → execute → post-action resample → output claim verified → checkpoint
  Failure enters BAGEL attribution + recovery, never silent dry-run success.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol

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


# ---------------------------------------------------------------------------
# RuntimeSnapshot — reads StateBus mid-freq slots for node context
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    """Snapshot of StateBus slots at decision time."""
    screen_state: str = "unknown"
    screen_claim_confidence: float = 0.0
    combat_active: bool = False
    navigation_active: bool = False
    frame_quality_score: float = 0.0
    observation_frame_id: int = 0
    snapshot_version: int = 0


class SnapshotProvider(Protocol):
    """Reads StateBus and produces a RuntimeSnapshot."""
    def snapshot(self) -> RuntimeSnapshot: ...


class StateBusSnapshotProvider:
    """Production SnapshotProvider that reads from a real StateBus."""

    __slots__ = ("_bus",)

    def __init__(self, state_bus: Any) -> None:
        self._bus = state_bus

    def snapshot(self) -> RuntimeSnapshot:
        screen_claim = self._bus.screen_claim.get()
        combat_signal = self._bus.combat_signal.get()
        navigation_signal = self._bus.navigation_signal.get()
        frame_quality = self._bus.frame_quality.get()
        obs = self._bus.latest_observation.get()

        screen_state = "unknown"
        screen_conf = 0.0
        if screen_claim is not None:
            screen_state = screen_claim.screen_state if isinstance(screen_claim.screen_state, str) else getattr(screen_claim.screen_state, "value", "unknown")
            screen_conf = screen_claim.confidence

        return RuntimeSnapshot(
            screen_state=screen_state,
            screen_claim_confidence=screen_conf,
            combat_active=combat_signal is not None and getattr(combat_signal, "enemy_visible", False),
            navigation_active=navigation_signal is not None and getattr(navigation_signal, "on_screen", False),
            frame_quality_score=getattr(frame_quality, "quality_score", 0.0) if frame_quality else 0.0,
            observation_frame_id=getattr(obs, "frame_id", 0) if obs else 0,
            snapshot_version=self._bus.screen_claim.version,
        )


# ---------------------------------------------------------------------------
# ClaimVerifier — validates input/output claims for a node
# ---------------------------------------------------------------------------


class ClaimVerifier(Protocol):
    """Verify that claims are satisfied for a node."""
    def verify_input_claims(self, node: MissionNodeV4, snapshot: RuntimeSnapshot) -> tuple[bool, str]: ...
    def verify_output_claims(self, node: MissionNodeV4, claim_data: dict[str, Any], snapshot: RuntimeSnapshot) -> tuple[bool, str]: ...


class DefaultClaimVerifier:
    """Default claim verifier: checks screen_state from RuntimeSnapshot against node input_claims."""

    def verify_input_claims(self, node: MissionNodeV4, snapshot: RuntimeSnapshot) -> tuple[bool, str]:
        if not node.input_claims:
            return True, ""
        for claim_contract in node.input_claims:
            expected_state = claim_contract.claim_type if hasattr(claim_contract, "claim_type") else str(claim_contract)
            if expected_state and expected_state != "any" and snapshot.screen_state != expected_state:
                return False, f"screen_state={snapshot.screen_state} != expected={expected_state}"
        return True, ""

    def verify_output_claims(self, node: MissionNodeV4, claim_data: dict[str, Any], snapshot: RuntimeSnapshot) -> tuple[bool, str]:
        if not node.output_claims:
            return True, ""
        if not claim_data and node.output_claims:
            return False, "no claim_data produced but output_claims required"
        if claim_data.get("dry_run"):
            return False, "dry_run does not satisfy output claims"
        if claim_data.get("execution_success") is False:
            return False, "semantic execution reported failure"
        if claim_data.get("execution_success") is True and claim_data.get("claim_id"):
            return True, ""
        required = {claim.claim_type for claim in node.output_claims if claim.claim_type}
        if not required:
            return True, ""
        explicit = set()
        for key in ("satisfied_claim_types", "verified_claims", "output_claims"):
            values = claim_data.get(key)
            if isinstance(values, (list, tuple, set)):
                explicit.update(str(value) for value in values)
        explicit.update(key for key, value in claim_data.items() if value and key in required)
        missing = sorted(required - explicit)
        if missing:
            return False, f"missing output claim evidence: {missing}"
        return True, ""


# ---------------------------------------------------------------------------
# CheckpointPublisher — writes checkpoint to StateBus + disk
# ---------------------------------------------------------------------------


class CheckpointPublisher(Protocol):
    """Publish checkpoint to StateBus and optionally to disk."""
    def publish(self, checkpoint: MainlineCheckpoint) -> None: ...


class MainlineCheckpointPublisher:
    """Publishes MainlineCheckpoint to StateBus.checkpoint_state and disk.

    Disk persistence is mandatory. If no disk_store is provided, falls back
    to a JSONL file in the current working directory.
    """

    __slots__ = ("_bus", "_disk_store", "_fallback_path")

    def __init__(self, state_bus: Any, disk_store: Any = None) -> None:
        self._bus = state_bus
        self._disk_store = disk_store
        self._fallback_path: Any = None
        if disk_store is None:
            try:
                import pathlib
                self._fallback_path = pathlib.Path("checkpoints")
                self._fallback_path.mkdir(exist_ok=True)
            except Exception:
                self._fallback_path = None

    def publish(self, checkpoint: MainlineCheckpoint) -> None:
        self._bus.checkpoint_state.put(checkpoint)
        # Primary disk store
        if self._disk_store is not None:
            try:
                task_state = {
                    "phase": checkpoint.phase,
                    "graph_id": checkpoint.graph_id,
                    "completed_nodes": list(checkpoint.completed_nodes),
                    "failed_nodes": list(checkpoint.failed_nodes),
                    "skipped_nodes": list(checkpoint.skipped_nodes),
                    "bagel_graph_version": checkpoint.bagel_graph_version,
                }
                cp = self._disk_store.create_checkpoint(
                    session_id=checkpoint.checkpoint_id,
                    triggered_by="mainline_node_complete",
                    task_state=task_state,
                )
                self._disk_store.save(cp)
            except Exception as exc:
                log.warning("[CheckpointPublisher] disk save failed: %s", exc)
                self._write_fallback(checkpoint)
        else:
            self._write_fallback(checkpoint)

    def _write_fallback(self, checkpoint: MainlineCheckpoint) -> None:
        """Write checkpoint to JSONL file as fallback."""
        if self._fallback_path is None:
            return
        try:
            import json
            data = {
                "checkpoint_id": checkpoint.checkpoint_id,
                "phase": checkpoint.phase,
                "graph_id": checkpoint.graph_id,
                "completed_nodes": list(checkpoint.completed_nodes),
                "failed_nodes": list(checkpoint.failed_nodes),
                "skipped_nodes": list(checkpoint.skipped_nodes),
            }
            path = self._fallback_path / f"{checkpoint.checkpoint_id}.jsonl"
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data) + "\n")
        except Exception as exc:
            log.warning("[CheckpointPublisher] fallback write failed: %s", exc)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


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
    skipped_nodes: tuple[str, ...] = ()
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
    8. Publish checkpoint to StateBus + disk
    """

    def __init__(
        self,
        sentinel: SentinelRuntime | None = None,
        claim_check_fn: Any = None,
        skill_execute_fn: Any = None,
        max_node_retries: int = 2,
        max_duration_sec: float = 600.0,
        snapshot_provider: SnapshotProvider | None = None,
        claim_verifier: ClaimVerifier | None = None,
        checkpoint_publisher: CheckpointPublisher | None = None,
        type_handlers: dict[str, Any] | None = None,
        state_bus: Any = None,
    ) -> None:
        self._sentinel = sentinel or SentinelRuntime()
        self._claim_check = claim_check_fn
        self._skill_execute = skill_execute_fn
        self._max_node_retries = max_node_retries
        self._max_duration_sec = max_duration_sec
        self._somatic = SomaticState()
        self._snapshot_provider = snapshot_provider
        self._claim_verifier = claim_verifier or DefaultClaimVerifier()
        self._checkpoint_publisher = checkpoint_publisher
        self._graph: MissionGraphV4 | None = None
        # Node type handlers: node_type prefix → callable(node) -> claim_data
        self._type_handlers: dict[str, Any] = type_handlers or {}
        # StateBus integration for Orchestrator coordination
        self._state_bus = state_bus

    def _take_snapshot(self) -> RuntimeSnapshot:
        if self._snapshot_provider is not None:
            return self._snapshot_provider.snapshot()
        return RuntimeSnapshot()

    def register_type_handler(self, node_type_prefix: str, handler: Any) -> None:
        """Register a handler for nodes whose node_type starts with prefix.

        Handler signature: handler(node: MissionNodeV4) -> dict[str, Any]
        Matching uses longest-prefix: "combat_boss" beats "combat" beats "".
        """
        self._type_handlers[node_type_prefix] = handler

    def _resolve_type_handler(self, node: MissionNodeV4) -> Any | None:
        """Find the best-matching type handler for a node.

        Uses longest-prefix match on node.node_type.
        """
        if not self._type_handlers:
            return None
        best_prefix = ""
        best_handler = None
        for prefix, handler in self._type_handlers.items():
            if node.node_type.startswith(prefix) and len(prefix) > len(best_prefix):
                best_prefix = prefix
                best_handler = handler
        return best_handler

    def _should_pause_for_orchestrator(self) -> bool:
        """Check if Orchestrator has issued a pause/emergency interrupt."""
        if self._state_bus is None:
            return False
        try:
            interrupt = self._state_bus.next_interrupt(timeout_sec=0.0)
            if interrupt is not None:
                priority = getattr(interrupt, "priority", 100)
                # P0-P2 (emergency/watchdog/override) forces pause
                if priority <= 20:
                    log.warning(
                        "[MainlineRunner] pausing for Orchestrator interrupt: %s",
                        getattr(interrupt, "code", "unknown"),
                    )
                    return True
        except Exception:
            pass
        return False

    def run(self, graph: MissionGraphV4) -> MissionRunResult:
        """Execute a validated mission graph."""
        self._graph = graph
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
        skipped: set[str] = set()

        execution_queue = list(order)
        idx = 0
        while idx < len(execution_queue):
            if time.perf_counter() - start > self._max_duration_sec:
                log.warning("[MainlineRunner] Duration budget exhausted")
                break

            # Check Orchestrator coordination interrupts
            if self._should_pause_for_orchestrator():
                result.success = False
                break

            node_id = execution_queue[idx]
            node = graph.get_node(node_id)
            if node is None:
                log.warning("[MainlineRunner] Node %r not found in graph, skipping", node_id)
                skipped.add(node_id)
                result.skipped_nodes.append(node_id)
                result.node_results.append(NodeResult(node_id, "skipped", error="node_not_found"))
                self._publish_checkpoint("checkpoint", graph, completed, failed, skipped)
                idx += 1
                continue

            # Check if predecessors completed
            preds = graph.predecessors(node_id)
            if any(p in failed for p in preds):
                skipped.add(node_id)
                result.skipped_nodes.append(node_id)
                result.node_results.append(NodeResult(node_id, "skipped", error="predecessor_failed"))
                self._publish_checkpoint("checkpoint", graph, completed, failed, skipped)
                idx += 1
                continue

            # Execute node with retries
            node_result = self._execute_node(node, completed)
            result.node_results.append(node_result)

            if node_result.status == "completed":
                completed.add(node_id)
                result.completed_nodes.append(node_id)
                self._publish_checkpoint("checkpoint", graph, completed, failed, skipped)
            else:
                from planning.mainline.bagel_jit_router import BagelJitRouter
                router = BagelJitRouter(graph)
                mutated = router.handle_belief_falsification(
                    falsified_belief_id=f"{node_id}_belief_0",
                    failed_node_id=node_id,
                )
                if mutated:
                    log.info("[MainlineRunner] Graph healed by JIT router. Recalculating topological order.")
                    new_order = graph.topological_order()
                    if new_order:
                        execution_queue = [nid for nid in new_order if nid not in completed]
                        idx = 0
                        continue

                failed.add(node_id)
                result.failed_nodes.append(node_id)
                self._publish_checkpoint("attribute_recover", graph, completed, failed, skipped)

            # Sentinel check
            event = self._sentinel.intervene(self._somatic)
            if event is not None and event.result is not None:
                result.sentinel_interventions += 1
                if event.result.status == "budget_exhausted":
                    log.warning("[MainlineRunner] Sentinel budget exhausted, aborting")
                    break
            idx += 1

        result.duration_sec = time.perf_counter() - start

        # Success if all terminal nodes completed
        terminals = set(graph.terminal_nodes())
        result.success = terminals.issubset(completed) if terminals else bool(completed)

        return result

    def _execute_node(self, node: MissionNodeV4, completed: set[str]) -> NodeResult:
        """Execute a single node: precheck → execute → post_verify → checkpoint."""
        # --- PRE-CHECK: verify input claims ---
        pre_snapshot = self._take_snapshot()
        input_ok, input_reason = self._verify_input_claims(node, pre_snapshot)
        if not input_ok:
            log.warning("[MainlineRunner] Node %r input claims not satisfied: %s", node.node_id, input_reason)
            return NodeResult(node.node_id, "blocked", error=f"input_claim_failed: {input_reason}")

        # --- EXECUTE with retries ---
        last_error = ""
        claim_data: dict[str, Any] = {}
        max_retries = min(self._max_node_retries, node.budgets.max_retries)
        node_started = time.perf_counter()
        for attempt in range(max_retries + 1):
            start = time.perf_counter()
            if start - node_started > node.budgets.max_duration_sec:
                return NodeResult(
                    node.node_id,
                    "failed",
                    start - node_started,
                    error="node_duration_budget_exhausted",
                )

            if self._skill_execute is not None:
                try:
                    # Type-aware routing: use type handler if registered
                    type_handler = self._resolve_type_handler(node)
                    if type_handler is not None:
                        claim_data = type_handler(node)
                        log.info(
                            "[MainlineRunner] Node %r routed via type_handler for %r",
                            node.node_id, node.node_type,
                        )
                    else:
                        claim_data = self._skill_execute(node)
                    duration = time.perf_counter() - start
                    self._update_somatic(node)
                except Exception as exc:
                    last_error = str(exc)
                    duration = time.perf_counter() - start
                    if attempt == max_retries:
                        return NodeResult(node.node_id, "failed", duration, error=last_error)
                    continue
            else:
                # Dry-run mode: BLOCKED — must not silently succeed
                duration = time.perf_counter() - start
                log.warning(
                    "[MainlineRunner] Node %r has no skill_execute_fn — "
                    "marking blocked (not completed). Phase 8 closure forbids silent success.",
                    node.node_id,
                )
                return NodeResult(node.node_id, "blocked", duration, {"dry_run": True}, "no_skill_execute_fn")

            # --- POST-VERIFY: verify output claims ---
            post_snapshot = self._take_snapshot()
            output_ok, output_reason = self._verify_output_claims(node, claim_data, post_snapshot)
            if output_ok:
                return NodeResult(node.node_id, "completed", duration, claim_data or {})
            else:
                log.warning(
                    "[MainlineRunner] Node %r output claims not satisfied (attempt %d): %s",
                    node.node_id, attempt, output_reason,
                )
                if attempt == max_retries:
                    return NodeResult(node.node_id, "failed", duration, claim_data, f"output_claim_failed: {output_reason}")
                last_error = f"output_claim_failed: {output_reason}"
                continue

        return NodeResult(node.node_id, "failed", error=last_error or "max_retries_exceeded")

    def _verify_input_claims(
        self,
        node: MissionNodeV4,
        snapshot: RuntimeSnapshot,
    ) -> tuple[bool, str]:
        ok, reason = self._claim_verifier.verify_input_claims(node, snapshot)
        if not ok:
            return ok, reason
        if self._claim_check is None:
            return True, ""
        for claim in node.input_claims:
            claim_ok, claim_reason = self._call_legacy_claim_check(node, claim, snapshot)
            if not claim_ok:
                return False, claim_reason or f"legacy claim_check_fn rejected {claim.claim_type}"
        return True, ""

    def _verify_output_claims(
        self,
        node: MissionNodeV4,
        claim_data: dict[str, Any],
        snapshot: RuntimeSnapshot,
    ) -> tuple[bool, str]:
        ok, reason = self._claim_verifier.verify_output_claims(node, claim_data, snapshot)
        if not ok:
            return ok, reason
        # Also run legacy claim_check_fn on output claims
        if self._claim_check is not None:
            for claim in node.output_claims:
                claim_ok, claim_reason = self._call_legacy_claim_check(node, claim, snapshot)
                if not claim_ok:
                    return False, claim_reason or f"legacy claim_check_fn rejected output {claim.claim_type}"
        return True, ""

    def _call_legacy_claim_check(
        self,
        node: MissionNodeV4,
        claim: Any,
        snapshot: RuntimeSnapshot,
    ) -> tuple[bool, str]:
        """Call legacy claim_check_fn with tolerant arity handling."""
        assert self._claim_check is not None
        attempts = (
            (node, claim, snapshot),
            (claim, snapshot),
            (claim,),
        )
        last_error = ""
        for args in attempts:
            try:
                return self._normalize_claim_check_result(self._claim_check(*args))
            except TypeError as exc:
                last_error = str(exc)
                continue
            except Exception as exc:
                return False, str(exc)
        return False, f"claim_check_fn invocation failed: {last_error}"

    @staticmethod
    def _normalize_claim_check_result(result: Any) -> tuple[bool, str]:
        if isinstance(result, tuple):
            if not result:
                return False, "empty claim_check result"
            ok = bool(result[0])
            reason = str(result[1]) if len(result) > 1 and result[1] else ""
            return ok, reason
        return bool(result), "" if result else "claim_check_fn returned false"

    def _publish_checkpoint(
        self,
        phase: str,
        graph: MissionGraphV4,
        completed: set[str],
        failed: set[str],
        skipped: set[str] | None = None,
    ) -> None:
        if self._checkpoint_publisher is None:
            return
        cp = MainlineCheckpoint(
            checkpoint_id=f"ckpt_{time.time_ns()}",
            phase=phase,
            context_version=0,
            graph_id=graph.graph_id,
            completed_nodes=tuple(sorted(completed)),
            failed_nodes=tuple(sorted(failed)),
            skipped_nodes=tuple(sorted(skipped or ())),
        )
        self._checkpoint_publisher.publish(cp)

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
