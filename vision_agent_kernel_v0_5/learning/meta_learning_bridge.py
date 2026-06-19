"""Meta-Learning Bridge — connects BAGEL attribution to Skill induction.

Gap #2: BAGEL attribution and learning systems are parallel lines.
This bridge connects them so that:
1. BAGEL falsification evidence → BeliefProposer generates hypotheses
2. Attribution results → DecisionMemory (with failure mode classification)
3. DecisionMemory patterns → SkillInductionGate (with belief context)
4. Exploration results → BAGEL as belief evidence

This closes the loop: failure → attribution → learning → improved future behavior.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from bagel.belief_proposer import (
    BeliefProposer,
    FailureMode,
    HypothesisProposal,
    ProposerResult,
    classify_failure_mode,
)
from bagel.fig_schema import (
    BeliefNode,
    FalsifiableInterventionGraph,
    FeedbackNode,
)
from learning.decision_memory import DecisionMemory, DecisionQuery

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AttributionLearningEvent:
    """A learning event produced from BAGEL attribution analysis."""
    event_id: str
    falsified_belief_id: str
    failure_mode: FailureMode
    target_object: str
    original_hypothesis: str
    proposed_alternatives: int
    best_alternative: str
    decision_memory_match: bool
    confidence: float
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if self.created_at == 0.0:
            object.__setattr__(self, "created_at", time.perf_counter())


@dataclass(frozen=True, slots=True)
class BridgeCycleResult:
    """Result of one meta-learning bridge cycle."""
    cycle_id: str
    falsified_belief_ids: tuple[str, ...]
    proposals_generated: int
    beliefs_committed: int
    decision_memory_updates: int
    skill_induction_candidates: int


class MetaLearningBridge:
    """Bridge BAGEL attribution results into the learning pipeline.

    This is the missing connector between:
    - BAGEL Arbiter (falsification decisions)
    - DecisionMemory (strategy storage)
    - SkillInductionGate (skill creation)
    - BeliefProposer (hypothesis generation)

    Usage:
        bridge = MetaLearningBridge(fig, decision_memory, belief_proposer)
        result = bridge.on_falsification_cycle(falsified_beliefs, feedbacks)
    """

    def __init__(
        self,
        fig: FalsifiableInterventionGraph,
        decision_memory: DecisionMemory,
        belief_proposer: BeliefProposer,
        skill_inductor: Any | None = None,
    ) -> None:
        self._fig = fig
        self._memory = decision_memory
        self._proposer = belief_proposer
        self._skill_inductor = skill_inductor
        self._learning_events: list[AttributionLearningEvent] = []
        self._failure_mode_counts: dict[str, int] = {}

    def on_falsification_cycle(
        self,
        falsified_beliefs: list[BeliefNode],
        feedbacks: list[FeedbackNode],
        error_context: str = "",
    ) -> BridgeCycleResult:
        """Process a batch of falsified beliefs through the learning pipeline.

        Pipeline:
        1. For each falsified belief:
           a. Classify failure mode
           b. Generate alternative hypotheses via BeliefProposer
           c. Commit best hypothesis to FIG
           d. Record attribution event to DecisionMemory
        2. Check if accumulated failure patterns suggest skill induction
        """
        cycle_id = f"bridge_{uuid.uuid4().hex[:8]}"
        proposals_total = 0
        beliefs_committed = 0
        memory_updates = 0

        # Build feedback lookup by action_id
        feedback_by_action: dict[str, list[FeedbackNode]] = {}
        for fb in feedbacks:
            feedback_by_action.setdefault(fb.action_id, []).append(fb)

        for belief in falsified_beliefs:
            # Find relevant feedback
            relevant_feedback = self._find_feedback_for_belief(belief, feedback_by_action)
            fb_desc = "; ".join(fb.description for fb in relevant_feedback)

            # 1. Propose alternative hypotheses
            result = self._proposer.propose(
                falsified=belief,
                falsification_reason=f"falsified at {time.perf_counter():.3f}",
                feedback_description=fb_desc,
                error_context=error_context,
            )

            proposals_total += len(result.proposals)

            # 2. Commit best proposal to FIG
            new_belief = self._proposer.commit_best_proposal(result)
            if new_belief is not None:
                beliefs_committed += 1

            # 3. Record to DecisionMemory with failure mode classification
            self._memory.record(
                goal=belief.target_object,
                capsule_id="bagel_attribution",
                screen_state="unknown",
                plan=[{
                    "belief_id": belief.belief_id,
                    "hypothesis": belief.hypothesis,
                    "failure_mode": result.failure_mode,
                    "alternatives": [p.hypothesis for p in result.proposals[:3]],
                }],
                success=False,
                duration_sec=0.0,
                confidence=belief.confidence,
            )
            memory_updates += 1

            # 4. Track failure mode distribution
            mode_key = result.failure_mode
            self._failure_mode_counts[mode_key] = self._failure_mode_counts.get(mode_key, 0) + 1

            # 5. Create learning event
            best_alt = result.best_proposal.hypothesis if result.best_proposal else "none"
            event = AttributionLearningEvent(
                event_id=f"ale_{uuid.uuid4().hex[:8]}",
                falsified_belief_id=belief.belief_id,
                failure_mode=result.failure_mode,
                target_object=belief.target_object,
                original_hypothesis=belief.hypothesis,
                proposed_alternatives=len(result.proposals),
                best_alternative=best_alt,
                decision_memory_match=any(
                    p.source == "decision_memory" for p in result.proposals
                ),
                confidence=result.best_proposal.confidence if result.best_proposal else 0.0,
            )
            self._learning_events.append(event)

        # 6. Check for skill induction candidates
        skill_candidates = self._check_skill_induction_candidates()

        log.info(
            "[MetaLearningBridge] Cycle %s: %d falsified → %d proposals → %d committed → %d skill candidates",
            cycle_id, len(falsified_beliefs), proposals_total, beliefs_committed, len(skill_candidates),
        )

        return BridgeCycleResult(
            cycle_id=cycle_id,
            falsified_belief_ids=tuple(b.belief_id for b in falsified_beliefs),
            proposals_generated=proposals_total,
            beliefs_committed=beliefs_committed,
            decision_memory_updates=memory_updates,
            skill_induction_candidates=len(skill_candidates),
        )

    def on_exploration_result(
        self,
        exploration_target: str,
        success: bool,
        actions_taken: list[dict[str, Any]],
        scene_description: str = "",
    ) -> None:
        """Feed exploration results into the learning pipeline.

        Exploration results become belief evidence in BAGEL and strategy
        records in DecisionMemory, closing the exploration→learning loop.
        """
        # Record to DecisionMemory
        self._memory.record(
            goal=exploration_target,
            capsule_id="exploration",
            screen_state=scene_description or "unknown",
            plan=actions_taken,
            success=success,
            duration_sec=0.0,
            confidence=0.6 if success else 0.3,
        )

        log.info(
            "[MetaLearningBridge] Exploration result for '%s': %s (%d actions)",
            exploration_target, "success" if success else "failure", len(actions_taken),
        )

    def get_learning_summary(self) -> dict[str, Any]:
        """Return a summary of all learning events processed by this bridge."""
        return {
            "total_events": len(self._learning_events),
            "failure_mode_distribution": dict(self._failure_mode_counts),
            "recent_events": [
                {
                    "event_id": e.event_id,
                    "target": e.target_object,
                    "failure_mode": e.failure_mode,
                    "alternatives": e.proposed_alternatives,
                    "confidence": e.confidence,
                }
                for e in self._learning_events[-10:]
            ],
        }

    def _find_feedback_for_belief(
        self, belief: BeliefNode, feedback_by_action: dict[str, list[FeedbackNode]],
    ) -> list[FeedbackNode]:
        """Find feedback nodes related to a belief via its actions."""
        related: list[FeedbackNode] = []
        for action in self._fig.actions.values():
            if belief.belief_id in action.belief_ids:
                related.extend(feedback_by_action.get(action.action_id, []))
        return related

    def _check_skill_induction_candidates(self) -> list[dict[str, Any]]:
        """Check if accumulated failure patterns suggest a new skill should be induced.

        When the same failure mode occurs repeatedly for the same target,
        it suggests the system needs a new skill for that scenario.
        """
        candidates: list[dict[str, Any]] = []

        # Group learning events by (target, failure_mode)
        pattern_counts: dict[tuple[str, str], int] = {}
        for event in self._learning_events:
            key = (event.target_object, event.failure_mode)
            pattern_counts[key] = pattern_counts.get(key, 0) + 1

        # If a pattern occurs 3+ times, it's a skill induction candidate
        for (target, mode), count in pattern_counts.items():
            if count >= 3:
                # Check DecisionMemory for successful strategies
                records = self._memory.query(DecisionQuery(goal=target, limit=5))
                success_records = [r for r in records if r.success]

                candidates.append({
                    "target": target,
                    "failure_mode": mode,
                    "occurrence_count": count,
                    "has_successful_strategies": len(success_records) > 0,
                    "suggested_skill_type": self._infer_skill_type(mode),
                })

                # Pass to skill inductor if available
                if self._skill_inductor is not None and success_records:
                    try:
                        self._skill_inductor.induce_from_patterns(
                            target=target,
                            failure_mode=mode,
                            successful_plans=[r.plan_steps() for r in success_records],
                        )
                    except Exception as exc:
                        log.debug("[MetaLearningBridge] Skill induction delegate failed: %s", exc)

        return candidates

    @staticmethod
    def _infer_skill_type(failure_mode: FailureMode) -> str:
        """Map failure mode to suggested skill type."""
        mapping = {
            "strategy": "combat",
            "perception": "verification",
            "execution": "recovery",
            "environment": "recovery",
            "resource": "navigation",
            "precondition": "navigation",
        }
        return mapping.get(failure_mode, "ui")
