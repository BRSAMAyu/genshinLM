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

import atexit
import logging
import math
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
    CausalBridgeNode,
    CondensedNode,
    FalsifiableInterventionGraph,
    FeedbackNode,
    ProbeNode,
    _node_to_dict,
)
from bagel.feedback_shift import FeedbackShiftResult, discrete_tvd, single_probe_ifs
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


@dataclass(frozen=True, slots=True)
class JitRegenerationRequest:
    action_id: str
    allowed: bool
    reason: str
    parent_graph_version: int


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
    _frozen_snapshot: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        # Register BAGEL state slot on StateBus
        self.state_bus.register_slot("bagel_evidence_state")
        self.state_bus.register_slot("bagel_attribution_result")
        atexit.register(self.shutdown)

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
            payload=_node_to_dict(belief),
        )
        self._append_event(event)
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
            payload=_node_to_dict(action),
        )
        self._append_event(event)
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
                payload=_node_to_dict(action),
            )
            self._append_event(event)
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
            payload=_node_to_dict(feedback),
        )
        self._append_event(event)

        # Add evidence signal to matrix
        action = self.fig.snapshot()["actions"].get(feedback.action_id)
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

    # -- BAGEL v1.2 phase isolation -------------------------------------

    def freeze_attribution_snapshot(self, trace_id: str = "") -> dict[str, Any]:
        """Freeze the current FIG for attribution; execution must pause."""
        self.fig.set_phase("attribution_frozen")
        self._frozen_snapshot = self.fig.snapshot()
        self._append_event(BagelEvent(
            event_type="AttributionSnapshotFrozen",
            graph_id=self.fig.graph_id,
            graph_version=self.fig.version,
            trace_id=trace_id or self._trace_id,
            payload={
                "phase": "attribution_frozen",
                "belief_count": len(self._frozen_snapshot["beliefs"]),
                "action_count": len(self._frozen_snapshot["actions"]),
            },
        ))
        return self._frozen_snapshot

    def commit_attribution_decision(self, trace_id: str = "") -> None:
        """Commit attribution decisions and create a new graph version."""
        self.fig.set_phase("attribution_committed")
        self._append_event(BagelEvent(
            event_type="AttributionDecisionCommitted",
            graph_id=self.fig.graph_id,
            graph_version=self.fig.version,
            trace_id=trace_id or self._trace_id,
            payload={"phase": "attribution_committed"},
        ))

    def enter_execution_phase(self, trace_id: str = "") -> None:
        """Resume execution after attribution has committed."""
        self.fig.set_phase("execution")
        self._frozen_snapshot = None
        self._append_event(BagelEvent(
            event_type="ExecutionPhaseEntered",
            graph_id=self.fig.graph_id,
            graph_version=self.fig.version,
            trace_id=trace_id or self._trace_id,
            payload={"phase": "execution"},
        ))

    def jit_regenerate_stale_action(
        self,
        action_id: str,
        trace_id: str = "",
        regenerate_fn: Callable[[ActionNode], ActionNode] | None = None,
    ) -> JitRegenerationRequest:
        """Regenerate a stale action only in execution phase."""
        snap = self.fig.snapshot()
        if snap.get("phase") == "attribution_frozen":
            return JitRegenerationRequest(action_id, False, "attribution_snapshot_frozen", self.fig.version)
        action = snap["actions"].get(action_id)
        if action is None:
            return JitRegenerationRequest(action_id, False, "action_not_found", self.fig.version)
        if action.status != "aborted":
            return JitRegenerationRequest(action_id, False, "action_not_stale", self.fig.version)

        if regenerate_fn is not None:
            regenerated = regenerate_fn(action)
            self.fig.update_action(
                action_id,
                status=regenerated.status,
                fingerprint=regenerated.fingerprint,
                claim_id=regenerated.claim_id,
                metadata=regenerated.metadata,
            )
        self._append_event(BagelEvent(
            event_type="JitRegenerationRequested",
            graph_id=self.fig.graph_id,
            graph_version=self.fig.version,
            trace_id=trace_id or self._trace_id,
            payload={"action_id": action_id, "phase": snap.get("phase"), "regenerated": regenerate_fn is not None},
        ))
        return JitRegenerationRequest(action_id, True, "jit_regeneration_allowed", self.fig.version)

    # -- BAGEL v1.2 delayed feedback and feedback shift ------------------

    def register_causal_bridge(self, bridge: CausalBridgeNode, trace_id: str = "") -> CausalBridgeNode:
        self.fig.add_bridge(bridge)
        self._append_event(BagelEvent(
            event_type="CausalBridgeRegistered",
            graph_id=self.fig.graph_id,
            graph_version=self.fig.version,
            trace_id=trace_id or self._trace_id,
            payload=_node_to_dict(bridge),
        ))
        return bridge

    def score_delayed_feedback(self, bridge: CausalBridgeNode) -> float:
        """LongRangeScore proxy: bridge strength with temporal decay freshness."""
        snap = self.fig.snapshot()
        belief = snap["beliefs"].get(bridge.to_belief)
        if belief is None:
            return 0.0
        # Exponential freshness decay instead of binary 0/1
        age = time.perf_counter() - belief.updated_at
        freshness = math.exp(-0.01 * age)
        if belief.lifecycle in ("stale", "retired", "posthoc_invalid", "falsified"):
            freshness = 0.0
        reversibility = 1.0 - min(1.0, float(belief.metadata.get("irreversibility", 0.0)))
        return max(0.0, min(1.0, bridge.weight * freshness * reversibility))

    def compute_feedback_shift(
        self,
        belief_id: str,
        before: list[str],
        after: list[str],
        signal_quality: float = 1.0,
        threshold: float = 0.2,
    ) -> FeedbackShiftResult:
        if len(before) <= 1 and len(after) <= 1:
            result = single_probe_ifs(
                belief_id=belief_id,
                before_failure=before[0] if before else "",
                after_failure=after[0] if after else "",
                signal_quality=signal_quality,
                threshold=threshold,
            )
        else:
            result = discrete_tvd(belief_id=belief_id, before=before, after=after, threshold=threshold)

        # Guard: don't update terminal or falsified beliefs
        snap = self.fig.snapshot()
        belief = snap["beliefs"].get(belief_id)
        if belief is not None and belief.lifecycle not in ("falsified", "retired", "posthoc_invalid"):
            self.fig.update_belief(
                belief_id,
                ifs_score=result.ifs_score,
                tvd_score=result.tvd_score,
                attribution_quality=max(result.ifs_score, result.tvd_score),
                lifecycle="confirmed" if result.attributed else "noise_disturbance",
            )
        return result

    # -- BAGEL v1.2 condensation ----------------------------------------

    def condense_stable_subgraph(
        self,
        node_ids: tuple[str, ...],
        interface_contract: dict[str, Any],
        trace_id: str = "",
    ) -> CondensedNode | None:
        snap = self.fig.snapshot()
        unstable = {"provisional", "committed", "suspect", "falsified", "stale", "challenged", "posthoc_invalid"}
        for node_id in node_ids:
            belief = snap["beliefs"].get(node_id)
            if belief is not None and belief.lifecycle in unstable:
                return None
        condensed = CondensedNode(
            condensed_id=f"cond_{int(time.perf_counter() * 1000)}",
            source_node_ids=node_ids,
            interface_contract=interface_contract,
            summary_belief=str(interface_contract.get("summary", "stable_subgraph")),
            survival_evidence=tuple(interface_contract.get("outputs", ()) or ()),
            risk_summary=dict(interface_contract.get("risk_summary", {}) or {}),
            artifact_fingerprints=tuple(interface_contract.get("modified_artifacts", ()) or ()),
            expand_event_ref=self.fig.graph_id,
        )
        self.fig.add_condensed_node(condensed)
        self._append_event(BagelEvent(
            event_type="SubgraphCondensed",
            graph_id=self.fig.graph_id,
            graph_version=self.fig.version,
            trace_id=trace_id or self._trace_id,
            payload=_node_to_dict(condensed),
        ))
        return condensed

    def expand_condensed_node(self, condensed_id: str) -> tuple[str, ...]:
        node = self.fig.snapshot()["condensed_nodes"].get(condensed_id)
        return tuple(node.source_node_ids) if node else ()

    # -- Phase 4: Attribution Cycle (on failure) --

    def run_attribution_cycle(
        self,
        trace_id: str = "",
        probe_executor: Callable | None = None,
    ) -> AttributionCycleResult:
        """Run a complete attribution cycle after failure."""
        self._attribution_count += 1
        cycle_id = f"attr_{self._attribution_count}_{int(time.perf_counter())}"

        # Phase reset guard: if stuck in attribution_frozen, reset first
        if self.fig.phase == "attribution_frozen":
            self.reset_phase(trace_id)

        self.freeze_attribution_snapshot(trace_id)

        # Step 1: Arbitrate
        results = self.arbiter.arbitrate(self.fig, self.matrix)

        # Step 2: Generate probes for conflicts
        probes = self.arbiter.generate_probe_requests(results)
        for probe in probes:
            self.fig.add_probe(probe)
            self._append_event(BagelEvent(
                event_type="ProbeGenerated",
                graph_id=self.fig.graph_id,
                graph_version=self.fig.version,
                trace_id=trace_id,
                payload=_node_to_dict(probe),
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
                    updated_probe = self.fig.snapshot()["probes"].get(probe.probe_id)
                    self._append_event(BagelEvent(
                        event_type="ProbeExecuted",
                        graph_id=self.fig.graph_id,
                        graph_version=self.fig.version,
                        trace_id=trace_id,
                        payload=_node_to_dict(updated_probe) if updated_probe else {
                            "probe_id": probe.probe_id,
                            "status": executed.status,
                            "result": executed.result,
                        },
                    ))
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

                self._append_event(BagelEvent(
                    event_type="BeliefRevised" if result.new_lifecycle != "stale" else "BeliefStaled",
                    graph_id=self.fig.graph_id,
                    graph_version=self.fig.version,
                    trace_id=trace_id,
                    payload={
                        "belief_id": result.belief_id,
                        "old_lifecycle": result.old_lifecycle,
                        "new_lifecycle": result.new_lifecycle,
                        "lifecycle": result.new_lifecycle,
                        "score": result.score,
                        "reason": result.reason,
                        "strategy": decision.strategy,
                    },
                ))
                if decision.strategy == "stale_marking":
                    action_snapshot = self.fig.snapshot()["actions"]
                    for action_id in decision.affected_action_ids:
                        action = action_snapshot.get(action_id)
                        if action is not None:
                            self._append_event(BagelEvent(
                                event_type="ActionExecuted",
                                graph_id=self.fig.graph_id,
                                graph_version=self.fig.version,
                                trace_id=trace_id,
                                payload=_node_to_dict(action),
                            ))
            else:
                # Direct lifecycle update
                self.fig.update_belief(result.belief_id, lifecycle=result.new_lifecycle)
                self._append_event(BagelEvent(
                    event_type="ArbiterUpdated",
                    graph_id=self.fig.graph_id,
                    graph_version=self.fig.version,
                    trace_id=trace_id,
                    payload={
                        "belief_id": result.belief_id,
                        "old_lifecycle": result.old_lifecycle,
                        "new_lifecycle": result.new_lifecycle,
                        "lifecycle": result.new_lifecycle,
                        "score": result.score,
                        "reason": result.reason,
                    },
                ))

        # Build score summary
        scores = self.matrix.score_all()
        belief_scores = {bid: s.score for bid, s in scores.items()}

        # Step 5: Extract omitted beliefs from trace events
        omitted_count = self._extract_omitted_beliefs(trace_id)

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

        self.commit_attribution_decision(trace_id)
        self.enter_execution_phase(trace_id)
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
            "timeout": "insufficient",
            "flaky": "insufficient",
        }
        return mapping.get(feedback_polarity, "neutral")

    def _publish_belief_state(self) -> None:
        """Publish current belief state to StateBus."""
        slot = self.state_bus.get_slot("bagel_evidence_state")
        if slot:
            snap = self.fig.snapshot()
            slot.put({
                "graph_id": self.fig.graph_id,
                "version": self.fig.version,
                "belief_count": len(snap["beliefs"]),
                "active": len(self.fig.active_beliefs()),
                "suspect": len(self.fig.suspect_beliefs()),
                "falsified": len(self.fig.falsified_beliefs()),
            })

    def _append_event(self, event: BagelEvent) -> None:
        if not self.event_store.append(event):
            log.error("[BAGEL] Event store write failed for %s", event.event_type)

    def _extract_omitted_beliefs(self, trace_id: str) -> int:
        """Extract omitted beliefs from trace events and inject into FIG."""
        try:
            from bagel.omitted_belief import ConstrainedVerbalizer, ExtractInvariantSym
            events = self.event_store.query(trace_id=trace_id, limit=20)
            records = [
                {"source": e.payload.get("source", ""),
                 "anchor": e.payload.get("anchor", e.event_type),
                 "symbol": e.payload.get("symbol", ""),
                 "constraint": e.payload.get("constraint", ""),
                 "operator": e.payload.get("operator", "requires"),
                 "graph_distance": e.payload.get("graph_distance", 0)}
                for e in events
            ]
            extractor = ExtractInvariantSym()
            verbalizer = ConstrainedVerbalizer()
            invariants = extractor.extract(records)
            count = 0
            for inv in invariants:
                candidate = verbalizer.verbalize(inv)
                self.fig.add_belief(candidate.belief)
                count += 1
            if count:
                log.info("[BAGEL] Extracted %d omitted beliefs from trace %s", count, trace_id)
            return count
        except Exception as exc:
            log.debug("[BAGEL] Omitted belief extraction failed: %s", exc)
            return 0

    def get_suspect_summary(self) -> dict[str, Any]:
        """Get a summary of current suspect/falsified beliefs."""
        snap = self.fig.snapshot()
        return {
            "active": [b.belief_id for b in self.fig.active_beliefs()],
            "suspect": [b.belief_id for b in self.fig.suspect_beliefs()],
            "falsified": [b.belief_id for b in self.fig.falsified_beliefs()],
            "total_beliefs": len(snap["beliefs"]),
            "total_actions": len(snap["actions"]),
            "total_feedbacks": len(snap["feedbacks"]),
        }

    def quest_transition(
        self,
        new_mission_id: str,
        carry_forward_beliefs: list[str] | None = None,
        trace_id: str = "",
    ) -> dict[str, Any]:
        """Transition to a new quest/mission boundary.

        1. Run final attribution cycle.
        2. Archive FIG state.
        3. Evict terminal beliefs.
        4. Clear stale evidence signals.
        5. Reset probe taboos.
        6. Carry forward specified beliefs.
        """
        old_mission_id = self.fig.mission_id
        snap = self.fig.snapshot()

        # Archive current state
        self._append_event(BagelEvent(
            event_type="QuestArchived",
            graph_id=self.fig.graph_id,
            graph_version=self.fig.version,
            trace_id=trace_id or self._trace_id,
            payload={
                "mission_id": old_mission_id,
                "belief_count": len(snap["beliefs"]),
                "fig_snapshot": {k: {kk: _node_to_dict(vv) if hasattr(vv, '__dataclass_fields__') else vv for kk, vv in v.items()} if isinstance(v, dict) else v for k, v in snap.items()},
            },
        ))

        # Evict terminal beliefs
        evicted = self.fig.evict_terminated(max_age_sec=0.0)

        # Clear ALL evidence signals for quest boundary
        signals_cleared = self.matrix.clear()

        # Remove beliefs not in carry_forward list
        if carry_forward_beliefs is not None:
            carry_set = set(carry_forward_beliefs)
            for bid in list(self.fig.snapshot()["beliefs"].keys()):
                if bid not in carry_set:
                    self.fig.update_belief(bid, lifecycle="retired")
            self.fig.evict_terminated(max_age_sec=0.0)

        # Reset probe policy taboos for new quest
        self.probe_policy.reset_taboo()

        # Set new mission
        self.fig.mission_id = new_mission_id
        self._bump()

        self._append_event(BagelEvent(
            event_type="QuestTransition",
            graph_id=self.fig.graph_id,
            graph_version=self.fig.version,
            trace_id=trace_id or self._trace_id,
            payload={
                "old_mission_id": old_mission_id,
                "new_mission_id": new_mission_id,
                "evicted_beliefs": evicted,
                "signals_cleared": signals_cleared,
            },
        ))

        return {
            "old_mission_id": old_mission_id,
            "new_mission_id": new_mission_id,
            "evicted": evicted,
            "signals_cleared": signals_cleared,
        }

    def _bump(self) -> None:
        self.fig.version += 1

    def reset_phase(self, trace_id: str = "") -> None:
        """Reset FIG phase to execution (for recovery paths)."""
        self.fig.set_phase("execution")
        self._frozen_snapshot = None

    def shutdown(self) -> None:
        """Graceful shutdown: close event store."""
        try:
            self.event_store.close()
        except Exception:
            pass
