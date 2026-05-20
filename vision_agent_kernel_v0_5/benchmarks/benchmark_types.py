from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(slots=True)
class BenchmarkMetrics:
    frame_to_observation_ms: float = 0.0
    observation_to_interrupt_ms: float = 0.0
    interrupt_to_lease_ms: float = 0.0
    danger_clear_time_ms: float = 0.0
    danger_false_clear_rate: float = 0.0
    resume_success_rate: float = 0.0
    max_consecutive_dodges: int = 0
    final_task_success: bool = False
    evidence_coverage: float = 0.0


@dataclass(slots=True)
class BenchmarkResult:
    benchmark_id: str
    run_id: str
    suite_name: str
    scenario_name: str
    passed: bool
    metrics: BenchmarkMetrics
    evidence_ids: list[str] = field(default_factory=list)
    report: dict[str, object] = field(default_factory=dict)
