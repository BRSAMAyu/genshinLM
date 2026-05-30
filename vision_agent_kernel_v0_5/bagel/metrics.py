"""BAGEL v2.1 metric partitions.

Attribution, revision, and repair quality are deliberately measured separately
so the runtime does not confuse "found a likely cause" with "made a safe fix"
or "the task finally succeeded".
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AttributionMetrics:
    top1_attribution_accuracy: float = 0.0
    topk_attribution_accuracy: float = 0.0
    entropy_reduction: float = 0.0
    valid_probe_rate: float = 0.0
    non_decidable_rate: float = 0.0


@dataclass(frozen=True, slots=True)
class RevisionMetrics:
    safe_revision_rate: float = 0.0
    cascade_regression_rate: float = 0.0
    stale_jit_regeneration_rate: float = 0.0
    proxy_fidelity_pass_rate: float = 0.0


@dataclass(frozen=True, slots=True)
class RepairMetrics:
    final_repair_success_rate: float = 0.0
    recovery_after_first_failure: float = 0.0
    cost_to_success: float = 0.0
    full_retry_avoidance_rate: float = 0.0


@dataclass(frozen=True, slots=True)
class BagelThreeLayerMetrics:
    attribution: AttributionMetrics
    revision: RevisionMetrics
    repair: RepairMetrics
