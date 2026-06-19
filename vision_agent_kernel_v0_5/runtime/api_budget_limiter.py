"""Global API budget limiter — prevents runaway API spending.

Tracks API call counts and estimated costs per session with configurable limits.
When budget is exhausted, calls are rejected with BudgetExhausted rather than silently
passing through.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

log = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class BudgetEntry:
    """A single API call record."""
    api_name: str
    model: str
    timestamp: float
    estimated_cost_usd: float
    input_tokens: int = 0
    output_tokens: int = 0


class BudgetExhausted(Exception):
    """Raised when an API call would exceed the budget limit."""


@dataclass(slots=True)
class BudgetConfig:
    """Configuration for the budget limiter."""
    max_calls_per_session: int = 500
    max_cost_usd_per_session: float = 10.0
    max_calls_per_minute: int = 60
    max_calls_per_api_per_session: dict[str, int] = field(default_factory=dict)


class ApiBudgetLimiter:
    """Global API budget limiter with per-session and per-minute tracking."""

    def __init__(self, config: BudgetConfig | None = None) -> None:
        self._config = config or BudgetConfig()
        self._lock = Lock()
        self._entries: list[BudgetEntry] = []
        self._total_cost: float = 0.0
        self._session_start: float = time.perf_counter()

    @property
    def total_calls(self) -> int:
        return len(self._entries)

    @property
    def total_cost_usd(self) -> float:
        return self._total_cost

    @property
    def remaining_budget_usd(self) -> float:
        return max(0.0, self._config.max_cost_usd_per_session - self._total_cost)

    @property
    def remaining_calls(self) -> int:
        return max(0, self._config.max_calls_per_session - len(self._entries))

    def check_budget(self, api_name: str, estimated_cost: float = 0.0) -> None:
        """Check if a call is within budget. Raises BudgetExhausted if not."""
        with self._lock:
            # Per-session call limit
            if len(self._entries) >= self._config.max_calls_per_session:
                raise BudgetExhausted(
                    f"Session call limit reached: {len(self._entries)}/{self._config.max_calls_per_session}"
                )

            # Per-session cost limit
            if self._total_cost + estimated_cost > self._config.max_cost_usd_per_session:
                raise BudgetExhausted(
                    f"Session cost limit reached: ${self._total_cost:.4f} + "
                    f"${estimated_cost:.4f} > ${self._config.max_cost_usd_per_session:.2f}"
                )

            # Per-minute rate limit
            now = time.perf_counter()
            recent_calls = sum(
                1 for e in self._entries if now - e.timestamp < 60.0
            )
            if recent_calls >= self._config.max_calls_per_minute:
                raise BudgetExhausted(
                    f"Rate limit reached: {recent_calls} calls in the last minute"
                )

            # Per-API limit
            api_limit = self._config.max_calls_per_api_per_session.get(api_name)
            if api_limit is not None:
                api_calls = sum(1 for e in self._entries if e.api_name == api_name)
                if api_calls >= api_limit:
                    raise BudgetExhausted(
                        f"API limit for {api_name}: {api_calls}/{api_limit}"
                    )

    def record_call(
        self,
        api_name: str,
        model: str = "",
        estimated_cost_usd: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> BudgetEntry:
        """Record an API call. Checks budget first, then records."""
        self.check_budget(api_name, estimated_cost_usd)

        with self._lock:
            entry = BudgetEntry(
                api_name=api_name,
                model=model,
                timestamp=time.perf_counter(),
                estimated_cost_usd=estimated_cost_usd,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            self._entries.append(entry)
            self._total_cost += estimated_cost_usd

        if self._total_cost > self._config.max_cost_usd_per_session * 0.8:
            log.warning(
                "[ApiBudget] %.0f%% of budget used: $%.4f / $%.2f",
                self._total_cost / self._config.max_cost_usd_per_session * 100,
                self._total_cost,
                self._config.max_cost_usd_per_session,
            )

        return entry

    def try_record_call(
        self,
        api_name: str,
        model: str = "",
        estimated_cost_usd: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> BudgetEntry | None:
        """Try to record a call. Returns None if budget exhausted (no exception)."""
        try:
            return self.record_call(api_name, model, estimated_cost_usd, input_tokens, output_tokens)
        except BudgetExhausted:
            return None

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of budget usage."""
        with self._lock:
            by_api: dict[str, int] = {}
            for e in self._entries:
                by_api[e.api_name] = by_api.get(e.api_name, 0) + 1

            elapsed = time.perf_counter() - self._session_start
            return {
                "total_calls": len(self._entries),
                "total_cost_usd": round(self._total_cost, 4),
                "remaining_calls": self.remaining_calls,
                "remaining_budget_usd": round(self.remaining_budget_usd, 4),
                "elapsed_sec": round(elapsed, 1),
                "calls_per_api": by_api,
                "budget_utilization_pct": round(
                    self._total_cost / max(0.01, self._config.max_cost_usd_per_session) * 100, 1
                ),
            }

    def reset(self) -> None:
        """Reset the budget tracker for a new session."""
        with self._lock:
            self._entries.clear()
            self._total_cost = 0.0
            self._session_start = time.perf_counter()
