from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from learning.decision_memory import DecisionMemory, DecisionQuery
from planning.action_affordance import AffordanceDeriver
from planning.hierarchical_planner import HierarchicalPlanner, PlannerConfig, PlanResult
from planning.mission_graph_v3 import MissionGraph, MissionNode
from planning.screen_state_claim import (
    ActionAffordance,
    ScreenStateClaim,
    TaskStateSnapshot,
)
from planning.screen_state_claim_builder import (
    ClassifierOutput,
    OcrOutput,
    ScreenStateClaimBuilder,
    VLMOutput,
)
from runtime.claim_events import ClaimEventPublisher
from runtime.claim_runtime import ObservationClaim, RiskLevel, StateDeltaClaim, ReliabilityStore
from runtime.claim_worker import ClaimGraphCommand, ClaimGraphWorker
from planning.applicability_gate import SkillApplicabilityGate
from planning.skill_capability_catalog import SkillCapabilityCatalog
from planning.goal_stack import GoalStack
from planning.quest_tracker import QuestStateTracker
from agent.exploration_agent import ExplorationAgent
from learning.skill_induction_gate import SkillInductionGate
from recording.semantic_distiller import SemanticSkillDistiller
from learning.evolution_engine import EvolutionEngine
from app_service.skill_manager import RecordedEvent

try:
    from core.state_bus import StateBus
except Exception:  # pragma: no cover
    StateBus = Any  # type: ignore[assignment]


class _NullStateBus:
    """Minimal null-object satisfying the StateBus interface used by EvolutionEngine.

    Used when no real StateBus is provided so that EvolutionEngine can be
    constructed without importing unittest.mock in production code.
    """

    class _NullShutdown:
        def is_set(self) -> bool:
            return False

    shutdown_flag = _NullShutdown()

    def subscribe(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        pass

    def get_slot(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        return None

    def register_slot(self, *args: Any, **kwargs: Any) -> "_NullSlot":  # noqa: ANN401
        return _NullSlot()

    def publish(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        pass


class _NullSlot:
    """Null slot that silently swallows puts."""

    def put(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        pass

    def get(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        return None

log = logging.getLogger(__name__)


class PerceptionProvider(Protocol):
    def capture_frame(self) -> np.ndarray | None: ...
    def analyze_vlm(self, frame: np.ndarray, game_id: str) -> VLMOutput | None: ...
    def classify_screen(self, frame: np.ndarray) -> ClassifierOutput | None: ...
    def ocr_scan(self, frame: np.ndarray) -> list[OcrOutput]: ...


class ActionExecutor(Protocol):
    def execute_semantic(self, action: str, target: str, context: dict[str, Any]) -> bool: ...
    def is_target_focused(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class TaskBrainConfig:
    capsule_id: str
    game_id: str
    max_iterations: int = 100
    action_interval_sec: float = 1.0
    plan_interval_sec: float = 10.0
    state_sample_interval_sec: float = 2.0
    record_strategies: bool = True
    require_confirmation_risk: str = "high"
    require_claim_verification: bool = True
    post_action_resample: bool = True


@dataclass(slots=True)
class TaskBrainResult:
    success: bool
    goal: str
    iterations: int
    actions_taken: int
    mission_progress: tuple[int, int]
    duration_sec: float
    error: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)


class AutonomousTaskBrain:
    """The strategic brain that ties perception, planning, and execution together.

    Loop:
        1. Capture frame → build ScreenStateClaim
        2. Derive available actions (affordances)
        3. Check MissionGraph progress
        4. If no active plan or plan stuck → plan via HierarchicalPlanner
        5. Execute next MissionNode semantic action
        6. Verify result, update MissionGraph
        7. Record strategy to DecisionMemory
    """

    def __init__(
        self,
        perception: PerceptionProvider,
        executor: ActionExecutor,
        config: TaskBrainConfig,
        planner: HierarchicalPlanner | None = None,
        decision_memory: DecisionMemory | None = None,
        state_bus: StateBus | None = None,
        claim_worker: ClaimGraphWorker | None = None,
        skill_catalog: SkillCapabilityCatalog | None = None,
        reliability_store: ReliabilityStore | None = None,
        exploration_agent: ExplorationAgent | None = None,
        skill_induction_gate: SkillInductionGate | None = None,
    ) -> None:
        self._perception = perception
        self._executor = executor
        self._config = config
        self._planner = planner or HierarchicalPlanner()
        self._memory = decision_memory or DecisionMemory()
        self._claim_builder = ScreenStateClaimBuilder()
        self._affordance_deriver = AffordanceDeriver()
        self._current_graph: MissionGraph | None = None
        self._current_claim: ScreenStateClaim | None = None
        self._frame_id = 0
        self._history: list[dict[str, Any]] = []
        self._shutdown = threading.Event()
        self._state_bus = state_bus
        self._claim_worker = claim_worker or ClaimGraphWorker(
            publisher=ClaimEventPublisher(state_bus) if state_bus is not None else None,
            mission_id=f"taskbrain:{config.capsule_id}",
        )
        self._reliability_store = reliability_store or ReliabilityStore()
        self._catalog = skill_catalog or SkillCapabilityCatalog()
        self._applicability_gate = SkillApplicabilityGate(self._catalog, self._reliability_store)
        self._goal_stack = GoalStack()
        self._quest_tracker = QuestStateTracker()
        self._exploration_agent = exploration_agent or ExplorationAgent(
            self._perception,
            risk_level=self._config.require_confirmation_risk,
        )
        _bus_for_engine: Any = self._state_bus if self._state_bus is not None else _NullStateBus()
        self._evolution_engine = EvolutionEngine(_bus_for_engine)
        self._distiller = SemanticSkillDistiller()
        self._skill_induction_gate = skill_induction_gate or SkillInductionGate(
            self._distiller,
            self._evolution_engine,
        )
        # H3: accumulate exploration events across iterations for richer trace induction
        self._exploration_trace: list[RecordedEvent] = []

    def request_stop(self) -> None:
        self._shutdown.set()

    def _interruptible_wait(self, seconds: float) -> None:
        """Wait in 50ms chunks, checking for shutdown interrupts."""
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            if self._shutdown.is_set():
                return
            time.sleep(min(0.05, deadline - time.perf_counter()))

    def run(self, goal: str) -> TaskBrainResult:
        started = time.perf_counter()
        total_actions = 0
        error = None
        last_plan_time = 0.0
        last_state_time = 0.0

        self._goal_stack.clear()
        self._goal_stack.push(goal)

        try:
            for i in range(1, self._config.max_iterations + 1):
                if self._state_bus is not None and self._state_bus.shutdown_flag.is_set():
                    error = "state_bus_shutdown_requested"
                    self._shutdown.set()
                    break

                active_goal = self._goal_stack.peek()
                if not active_goal:
                    return self._build_result(True, goal, i, total_actions, started)
                self._frame_id = i
                if i % 10 == 0 or i == 1:
                    log.info("[TaskBrain] Iteration %d/%d — goal: %s", i, self._config.max_iterations, goal)

                # 1. Capture frame
                frame = self._perception.capture_frame()
                if frame is None:
                    log.warning("[TaskBrain] No frame, waiting")
                    self._interruptible_wait(1.0)
                    continue

                # 2. Build screen state claim (perception fusion)
                now = time.perf_counter()
                if now - last_state_time >= self._config.state_sample_interval_sec:
                    vlm = self._perception.analyze_vlm(frame, self._config.game_id)
                    classifier = self._perception.classify_screen(frame)
                    ocr = self._perception.ocr_scan(frame)
                    self._current_claim = self._claim_builder.build(
                        game_id=self._config.game_id,
                        frame_id=i,
                        vlm=vlm,
                        classifier=classifier,
                        ocr_results=ocr,
                    )
                    # Update QuestState Tracker
                    quest_state = self._quest_tracker.update_state(self._current_claim)
                    if quest_state.objective_text and quest_state.objective_text != active_goal:
                        self._goal_stack.push(quest_state.objective_text)
                        active_goal = quest_state.objective_text

                    self._publish_task_state(())
                    last_state_time = now

                if self._current_claim is None:
                    self._interruptible_wait(0.5)
                    continue

                # 3. Derive affordances
                affordances = self._affordance_deriver.derive(self._current_claim)
                self._publish_task_state(tuple(affordances))

                # 4. Plan if needed
                if self._current_graph is None or self._current_graph.is_complete():
                    if self._current_graph is not None and self._current_graph.is_complete():
                        exec_done, exec_total = self._current_graph.executable_progress()
                        if exec_done == exec_total and not self._current_graph.failed_nodes():
                            self._record_strategy(goal, True, started)
                            return self._build_result(True, goal, i, total_actions, started)

                    now = time.perf_counter()
                    if now - last_plan_time >= self._config.plan_interval_sec:
                        best = self._memory.best_strategy_for(
                            goal, self._config.capsule_id, self._current_claim.screen_state,
                        )
                        plan_result = self._planner.plan(
                            goal=goal,
                            capsule_id=self._config.capsule_id,
                            current_state=self._current_claim,
                            available_actions=[a.semantic_action for a in affordances],
                        )
                        self._current_graph = plan_result.graph
                        last_plan_time = now
                        log.info(
                            "[TaskBrain] Planned: %d nodes, confidence=%.2f, complexity=%s",
                            len(self._current_graph.nodes), plan_result.confidence, plan_result.complexity,
                        )
                        if best:
                            log.info("[TaskBrain] Historical best: confidence=%.2f", best.confidence)

                # 5. Execute next mission node
                node = self._current_graph.next_pending() if self._current_graph else None
                if node is None:
                    if self._current_graph and self._current_graph.failed_nodes():
                        log.warning("[TaskBrain] Mission has failed nodes, re-planning")
                        self._current_graph = None
                        continue
                    self._interruptible_wait(self._config.action_interval_sec)
                    continue

                success = self._execute_node(node, affordances)
                node.attempts += 1
                if success:
                    node.status = "completed"
                    total_actions += 1
                    if self._current_claim:
                        context = {
                            "capsule_id": self._config.capsule_id,
                            "screen_state": self._current_claim.screen_state,
                            "mission_phase": node.semantic_action,
                            "target_class": node.semantic_action,
                        }
                        self._reliability_store.record(node.semantic_action, context, "matched")
                    self._history.append({
                        "iteration": i,
                        "node": node.label,
                        "action": node.semantic_action,
                        "screen_state": self._current_claim.screen_state,
                        "success": True,
                    })
                else:
                    if self._current_claim:
                        context = {
                            "capsule_id": self._config.capsule_id,
                            "screen_state": self._current_claim.screen_state,
                            "mission_phase": node.semantic_action,
                            "target_class": node.semantic_action,
                        }
                        self._reliability_store.record(node.semantic_action, context, "mismatch")
                    if node.attempts >= node.max_attempts:
                        node.status = "failed"
                        log.warning("[TaskBrain] Node %s failed after %d attempts", node.node_id, node.attempts)
                    self._history.append({
                        "iteration": i,
                        "node": node.label,
                        "action": node.semantic_action,
                        "screen_state": self._current_claim.screen_state,
                        "success": False,
                        "attempts": node.attempts,
                    })

                self._interruptible_wait(self._config.action_interval_sec)

        except KeyboardInterrupt:
            error = "interrupted"
            log.info("[TaskBrain] Interrupted by user")
        except Exception as exc:
            error = str(exc)
            log.error("[TaskBrain] Error: %s", exc)

        self._record_strategy(goal, False, started)
        return self._build_result(False, goal, self._config.max_iterations, total_actions, started, error)

    def _execute_node(self, node: MissionNode, affordances: list[ActionAffordance]) -> bool:
        if not self._executor.is_target_focused():
            log.warning("[TaskBrain] Target window not focused")
            return False

        matched = [a for a in affordances if a.semantic_action == node.semantic_action]

        if self._current_claim:
            scores = self._applicability_gate.evaluate_skills(
                node.semantic_action,
                self._current_claim,
                risk_policy=self._config.require_confirmation_risk,
            )
            if scores:
                best_score = scores[0]
                if not best_score.allowed:
                    log.warning(
                        "[TaskBrain] Skill applicability gate blocked %s: %s",
                        node.semantic_action, best_score.reason
                    )
                    return False
            elif not matched and node.semantic_action not in ("observe", "wait", "move", "look"):
                # SLOW PATH: Direct exploratory probe and dynamic induction when no screen affordance matches
                log.info("[TaskBrain] Entering slow exploration for goal: %s", node.semantic_action)
                frame = self._perception.capture_frame()
                if frame is not None:
                    explore_action = self._exploration_agent.explore_next_step(frame, node.semantic_action, self._current_claim)
                    log.info("[TaskBrain] Exploration agent suggests: %s", explore_action.rationale)
                    if explore_action.requires_human_approval:
                        log.warning("[TaskBrain] Human approval required for exploration action")
                        return False
                    success = self._executor.execute_semantic(
                        action=explore_action.action_type,
                        target=explore_action.target,
                        context={"source": "exploration"},
                    )
                    if success:
                        # H3: append to trace buffer — induction runs on the full batch
                        event = RecordedEvent(
                            event_type="mouse_click" if "click" in explore_action.action_type else explore_action.action_type,
                            timestamp=time.time(),
                            active_window_title=self._config.game_id,
                            observation_summary={
                                "screen_state": self._current_claim.screen_state,
                                "frame_id": self._current_claim.frame_id,
                                "source": "exploration_agent",
                            },
                            target_state="TRACKED",
                            payload={
                                "action_type": explore_action.action_type,
                                "anchor_id": explore_action.target if explore_action.action_type == "click_anchor" else "",
                                "params": {},
                            },
                            observation_frame_id=self._current_claim.frame_id,
                        )
                        self._exploration_trace.append(event)
                        # Attempt induction on the accumulated trace (not a single event)
                        induced = self._skill_induction_gate.induce_skill_from_trace(
                            list(self._exploration_trace), node.semantic_action, self._current_claim.screen_state
                        )
                        if induced:
                            self._catalog.register_induced_skill(induced)
                            self._exploration_trace.clear()  # trace promoted → reset buffer
                            log.info("[TaskBrain] Dynamic skill induction successful for: %s", node.semantic_action)
                        if self._config.post_action_resample:
                            self._resample_current_state_after_action()
                        if self._config.require_claim_verification:
                            return self._verify_node_claim(node, [])
                    return success
        if self._requires_human_confirmation(node, matched):
            log.warning("[TaskBrain] Human confirmation required for node %s", node.node_id)
            return False
        target = matched[0].target_label if matched else node.target

        log.info("[TaskBrain] Executing: %s → %s (target: %s)", node.node_id, node.semantic_action, target)
        controller_ok = self._executor.execute_semantic(
            action=node.semantic_action,
            target=target,
            context={"node_id": node.node_id, "label": node.label},
        )
        if not controller_ok:
            return False
        if self._config.post_action_resample:
            self._resample_current_state_after_action()
        if not self._config.require_claim_verification:
            return True
        return self._verify_node_claim(node, matched)

    def _resample_current_state_after_action(self) -> bool:
        frame = self._perception.capture_frame()
        if frame is None:
            return False
        vlm = self._perception.analyze_vlm(frame, self._config.game_id)
        classifier = self._perception.classify_screen(frame)
        ocr = self._perception.ocr_scan(frame)
        if vlm is None and classifier is None and not ocr:
            return False
        self._frame_id += 1
        self._current_claim = self._claim_builder.build(
            game_id=self._config.game_id,
            frame_id=self._frame_id,
            vlm=vlm,
            classifier=classifier,
            ocr_results=ocr,
        )
        self._publish_task_state(())
        return True

    def _requires_human_confirmation(self, node: MissionNode, matched: list[ActionAffordance]) -> bool:
        threshold = _risk_rank(self._config.require_confirmation_risk)
        if _risk_rank(node.risk_level) >= threshold:
            return True
        return any(a.requires_confirmation or _risk_rank(a.risk_level) >= threshold for a in matched)

    def _verify_node_claim(self, node: MissionNode, matched: list[ActionAffordance]) -> bool:
        if self._current_claim is None:
            return False
        strict_terminal = node.node_type == "verify" or bool(node.verifier) or node.risk_level in {"high", "critical"}
        claim = StateDeltaClaim(
            claim_id=f"taskbrain:{node.node_id}:{node.attempts + 1}:{uuid.uuid4().hex[:8]}",
            mission_id=self._current_graph.graph_id if self._current_graph else "taskbrain",
            node_id=node.node_id,
            skill_id=node.semantic_action or node.verifier or node.node_id,
            claim_type="screen_state_transition" if strict_terminal else "semantic_action_executed",
            claimed_delta={
                "semantic_action": node.semantic_action,
                "target": node.target,
                "expected_state": node.expected_state,
                "screen_state": self._current_claim.screen_state,
            },
            risk_level=_risk_literal(node.risk_level),
            status="asserted",
        )
        observations = self._observation_claims_for_node(node, matched, claim.claim_id)
        if not observations:
            log.warning("[TaskBrain] Node %s has no claim evidence", node.node_id)
            return False

        add_result = self._claim_worker.submit(ClaimGraphCommand("add_claim", claim=claim))
        if not add_result.ok:
            log.warning("[TaskBrain] Claim add failed for %s: %s", node.node_id, add_result.error)
            return False
        for observation in observations:
            obs_result = self._claim_worker.submit(ClaimGraphCommand("add_observation", observation=observation))
            if not obs_result.ok:
                log.warning("[TaskBrain] Claim observation failed for %s: %s", node.node_id, obs_result.error)
                return False
        adjudicated = self._claim_worker.submit(ClaimGraphCommand("adjudicate", claim_id=claim.claim_id))
        if not adjudicated.ok or adjudicated.adjudication is None:
            log.warning("[TaskBrain] Claim adjudication failed for %s: %s", node.node_id, adjudicated.error)
            return False
        status = adjudicated.adjudication.status
        self._history.append({
            "node": node.label,
            "claim_id": claim.claim_id,
            "claim_status": status,
            "claim_confidence": adjudicated.adjudication.confidence,
            "claim_reason": adjudicated.adjudication.reason,
        })
        if strict_terminal:
            return status in {"verified", "audited", "locked", "reverified"}
        return status in {"verified", "audited", "locked", "reverified", "tentative"}

    def _observation_claims_for_node(
        self, node: MissionNode, matched: list[ActionAffordance], claim_id: str,
    ) -> list[ObservationClaim]:
        assert self._current_claim is not None
        observations: list[ObservationClaim] = []

        def _obs(source_family: str, quality: float, metadata: dict[str, Any] | None = None) -> ObservationClaim:
            quality = max(0.0, min(1.0, quality))
            return ObservationClaim(
                observation_id=f"obs:{node.node_id}:{source_family}:{uuid.uuid4().hex[:8]}",
                claim_id=claim_id,
                source_family=source_family,
                polarity="support",
                signal_quality=quality,
                frame_id=self._current_claim.frame_id,
                verifier_id=f"taskbrain_{source_family}",
                confidence=quality,
                metadata=metadata or {},
            )

        if self._current_claim.screen_state != "unknown" and self._current_claim.confidence >= 0.5:
            observations.append(_obs(
                "screen_state",
                self._current_claim.confidence,
                {"screen_state": self._current_claim.screen_state},
            ))
        if matched:
            best = max(matched, key=lambda action: action.confidence)
            observations.append(_obs(
                "affordance",
                best.confidence,
                {"action_id": best.action_id, "target": best.target_label},
            ))
        if node.semantic_action == "observe" and self._current_claim.frame_id:
            observations.append(_obs(
                "frame_capture",
                max(0.55, self._current_claim.confidence),
                {"frame_id": self._current_claim.frame_id},
            ))
        return observations

    def _record_strategy(self, goal: str, success: bool, started: float) -> None:
        if not self._config.record_strategies or not self._current_graph:
            return
        try:
            plan = self._current_graph.to_dict()
            steps = [{"label": n["label"], "semantic_action": n["semantic_action"]} for n in plan.get("nodes", {}).values()]
            done, total = self._current_graph.progress()
            exec_done, exec_total = self._current_graph.executable_progress()
            progress_confidence = done / max(total, 1)
            if exec_total:
                progress_confidence = exec_done / exec_total
            self._memory.record(
                goal=goal,
                capsule_id=self._config.capsule_id,
                screen_state=self._current_claim.screen_state if self._current_claim else "unknown",
                plan=steps,
                success=success,
                duration_sec=time.perf_counter() - started,
                confidence=progress_confidence if success else progress_confidence * 0.5,
            )
        except Exception as exc:
            log.warning("[TaskBrain] Failed to record strategy: %s", exc)

    def _build_result(
        self, success: bool, goal: str, iterations: int,
        actions: int, started: float, error: str | None = None,
    ) -> TaskBrainResult:
        progress = self._current_graph.progress() if self._current_graph else (0, 0)
        if self._current_graph:
            progress = self._current_graph.executable_progress()
        return TaskBrainResult(
            success=success,
            goal=goal,
            iterations=iterations,
            actions_taken=actions,
            mission_progress=progress,
            duration_sec=time.perf_counter() - started,
            error=error,
            history=list(self._history),
        )

    def _publish_task_state(self, affordances: tuple[ActionAffordance, ...]) -> None:
        if self._state_bus is None or self._current_claim is None:
            return
        snapshot = TaskStateSnapshot(claim=self._current_claim, available_actions=affordances)
        slot = self._state_bus.register_slot("agent.task_state_snapshot")
        slot.put(snapshot)
        self._state_bus.publish("agent_task_state", snapshot)


def _risk_rank(risk: str) -> int:
    return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(risk.lower(), 1)


def _risk_literal(risk: str) -> RiskLevel:
    normalized = risk.lower()
    if normalized in {"low", "medium", "high", "critical"}:
        return normalized  # type: ignore[return-value]
    return "medium"
