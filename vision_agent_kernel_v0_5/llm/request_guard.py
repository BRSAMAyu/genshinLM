from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class LLMUsageBudget:
    max_calls_per_minute: int = 6
    max_calls_per_task: int = 3
    max_estimated_tokens_per_task: int = 6000
    estimated_cost_units: int = 0
    calls_this_task: int = 0
    call_timestamps: list[float] = field(default_factory=list)


class LLMRequestGuard:
    def __init__(self, budget: LLMUsageBudget | None = None) -> None:
        self._budget = budget or LLMUsageBudget()

    def check(self, estimated_tokens: int = 1000) -> None:
        now = time.perf_counter()
        self._budget.call_timestamps = [item for item in self._budget.call_timestamps if now - item < 60.0]
        if len(self._budget.call_timestamps) >= self._budget.max_calls_per_minute:
            raise RuntimeError("LLM rate limit guard blocked request: max calls per minute reached")
        if self._budget.calls_this_task >= self._budget.max_calls_per_task:
            raise RuntimeError("LLM task budget guard blocked request: max calls per task reached")
        if self._budget.estimated_cost_units + estimated_tokens > self._budget.max_estimated_tokens_per_task:
            raise RuntimeError("LLM token/cost guard blocked request: estimated task budget exceeded")
        self._budget.call_timestamps.append(now)
        self._budget.calls_this_task += 1
        self._budget.estimated_cost_units += estimated_tokens

    def reset_task(self) -> None:
        self._budget.calls_this_task = 0
        self._budget.estimated_cost_units = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "max_calls_per_minute": self._budget.max_calls_per_minute,
            "max_calls_per_task": self._budget.max_calls_per_task,
            "calls_this_task": self._budget.calls_this_task,
            "estimated_cost_units": self._budget.estimated_cost_units,
            "max_estimated_tokens_per_task": self._budget.max_estimated_tokens_per_task,
        }
