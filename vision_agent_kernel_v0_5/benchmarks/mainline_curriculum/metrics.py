"""Benchmark Metrics — standard performance measurements.

Metric fields (from execution plan section 10.3):
- TSR: Task Success Rate
- VCR: Verification Coverage Rate
- HIC: Human Intervention Count
- RSR: Recovery Success Rate
- SRR: Skill Reliability Rate (Wilson lower bound)
- CTR: Claim Throughput Rate (claims/min)
- FSR: Falsification Success Rate
- CCR: Completion Rate (nodes completed / total nodes)
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MetricSnapshot:
    """Single benchmark run metrics."""
    task_id: str = ""
    variant: str = "full_system"
    tsr: float = 0.0
    vcr: float = 0.0
    hic: int = 0
    rsr: float = 0.0
    srr: float = 0.0
    ctr: float = 0.0
    fsr: float = 0.0
    ccr: float = 0.0
    time_to_success_sec: float = 0.0
    token_cost: int = 0
    claim_count: int = 0
    bagel_revisions: int = 0
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            object.__setattr__(self, "timestamp", time.perf_counter())

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "variant": self.variant,
            "tsr": self.tsr,
            "vcr": self.vcr,
            "hic": self.hic,
            "rsr": self.rsr,
            "srr": self.srr,
            "ctr": self.ctr,
            "fsr": self.fsr,
            "ccr": self.ccr,
            "time_to_success_sec": self.time_to_success_sec,
            "token_cost": self.token_cost,
            "claim_count": self.claim_count,
            "bagel_revisions": self.bagel_revisions,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass(slots=True)
class BenchmarkReport:
    """Aggregated report across multiple task runs."""
    variant: str = "full_system"
    task_metrics: list[MetricSnapshot] = field(default_factory=list)

    def add(self, metric: MetricSnapshot) -> None:
        self.task_metrics.append(metric)

    @property
    def overall_tsr(self) -> float:
        if not self.task_metrics:
            return 0.0
        return sum(m.tsr for m in self.task_metrics) / len(self.task_metrics)

    @property
    def bottleneck_task(self) -> str:
        """Task with lowest TSR. Ties broken by task_id for determinism."""
        if not self.task_metrics:
            return ""
        return min(self.task_metrics, key=lambda m: (m.tsr, m.task_id)).task_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "task_count": len(self.task_metrics),
            "overall_tsr": self.overall_tsr,
            "bottleneck_task": self.bottleneck_task,
            "tasks": [m.to_dict() for m in self.task_metrics],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
