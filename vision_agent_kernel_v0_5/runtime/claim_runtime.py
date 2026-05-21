from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Literal


RiskLevel = Literal["low", "medium", "high", "critical"]
ClaimStatus = Literal[
    "asserted", "tentative", "verified", "locked", "audited",
    "uncertain", "disputed", "suspect", "demoted", "reverified", "rejected", "expired",
    "error",
]
AuditStatus = Literal["pending", "matched", "mismatch", "contaminated", "unverifiable"]
CascadeAction = Literal["continue_with_warning", "revalidate_cluster", "pause_replan", "safe_abort_user_confirm"]
UncertaintyAction = Literal[
    "auto_execute",
    "resample_observation",
    "alternate_verifier",
    "safe_probe",
    "local_recovery",
    "human_confirm",
    "abort_safe",
]


_DEFAULT_STABILIZATION_MS = {
    "ui_screen_transition": 800,
    "dialogue_advance": 500,
    "inventory_delta": 1200,
    "collection_pickup": 900,
    "teleport_loaded": 1500,
    "navigation_arrival": 700,
    "combat_target_killed": 1200,
    "boss_phase_changed": 1800,
    "danger_cleared": 200,
    "generic_unknown": 1000,
}


@dataclass(frozen=True, slots=True)
class SignalEvidence:
    signal_id: str
    source: str
    confidence: float
    frame_id: int | None = None
    roi_id: str = ""
    timestamp: float = field(default_factory=time.time)
    spatial_quality: float = 1.0
    ocr_quality: float = 1.0
    detector_confidence: float = 1.0
    frame_consistency: float = 1.0
    temporal_pattern_match: float = 1.0
    cross_signal_agreement: float = 1.0

    def quality(self) -> float:
        values = [
            self.confidence,
            self.spatial_quality,
            self.ocr_quality,
            self.detector_confidence,
            self.frame_consistency,
            self.temporal_pattern_match,
            self.cross_signal_agreement,
        ]
        return _clamp(sum(_clamp(value) for value in values) / len(values))


@dataclass(frozen=True, slots=True)
class ConfidenceFactors:
    signal_quality: float
    verifier_historical_reliability: float
    context_match_score: float
    sample_sufficiency: float = 1.0
    drift_penalty: float = 1.0

    def compute(self) -> float:
        return _clamp(
            self.signal_quality
            * self.verifier_historical_reliability
            * self.context_match_score
            * self.sample_sufficiency
            * self.drift_penalty
        )


@dataclass(frozen=True, slots=True)
class ClaimTimeWindows:
    before_window: tuple[float, float] | None = None
    action_window: tuple[float, float] | None = None
    observation_window: tuple[float, float] | None = None
    confirmation_window: tuple[float, float] | None = None
    expiry: float | None = None


@dataclass(frozen=True, slots=True)
class StateDeltaClaim:
    claim_id: str
    mission_id: str
    node_id: str
    skill_id: str
    claim_type: str
    claimed_delta: dict[str, Any]
    status: ClaimStatus = "asserted"
    risk_level: RiskLevel = "medium"
    confidence: float = 0.0
    confidence_factors: ConfidenceFactors | None = None
    evidence_refs: list[str] = field(default_factory=list)
    signals: list[SignalEvidence] = field(default_factory=list)
    input_claims: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    inferred_depends_on: list[str] = field(default_factory=list)
    time_windows: ClaimTimeWindows = field(default_factory=ClaimTimeWindows)
    stabilization_window_ms: int = 1000
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def all_dependencies(self) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for claim_id in [*self.input_claims, *self.depends_on, *self.inferred_depends_on]:
            if claim_id and claim_id not in seen:
                ordered.append(claim_id)
                seen.add(claim_id)
        return ordered

    @staticmethod
    def stabilization_default(claim_type: str) -> int:
        return _DEFAULT_STABILIZATION_MS.get(claim_type, _DEFAULT_STABILIZATION_MS["generic_unknown"])

    @classmethod
    def from_signals(
        cls,
        *,
        claim_id: str,
        mission_id: str,
        node_id: str,
        skill_id: str,
        claim_type: str,
        claimed_delta: dict[str, Any],
        verifier_historical_reliability: float,
        context_match_score: float,
        sample_sufficiency: float = 1.0,
        drift_penalty: float = 1.0,
        signals: list[SignalEvidence] | None = None,
        **kwargs: Any,
    ) -> "StateDeltaClaim":
        signal_list = signals or []
        signal_quality = (
            sum(signal.quality() for signal in signal_list) / len(signal_list)
            if signal_list
            else 0.0
        )
        factors = ConfidenceFactors(
            signal_quality=signal_quality,
            verifier_historical_reliability=verifier_historical_reliability,
            context_match_score=context_match_score,
            sample_sufficiency=sample_sufficiency,
            drift_penalty=drift_penalty,
        )
        return cls(
            claim_id=claim_id,
            mission_id=mission_id,
            node_id=node_id,
            skill_id=skill_id,
            claim_type=claim_type,
            claimed_delta=claimed_delta,
            confidence=factors.compute(),
            confidence_factors=factors,
            signals=signal_list,
            stabilization_window_ms=cls.stabilization_default(claim_type),
            **kwargs,
        )


@dataclass(frozen=True, slots=True)
class ObservationClaim:
    observation_id: str
    claim_id: str
    source_family: str
    polarity: Literal["support", "refute", "neutral"]
    signal_quality: float
    frame_id: int | None = None
    roi_id: str = ""
    graph_node_refs: list[str] = field(default_factory=list)
    verifier_id: str = ""
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdjudicationEvent:
    adjudication_id: str
    claim_id: str
    old_status: ClaimStatus
    new_status: ClaimStatus
    reason: str
    confidence: float = 0.0
    evidence_votes_summary: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class DependencyGap:
    claim_id: str
    inferred_dependency: str
    code: str = "DEPENDENCY_DECLARATION_GAP"


@dataclass(frozen=True, slots=True)
class CascadeReport:
    root_claim_id: str
    affected_claims: list[str]
    dependency_gaps: list[DependencyGap] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CascadeDecision:
    action: CascadeAction
    affected_claims: list[str]
    reason: str


@dataclass(frozen=True, slots=True)
class FalseNegativeReport:
    upstream_claim_id: str
    downstream_claim_id: str
    revalidated: bool
    reason: str


class ClaimGraph:
    """Claim dependency graph with cluster-scoped invalidation.

    Three node types: StateDeltaClaim, ObservationClaim, AdjudicationEvent.
    Single-writer event loop + immutable snapshots for concurrency safety (Section 17.1).
    """

    def __init__(self) -> None:
        self._claims: dict[str, StateDeltaClaim] = {}
        self._observations: dict[str, ObservationClaim] = {}
        self._adjudications: dict[str, AdjudicationEvent] = {}
        self._children: dict[str, set[str]] = defaultdict(set)
        self._evidence: dict[str, list[str]] = defaultdict(list)
        self._dependency_gaps: list[DependencyGap] = []

    def add_claim(self, claim: StateDeltaClaim, inferred_dependencies: list[str] | None = None) -> list[DependencyGap]:
        gaps: list[DependencyGap] = []
        inferred = list(inferred_dependencies or [])
        missing = [dep for dep in inferred if dep not in claim.all_dependencies]
        if missing:
            claim = replace(claim, inferred_depends_on=[*claim.inferred_depends_on, *missing])
            gaps = [DependencyGap(claim.claim_id, dep) for dep in missing]
            self._dependency_gaps.extend(gaps)
        self._claims[claim.claim_id] = claim
        for dep in claim.all_dependencies:
            self._children[dep].add(claim.claim_id)
        return gaps

    def add_observation(self, obs: ObservationClaim) -> None:
        self._observations[obs.observation_id] = obs
        self._evidence[obs.claim_id].append(obs.observation_id)

    def add_adjudication(self, event: AdjudicationEvent) -> None:
        self._adjudications[event.adjudication_id] = event

    def get_observations_for(self, claim_id: str) -> list[ObservationClaim]:
        obs_ids = self._evidence.get(claim_id, [])
        return [self._observations[oid] for oid in obs_ids if oid in self._observations]

    def get_adjudications_for(self, claim_id: str) -> list[AdjudicationEvent]:
        return [e for e in self._adjudications.values() if e.claim_id == claim_id]

    @property
    def claim_count(self) -> int:
        return len(self._claims)

    @property
    def observation_count(self) -> int:
        return len(self._observations)

    def snapshot(self) -> dict[str, Any]:
        return {
            "claim_count": len(self._claims),
            "observation_count": len(self._observations),
            "adjudication_count": len(self._adjudications),
            "claims": {cid: c.status for cid, c in self._claims.items()},
            "latest_claim_id": max(self._claims.keys()) if self._claims else "",
        }

    def get(self, claim_id: str) -> StateDeltaClaim:
        return self._claims[claim_id]

    def get_optional(self, claim_id: str) -> StateDeltaClaim | None:
        return self._claims.get(claim_id)

    def update_claim(self, claim: StateDeltaClaim) -> None:
        self._claims[claim.claim_id] = claim

    def downstream(self, claim_id: str) -> list[str]:
        seen: set[str] = set()
        queue: deque[str] = deque(sorted(self._children.get(claim_id, set())))
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            queue.extend(sorted(self._children.get(current, set())))
        return sorted(seen)

    def demote(self, claim_id: str, reason: str = "audit_mismatch") -> CascadeReport:
        affected = [claim_id, *self.downstream(claim_id)]
        for current_id in affected:
            claim = self._claims[current_id]
            new_status: ClaimStatus = "demoted" if current_id == claim_id else "suspect"
            self._claims[current_id] = replace(
                claim,
                status=new_status,
                metadata={**claim.metadata, "demotion_reason": reason, "cascade_root": claim_id},
            )
        return CascadeReport(claim_id, affected, list(self._dependency_gaps))

    def cascade_decision(
        self,
        *,
        root_claim_id: str,
        decision_dependencies: list[str],
        risk_level: RiskLevel,
    ) -> CascadeDecision:
        affected = [root_claim_id, *self.downstream(root_claim_id)]
        if not set(decision_dependencies).intersection(affected):
            return CascadeDecision("continue_with_warning", affected, "decision_does_not_depend_on_affected_cluster")
        if risk_level == "low":
            return CascadeDecision("revalidate_cluster", affected, "low_risk_dependency_cluster_requires_revalidation")
        if risk_level in {"medium", "high"}:
            return CascadeDecision("pause_replan", affected, "dependent_decision_requires_replan")
        return CascadeDecision("safe_abort_user_confirm", affected, "critical_risk_dependency_invalidated")

    def revalidate_from_downstream(
        self,
        downstream_claim_id: str,
        verifier_fn: Callable[[StateDeltaClaim], bool] | None = None,
    ) -> list[FalseNegativeReport]:
        """If downstream claim is verified but upstream is demoted/suspect, re-evaluate upstream.

        This detects false negatives: the verifier said upstream failed, but downstream
        success implies the upstream was actually correct.
        """
        reports: list[FalseNegativeReport] = []
        downstream_claim = self._claims.get(downstream_claim_id)
        if downstream_claim is None or downstream_claim.status not in ("verified", "tentative"):
            return reports
        for parent_id in downstream_claim.all_dependencies:
            parent = self._claims.get(parent_id)
            if parent is None or parent.status not in ("demoted", "suspect"):
                continue
            revalidated = True
            if verifier_fn is not None:
                revalidated = verifier_fn(parent)
            if revalidated:
                self._claims[parent_id] = replace(
                    parent,
                    status="tentative",
                    metadata={**parent.metadata, "revalidated_from": downstream_claim_id},
                )
            reports.append(FalseNegativeReport(
                upstream_claim_id=parent_id,
                downstream_claim_id=downstream_claim_id,
                revalidated=revalidated,
                reason="downstream_verified_upstream_demoted" if not revalidated else "upstream_revalidated_via_downstream",
            ))
        return reports


@dataclass(frozen=True, slots=True)
class RiskThreshold:
    min_auto_execution_confidence: float
    min_auto_replan_confidence: float
    human_confirm: str


RISK_THRESHOLDS: dict[RiskLevel, RiskThreshold] = {
    "low": RiskThreshold(0.60, 0.50, "false"),
    "medium": RiskThreshold(0.70, 0.60, "when_uncertain_or_replan_loop"),
    "high": RiskThreshold(0.80, 0.70, "required_for_low_reliability_skill"),
    "critical": RiskThreshold(1.01, 1.01, "always"),
}


@dataclass(frozen=True, slots=True)
class ReplanOption:
    option_id: str
    confidence: float
    description: str = ""


@dataclass(frozen=True, slots=True)
class UncertaintyDecision:
    action: UncertaintyAction
    reason: str
    confidence: float
    max_wait_ms: int = 0


class UncertaintyPolicy:
    def __init__(self, max_replan_cycle_per_node: int = 3) -> None:
        self.max_replan_cycle_per_node = max_replan_cycle_per_node

    def decide(
        self,
        *,
        confidence: float,
        risk_level: RiskLevel,
        replan_count: int = 0,
        options: list[ReplanOption] | None = None,
        can_resample: bool = True,
        alternate_verifier_available: bool = False,
        safe_probe_available: bool = False,
        local_recovery_available: bool = False,
    ) -> UncertaintyDecision:
        threshold = RISK_THRESHOLDS[risk_level]
        if replan_count >= self.max_replan_cycle_per_node:
            return UncertaintyDecision("abort_safe", "max_replan_cycle_exceeded", confidence)
        if confidence >= threshold.min_auto_execution_confidence:
            return UncertaintyDecision("auto_execute", "confidence_above_risk_threshold", confidence)
        if options:
            best = max(option.confidence for option in options)
            if best < threshold.min_auto_replan_confidence:
                return UncertaintyDecision("human_confirm", "all_replan_options_below_threshold", confidence)
        if risk_level == "critical":
            return UncertaintyDecision("human_confirm", "critical_risk_requires_human_confirmation", confidence)
        if can_resample:
            return UncertaintyDecision("resample_observation", "first_uncertainty_exit", confidence, max_wait_ms=1500)
        if alternate_verifier_available:
            return UncertaintyDecision("alternate_verifier", "use_independent_verifier", confidence, max_wait_ms=2500)
        if safe_probe_available:
            return UncertaintyDecision("safe_probe", "probe_without_committing_terminal_success", confidence, max_wait_ms=2000)
        if local_recovery_available:
            return UncertaintyDecision("local_recovery", "local_recovery_before_llm_replan", confidence, max_wait_ms=5000)
        return UncertaintyDecision("human_confirm", "uncertainty_exits_exhausted", confidence)


@dataclass(frozen=True, slots=True)
class AuditSnapshot:
    inventory_before: dict[str, int] = field(default_factory=dict)
    position_before: dict[str, float] = field(default_factory=dict)
    screen_state_before: str = ""
    team_state_before: dict[str, Any] = field(default_factory=dict)
    active_task_before: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DelayedAuditRecord:
    audit_id: str
    claim_id: str
    skill_id: str
    status: AuditStatus
    snapshot: AuditSnapshot
    expected_delta: dict[str, Any]
    observed_delta: dict[str, Any] = field(default_factory=dict)
    contamination_reasons: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None


class DelayedAuditEngine:
    def create_record(
        self,
        *,
        audit_id: str,
        claim: StateDeltaClaim,
        snapshot: AuditSnapshot,
    ) -> DelayedAuditRecord:
        return DelayedAuditRecord(
            audit_id=audit_id,
            claim_id=claim.claim_id,
            skill_id=claim.skill_id,
            status="pending",
            snapshot=snapshot,
            expected_delta=claim.claimed_delta,
        )

    def complete(
        self,
        record: DelayedAuditRecord,
        observed_delta: dict[str, Any],
        contamination_reasons: list[str] | None = None,
    ) -> DelayedAuditRecord:
        contamination = contamination_reasons or []
        if contamination:
            status: AuditStatus = "contaminated"
        elif observed_delta == record.expected_delta:
            status = "matched"
        else:
            status = "mismatch"
        return replace(
            record,
            status=status,
            observed_delta=observed_delta,
            contamination_reasons=contamination,
            completed_at=time.time(),
        )


@dataclass(frozen=True, slots=True)
class AuditDifficultyStatus:
    skill_id: str
    contaminated_rate: float
    total_audits: int
    audit_difficult: bool
    recommendation: str


class AuditDifficultyTracker:
    def __init__(self, threshold: float = 0.5, min_total: int = 4, low_activity_retry_limit: int = 3) -> None:
        self.threshold = threshold
        self.min_total = min_total
        self.low_activity_retry_limit = low_activity_retry_limit
        self._counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def record(self, skill_id: str, status: AuditStatus, *, low_activity_retry: bool = False) -> AuditDifficultyStatus:
        self._counts[skill_id]["total"] += 1
        self._counts[skill_id][status] += 1
        if low_activity_retry:
            self._counts[skill_id]["low_activity_retries"] += 1
        return self.status(skill_id)

    def status(self, skill_id: str) -> AuditDifficultyStatus:
        counts = self._counts[skill_id]
        total = counts["total"]
        contaminated_rate = counts["contaminated"] / total if total else 0.0
        difficult = (
            total >= self.min_total
            and contaminated_rate > self.threshold
            and counts["low_activity_retries"] >= self.low_activity_retry_limit
        )
        if difficult:
            recommendation = "mark_audit_difficult"
        elif total >= self.min_total and contaminated_rate > self.threshold:
            recommendation = "switch_to_low_activity_window_audit"
        else:
            recommendation = "continue_standard_audit"
        return AuditDifficultyStatus(skill_id, contaminated_rate, total, difficult, recommendation)


@dataclass(frozen=True, slots=True)
class ReliabilityEstimate:
    skill_id: str
    reliability: float
    level_used: int
    total: int
    successes: int
    sample_sufficient: bool
    drift_penalty: float = 1.0


class ReliabilityStore:
    def __init__(self, min_samples: int = 5) -> None:
        self.min_samples = min_samples
        self._counts: dict[tuple[str, tuple[str, ...]], dict[str, int]] = defaultdict(lambda: {"success": 0, "total": 0})
        self._drift_demoted_skills: set[str] = set()

    def record(self, skill_id: str, context: dict[str, str], outcome: AuditStatus) -> None:
        if outcome == "contaminated":
            return
        success = 1 if outcome == "matched" else 0
        for level in range(0, 6):
            key = self._context_key(skill_id, context, level)
            self._counts[(skill_id, key)]["success"] += success
            self._counts[(skill_id, key)]["total"] += 1

    def estimate(self, skill_id: str, context: dict[str, str], preferred_level: int = 3) -> ReliabilityEstimate:
        for level in range(preferred_level, -1, -1):
            key = self._context_key(skill_id, context, level)
            counts = self._counts.get((skill_id, key), {"success": 0, "total": 0})
            if counts["total"] >= self.min_samples or level == 0:
                lower = wilson_lower_bound(counts["success"], counts["total"])
                sufficient = counts["total"] >= self.min_samples
                sufficiency = min(1.0, counts["total"] / self.min_samples) if self.min_samples else 1.0
                drift_penalty = 0.5 if skill_id in self._drift_demoted_skills else 1.0
                return ReliabilityEstimate(
                    skill_id=skill_id,
                    reliability=_clamp(lower * sufficiency * drift_penalty),
                    level_used=level,
                    total=counts["total"],
                    successes=counts["success"],
                    sample_sufficient=sufficient,
                    drift_penalty=drift_penalty,
                )
        return ReliabilityEstimate(skill_id, 0.0, 0, 0, 0, False)

    def mark_version_drift(self, skill_id: str) -> None:
        self._drift_demoted_skills.add(skill_id)

    @staticmethod
    def _context_key(skill_id: str, context: dict[str, str], level: int) -> tuple[str, ...]:
        if level == 0:
            return ("global", skill_id)
        parts = [context.get("capsule_id", "core"), skill_id]
        if level >= 2:
            parts.extend([context.get("screen_state", ""), context.get("mission_phase", "")])
        if level >= 3:
            parts.append(context.get("target_class", ""))
        if level >= 4:
            parts.append(context.get("profile_bucket", ""))
        if level >= 5:
            game_specific = context.get("game_specific", "")
            parts.append(game_specific)
        return tuple(parts)


@dataclass(frozen=True, slots=True)
class StabilizationEstimate:
    claim_type: str
    current_window_ms: int
    sample_count: int
    failure_rate: float
    recommended_window_ms: int


class StabilizationTracker:
    """Auto-adjust stabilization windows based on historical failure rates.

    If the next action after a claim frequently fails, the window is too short.
    If it's consistently stable, the window can be slowly reduced.
    """

    _MAX_SAMPLES_PER_TYPE = 200

    def __init__(
        self,
        defaults: dict[str, int] | None = None,
        min_window_ms: int = 200,
        max_window_ms: int = 5000,
        increase_factor: float = 1.3,
        decrease_factor: float = 0.95,
        min_samples: int = 5,
    ) -> None:
        self._defaults = defaults or dict(_DEFAULT_STABILIZATION_MS)
        self._min = min_window_ms
        self._max = max_window_ms
        self._increase = increase_factor
        self._decrease = decrease_factor
        self._min_samples = min_samples
        self._samples: dict[str, deque[bool]] = defaultdict(lambda: deque(maxlen=self._MAX_SAMPLES_PER_TYPE))
        self._current_windows: dict[str, int] = dict(self._defaults)

    def record(self, claim_type: str, next_action_succeeded: bool) -> StabilizationEstimate:
        self._samples[claim_type].append(next_action_succeeded)
        samples = self._samples[claim_type]
        if len(samples) < self._min_samples:
            return self.estimate(claim_type)
        failure_rate = 1.0 - (sum(samples) / len(samples))
        current = self._current_windows.get(claim_type, self._defaults.get(claim_type, 1000))
        if failure_rate > 0.2:
            new_window = min(self._max, int(current * self._increase))
        elif failure_rate < 0.05:
            new_window = max(
                self._defaults.get(claim_type, 1000),
                int(current * self._decrease),
            )
        else:
            new_window = current
        self._current_windows[claim_type] = new_window
        return StabilizationEstimate(
            claim_type=claim_type,
            current_window_ms=new_window,
            sample_count=len(samples),
            failure_rate=failure_rate,
            recommended_window_ms=new_window,
        )

    def estimate(self, claim_type: str) -> StabilizationEstimate:
        current = self._current_windows.get(claim_type, self._defaults.get(claim_type, 1000))
        samples = self._samples.get(claim_type, [])
        failure_rate = 1.0 - (sum(samples) / len(samples)) if samples else 0.0
        return StabilizationEstimate(
            claim_type=claim_type,
            current_window_ms=current,
            sample_count=len(samples),
            failure_rate=failure_rate,
            recommended_window_ms=current,
        )


# Canonical DriftDetector lives in reliability/drift_detector.py.
# Kept here for backward compat with existing tests importing from runtime.claim_runtime.

@dataclass(frozen=True, slots=True)
class DriftSignal:
    signal_id: str
    detector_type: str
    score: float
    description: str


@dataclass(frozen=True, slots=True)
class DriftReport:
    drifted: bool
    signals: list[DriftSignal]
    affected_skills: list[str]
    recommendation: str


class DriftDetector:
    """Detect environment version changes that invalidate historical reliability.

    Checks for layout shifts, OCR anchor shifts, template match drops,
    color distribution shifts, and detector confidence drops.
    """

    def __init__(
        self,
        layout_shift_threshold: float = 0.3,
        ocr_shift_threshold: float = 0.25,
        template_drop_threshold: float = 0.3,
        confidence_drop_threshold: float = 0.2,
    ) -> None:
        self.layout_shift_threshold = layout_shift_threshold
        self.ocr_shift_threshold = ocr_shift_threshold
        self.template_drop_threshold = template_drop_threshold
        self.confidence_drop_threshold = confidence_drop_threshold
        self._baselines: dict[str, dict[str, float]] = {}

    def set_baseline(self, component_id: str, metrics: dict[str, float]) -> None:
        self._baselines[component_id] = dict(metrics)

    def check(
        self,
        component_id: str,
        current_metrics: dict[str, float],
        affected_skills: list[str] | None = None,
    ) -> DriftReport:
        baseline = self._baselines.get(component_id)
        if baseline is None:
            return DriftReport(False, [], [], "no_baseline")
        signals: list[DriftSignal] = []
        for metric_name, current_value in current_metrics.items():
            baseline_value = baseline.get(metric_name)
            if baseline_value is None:
                continue
            delta = abs(current_value - baseline_value)
            threshold = self._pick_threshold(metric_name)
            if delta > threshold:
                signals.append(DriftSignal(
                    signal_id=f"{component_id}:{metric_name}",
                    detector_type=self._classify_metric(metric_name),
                    score=delta,
                    description=f"{metric_name}: baseline={baseline_value:.3f} current={current_value:.3f} delta={delta:.3f}",
                ))
        drifted = len(signals) > 0
        skills = affected_skills or []
        recommendation = "invalidate_and_bootstrap" if drifted else "stable"
        return DriftReport(drifted, signals, skills, recommendation)

    def _pick_threshold(self, metric_name: str) -> float:
        name = metric_name.lower()
        if "layout" in name or "position" in name:
            return self.layout_shift_threshold
        if "ocr" in name or "anchor" in name:
            return self.ocr_shift_threshold
        if "template" in name or "match" in name:
            return self.template_drop_threshold
        if "confidence" in name or "detection" in name:
            return self.confidence_drop_threshold
        return 0.3

    @staticmethod
    def _classify_metric(metric_name: str) -> str:
        name = metric_name.lower()
        if "layout" in name or "position" in name:
            return "layout_shift"
        if "ocr" in name or "anchor" in name:
            return "ocr_anchor_shift"
        if "template" in name or "match" in name:
            return "template_match_drop"
        if "confidence" in name or "detection" in name:
            return "detector_confidence_drop"
        return "unknown"


@dataclass(frozen=True, slots=True)
class GateDecision:
    allowed: bool
    requires_human_confirm: bool
    reason: str
    estimate: ReliabilityEstimate
    threshold: RiskThreshold


class CapabilityReliabilityGate:
    def __init__(self, store: ReliabilityStore) -> None:
        self.store = store

    def evaluate(self, skill_id: str, context: dict[str, str], risk_level: RiskLevel) -> GateDecision:
        estimate = self.store.estimate(skill_id, context)
        threshold = RISK_THRESHOLDS[risk_level]
        if risk_level == "critical":
            return GateDecision(False, True, "critical_risk_requires_human_confirmation", estimate, threshold)
        if estimate.reliability >= threshold.min_auto_execution_confidence:
            return GateDecision(True, False, "reliability_above_threshold", estimate, threshold)
        if risk_level == "high":
            return GateDecision(False, True, "high_risk_low_reliability_requires_confirmation", estimate, threshold)
        return GateDecision(False, False, "reliability_below_threshold", estimate, threshold)


@dataclass(frozen=True, slots=True)
class RunJournalEntry:
    decision_id: str
    mission_id: str
    goal: str
    action: str
    expected_delta: dict[str, Any]
    actual_delta: dict[str, Any] = field(default_factory=dict)
    claim_id: str = ""
    outcome: str = ""
    failure_reason: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    context: dict[str, str] = field(default_factory=dict)
    alternatives_rejected: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DecisionMemoryPacket:
    current_goal: str
    last_successful_approach: str
    current_obstacle: str
    recovery_options: list[str]
    confidence_this_works: float
    do_not_repeat: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)


class EpisodeAnalyzer:
    """Distill raw RunJournal entries into LLM-facing decision memory."""

    def summarize(self, entries: list[RunJournalEntry], current_goal: str) -> DecisionMemoryPacket:
        relevant = [entry for entry in entries if entry.goal == current_goal]
        successes = [entry for entry in relevant if entry.outcome in {"matched", "verified", "success"}]
        failures = [entry for entry in relevant if entry.outcome in {"mismatch", "failed", "demoted"}]
        last_success = successes[-1] if successes else None
        last_failure = failures[-1] if failures else None
        success_rate = len(successes) / len(relevant) if relevant else 0.0
        recovery_options = sorted({entry.action for entry in successes[-3:]}) or ["ask_user"]
        return DecisionMemoryPacket(
            current_goal=current_goal,
            last_successful_approach=last_success.action if last_success else "none_recorded",
            current_obstacle=last_failure.failure_reason if last_failure else "",
            recovery_options=recovery_options,
            confidence_this_works=_clamp(success_rate),
            do_not_repeat=[entry.action for entry in failures[-3:]],
            evidence_refs=[ref for entry in relevant[-5:] for ref in entry.evidence_refs],
        )


@dataclass(frozen=True, slots=True)
class PlanCandidate:
    plan_id: str
    skill_ids: list[str]
    dependency_edges: list[tuple[str, str]]
    repeated_failed_paths: list[str] = field(default_factory=list)
    missing_preconditions: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PlanQualityResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


class PlanQualityChecklist:
    def validate(
        self,
        candidate: PlanCandidate,
        reliability_lookup: Callable[[str], float],
        min_skill_reliability: float = 0.6,
    ) -> PlanQualityResult:
        errors: list[str] = []
        for skill_id in candidate.skill_ids:
            if reliability_lookup(skill_id) < min_skill_reliability:
                errors.append(f"low_reliability_skill:{skill_id}")
        if candidate.missing_preconditions:
            errors.extend(f"missing_precondition:{item}" for item in candidate.missing_preconditions)
        if candidate.repeated_failed_paths:
            errors.extend(f"repeated_failed_path:{item}" for item in candidate.repeated_failed_paths)
        if self._has_cycle(candidate.dependency_edges):
            errors.append("plan_cycle_detected")
        return PlanQualityResult(ok=not errors, errors=errors)

    @staticmethod
    def _has_cycle(edges: list[tuple[str, str]]) -> bool:
        graph: dict[str, list[str]] = defaultdict(list)
        nodes: set[str] = set()
        for src, dst in edges:
            graph[src].append(dst)
            nodes.add(src)
            nodes.add(dst)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            for nxt in graph.get(node, []):
                if visit(nxt):
                    return True
            visiting.remove(node)
            visited.add(node)
            return False

        return any(visit(node) for node in nodes)


def wilson_lower_bound(successes: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    phat = successes / total
    denominator = 1 + z * z / total
    centre = phat + z * z / (2 * total)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total)
    return _clamp((centre - margin) / denominator)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(frozen=True, slots=True)
class ClaimExecutionResult:
    claim: StateDeltaClaim
    gate_decision: GateDecision
    audit_record: DelayedAuditRecord | None
    uncertainty_decision: UncertaintyDecision | None
    journal_entry: RunJournalEntry


class ClaimProducingExecutor:
    """Bridge between skill execution and the Claim-Centric Runtime.

    Orchestrates: pre-flight gate check → claim production → verification →
    audit creation → reliability update → journal recording.
    """

    def __init__(
        self,
        *,
        claim_graph: ClaimGraph | None = None,
        reliability_store: ReliabilityStore | None = None,
        uncertainty_policy: UncertaintyPolicy | None = None,
        audit_engine: DelayedAuditEngine | None = None,
        episode_analyzer: EpisodeAnalyzer | None = None,
        stabilization_tracker: StabilizationTracker | None = None,
    ) -> None:
        self.claim_graph = claim_graph or ClaimGraph()
        self.reliability_store = reliability_store or ReliabilityStore()
        self.gate = CapabilityReliabilityGate(self.reliability_store)
        self.uncertainty_policy = uncertainty_policy or UncertaintyPolicy()
        self.audit_engine = audit_engine or DelayedAuditEngine()
        self.episode_analyzer = episode_analyzer or EpisodeAnalyzer()
        self.stabilization_tracker = stabilization_tracker or StabilizationTracker()
        self._replan_counts: dict[str, int] = defaultdict(int)
        self._journal: list[RunJournalEntry] = []

    def pre_flight(
        self,
        skill_id: str,
        context: dict[str, str],
        risk_level: RiskLevel,
        node_id: str = "",
    ) -> tuple[GateDecision, UncertaintyDecision]:
        gate_decision = self.gate.evaluate(skill_id, context, risk_level)
        replan_count = self._replan_counts.get(node_id, 0)
        uncertainty_decision = self.uncertainty_policy.decide(
            confidence=gate_decision.estimate.reliability,
            risk_level=risk_level,
            replan_count=replan_count,
        )
        return gate_decision, uncertainty_decision

    def produce_claim(
        self,
        *,
        claim_id: str,
        mission_id: str,
        node_id: str,
        skill_id: str,
        claim_type: str,
        claimed_delta: dict[str, Any],
        risk_level: RiskLevel = "medium",
        context: dict[str, str] | None = None,
        signals: list[SignalEvidence] | None = None,
        input_claims: list[str] | None = None,
        inferred_dependencies: list[str] | None = None,
        snapshot: AuditSnapshot | None = None,
    ) -> ClaimExecutionResult:
        ctx = context or {}
        gate_decision = self.gate.evaluate(skill_id, ctx, risk_level)
        estimate = gate_decision.estimate
        replan_count = self._replan_counts.get(node_id, 0)
        uncertainty_decision = self.uncertainty_policy.decide(
            confidence=estimate.reliability,
            risk_level=risk_level,
            replan_count=replan_count,
        )
        context_match = min(1.0, estimate.total / max(1, self.reliability_store.min_samples))
        claim = StateDeltaClaim.from_signals(
            claim_id=claim_id,
            mission_id=mission_id,
            node_id=node_id,
            skill_id=skill_id,
            claim_type=claim_type,
            claimed_delta=claimed_delta,
            verifier_historical_reliability=estimate.reliability,
            context_match_score=context_match,
            sample_sufficiency=min(1.0, estimate.total / max(1, self.reliability_store.min_samples)),
            drift_penalty=estimate.drift_penalty,
            signals=signals,
            input_claims=input_claims or [],
            risk_level=risk_level,
        )
        stab = self.stabilization_tracker.estimate(claim_type)
        claim = replace(claim, stabilization_window_ms=stab.current_window_ms)
        self.claim_graph.add_claim(claim, inferred_dependencies=inferred_dependencies)
        audit_record: DelayedAuditRecord | None = None
        if snapshot is not None:
            audit_record = self.audit_engine.create_record(
                audit_id=f"audit_{claim_id}", claim=claim, snapshot=snapshot,
            )
        journal_entry = RunJournalEntry(
            decision_id=f"d_{claim_id}",
            mission_id=mission_id,
            goal=claimed_delta.get("goal", ""),
            action=skill_id,
            expected_delta=claimed_delta,
            outcome="asserted",
            claim_id=claim_id,
            context=ctx,
        )
        self._journal.append(journal_entry)
        return ClaimExecutionResult(
            claim=claim,
            gate_decision=gate_decision,
            audit_record=audit_record,
            uncertainty_decision=uncertainty_decision,
            journal_entry=journal_entry,
        )

    def verify_claim(
        self,
        claim_id: str,
        ok: bool,
        actual_delta: dict[str, Any] | None = None,
        audit_record: DelayedAuditRecord | None = None,
        context: dict[str, str] | None = None,
    ) -> StateDeltaClaim:
        claim = self.claim_graph.get(claim_id)
        new_status: ClaimStatus = "verified" if ok else "demoted"
        claim = replace(claim, status=new_status)
        self.claim_graph.update_claim(claim)
        if not ok:
            self.claim_graph.demote(claim_id, reason="verifier_rejected")
            self._replan_counts[claim.node_id] = self._replan_counts.get(claim.node_id, 0) + 1
        if actual_delta is not None and audit_record is not None:
            completed = self.audit_engine.complete(audit_record, actual_delta)
            if completed.status == "matched":
                self.reliability_store.record(claim.skill_id, context or {}, "matched")
            elif completed.status == "mismatch":
                self.reliability_store.record(claim.skill_id, context or {}, "mismatch")
        if ok:
            self.stabilization_tracker.record(claim.claim_type, True)
            reports = self.claim_graph.revalidate_from_downstream(claim_id)
            for report in reports:
                if report.revalidated:
                    self.stabilization_tracker.record(claim.claim_type, True)
        else:
            self.stabilization_tracker.record(claim.claim_type, False)
        return self.claim_graph.get(claim_id)

    @property
    def journal(self) -> list[RunJournalEntry]:
        return list(self._journal)

    def summarize_for_llm(self, current_goal: str) -> DecisionMemoryPacket:
        return self.episode_analyzer.summarize(self._journal, current_goal)
