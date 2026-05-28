"""FIG schema — Falsifiable Intervention Graph.

A FIG is a directed acyclic graph where:
- BeliefNodes represent *testable hypotheses* about the world.
- ActionNodes represent *decisions* driven by beliefs.
- FeedbackNodes represent *outcomes* observed after actions.
- ProbeNodes represent *falsification experiments* to test beliefs.
- TypedEdges connect them with labeled causal relationships.

Key invariant: BeliefCommit must precede ActionProposal.
Post-hoc belief insertion is rejected or tagged posthoc_invalid.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
import dataclasses as _dc
from dataclasses import dataclass, field
from typing import Any, Literal

# -- Lifecycle states -----------------------------------------------------

BeliefLifecycleState = Literal[
    "provisional",       # intent-level, not yet fingerprinted
    "committed",         # fingerprint confirmed, driving actions (Nominal)
    "confirmed",         # positive feedback received (Attributed)
    "survived",          # passed falsification probe, high confidence
    "suspect",           # at least one falsification signal
    "falsified",         # falsification probe succeeded
    "noise_disturbance", # failed feedback coupling, not a useful belief
    "retired",           # no longer active
    "stale",             # downstream of a falsified belief, needs JIT regeneration
    "posthoc_invalid",   # inserted after action, not usable for attribution
    "challenged",        # under attribution review, not yet falsified
]

BeliefCausalRole = Literal[
    "objective_type_hypothesis",
    "ui_affordance_hypothesis",
    "navigation_hypothesis",
    "combat_strategy_hypothesis",
    "resource_sufficiency_hypothesis",
    "screen_state_hypothesis",
    "enemy_state_hypothesis",
    "team_capability_hypothesis",
    "quest_progress_hypothesis",
    "custom",
]

ActionStatus = Literal[
    "proposed",
    "materialized",
    "executing",
    "completed",
    "failed",
    "aborted",
]

FeedbackPolarity = Literal[
    "positive",       # outcome matches expectation
    "negative",       # outcome contradicts expectation
    "neutral",        # outcome inconclusive
    "error",          # execution error, not a belief issue
    "insufficient",   # not enough signal to judge
    "timeout",        # probe or feedback timed out
    "flaky",          # repeated but inconsistent signal
]

ProbeStatus = Literal[
    "generated",
    "sanity_checked",
    "approved",
    "executing",
    "passed",         # belief survived the probe
    "failed",         # belief was falsified
    "inconclusive",
    "timed_out",
    "rejected",       # sanity check failed
    "non_decidable",  # executed but cannot adjudicate target invariant
]

EdgeKind = Literal[
    "belief_drives_action",
    "action_produces_feedback",
    "feedback_tests_belief",
    "probe_tests_belief",
    "belief_depends_on_belief",
    "belief_conflicts_belief",
    "action_alternative_to_action",
    "feedback_bridges_belief",
    "condensed_from",
]

BridgeType = Literal[
    "artifact_continuity",
    "contract_continuity",
    "state_continuity",
    "regression_link",
    "performance_link",
]

CondensedNodeKind = Literal["super_belief"]

ProbeClusterState = Literal[
    "decidable",
    "non_decidable_once",
    "non_decidable_repeated",
    "undecidable_cluster",
    "requires_controlled_rollback",
    "requires_human_review",
]

AttributionPhaseState = Literal[
    "execution",
    "attribution_frozen",
    "attribution_committed",
]


# -- Identity -------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BeliefIdentity:
    """Two-phase identity for a belief.

    Phase 1 (provisional): identified by intent/action anchor.
    Phase 2 (committed): identified by materialized fingerprint.
    """
    belief_id: str
    provisional_anchor: str = ""
    fingerprint: str = ""

    @property
    def is_confirmed_identity(self) -> bool:
        return bool(self.fingerprint)


@dataclass(frozen=True, slots=True)
class StructuredValidityCondition:
    """Runtime-detectable condition that keeps a belief valid."""
    kind: str
    target: str
    expected: str = ""
    on_violation: str = "mark_stale"


# -- Core Nodes -----------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BeliefNode:
    belief_id: str
    target_object: str
    causal_role: BeliefCausalRole
    hypothesis: str
    falsification_condition: str
    lifecycle: BeliefLifecycleState = "provisional"
    identity: BeliefIdentity | None = None
    confidence: float = 0.5
    intervenable: bool = True
    risk_level: str = "low"
    valid_while_structured: tuple[StructuredValidityCondition, ...] = ()
    ifs_score: float = 0.0
    tvd_score: float = 0.0
    attribution_quality: float = 0.0
    condensed_from: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        if self.created_at == 0.0:
            object.__setattr__(self, "created_at", time.perf_counter())
            object.__setattr__(self, "updated_at", self.created_at)


@dataclass(frozen=True, slots=True)
class ActionNode:
    action_id: str
    belief_ids: tuple[str, ...]
    action_type: str
    params: dict[str, Any] = field(default_factory=dict)
    status: ActionStatus = "proposed"
    fingerprint: str = ""
    claim_id: str = ""
    risk_level: str = "low"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        if self.created_at == 0.0:
            object.__setattr__(self, "created_at", time.perf_counter())
            object.__setattr__(self, "updated_at", self.created_at)


@dataclass(frozen=True, slots=True)
class FeedbackNode:
    feedback_id: str
    action_id: str
    polarity: FeedbackPolarity
    signal_quality: float = 0.5
    evidence_refs: tuple[str, ...] = ()
    claim_refs: tuple[str, ...] = ()
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if self.created_at == 0.0:
            object.__setattr__(self, "created_at", time.perf_counter())


@dataclass(frozen=True, slots=True)
class ProbeNode:
    probe_id: str
    belief_id: str
    description: str
    failure_criteria: str
    status: ProbeStatus = "generated"
    falsification_invariant: str = ""
    irreversible: bool = False
    can_distinguish: tuple[str, str] = ("", "")
    timeout_risk: str = ""
    noise_risk: str = ""
    probe_cluster_id: str = ""
    non_decidable_count: int = 0
    sanity_status: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    executed_at: float = 0.0

    def __post_init__(self) -> None:
        if self.created_at == 0.0:
            object.__setattr__(self, "created_at", time.perf_counter())


# -- Edges ----------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TypedEdge:
    edge_id: str
    source_id: str
    target_id: str
    kind: EdgeKind
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CausalBridgeNode:
    """Connect delayed feedback to an earlier belief by explicit evidence."""
    bridge_id: str
    from_feedback: str
    to_belief: str
    bridge_type: BridgeType
    evidence: tuple[str, ...] = ()
    weight: float = 0.5
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if self.created_at == 0.0:
            object.__setattr__(self, "created_at", time.perf_counter())


@dataclass(frozen=True, slots=True)
class CondensedNode:
    """Stable subgraph summary kept in the active FIG frontier."""
    condensed_id: str
    kind: CondensedNodeKind = "super_belief"
    source_node_ids: tuple[str, ...] = ()
    interface_contract: dict[str, Any] = field(default_factory=dict)
    summary_belief: str = ""
    survival_evidence: tuple[str, ...] = ()
    risk_summary: dict[str, Any] = field(default_factory=dict)
    artifact_fingerprints: tuple[str, ...] = ()
    expand_event_ref: str = ""
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if self.created_at == 0.0:
            object.__setattr__(self, "created_at", time.perf_counter())


# -- FIG container --------------------------------------------------------

@dataclass(slots=True)
class FalsifiableInterventionGraph:
    """Mutable container for a single mission/session's FIG."""
    graph_id: str = ""
    mission_id: str = ""
    beliefs: dict[str, BeliefNode] = field(default_factory=dict)
    actions: dict[str, ActionNode] = field(default_factory=dict)
    feedbacks: dict[str, FeedbackNode] = field(default_factory=dict)
    probes: dict[str, ProbeNode] = field(default_factory=dict)
    bridges: dict[str, CausalBridgeNode] = field(default_factory=dict)
    condensed_nodes: dict[str, CondensedNode] = field(default_factory=dict)
    edges: list[TypedEdge] = field(default_factory=list)
    version: int = 0
    phase: AttributionPhaseState = "execution"
    _ordering_lock: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if not self.graph_id:
            object.__setattr__(self, "graph_id", f"fig_{uuid.uuid4().hex[:8]}")

    # -- Mutation methods (return new version) --

    def commit_belief(self, belief: BeliefNode) -> None:
        """Insert a belief. Rejects if post-hoc relative to existing actions."""
        with self._lock:
            self._commit_belief_unlocked(belief)

    def _commit_belief_unlocked(self, belief: BeliefNode) -> None:
        if belief.lifecycle == "posthoc_invalid":
            self.beliefs[belief.belief_id] = belief
            self._bump()
            return
        # Check: if any action already exists driven by this belief, it's post-hoc.
        for action in self.actions.values():
            if belief.belief_id in action.belief_ids:
                tagged = _dc.replace(belief, lifecycle="posthoc_invalid")
                self.beliefs[belief.belief_id] = tagged
                self._bump()
                return
        self.beliefs[belief.belief_id] = belief
        self._ordering_lock[belief.belief_id] = self.version
        self._bump()

    def propose_action(self, action: ActionNode) -> None:
        """Insert an action. Requires all driving beliefs to be committed."""
        with self._lock:
            self._propose_action_unlocked(action)

    def _propose_action_unlocked(self, action: ActionNode) -> None:
        for bid in action.belief_ids:
            belief = self.beliefs.get(bid)
            if belief is None:
                raise ValueError(f"Action references unknown belief {bid!r}")
            if belief.lifecycle in ("posthoc_invalid", "retired"):
                raise ValueError(
                    f"Action references {bid!r} with lifecycle {belief.lifecycle!r}"
                )
        self.actions[action.action_id] = action
        self._bump()

    def add_feedback(self, feedback: FeedbackNode) -> None:
        with self._lock:
            self.feedbacks[feedback.feedback_id] = feedback
            self._bump()

    def add_probe(self, probe: ProbeNode) -> None:
        with self._lock:
            self.probes[probe.probe_id] = probe
            self._bump()

    def add_bridge(self, bridge: CausalBridgeNode) -> None:
        with self._lock:
            self.bridges[bridge.bridge_id] = bridge
            self.edges.append(TypedEdge(
                edge_id=f"edge_{bridge.bridge_id}",
                source_id=bridge.from_feedback,
                target_id=bridge.to_belief,
                kind="feedback_bridges_belief",
                weight=bridge.weight,
                metadata={"bridge_type": bridge.bridge_type, "evidence": list(bridge.evidence)},
            ))
            self._bump()

    def add_condensed_node(self, node: CondensedNode) -> None:
        with self._lock:
            self.condensed_nodes[node.condensed_id] = node
            for source_id in node.source_node_ids:
                self.edges.append(TypedEdge(
                    edge_id=f"edge_{node.condensed_id}_{source_id}",
                    source_id=node.condensed_id,
                    target_id=source_id,
                    kind="condensed_from",
                    metadata={"expand_event_ref": node.expand_event_ref},
                ))
            self._bump()

    def set_phase(self, phase: AttributionPhaseState) -> None:
        with self._lock:
            self.phase = phase
            self._bump()

    def add_edge(self, edge: TypedEdge) -> None:
        with self._lock:
            self.edges.append(edge)
            self._bump()

    # Terminal lifecycle states — no updates allowed from these.
    _TERMINAL_LIFECYCLES: frozenset[str] = frozenset({"retired", "posthoc_invalid", "falsified"})

    def update_belief(self, belief_id: str, **overrides: Any) -> BeliefNode | None:
        """Update a belief with field overrides. Returns updated node."""
        with self._lock:
            belief = self.beliefs.get(belief_id)
            if belief is None:
                return None
            if belief.lifecycle in self._TERMINAL_LIFECYCLES:
                return None
            updated = _dc.replace(belief, updated_at=time.perf_counter(), **overrides)
            self.beliefs[belief_id] = updated
            # Clean ordering lock on terminal transition
            new_lc = overrides.get("lifecycle")
            if new_lc in self._TERMINAL_LIFECYCLES:
                self._ordering_lock.pop(belief_id, None)
                self._invalidate_condensed_unlocked(belief_id)
            self._bump()
            return updated

    def evict_terminated(self, max_age_sec: float = 300.0) -> int:
        """Remove beliefs with terminal lifecycles older than max_age_sec.

        Also removes orphaned actions, feedbacks, probes, edges, and ordering entries.
        Returns count of evicted beliefs.
        """
        now = time.perf_counter()
        with self._lock:
            # Find beliefs to evict
            to_evict: set[str] = set()
            for bid, belief in list(self.beliefs.items()):
                if belief.lifecycle in self._TERMINAL_LIFECYCLES:
                    age = now - belief.updated_at
                    if age >= max_age_sec:
                        to_evict.add(bid)

            if not to_evict:
                return 0

            # Find actions where ALL driving beliefs are evicted
            action_to_evict: set[str] = set()
            for aid, action in list(self.actions.items()):
                if all(bid in to_evict for bid in action.belief_ids):
                    action_to_evict.add(aid)

            # Find feedbacks for evicted actions
            feedback_to_evict: set[str] = set()
            for fid, fb in list(self.feedbacks.items()):
                if fb.action_id in action_to_evict:
                    feedback_to_evict.add(fid)

            # Find probes for evicted beliefs
            probe_to_evict: set[str] = set()
            for pid, probe in list(self.probes.items()):
                if probe.belief_id in to_evict:
                    probe_to_evict.add(pid)

            # Remove edges referencing evicted nodes
            evicted_all = to_evict | action_to_evict | feedback_to_evict | probe_to_evict
            self.edges = [
                e for e in self.edges
                if e.source_id not in evicted_all and e.target_id not in evicted_all
            ]

            # Remove from dicts
            for bid in to_evict:
                self.beliefs.pop(bid, None)
                self._ordering_lock.pop(bid, None)
            for aid in action_to_evict:
                self.actions.pop(aid, None)
            for fid in feedback_to_evict:
                self.feedbacks.pop(fid, None)
            for pid in probe_to_evict:
                self.probes.pop(pid, None)

            self._bump()
            return len(to_evict)

    def _invalidate_condensed_unlocked(self, belief_id: str) -> list[str]:
        """Remove condensed nodes that reference a belief transitioning to terminal."""
        removed: list[str] = []
        for cid, node in list(self.condensed_nodes.items()):
            if belief_id in node.source_node_ids:
                del self.condensed_nodes[cid]
                self.edges = [e for e in self.edges if e.source_id != cid]
                removed.append(cid)
        return removed

    def update_action(self, action_id: str, **overrides: Any) -> ActionNode | None:
        with self._lock:
            action = self.actions.get(action_id)
            if action is None:
                return None
            updated = _dc.replace(action, updated_at=time.perf_counter(), **overrides)
            self.actions[action_id] = updated
            self._bump()
            return updated

    def update_probe(self, probe_id: str, **overrides: Any) -> ProbeNode | None:
        with self._lock:
            probe = self.probes.get(probe_id)
            if probe is None:
                return None
            updated = _dc.replace(probe, **overrides)
            self.probes[probe_id] = updated
            self._bump()
            return updated

    # -- Query methods --

    def actions_for_belief(self, belief_id: str) -> list[ActionNode]:
        with self._lock:
            return [a for a in self.actions.values() if belief_id in a.belief_ids]

    def feedbacks_for_action(self, action_id: str) -> list[FeedbackNode]:
        with self._lock:
            return [f for f in self.feedbacks.values() if f.action_id == action_id]

    def feedbacks_for_belief(self, belief_id: str) -> list[FeedbackNode]:
        """Collect all feedbacks for all actions driven by this belief."""
        with self._lock:
            result: list[FeedbackNode] = []
            for action in self.actions.values():
                if belief_id in action.belief_ids:
                    result.extend(
                        f for f in self.feedbacks.values() if f.action_id == action.action_id
                    )
            return result

    def downstream_beliefs(self, belief_id: str) -> list[str]:
        """BFS to find beliefs that depend on the given belief."""
        with self._lock:
            visited: set[str] = {belief_id}
            queue = deque([belief_id])
            result: list[str] = []
            while queue:
                current = queue.popleft()
                for edge in self.edges:
                    if edge.kind == "belief_depends_on_belief" and edge.target_id == current:
                        downstream_id = edge.source_id
                        if downstream_id not in visited and downstream_id in self.beliefs:
                            visited.add(downstream_id)
                            result.append(downstream_id)
                            queue.append(downstream_id)
            return result

    def suspect_beliefs(self) -> list[BeliefNode]:
        """Beliefs with falsification signals but not yet falsified."""
        with self._lock:
            return [b for b in self.beliefs.values() if b.lifecycle == "suspect"]

    def falsified_beliefs(self) -> list[BeliefNode]:
        with self._lock:
            return [b for b in self.beliefs.values() if b.lifecycle == "falsified"]

    def active_beliefs(self) -> list[BeliefNode]:
        with self._lock:
            return [
                b for b in self.beliefs.values()
                if b.lifecycle in ("committed", "confirmed", "provisional")
            ]

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "graph_id": self.graph_id,
                "mission_id": self.mission_id,
                "version": self.version,
                "beliefs": {k: _node_to_dict(v) for k, v in self.beliefs.items()},
                "actions": {k: _node_to_dict(v) for k, v in self.actions.items()},
                "feedbacks": {k: _node_to_dict(v) for k, v in self.feedbacks.items()},
                "probes": {k: _node_to_dict(v) for k, v in self.probes.items()},
                "bridges": {k: _node_to_dict(v) for k, v in self.bridges.items()},
                "condensed_nodes": {k: _node_to_dict(v) for k, v in self.condensed_nodes.items()},
                "edges": [_node_to_dict(e) for e in self.edges],
                "phase": self.phase,
            }

    def snapshot(self) -> dict[str, Any]:
        """Return a consistent point-in-time snapshot of all FIG data.

        The snapshot is a shallow copy of the internal dicts and lists,
        suitable for multi-query operations that need atomicity.
        """
        with self._lock:
            return {
                "beliefs": dict(self.beliefs),
                "actions": dict(self.actions),
                "feedbacks": dict(self.feedbacks),
                "probes": dict(self.probes),
                "bridges": dict(self.bridges),
                "condensed_nodes": dict(self.condensed_nodes),
                "edges": list(self.edges),
                "phase": self.phase,
            }

    # -- Internal --

    def _bump(self) -> None:
        self.version += 1


def _node_to_dict(node: Any) -> dict[str, Any]:
    """Convert a dataclass tree to JSON-safe primitive containers."""
    def _convert(value: Any) -> Any:
        if _dc.is_dataclass(value):
            return {
                f.name: _convert(getattr(value, f.name))
                for f in _dc.fields(value)
            }
        if isinstance(value, tuple):
            return [_convert(v) for v in value]
        if isinstance(value, list):
            return [_convert(v) for v in value]
        if isinstance(value, dict):
            return {str(k): _convert(v) for k, v in value.items()}
        return value

    if _dc.is_dataclass(node):
        return _convert(node)
    return {"value": str(node)}
