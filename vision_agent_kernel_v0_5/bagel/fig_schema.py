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
]

EdgeKind = Literal[
    "belief_drives_action",
    "action_produces_feedback",
    "feedback_tests_belief",
    "probe_tests_belief",
    "belief_depends_on_belief",
    "belief_conflicts_belief",
    "action_alternative_to_action",
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
    edges: list[TypedEdge] = field(default_factory=list)
    version: int = 0
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
            self._bump()
            return updated

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
        """BFS to find beliefs that depend on the given belief.

        Edge direction: (dependent, dependency), so target_id == current means
        source_id depends on current, i.e., source_id is downstream.
        """
        with self._lock:
            visited: set[str] = {belief_id}
            queue = [belief_id]
            result: list[str] = []
            while queue:
                current = queue.pop(0)
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
                "edges": [_node_to_dict(e) for e in self.edges],
            }

    # -- Internal --

    def _bump(self) -> None:
        self.version += 1


def _node_to_dict(node: Any) -> dict[str, Any]:
    """Convert a frozen dataclass to a dict, handling tuples."""
    if _dc.is_dataclass(node):
        result = {}
        for f in _dc.fields(node):
            val = getattr(node, f.name)
            if isinstance(val, tuple) and val and isinstance(val[0], (str, int, float)):
                result[f.name] = list(val)
            elif hasattr(val, "to_dict"):
                result[f.name] = val.to_dict()
            else:
                result[f.name] = val
        return result
    return {"value": str(node)}
