"""BeliefProposer — generates alternative hypotheses after belief falsification.

The #1 gap in BAGEL: the system can falsify beliefs but cannot propose new ones.
This module analyzes falsification evidence and generates 1-3 structured
alternative hypotheses that can be committed to the FIG as new provisional beliefs.

Pipeline:
1. Receive falsified belief + falsification evidence (from Arbiter)
2. Classify the failure mode (strategy/perception/execution/environment)
3. Query DecisionMemory for related successful strategies
4. Generate candidate hypotheses with confidence estimates
5. Return ranked proposals for FIG injection
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from bagel.fig_schema import (
    BeliefCausalRole,
    BeliefNode,
    FalsifiableInterventionGraph,
    TypedEdge,
)

log = logging.getLogger(__name__)

# -- Failure mode classification -------------------------------------------

FailureMode = Literal[
    "strategy",      # Wrong plan/approach (e.g., wrong combat rotation)
    "perception",    # Misread scene (e.g., thought it was dialogue, was combat)
    "execution",     # Correct plan but action failed (e.g., input blocked)
    "environment",   # External factor (e.g., network lag, loading screen)
    "resource",      # Insufficient resources (e.g., out of stamina, wrong team)
    "precondition",  # Assumption violated (e.g., waypoint not unlocked)
]


@dataclass(frozen=True, slots=True)
class HypothesisProposal:
    """A candidate alternative hypothesis generated after falsification."""
    proposal_id: str
    falsified_belief_id: str
    hypothesis: str
    causal_role: BeliefCausalRole
    failure_mode: FailureMode
    falsification_condition: str
    confidence: float
    reasoning: str
    supporting_evidence: tuple[str, ...] = ()
    source: str = "belief_proposer"  # belief_proposer | decision_memory | vlm
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if self.created_at == 0.0:
            object.__setattr__(self, "created_at", time.perf_counter())


@dataclass(frozen=True, slots=True)
class ProposerResult:
    """Result of a belief proposal cycle."""
    falsified_belief_id: str
    failure_mode: FailureMode
    proposals: tuple[HypothesisProposal, ...]
    best_proposal: HypothesisProposal | None


# -- Failure mode classifier -----------------------------------------------

_CLASSIFICATION_RULES: list[tuple[tuple[str, ...], FailureMode]] = (
    (("timeout", "timed_out", "no_response"), "environment"),
    (("not_found", "missing", "absent", "invisible"), "perception"),
    (("blocked", "rejected", "denied", "unauthorized"), "execution"),
    (("wrong_", "incorrect", "mismatch", "unexpected"), "strategy"),
    (("stamina", "energy", "resource", "insufficient"), "resource"),
    (("locked", "unavailable", "prerequisite", "pre_quest"), "precondition"),
)


def classify_failure_mode(
    falsification_reason: str,
    feedback_description: str = "",
    error_context: str = "",
) -> FailureMode:
    """Classify why a belief was falsified into a failure mode category."""
    combined = f"{falsification_reason} {feedback_description} {error_context}".lower()
    for keywords, mode in _CLASSIFICATION_RULES:
        if any(kw in combined for kw in keywords):
            return mode
    return "strategy"


# -- Hypothesis generation strategies ---------------------------------------

_STRATEGY_TEMPLATES: dict[FailureMode, list[str]] = {
    "strategy": [
        "try_alternative_approach:{target}:{original_action}→{alt_action}",
        "change_combat_strategy:{target}:elemental_reaction_optimized",
        "retry_with_different_route:{target}:path_variant_B",
    ],
    "perception": [
        "reobserve_scene:{target}:wait_and_recapture",
        "use_different_detection:{target}:ocr_instead_of_template",
        "expand_search_region:{target}:wider_roi_scan",
    ],
    "execution": [
        "retry_with_delay:{target}:increased_timeout",
        "use_fallback_input:{target}:keyboard_instead_of_click",
        "reacquire_focus:{target}:refocus_window_first",
    ],
    "environment": [
        "wait_and_retry:{target}:loading_screen_recovery",
        "recover_from_interruption:{target}:resume_from_checkpoint",
        "reset_to_known_state:{target}:teleport_to_safe_point",
    ],
    "resource": [
        "farm_resource_first:{target}:gather_missing_material",
        "switch_team_composition:{target}:appropriate_element_team",
        "rest_and_recover:{target}:heal_at_statue",
    ],
    "precondition": [
        "complete_prerequisite:{target}:unlock_waypoint_first",
        "fulfill_quest_requirement:{target}:complete_pre_quest",
        "change_approach:{target}:alternative_unlocked_path",
    ],
}

_ACTION_ALTERNATIVES: dict[str, str] = {
    "attack": "dodge_then_attack",
    "click": "key_press_enter",
    "navigate": "teleport",
    "interact": "wait_then_interact",
    "combat": "elemental_skill",
    "open": "hotkey",
    "select": "scroll_to",
    "confirm": "double_click",
}


def _generate_hypotheses(
    falsified: BeliefNode,
    failure_mode: FailureMode,
    decision_hints: list[dict[str, Any]],
) -> list[HypothesisProposal]:
    """Generate candidate hypotheses based on failure mode and context."""
    proposals: list[HypothesisProposal] = []
    templates = _STRATEGY_TEMPLATES.get(failure_mode, _STRATEGY_TEMPLATES["strategy"])
    target = falsified.target_object
    original_hypothesis = falsified.hypothesis

    for idx, template in enumerate(templates[:3]):
        alt_action = _ACTION_ALTERNATIVES.get(
            falsified.causal_role.split("_")[0] if "_" in falsified.causal_role else "interact",
            "alternative_action",
        )
        hypothesis_text = template.format(
            target=target,
            original_action=original_hypothesis[:50],
            alt_action=alt_action,
        )

        confidence = max(0.1, 0.6 - idx * 0.15)

        # Boost confidence if DecisionMemory has similar successful strategies
        for hint in decision_hints:
            if hint.get("success") and target.lower() in hint.get("goal", "").lower():
                confidence = min(0.9, confidence + 0.15)
                break

        supporting: list[str] = []
        if decision_hints:
            supporting.append(f"decision_memory:{len(decision_hints)}_similar_records")

        proposals.append(HypothesisProposal(
            proposal_id=f"prop_{uuid.uuid4().hex[:8]}",
            falsified_belief_id=falsified.belief_id,
            hypothesis=hypothesis_text,
            causal_role=falsified.causal_role,
            failure_mode=failure_mode,
            falsification_condition=f"action_succeeds:{hypothesis_text[:60]}",
            confidence=confidence,
            reasoning=f"Falsified belief '{falsified.belief_id}' suggests {failure_mode} failure. "
                      f"Alternative: {hypothesis_text}",
            supporting_evidence=tuple(supporting),
            source="decision_memory" if decision_hints else "belief_proposer",
        ))

    return proposals


# -- BeliefProposer ---------------------------------------------------------

class BeliefProposer:
    """Analyze falsified beliefs and propose structured alternative hypotheses.

    This is the critical missing piece in BAGEL's learning loop:
    without hypothesis generation, falsification only removes beliefs
    without creating replacements, leaving the system unable to adapt.

    Usage:
        proposer = BeliefProposer(fig, decision_memory)
        result = proposer.propose(falsified_belief, evidence_description)
        for proposal in result.proposals:
            fig.commit_belief(proposal.to_belief_node())
    """

    def __init__(
        self,
        fig: FalsifiableInterventionGraph | None = None,
        decision_memory: Any = None,
        max_proposals: int = 3,
    ) -> None:
        self._fig = fig
        self._decision_memory = decision_memory
        self._max_proposals = max_proposals

    def propose(
        self,
        falsified: BeliefNode,
        falsification_reason: str = "",
        feedback_description: str = "",
        error_context: str = "",
    ) -> ProposerResult:
        """Generate alternative hypotheses for a falsified belief.

        Args:
            falsified: The belief that was falsified.
            falsification_reason: Why the belief was falsified (from Arbiter).
            feedback_description: Description of the negative feedback.
            error_context: Additional error context from execution.

        Returns:
            ProposerResult with ranked proposals.
        """
        # 1. Classify failure mode
        failure_mode = classify_failure_mode(
            falsification_reason, feedback_description, error_context,
        )

        # 2. Query DecisionMemory for related successful strategies
        decision_hints = self._query_decision_memory(falsified)

        # 3. Generate hypotheses
        proposals = _generate_hypotheses(falsified, failure_mode, decision_hints)

        # 4. Rank by confidence (highest first)
        proposals.sort(key=lambda p: p.confidence, reverse=True)
        proposals = proposals[:self._max_proposals]

        best = proposals[0] if proposals else None

        log.info(
            "[BeliefProposer] Falsified belief '%s' (%s) → %d proposals, best=%.2f",
            falsified.belief_id, failure_mode, len(proposals),
            best.confidence if best else 0.0,
        )

        return ProposerResult(
            falsified_belief_id=falsified.belief_id,
            failure_mode=failure_mode,
            proposals=tuple(proposals),
            best_proposal=best,
        )

    def commit_best_proposal(self, result: ProposerResult) -> BeliefNode | None:
        """Commit the best proposal to the FIG as a new provisional belief.

        Returns the new BeliefNode or None if no proposals or no FIG.
        """
        if result.best_proposal is None or self._fig is None:
            return None

        proposal = result.best_proposal
        new_belief = BeliefNode(
            belief_id=f"belief_{uuid.uuid4().hex[:8]}",
            target_object=proposal.hypothesis.split(":")[1] if ":" in proposal.hypothesis else "unknown",
            causal_role=proposal.causal_role,
            hypothesis=proposal.hypothesis,
            falsification_condition=proposal.falsification_condition,
            lifecycle="provisional",
            confidence=proposal.confidence,
            risk_level="medium",
            metadata={
                "source": proposal.source,
                "failure_mode": proposal.failure_mode,
                "falsified_parent": proposal.falsified_belief_id,
                "reasoning": proposal.reasoning,
                "supporting_evidence": list(proposal.supporting_evidence),
            },
        )

        self._fig.commit_belief(new_belief)
        if hasattr(self._fig, "add_edge"):
            self._fig.add_edge(TypedEdge(
                edge_id=f"edge_{new_belief.belief_id}",
                source_id=proposal.falsified_belief_id,
                target_id=new_belief.belief_id,
                kind="belief_conflicts_belief",
            ))

        log.info(
            "[BeliefProposer] Committed proposal '%s' as belief '%s' (confidence=%.2f)",
            proposal.proposal_id, new_belief.belief_id, new_belief.confidence,
        )
        return new_belief

    def _query_decision_memory(self, falsified: BeliefNode) -> list[dict[str, Any]]:
        """Query DecisionMemory for strategies related to the falsified belief's target."""
        if self._decision_memory is None:
            return []

        try:
            from learning.decision_memory import DecisionQuery
            query = DecisionQuery(
                goal=falsified.target_object,
                limit=5,
            )
            records = self._decision_memory.query(query)
            return [
                {
                    "goal": r.goal,
                    "success": r.success,
                    "confidence": r.confidence,
                    "plan": r.plan_steps(),
                }
                for r in records
            ]
        except Exception as exc:
            log.debug("[BeliefProposer] DecisionMemory query failed: %s", exc)
            return []
