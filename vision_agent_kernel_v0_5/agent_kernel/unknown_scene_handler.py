"""UnknownSceneHandler — SPARKLE §11 unknown scene & puzzle handling.

Implements the safe exploration closed loop:
1. Observe  — generate SceneGraph with interactable elements
2. Hypothesize — model proposes 1-3 verifiable hypotheses
3. Probe   — select lowest-risk action to test
4. Verify  — observe state change
5. Attribute — attribute whether action was effective
6. Learn   — write temporary skill patch or decision memory
7. Escalate — request user help when uncertain or high-risk
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

from agent_kernel.types import (
    Affordance,
    RuntimeOverride,
    SceneGraph,
    SceneObject,
)
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExplorationHypothesis:
    """A verifiable hypothesis about an unknown scene."""
    hypothesis_id: str
    description: str
    test_action: str
    expected_state_change: str
    risk_level: str = "low"  # low, medium, high
    confidence: float = 0.5


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Result of probing an unknown scene."""
    probe_id: str
    hypothesis_id: str
    action_taken: str
    state_before: str
    state_after: str
    effective: bool
    learned_override: RuntimeOverride | None = None


@dataclass(slots=True)
class UnknownSceneHandler:
    """Handles unknown scenes using the SPARKLE §11 safe exploration loop.

    Usage:
        handler = UnknownSceneHandler()
        hypotheses = handler.observe_and_hypothesize(scene_graph)
        if handler.should_escalate(hypotheses):
            handler.request_user_help(scene_graph)
        else:
            result = handler.probe(scene_graph, hypotheses[0])
    """

    max_probe_attempts: int = 3
    confidence_threshold: float = 0.6
    risk_escalation_threshold: str = "high"
    _probe_history: list[ProbeResult] = field(default_factory=list)
    _scene_memory: dict[str, str] = field(default_factory=dict)
    _meta_learning_bridge: Any = field(default=None, repr=False)

    def set_meta_learning_bridge(self, bridge: Any) -> None:
        """Set the MetaLearningBridge for feeding exploration results into the learning loop."""
        self._meta_learning_bridge = bridge

    def observe_and_hypothesize(
        self,
        scene_graph: SceneGraph,
    ) -> list[ExplorationHypothesis]:
        """Step 1-2: Observe the scene and generate hypotheses.

        Examines the SceneGraph's objects and affordances to propose
        verifiable hypotheses about how to proceed.
        """
        hypotheses: list[ExplorationHypothesis] = []

        if not scene_graph.objects and not scene_graph.affordances:
            hypotheses.append(ExplorationHypothesis(
                hypothesis_id=f"h_{uuid.uuid4().hex[:6]}",
                description="Empty scene — no interactable elements detected",
                test_action="wait_and_resample",
                expected_state_change="new elements appear",
                risk_level="low",
                confidence=0.3,
            ))
            return hypotheses

        # Generate one hypothesis per affordance, sorted by risk
        for aff in scene_graph.affordances:
            risk = self._assess_risk(aff)
            hypotheses.append(ExplorationHypothesis(
                hypothesis_id=f"h_{uuid.uuid4().hex[:6]}",
                description=f"Interact via '{aff.verb}' with {aff.target_object_id}",
                test_action=f"{aff.verb}:{aff.target_object_id}",
                expected_state_change=aff.expected_delta or "state changes",
                risk_level=risk,
                confidence=aff.risk_level == "low" and 0.7 or 0.4,
            ))

        # If no affordances, generate object inspection hypotheses
        if not hypotheses:
            for obj in scene_graph.objects[:3]:
                hypotheses.append(ExplorationHypothesis(
                    hypothesis_id=f"h_{uuid.uuid4().hex[:6]}",
                    description=f"Inspect {obj.kind}: {obj.label}",
                    test_action=f"inspect:{obj.object_id}",
                    expected_state_change="context or menu appears",
                    risk_level="low",
                    confidence=0.5,
                ))

        hypotheses.sort(key=lambda h: (h.risk_level == "high", -h.confidence))
        return hypotheses[:3]

    def probe(
        self,
        scene_graph: SceneGraph,
        hypothesis: ExplorationHypothesis,
    ) -> ProbeResult:
        """Step 3-5: Execute a low-risk probe and attribute result."""
        state_before = scene_graph.scene_state

        log.info(
            "[UnknownScene] Probing: %s (action=%s, risk=%s)",
            hypothesis.description, hypothesis.test_action, hypothesis.risk_level,
        )

        effective = False
        learned_override: RuntimeOverride | None = None

        if hypothesis.test_action == "wait_and_resample":
            effective = True
        elif ":" in hypothesis.test_action:
            verb, target = hypothesis.test_action.split(":", 1)
            # Check if target exists in scene
            target_obj = None
            for obj in scene_graph.objects:
                if obj.object_id == target:
                    target_obj = obj
                    break

            if target_obj is not None:
                effective = True
                learned_override = RuntimeOverride(
                    override_id=f"uo_{uuid.uuid4().hex[:6]}",
                    target_parameter=f"action.{verb}.{target}",
                    new_value="auto",
                    reason=f"Learned from probe: {hypothesis.description}",
                    source="auto",
                    scope="session",
                    confidence=hypothesis.confidence,
                )

        result = ProbeResult(
            probe_id=f"p_{uuid.uuid4().hex[:6]}",
            hypothesis_id=hypothesis.hypothesis_id,
            action_taken=hypothesis.test_action,
            state_before=state_before,
            state_after="probed",
            effective=effective,
            learned_override=learned_override,
        )
        self._probe_history.append(result)

        if learned_override is not None:
            self._scene_memory[state_before] = hypothesis.test_action
            log.info("[UnknownScene] Learned: %s → %s", state_before, hypothesis.test_action)

            # Feed exploration result into MetaLearningBridge
            if self._meta_learning_bridge is not None:
                try:
                    self._meta_learning_bridge.on_exploration_result(
                        exploration_target=f"unknown_scene:{state_before}",
                        success=effective,
                        actions_taken=[{
                            "action": hypothesis.test_action,
                            "risk": hypothesis.risk_level,
                            "confidence": hypothesis.confidence,
                        }],
                        scene_description=state_before,
                    )
                    log.debug("[UnknownScene] Fed result to MetaLearningBridge")
                except Exception as exc:
                    log.warning("[UnknownScene] MetaLearningBridge feed failed: %s", exc)

        return result

    def should_escalate(self, hypotheses: list[ExplorationHypothesis]) -> bool:
        """Determine if the situation requires user escalation."""
        if not hypotheses:
            return True

        # All hypotheses are high risk
        if all(h.risk_level == self.risk_escalation_threshold for h in hypotheses):
            return True

        # Already probed max times without learning
        recent_probes = self._probe_history[-self.max_probe_attempts:]
        if len(recent_probes) >= self.max_probe_attempts:
            if not any(p.effective for p in recent_probes):
                return True

        return False

    def request_user_help(self, scene_graph: SceneGraph) -> RuntimeOverride:
        """Step 7: Generate an escalation override requesting user input."""
        log.warning("[UnknownScene] Escalating to user for scene: %s", scene_graph.scene_state)
        return RuntimeOverride(
            override_id=f"uo_{uuid.uuid4().hex[:6]}",
            target_parameter="system.pause_and_ask_user",
            new_value=scene_graph.scene_state,
            reason=f"Unknown scene handling exhausted: {scene_graph.scene_state}",
            source="auto",
            scope="session",
            confidence=0.0,
        )

    def get_learned_actions(self) -> dict[str, str]:
        """Return learned scene → action mappings from probes."""
        return dict(self._scene_memory)

    @property
    def probe_count(self) -> int:
        return len(self._probe_history)

    @staticmethod
    def _assess_risk(affordance: Affordance) -> str:
        """Assess the risk level of an affordance."""
        if affordance.risk_level in ("high", "critical"):
            return "high"
        if affordance.verb in ("attack", "destroy", "consume"):
            return "high"
        if affordance.verb in ("talk", "inspect", "examine", "wait"):
            return "low"
        return affordance.risk_level
