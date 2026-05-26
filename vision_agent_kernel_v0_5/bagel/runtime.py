"""BAGEL Runtime — orchestrates the standard BAGEL loop.

Section 20 of the BAGEL theory defines the standard loop:
1. Executor reads active FIG slice.
2. Executor emits Nominal BeliefCommit before action.
3. Runtime validates forward structural constraints.
4. Executor emits ActionProposal.
5. Runtime materializes action fingerprint.
6. Action executes.
7. Environment emits Feedback.
8. Runtime labels signal quality.
9. On failure: freeze snapshot, sample attribution, compute entropy.
10. Run local or heterogeneous attribution.
11. Auditor fills Evidence Matrix.
12. Arbiter checks conflict, triggers tie-breaker probes.
13. Probe execution and matrix update.
14. Belief lifecycle updates (attributed/noise/revised/retired/stale).
15. Safe Revision check.
16. Regenerate affected slice or broader retry.

This runtime provides the programmatic API for each step.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from core.state_bus import StateBus
from bagel.arbiter import ArbitrationResult, BagelArbiter
from bagel.evidence_matrix import EvidenceMatrix, EvidenceSignal
from bagel.event_store import BagelEvent, BagelEventStore
from bagel.fig_schema import (
    ActionNode,
    BeliefLifecycleState,
    BeliefNode,
    FalsifiableInterventionGraph,
    FeedbackNode,
    ProbeNode,
)
from bagel.probe_policy import ProbePolicy
from bagel.safe_revision import RevisionDecision, SafeRevisionEngine

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AttributionCycleResult:
    """Result of one complete attribution cycle."""
    cycle_id: str
    belief_scores: dict[str, float]
    revised_belief_ids: list[str]
    stale_belief_ids: list[str]
    probes_generated: int
    strategy: str  # "local_attribution" | "heterogeneous_audit"


@dataclass(slots=True)
class BagelRuntime:
    """Top-level BAGEL runtime orchestrating the full attribution loop."""

    state_bus: StateBus = field(default_factory=StateBus)
    event_store: BagelEventStore = field(default_factory=BagelEventStore)
    fig: FalsifiableInterventionGraph = field(default_factory=FalsifiableInterventionGraph)
    matrix: EvidenceMatrix = field(default_factory=EvidenceMatrix)
    arbiter: BagelArbiter = field(default_factory=BagelArbiter)
    revision_engine: SafeRevisionEngine = field(default_factory=SafeRevisionEngine)
    probe_policy: ProbePolicy = field(default_factory=ProbePolicy)

    _trace_id: str = ""
    _attribution_count: int = 0

    def __post_init__(self) -> None:
        # Register BAGEL state slot on StateBus
        self.state_bus.register_slot("bagel_evidence_state")
        self.state_bus.register_slot("bagel_attribution_result")

    # -- Phase 1: Belief Commit (forward registration) --

    def commit_belief(
        self,
        belief: BeliefNode,
        trace_id: str = "",
    ) -> BeliefNode:
        """Register a belief before action execution.

        Validates forward structural constraints:
        - Has target_object and causal_role.
        - Has falsification_condition (for medium+ risk).
        - Is not post-hoc relative to existing actions.
        """
        # Forward structural validation
        if belief.risk_level in ("medium", "high") and not belief.falsification_condition:
            log.warning(
                "[BAGEL] Belief %s has risk=%s but no falsification_condition",
                belief.belief_id, belief.risk_level,
            )

        self.fig.commit_belief(belief)
        self._trace_id = trace_id

        # Record event
        event = BagelEvent(
            event_type="BeliefCommitted",
            graph_id=self.fig.graph_id,
            graph_version=self.fig.version,
            trace_id=trace_id,
            payload={"belief_id": belief.belief_id, "lifecycle": belief.lifecycle},
        )
        self.event_store.append(event)
        self._publish_belief_state()
        return belief

    # -- Phase 2: Action Proposal --

    def propose_action(
        self,
        action: ActionNode,
        trace_id: str = "",
    ) -> ActionNode:
        """Register an action driven by committed beliefs."""
        self.fig.propose_action(action)

        event = BagelEvent(
            event_type="ActionProposed",
            graph_id=self.fig.graph_id,
            graph_version=self.fig.version,
            trace_id=trace_id,
            payload={"action_id": action.action_id, "belief_ids": list(action.belief_ids)},
        )
        self.event_store.append(event)
        return action

    def materialize_action(
        self,
        action_id: str,
        fingerprint: str,
        claim_id: str = "",
    ) -> ActionNode | None:
        """Update action with real fingerprint after materialization."""
        action = self.fig.update_action(
            action_id,
            status="materialized",
            fingerprint=fingerprint,
            claim_id=claim_id,
        )
        if action:
            event = BagelEvent(
                event_type="ActionMaterialized",
                graph_id=self.fig.graph_id,
                graph_version=self.fig.version,
                trace_id=self._trace_id,
                payload={"action_id": action_id, "fingerprint": fingerprint},
            )
            self.event_store.append(event)
        return action

    # -- Phase 3: Feedback --

    def receive_feedback(self, feedback: FeedbackNode) -> None:
        """Record feedback from environment after action execution."""
        self.fig.add_feedback(feedback)

        event = BagelEvent(
            event_type="FeedbackReceived",
            graph_id=self.fig.graph_id,
            graph_version=self.fig.version,
            trace_id=self._trace_id,
            payload={
                "feedback_id": feedback.feedback_id,
                "action_id": feedback.action_id,
                "polarity": feedback.polarity,
                "signal_quality": feedback.signal_quality,
            },
        )
        self.event_store.append(event)

        # Add evidence signal to matrix
        action = self.fig.actions.get(feedback.action_id)
        if action:
            for belief_id in action.belief_ids:
                polarity = self._feedback_to_polarity(feedback.polarity)
                signal = EvidenceSignal(
                    signal_id=feedback.feedback_id,
                    belief_id=belief_id,
                    polarity=polarity,
                    weight=feedback.signal_quality,
                    source="feedback",
                )
                self.matrix.add_signal(signal)

    # -- Phase 4: Attribution Cycle (on failure) --

    def run_attribution_cycle(
        self,
        trace_id: str = "",
        probe_executor: Callable | None = None,
    ) -> AttributionCycleResult:
        """Run a complete attribution cycle after failure.

        Steps:
        1. Run arbiter on all beliefs with evidence.
        2. Check for conflicts → generate tie-breaker probes.
        3. Execute probes if executor provided.
        4. Re-run arbiter with probe results.
        5. Apply safe revision for falsified beliefs.
        6. Publish results.
        """
        self._attribution_count += 1
        cycle_id = f"attr_{self._attribution_count}_{int(time.perf_counter())}"

        # Step 1: Arbitrate
        results = self.arbiter.arbitrate(self.fig, self.matrix)

        # Step 2: Generate probes for conflicts
        probes = self.arbiter.generate_probe_requests(results)
        for probe in probes:
            self.fig.add_probe(probe)
            self.event_store.append(BagelEvent(
                event_type="ProbeGenerated",
                graph_id=self.fig.graph_id,
                graph_version=self.fig.version,
                trace_id=trace_id,
                payload={"probe_id": probe.probe_id, "belief_id": probe.belief_id},
            ))

        # Step 3: Execute probes if executor available
        if probe_executor:
            for probe in probes:
                if probe.status == "generated":
                    executed = self.probe_policy.execute_probe(probe, probe_executor)
                    self.fig.update_probe(
                        probe.probe_id,
                        status=executed.status,
                        result=executed.result,
                    )
                    # Add probe result as evidence signal
                    polarity = "refute" if executed.status == "failed" else "support"
                    self.matrix.add_signal(EvidenceSignal(
                        signal_id=probe.probe_id,
                        belief_id=probe.belief_id,
                        polarity=polarity,
                        weight=0.8,
                        is_core_probe=True,
                        source="probe",
                    ))

            # Re-arbitrate with probe results
            results = self.arbiter.arbitrate(self.fig, self.matrix)

        # Step 4: Apply arbitration + safe revision
        revised_belief_ids: list[str] = []
        stale_belief_ids: list[str] = []

        for result in results:
            if result.new_lifecycle in ("falsified", "retired", "stale"):
                decision = self.revision_engine.decide(
                    self.fig, result.belief_id, result.new_lifecycle,
                )
                changed = self.revision_engine.apply_revision(
                    self.fig, decision, result.new_lifecycle,
                )
                if decision.strategy == "local_revision":
                    revised_belief_ids.extend(changed)
                elif decision.strategy == "stale_marking":
                    stale_belief_ids.extend(changed)

                self.event_store.append(BagelEvent(
                    event_type="BeliefRevised" if result.new_lifecycle != "stale" else "BeliefStaled",
                    graph_id=self.fig.graph_id,
                    graph_version=self.fig.version,
                    trace_id=trace_id,
                    payload={
                        "belief_id": result.belief_id,
                        "old_lifecycle": result.old_lifecycle,
                        "new_lifecycle": result.new_lifecycle,
                        "score": result.score,
                        "reason": result.reason,
                        "strategy": decision.strategy,
                    },
                ))
            else:
                # Direct lifecycle update
                self.fig.update_belief(result.belief_id, lifecycle=result.new_lifecycle)

        # Build score summary
        scores = self.matrix.score_all()
        belief_scores = {bid: s.score for bid, s in scores.items()}

        # Publish to StateBus
        result_obj = AttributionCycleResult(
            cycle_id=cycle_id,
            belief_scores=belief_scores,
            revised_belief_ids=revised_belief_ids,
            stale_belief_ids=stale_belief_ids,
            probes_generated=len(probes),
            strategy="local_attribution",
        )

        slot = self.state_bus.get_slot("bagel_attribution_result")
        if slot:
            slot.put({
                "cycle_id": cycle_id,
                "belief_scores": belief_scores,
                "revised": revised_belief_ids,
                "stale": stale_belief_ids,
                "probes": len(probes),
            })

        return result_obj

    # -- Utility --

    def _feedback_to_polarity(self, feedback_polarity: str) -> str:
        """Map FIG feedback polarity to evidence matrix polarity."""
        mapping = {
            "positive": "support",
            "negative": "refute",
            "neutral": "neutral",
            "error": "insufficient",
            "insufficient": "insufficient",
        }
        return mapping.get(feedback_polarity, "neutral")

    def _publish_belief_state(self) -> None:
        """Publish current belief state to StateBus."""
        slot = self.state_bus.get_slot("bagel_evidence_state")
        if slot:
            slot.put({
                "graph_id": self.fig.graph_id,
                "version": self.fig.version,
                "belief_count": len(self.fig.beliefs),
                "active": len(self.fig.active_beliefs()),
                "suspect": len(self.fig.suspect_beliefs()),
                "falsified": len(self.fig.falsified_beliefs()),
            })

    def get_suspect_summary(self) -> dict[str, Any]:
        """Get a summary of current suspect/falsified beliefs."""
        return {
            "active": [b.belief_id for b in self.fig.active_beliefs()],
            "suspect": [b.belief_id for b in self.fig.suspect_beliefs()],
            "falsified": [b.belief_id for b in self.fig.falsified_beliefs()],
            "total_beliefs": len(self.fig.beliefs),
            "total_actions": len(self.fig.actions),
            "total_feedbacks": len(self.fig.feedbacks),
        }
