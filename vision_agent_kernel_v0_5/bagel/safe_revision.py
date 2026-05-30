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

RuntimeProfile = str


@dataclass(frozen=True, slots=True)
class RuntimeRiskPolicy:
    """BAGEL v2.1 runtime profile for verification-adjusted residual risk."""
    profile: RuntimeProfile = "safe_mode"
    residual_risk_kappa: float = 0.35
    min_verification_quality: float = 0.5

    @staticmethod
    def for_profile(profile: RuntimeProfile) -> "RuntimeRiskPolicy":
        if profile == "performance_mode":
            return RuntimeRiskPolicy(profile=profile, residual_risk_kappa=0.55, min_verification_quality=0.35)
        return RuntimeRiskPolicy(profile="safe_mode", residual_risk_kappa=0.35, min_verification_quality=0.5)


@dataclass(frozen=True, slots=True)
class CascadeReport:
    """Report of cascade analysis for a belief revision."""
    belief_id: str
    affected_actions: int
    affected_beliefs: int
    affected_action_ids: tuple[str, ...]
    affected_belief_ids: tuple[str, ...]
    total_actions: int
    total_beliefs: int
    affected_ratio: float
    coupling: float
    verification_coverage: float
    verification_quality: float
    cascade_risk: float
    residual_risk: float
    runtime_profile: RuntimeProfile
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
    runtime_profile: RuntimeProfile = "safe_mode"
    verification_quality_default: float = 0.6

    def assess_cascade(
        self,
        fig: FalsifiableInterventionGraph,
        belief_id: str,
    ) -> CascadeReport:
        """Compute cascade risk for revising a belief.

        All FIG queries are performed atomically via snapshot() to
        avoid TOCTOU from concurrent mutations.
        """
        snap = fig.snapshot()

        belief = snap["beliefs"].get(belief_id)
        if belief is None:
            return CascadeReport(
                belief_id=belief_id,
                affected_actions=0, affected_beliefs=0,
                affected_action_ids=(), affected_belief_ids=(),
                total_actions=len(snap["actions"]), total_beliefs=len(snap["beliefs"]),
                affected_ratio=0.0, coupling=0.0,
                verification_coverage=1.0, verification_quality=1.0,
                cascade_risk=0.0, residual_risk=0.0, runtime_profile=self.runtime_profile,
                is_safe=True, reason="belief_not_found",
            )

        # Find downstream beliefs from snapshot
        downstream_belief_ids = self._downstream_from_snapshot(snap, belief_id)

        # Find all affected actions (direct + downstream)
        affected_actions: set[str] = set()
        for bid in [belief_id] + list(downstream_belief_ids):
            for action in snap["actions"].values():
                if bid in action.belief_ids:
                    affected_actions.add(action.action_id)

        total_actions = max(len(snap["actions"]), 1)
        total_beliefs = max(len(snap["beliefs"]), 1)
        affected_ratio = len(affected_actions) / total_actions

        # Coupling: how many beliefs drive each affected action
        coupling_scores: list[float] = []
        for aid in affected_actions:
            action = snap["actions"].get(aid)
            if action:
                coupling_scores.append(len(action.belief_ids))
        coupling = (
            sum(coupling_scores) / len(coupling_scores) if coupling_scores else 0.0
        )

        # Verification coverage: ratio of affected actions with claims
        verified_count = sum(
            1 for aid in affected_actions
            if snap["actions"].get(aid) and snap["actions"][aid].claim_id
        )
        verification_coverage = verified_count / max(len(affected_actions), 1)

        policy = RuntimeRiskPolicy.for_profile(self.runtime_profile)
        verification_quality = max(0.0, min(1.0, self.verification_quality_default))

        # Raw cascade risk is topology-only; residual risk accounts for the
        # independent verification quality available after revision.
        cascade_risk = affected_ratio * coupling * self.coupling_weight
        verified_reduction = verification_coverage * verification_quality
        residual_risk = cascade_risk * (1 - verified_reduction)

        # Small absolute impact is always safe regardless of ratio
        is_safe = (
            residual_risk < min(self.kappa, policy.residual_risk_kappa)
            and verification_quality >= policy.min_verification_quality
            and len(affected_actions) <= self.max_impact
        ) or len(affected_actions) <= 2

        return CascadeReport(
            belief_id=belief_id,
            affected_actions=len(affected_actions),
            affected_beliefs=len(downstream_belief_ids),
            affected_action_ids=tuple(sorted(affected_actions)),
            affected_belief_ids=tuple(downstream_belief_ids),
            total_actions=total_actions,
            total_beliefs=total_beliefs,
            affected_ratio=affected_ratio,
            coupling=coupling,
            verification_coverage=verification_coverage,
            verification_quality=verification_quality,
            cascade_risk=cascade_risk,
            residual_risk=residual_risk,
            runtime_profile=policy.profile,
            is_safe=is_safe,
            reason="safe" if is_safe else f"residual_risk={residual_risk:.3f}",
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
            return RevisionDecision(
                belief_id=belief_id,
                safe=False,
                strategy="stale_marking",
                cascade_report=report,
                affected_action_ids=report.affected_action_ids,
                affected_belief_ids=report.affected_belief_ids,
                estimated_cost=report.residual_risk * 10,
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
            # Also mark affected actions as needing regeneration
            for aid in decision.affected_action_ids:
                fig.update_action(aid, status="aborted")
                changed.append(aid)
            log.info(
                "[SafeRevision] Stale marking for %d downstream beliefs, "
                "%d affected actions of %s",
                len(decision.affected_belief_ids),
                len(decision.affected_action_ids),
                decision.belief_id,
            )
        elif decision.strategy == "local_revision":
            log.info(
                "[SafeRevision] Local revision for belief %s -> %s",
                decision.belief_id, new_lifecycle,
            )

        return changed

    @staticmethod
    def _downstream_from_snapshot(
        snap: dict[str, Any], belief_id: str,
    ) -> list[str]:
        """BFS for downstream beliefs using a snapshot instead of live FIG."""
        from collections import deque
        visited: set[str] = {belief_id}
        queue = deque([belief_id])
        result: list[str] = []
        while queue:
            current = queue.popleft()
            for edge in snap["edges"]:
                if edge.kind == "belief_depends_on_belief" and edge.target_id == current:
                    downstream_id = edge.source_id
                    if downstream_id not in visited and downstream_id in snap["beliefs"]:
                        visited.add(downstream_id)
                        result.append(downstream_id)
                        queue.append(downstream_id)
        return result
