from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict
from dataclasses import dataclass
from typing import Any, Protocol

from bagel.fig_schema import ActionNode, BeliefIdentity, BeliefNode, FeedbackNode
from bagel.runtime import BagelRuntime
from planning.mainline.mission_graph_v4 import MissionNodeV4
from planning.recovery_orchestrator import (
    RecoveryCategory,
    RecoveryEvent,
    RecoveryOrchestrator,
    RecoverySeverity,
)
from runtime.claim_runtime import ClaimProducingExecutor
from runtime.claim_runtime import ObservationClaim, StateDeltaClaim
from runtime.claim_worker import ClaimGraphCommand, ClaimGraphWorker

log = logging.getLogger(__name__)


class SemanticActionExecutor(Protocol):
    def execute_semantic(self, action: str, target: str, context: dict[str, Any]) -> bool: ...

    def is_target_focused(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class MainlineSkillExecution:
    node_id: str
    action_id: str
    claim_id: str
    semantic_action: str
    target: str
    execution_success: bool
    attribution_triggered: bool = False

    def to_claim_data(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "action_id": self.action_id,
            "claim_id": self.claim_id,
            "semantic_action": self.semantic_action,
            "target": self.target,
            "execution_success": self.execution_success,
            "attribution_triggered": self.attribution_triggered,
        }


class MainlineSkillExecutor:
    """Execute MissionNodeV4 through a semantic executor and report feedback.

    The runner previously accepted a raw ``skill_execute_fn`` but did not offer
    a first-class bridge into the semantic executor, ClaimGraph, and BAGEL.
    This class provides that bridge for dry-run, QA, and authorized sandbox
    runtimes.
    """

    def __init__(
        self,
        action_executor: SemanticActionExecutor,
        *,
        claim_worker: ClaimGraphWorker | None = None,
        bagel_runtime: BagelRuntime | None = None,
        claim_runtime: ClaimProducingExecutor | None = None,
        recovery_orchestrator: RecoveryOrchestrator | None = None,
        enable_bagel_attribution: bool = False,
        mission_id: str = "mainline",
        raise_on_failure: bool = True,
    ) -> None:
        self._executor = action_executor
        self._claim_worker = claim_worker or ClaimGraphWorker(mission_id=mission_id)
        self._bagel_enabled = bool(bagel_runtime is not None or enable_bagel_attribution)
        self._bagel = bagel_runtime if bagel_runtime is not None else (BagelRuntime() if self._bagel_enabled else None)
        self._claim_runtime = claim_runtime or ClaimProducingExecutor()
        self._recovery = recovery_orchestrator or RecoveryOrchestrator(executor=action_executor)
        self._mission_id = mission_id
        self._raise_on_failure = raise_on_failure

    def execute_node_skill(self, node: MissionNodeV4) -> dict[str, Any]:
        semantic_action = self._semantic_action_for(node)
        target = self._target_for(node)
        risk_level = self._risk_level(node.risk_level)
        claim_context = {
            "node_type": node.node_type,
            "target": target or "unknown",
            "semantic_action": semantic_action,
            "risk_level": risk_level,
        }
        gate_decision, uncertainty_decision = self._claim_runtime.pre_flight(
            skill_id=semantic_action,
            context=claim_context,
            risk_level=risk_level,
            node_id=node.node_id,
        )
        context = {
            "node_id": node.node_id,
            "node_type": node.node_type,
            "risk_level": node.risk_level,
            "skill_candidates": list(node.skill_candidates),
            "metadata": dict(node.metadata),
            "semantic_action": semantic_action,
        }

        log.info(
            "[MainlineSkillExecutor] executing node=%s action=%s target=%s",
            node.node_id,
            semantic_action,
            target,
        )
        belief_ids = self._commit_missing_beliefs(node)
        action_id = f"act_{node.node_id}_{uuid.uuid4().hex[:8]}"
        claim_id = f"claim_{node.node_id}_{uuid.uuid4().hex[:8]}"
        if self._bagel is not None:
            action = ActionNode(
                action_id=action_id,
                belief_ids=tuple(belief_ids),
                action_type=semantic_action,
                params={"target": target, "node_type": node.node_type},
                status="proposed",
                risk_level=node.risk_level,
                metadata={"node_id": node.node_id},
            )
            self._bagel.propose_action(action, trace_id=node.node_id)

        focused = True
        try:
            focused = self._executor.is_target_focused()
        except Exception:
            focused = False

        started = time.perf_counter()
        success = False
        error = ""
        if gate_decision.requires_human_confirm:
            error = f"claim_gate_blocked:{gate_decision.reason}"
        elif focused:
            try:
                success = bool(self._executor.execute_semantic(semantic_action, target, context))
            except Exception as exc:
                error = f"{exc.__class__.__name__}: {exc}"
        else:
            error = "target_not_focused"

        if not success and not error:
            error = "semantic_execution_failed"

        if (not success and uncertainty_decision.action in {"local_recovery", "resample_observation", "alternate_verifier", "safe_probe"}):
            recovery_result = self._recovery.recover(self._build_recovery_event(node, error))
            if recovery_result.success:
                try:
                    success = bool(self._executor.execute_semantic(semantic_action, target, context))
                    if success:
                        error = ""
                except Exception as exc:
                    error = f"{exc.__class__.__name__}: {exc}"

        duration_sec = time.perf_counter() - started

        fingerprint = (
            f"node={node.node_id};action={semantic_action};target={target};"
            f"success={success};duration={duration_sec:.6f}"
        )
        if self._bagel is not None:
            self._bagel.materialize_action(action_id, fingerprint=fingerprint, claim_id=claim_id)
            self._bagel.receive_feedback(
                FeedbackNode(
                    feedback_id=f"fb_{action_id}",
                    action_id=action_id,
                    polarity="positive" if success else "negative",
                    signal_quality=1.0 if success else 0.8,
                    claim_refs=(claim_id,),
                    description="semantic execution succeeded" if success else (error or "semantic execution failed"),
                    metadata={"node_id": node.node_id, "duration_sec": duration_sec},
                )
            )
        self._record_claim(node, claim_id, semantic_action, target, success, action_id, duration_sec, error)
        claim_execution = self._claim_runtime.produce_claim(
            claim_id=f"cc_{claim_id}",
            mission_id=self._mission_id,
            node_id=node.node_id,
            skill_id=semantic_action,
            claim_type=node.output_claims[0].claim_type if node.output_claims else "semantic_action_executed",
            claimed_delta={
                "goal": node.node_type,
                "semantic_action": semantic_action,
                "target": target,
                "success": success,
            },
            risk_level=risk_level,
            context=claim_context,
        )
        self._claim_runtime.verify_claim(
            claim_execution.claim.claim_id,
            ok=success,
            actual_delta={"success": success, "error": error},
            context=claim_context,
        )
        decision_memory = self._claim_runtime.summarize_for_llm(node.node_type)

        attribution_triggered = False
        if not success and self._bagel is not None:
            attribution_triggered = True
            self._bagel.run_attribution_cycle(trace_id=node.node_id)

        execution = MainlineSkillExecution(
            node_id=node.node_id,
            action_id=action_id,
            claim_id=claim_id,
            semantic_action=semantic_action,
            target=target,
            execution_success=success,
            attribution_triggered=attribution_triggered,
        )
        if not success and self._raise_on_failure:
            raise RuntimeError(error or f"semantic action failed: {semantic_action}")
        return {
            **execution.to_claim_data(),
            "claim_runtime_gate_allowed": gate_decision.allowed,
            "claim_runtime_gate_reason": gate_decision.reason,
            "claim_runtime_uncertainty_action": uncertainty_decision.action,
            "claim_runtime_uncertainty_reason": uncertainty_decision.reason,
            "claim_runtime_decision_memory": asdict(decision_memory),
        }

    def _commit_missing_beliefs(self, node: MissionNodeV4) -> list[str]:
        if self._bagel is None:
            return []
        belief_ids: list[str] = []
        if node.belief_templates:
            for idx, template in enumerate(node.belief_templates):
                belief_id = f"{node.node_id}_belief_{idx}"
                belief = BeliefNode(
                    belief_id=belief_id,
                    target_object=template.target_object,
                    causal_role=template.causal_role or "custom",
                    hypothesis=template.hypothesis or f"{node.node_type} precondition for {template.target_object}",
                    falsification_condition=template.falsification_condition or "node output claim fails",
                    lifecycle="committed",
                    identity=BeliefIdentity(belief_id=belief_id, provisional_anchor=node.node_id),
                    risk_level=node.risk_level,
                    metadata={"mission_node": node.node_id},
                )
                self._bagel.commit_belief(belief, trace_id=node.node_id)
                belief_ids.append(belief_id)
            return belief_ids

        belief_id = f"{node.node_id}_belief_implicit"
        belief = BeliefNode(
            belief_id=belief_id,
            target_object=node.node_type,
            causal_role="custom",
            hypothesis=f"semantic action {self._semantic_action_for(node)!r} can advance node {node.node_id!r}",
            falsification_condition="semantic executor returns false or output claim is not verified",
            lifecycle="committed",
            identity=BeliefIdentity(belief_id=belief_id, provisional_anchor=node.node_id),
            risk_level=node.risk_level,
            metadata={"mission_node": node.node_id, "implicit": True},
        )
        self._bagel.commit_belief(belief, trace_id=node.node_id)
        return [belief_id]

    @staticmethod
    def _risk_level(value: str | None) -> str:
        if value in {"low", "medium", "high", "critical"}:
            return value
        return "medium"

    @staticmethod
    def _build_recovery_event(node: MissionNodeV4, error: str) -> RecoveryEvent:
        node_type = (node.node_type or "").lower()
        if "combat" in node_type:
            category = RecoveryCategory.COMBAT
        elif "nav" in node_type or "move" in node_type or "teleport" in node_type:
            category = RecoveryCategory.NAVIGATION
        elif "dialog" in node_type or "ui" in node_type or "menu" in node_type:
            category = RecoveryCategory.UI
        elif "quest" in node_type or "talk" in node_type:
            category = RecoveryCategory.QUEST
        else:
            category = RecoveryCategory.SYSTEM
        severity = RecoverySeverity.MODERATE if node.risk_level in {"high", "critical"} else RecoverySeverity.MINOR
        return RecoveryEvent(
            category=category,
            severity=severity,
            description=error or "semantic_execution_failed",
            context={"failure_type": "stuck"},
            source=f"mainline_skill_executor:{node.node_id}",
        )

    def _record_claim(
        self,
        node: MissionNodeV4,
        claim_id: str,
        semantic_action: str,
        target: str,
        success: bool,
        action_id: str,
        duration_sec: float,
        error: str,
    ) -> None:
        claim_type = node.output_claims[0].claim_type if node.output_claims else "semantic_action_executed"
        claim = StateDeltaClaim(
            claim_id=claim_id,
            mission_id=self._mission_id,
            node_id=node.node_id,
            skill_id=semantic_action,
            claim_type=claim_type,
            claimed_delta={
                "node_type": node.node_type,
                "semantic_action": semantic_action,
                "target": target,
                "success": success,
            },
            status="asserted",
            risk_level=node.risk_level,
            confidence=1.0 if success else 0.2,
            metadata={
                "action_id": action_id,
                "duration_sec": duration_sec,
                "error": error,
            },
        )
        self._claim_worker.submit(ClaimGraphCommand("add_claim", claim=claim))
        self._claim_worker.submit(
            ClaimGraphCommand(
                "add_observation",
                observation=ObservationClaim(
                    observation_id=f"obs_{claim_id}",
                    claim_id=claim_id,
                    source_family="semantic_executor",
                    polarity="support" if success else "refute",
                    signal_quality=1.0 if success else 0.8,
                    verifier_id="mainline_skill_executor",
                    confidence=1.0 if success else 0.8,
                    metadata={"action_id": action_id, "error": error},
                ),
            )
        )
        self._claim_worker.submit(ClaimGraphCommand("adjudicate", claim_id=claim_id))

    @staticmethod
    def _semantic_action_for(node: MissionNodeV4) -> str:
        value = node.metadata.get("semantic_action")
        if value:
            return str(value)
        if node.skill_candidates:
            return node.skill_candidates[0]
        return node.node_type

    @staticmethod
    def _target_for(node: MissionNodeV4) -> str:
        value = node.metadata.get("target")
        if value:
            return str(value)
        for claim in node.output_claims:
            if claim.target:
                return claim.target
        for claim in node.input_claims:
            if claim.target:
                return claim.target
        return ""
