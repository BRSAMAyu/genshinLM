from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class LongRunPolicy:
    max_node_duration_s: float = 300.0
    safe_point_interval_s: float = 600.0
    max_memory_growth_mb_per_hour: float = 256.0
    max_stale_frame_rate: float = 0.1
    max_queue_depth: int = 4096
    require_window_revalidation: bool = True
    require_profile_revalidation: bool = True


@dataclass(frozen=True, slots=True)
class HealthSample:
    elapsed_s: float
    memory_growth_mb_per_hour: float = 0.0
    stale_frame_rate: float = 0.0
    queue_depth: int = 0
    active_leases: int = 0
    focus_ok: bool = True
    profile_ok: bool = True
    extra: dict[str, float | int | bool | str] = field(default_factory=dict)


class LongRunWatchdog:
    def __init__(self, policy: LongRunPolicy | None = None) -> None:
        self.policy = policy or LongRunPolicy()

    def evaluate(self, sample: HealthSample) -> list[str]:
        violations: list[str] = []
        if sample.memory_growth_mb_per_hour > self.policy.max_memory_growth_mb_per_hour:
            violations.append("memory_growth_exceeded")
        if sample.stale_frame_rate > self.policy.max_stale_frame_rate:
            violations.append("stale_frame_rate_exceeded")
        if sample.queue_depth > self.policy.max_queue_depth:
            violations.append("queue_depth_exceeded")
        if self.policy.require_window_revalidation and not sample.focus_ok:
            violations.append("window_revalidation_failed")
        if self.policy.require_profile_revalidation and not sample.profile_ok:
            violations.append("profile_revalidation_failed")
        if sample.elapsed_s > self.policy.max_node_duration_s and sample.active_leases > 0:
            violations.append("node_timeout_with_active_lease")
        return violations

    def should_enter_safe_point(self, elapsed_since_safe_point_s: float) -> bool:
        return elapsed_since_safe_point_s >= self.policy.safe_point_interval_s
