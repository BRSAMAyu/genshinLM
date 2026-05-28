"""Finite-sample feedback-shift estimators for BAGEL v1.2.

The theory keeps mutual information as an ideal target, but the runtime uses
observable shifts from probes, replays, or regression checks.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class FeedbackShiftResult:
    belief_id: str
    ifs_score: float
    tvd_score: float
    sample_count: int
    attributed: bool


def single_probe_ifs(
    *,
    belief_id: str,
    before_failure: str,
    after_failure: str,
    signal_quality: float,
    threshold: float = 0.2,
) -> FeedbackShiftResult:
    """Single-probe IFS: changed feedback times signal quality."""
    quality = max(0.0, min(1.0, float(signal_quality)))
    ifs = quality if before_failure != after_failure else 0.0
    return FeedbackShiftResult(
        belief_id=belief_id,
        ifs_score=ifs,
        tvd_score=ifs,
        sample_count=1,
        attributed=ifs > threshold,
    )


def discrete_tvd(
    *,
    belief_id: str,
    before: Iterable[str],
    after: Iterable[str],
    threshold: float = 0.2,
) -> FeedbackShiftResult:
    """Discrete total-variation distance over finite feedback labels."""
    before_counts = Counter(before)
    after_counts = Counter(after)
    before_total = max(sum(before_counts.values()), 1)
    after_total = max(sum(after_counts.values()), 1)
    labels = set(before_counts) | set(after_counts)
    tvd = 0.5 * sum(
        abs(before_counts[label] / before_total - after_counts[label] / after_total)
        for label in labels
    )
    return FeedbackShiftResult(
        belief_id=belief_id,
        ifs_score=tvd,
        tvd_score=tvd,
        sample_count=before_total + after_total,
        attributed=tvd > threshold,
    )
