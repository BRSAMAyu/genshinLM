"""Evidence Matrix — BAGEL v1.1 non-symmetric causal activation.

The evidence matrix scores beliefs based on supporting (+1), refuting (-1),
neutral (0), and insufficient (NaN) signals. Unlike symmetric voting:

- A single core contradiction can veto many weak supporting signals.
- Irrelevant pass signals must be recorded as 0, not -1.
- Environment errors and insufficient signals are NaN (excluded from scoring).

Formula:
    M_ij in {+1, 0, -1, NaN}
    C_i = max_j(w_j * I[M_ij == +1])
    S_i = sum_j(w_j * I[M_ij == -1])
    R_i = sum_j(w_j * I[M_ij != 0])
    score_i = C_i - S_i + alpha * R_i / (epsilon + S_i)

Core probes with weight >= core_probe_veto_threshold triple the refute
weight, making S_i dominate the score (effective falsification veto).

Constraints:
- One core failure signal cannot be drowned by 100 irrelevant pass signals.
- Relevant survival signals can lower rank but not eliminate strong falsification.
- Multi-auditor high-conflict cannot average to a neutral conclusion.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Any, Literal

EvidenceValue = float  # +1.0, 0.0, -1.0, or float("nan")

EvidencePolarity = Literal["support", "refute", "neutral", "insufficient", "environment_error"]
NonDecidableSignal = Literal["timeout", "nan", "insufficient_signal", "flaky_result", "environment_error"]


@dataclass(frozen=True, slots=True)
class EvidenceSignal:
    """A single evidence signal for a belief."""
    signal_id: str
    belief_id: str
    polarity: EvidencePolarity
    weight: float = 1.0
    is_core_probe: bool = False
    auditor_id: str = ""
    source: str = ""
    description: str = ""

    @property
    def matrix_value(self) -> EvidenceValue:
        if self.polarity == "support":
            return 1.0
        if self.polarity == "refute":
            return -1.0
        if self.polarity == "neutral":
            return 0.0
        # insufficient / environment_error
        return float("nan")


@dataclass(frozen=True, slots=True)
class EvidenceScore:
    """Computed score for a belief from the evidence matrix."""
    belief_id: str
    score: float
    support_max: float
    refute_sum: float
    relevant_sum: float
    signal_count: int
    core_contradiction: bool
    conflict_detected: bool
    bounded_density_bonus: float = 0.0
    ifs_score: float = 0.0
    tvd_score: float = 0.0


@dataclass(frozen=True, slots=True)
class BoundedAsymmetricScore:
    """BAGEL v1.2 bounded activation components."""
    belief_id: str
    core_refute: float
    survival_mass: float
    related_density: float
    bounded_bonus: float
    score: float


@dataclass(frozen=True, slots=True)
class AuditorReliability:
    """Beta-Bernoulli cold-start reliability for an auditor."""
    auditor_id: str
    alpha: float = 1.0
    beta: float = 1.0
    min_weight: float = 0.1
    max_weight: float = 0.9

    @property
    def weight(self) -> float:
        raw = self.alpha / max(self.alpha + self.beta, 1e-9)
        return max(self.min_weight, min(self.max_weight, raw))

    def update(self, confirmed: bool) -> "AuditorReliability":
        if confirmed:
            return AuditorReliability(self.auditor_id, self.alpha + 1.0, self.beta, self.min_weight, self.max_weight)
        return AuditorReliability(self.auditor_id, self.alpha, self.beta + 1.0, self.min_weight, self.max_weight)


@dataclass(frozen=True, slots=True)
class ConflictCluster:
    """Tracks repeated non-decidable tie-breaker probes."""
    cluster_id: str
    belief_ids: tuple[str, ...]
    state: str = "decidable"
    non_decidable_count: int = 0
    taboo_probe_families: tuple[str, ...] = ()
    recommended_action: str = "continue_evidence_collection"


@dataclass(slots=True)
class EvidenceMatrix:
    """Matrix of evidence signals indexed by (belief, signal_source).

    Rows = beliefs, Columns = evidence sources.
    Cell values: +1 (support), -1 (refute), 0 (neutral), NaN (insufficient).
    """
    alpha: float = 0.1
    epsilon: float = 0.01
    core_probe_veto_threshold: float = 0.8
    conflict_threshold: float = 0.3

    _signals: dict[str, list[EvidenceSignal]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add_signal(self, signal: EvidenceSignal) -> None:
        with self._lock:
            self._signals.setdefault(signal.belief_id, []).append(signal)

    def add_signals(self, signals: list[EvidenceSignal]) -> None:
        with self._lock:
            for s in signals:
                self._signals.setdefault(s.belief_id, []).append(s)

    def score_belief(self, belief_id: str) -> EvidenceScore:
        """Compute the evidence score for a single belief."""
        with self._lock:
            signals = list(self._signals.get(belief_id, []))
        if not signals:
            return EvidenceScore(
                belief_id=belief_id, score=0.0,
                support_max=0.0, refute_sum=0.0, relevant_sum=0.0,
                signal_count=0, core_contradiction=False, conflict_detected=False,
            )

        support_weights: list[float] = []
        refute_weights: list[float] = []
        relevant_weights: list[float] = []
        core_contradiction = False

        for sig in signals:
            val = sig.matrix_value
            if math.isnan(val):
                continue
            if val > 0:
                w = sig.weight
                if sig.is_core_probe:
                    w *= 2.0  # Core probes have higher weight
                support_weights.append(w)
                relevant_weights.append(w)
            elif val < 0:
                w = sig.weight
                if sig.is_core_probe and w >= self.core_probe_veto_threshold:
                    core_contradiction = True
                    w *= 3.0  # Core contradiction is extremely strong
                refute_weights.append(w)
                relevant_weights.append(w)
            else:
                # neutral (0) — contributes to relevance count but not support/refute
                relevant_weights.append(sig.weight * 0.5)

        # C_i = max support weight
        c_i = max(support_weights) if support_weights else 0.0
        # S_i = sum refute weights
        s_i = sum(refute_weights)
        # R_i = sum relevant weights
        r_i = sum(relevant_weights)

        # Compute score: positive = belief likely correct, negative = belief likely wrong.
        # BAGEL v1.2 bounds the density term with tanh so hub beliefs cannot
        # dominate merely because many weakly related signals exist.
        bounded_bonus = self.alpha * math.tanh(r_i / (self.epsilon + s_i))
        if s_i > 0:
            score = c_i - s_i + bounded_bonus
        else:
            score = c_i + min(self.alpha, bounded_bonus)

        # Detect conflict: high support AND high refute
        conflict = (
            len(support_weights) > 0
            and len(refute_weights) > 0
            and abs(c_i - s_i) / max(c_i + s_i, self.epsilon) < self.conflict_threshold
        )

        return EvidenceScore(
            belief_id=belief_id,
            score=score,
            support_max=c_i,
            refute_sum=s_i,
            relevant_sum=r_i,
            signal_count=len(signals),
            core_contradiction=core_contradiction,
            conflict_detected=conflict,
            bounded_density_bonus=bounded_bonus,
        )

    def score_all(self) -> dict[str, EvidenceScore]:
        """Score all beliefs in the matrix."""
        with self._lock:
            belief_ids = list(self._signals.keys())
        return {bid: self.score_belief(bid) for bid in belief_ids}

    def top_suspects(self, limit: int = 10) -> list[EvidenceScore]:
        """Return beliefs sorted by most negative score (most falsified)."""
        scores = self.score_all()
        ranked = sorted(scores.values(), key=lambda s: s.score)
        return ranked[:limit]

    def clear(self) -> None:
        with self._lock:
            self._signals.clear()

    def signal_count(self, belief_id: str | None = None) -> int:
        with self._lock:
            if belief_id:
                return len(self._signals.get(belief_id, []))
            return sum(len(v) for v in self._signals.values())

    def signals_for(self, belief_id: str) -> list[EvidenceSignal]:
        with self._lock:
            return list(self._signals.get(belief_id, []))
