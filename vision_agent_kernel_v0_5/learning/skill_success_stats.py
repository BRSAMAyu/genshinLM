from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SkillStats:
    skill_id: str
    total_runs: int = 0
    successes: int = 0
    total_duration_sec: float = 0.0
    common_failures: dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        return self.successes / self.total_runs if self.total_runs else 0.0


class SkillSuccessStats:
    def __init__(self) -> None:
        self._stats: dict[str, SkillStats] = {}

    def record(self, skill_id: str, success: bool, duration_sec: float, failure_code: str | None = None) -> SkillStats:
        stats = self._stats.setdefault(skill_id, SkillStats(skill_id))
        stats.total_runs += 1
        stats.successes += int(success)
        stats.total_duration_sec += duration_sec
        if failure_code:
            stats.common_failures[failure_code] = stats.common_failures.get(failure_code, 0) + 1
        return stats

