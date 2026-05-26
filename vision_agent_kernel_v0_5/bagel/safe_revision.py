"""Safe Revision — cascade risk assessment for belief modification.

When a belief is revised or falsified, we must assess the cascade risk:
how many downstream actions and beliefs would be affected?

Formula:
    Affected(b_i) = all downstream actions reachable from b_i
    CascadeRisk = affected_ratio * coupling * (1 - verification_coverage)
    SafeRevision = CascadeRisk < kappa and Impact < K

Protocol:
    if SafeRevision:
        revise belief
        regenerate affected local actions
        run targeted probes
    else:
        mark downstream nodes stale
        estimate expanded revision cost
        JIT regenerate stale actions before execution
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from bagel.fig_schema import (
    ActionNode,
    BeliefNode,
    BeliefLifecycleState,
    FalsifiableInterventionGraph,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CascadeReport:
    """Report of cascade analysis for a belief revision."""
    belief_id: str
    affected_actions: int
    affected_beliefs: int
    total_actions: int
    total_beliefs: int
    affected_ratio: float
    coupling: float
    verification_coverage: float
    cascade_risk: float
    is_safe: bool
    reason: str


@dataclass(frozen=True, slots=True)
class RevisionDecision:
    """Decision about whether a belief revision is safe."""
    belief_id: str
    safe: bool
    strategy: str  # "local_revision" | "stale_marking" | "abort"
    cascade_report: CascadeReport | None = None
    affected_action_ids: tuple[str, ...] = ()
    affected_belief_ids: tuple[str, ...] = ()
    estimated_cost: float = 0.0


@dataclass(slots=True)
class SafeRevisionEngine:
    """Evaluates cascade risk of belief revisions and applies safe protocol."""
    kappa: float = 0.5       # Max acceptable cascade risk
    max_impact: float = 10   # Max acceptable affected nodes
    coupling_weight: float = 1.0

    def assess_cascade(
        self,
        fig: FalsifiableInterventionGraph,
        belief_id: str,
    ) -> CascadeReport:
        """Compute cascade risk for revising a belief."""
        belief = fig.beliefs.get(belief_id)
        if belief is None:
            return CascadeReport(
                belief_id=belief_id,
                affected_actions=0, affected_beliefs=0,
                total_actions=len(fig.actions), total_beliefs=len(fig.beliefs),
                affected_ratio=0.0, coupling=0.0,
                verification_coverage=1.0, cascade_risk=0.0,
                is_safe=True, reason="belief_not_found",
            )

        # Find downstream beliefs
        downstream_belief_ids = fig.downstream_beliefs(belief_id)

        # Find all affected actions (direct + downstream)
        affected_actions: set[str] = set()
        for bid in [belief_id] + downstream_belief_ids:
            for action in fig.actions_for_belief(bid):
                affected_actions.add(action.action_id)

        total_actions = max(len(fig.actions), 1)
        total_beliefs = max(len(fig.beliefs), 1)
        affected_ratio = len(affected_actions) / total_actions

        # Coupling: how many beliefs drive each affected action
        coupling_scores: list[float] = []
        for aid in affected_actions:
            action = fig.actions.get(aid)
            if action:
                coupling_scores.append(len(action.belief_ids))
        coupling = (
            sum(coupling_scores) / len(coupling_scores) if coupling_scores else 0.0
        )

        # Verification coverage: ratio of affected actions with claims
        verified_count = sum(
            1 for aid in affected_actions
            if fig.actions.get(aid) and fig.actions[aid].claim_id
        )
        verification_coverage = verified_count / max(len(affected_actions), 1)

        # Cascade risk
        cascade_risk = affected_ratio * coupling * self.coupling_weight * (1 - verification_coverage)

        # Small absolute impact is always safe regardless of ratio
        is_safe = (cascade_risk < self.kappa and len(affected_actions) <= self.max_impact) or len(affected_actions) <= 2

        return CascadeReport(
            belief_id=belief_id,
            affected_actions=len(affected_actions),
            affected_beliefs=len(downstream_belief_ids),
            total_actions=total_actions,
            total_beliefs=total_beliefs,
            affected_ratio=affected_ratio,
            coupling=coupling,
            verification_coverage=verification_coverage,
            cascade_risk=cascade_risk,
            is_safe=is_safe,
            reason="safe" if is_safe else f"cascade_risk={cascade_risk:.3f}",
        )

    def decide(
        self,
        fig: FalsifiableInterventionGraph,
        belief_id: str,
        new_lifecycle: BeliefLifecycleState,
    ) -> RevisionDecision:
        """Decide whether a belief lifecycle transition is safe."""
        report = self.assess_cascade(fig, belief_id)

        if new_lifecycle == "falsified" and not report.is_safe:
            # High cascade — mark downstream stale instead of immediate revision
            return RevisionDecision(
                belief_id=belief_id,
                safe=False,
                strategy="stale_marking",
                cascade_report=report,
                affected_action_ids=tuple(
                    fig.actions_for_belief(belief_id)[i].action_id
                    for i in range(len(fig.actions_for_belief(belief_id)))
                ),
                affected_belief_ids=tuple(fig.downstream_beliefs(belief_id)),
                estimated_cost=report.cascade_risk * 10,
            )

        if new_lifecycle == "retired":
            return RevisionDecision(
                belief_id=belief_id,
                safe=True,
                strategy="local_revision",
                cascade_report=report,
            )

        # Default: safe local revision
        return RevisionDecision(
            belief_id=belief_id,
            safe=True,
            strategy="local_revision",
            cascade_report=report,
        )

    def apply_revision(
        self,
        fig: FalsifiableInterventionGraph,
        decision: RevisionDecision,
        new_lifecycle: BeliefLifecycleState,
        **belief_overrides: Any,
    ) -> list[str]:
        """Apply a revision decision to the FIG. Returns list of changed node IDs."""
        changed: list[str] = []

        # Update the belief itself
        fig.update_belief(decision.belief_id, lifecycle=new_lifecycle, **belief_overrides)
        changed.append(decision.belief_id)

        if decision.strategy == "stale_marking":
            # Mark downstream beliefs as stale
            for bid in decision.affected_belief_ids:
                fig.update_belief(bid, lifecycle="stale")
                changed.append(bid)
            log.info(
                "[SafeRevision] Stale marking for %d downstream beliefs of %s",
                len(decision.affected_belief_ids), decision.belief_id,
            )
        elif decision.strategy == "local_revision":
            # Only the target belief is changed — downstream untouched
            log.info(
                "[SafeRevision] Local revision for belief %s -> %s",
                decision.belief_id, new_lifecycle,
            )

        return changed
