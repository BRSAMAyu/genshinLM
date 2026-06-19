"""Sentinel verification coverage — tracks which sentinels have fired and which remain untested.

Provides coverage metrics so developers can identify blind spots in sentinel
testing and ensure all critical watchdog conditions are exercised.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

log = logging.getLogger(__name__)


@dataclass(slots=True)
class SentinelCoverageEntry:
    """Record of a single sentinel verification event."""
    sentinel_id: str
    condition: str
    fired_at: float
    result: str  # "pass", "fail", "timeout"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SentinelSpec:
    """Specification of a sentinel that should be verified."""
    sentinel_id: str
    description: str
    critical: bool = False
    category: str = "general"


class SentinelCoverageTracker:
    """Tracks sentinel verification coverage across sessions.

    Records which sentinels have been triggered and verified,
    and reports coverage gaps for critical sentinel conditions.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._specs: dict[str, SentinelSpec] = {}
        self._coverage: list[SentinelCoverageEntry] = []
        self._fired_ids: set[str] = set()

    def register_spec(self, spec: SentinelSpec) -> None:
        """Register a sentinel specification for coverage tracking."""
        with self._lock:
            self._specs[spec.sentinel_id] = spec

    def register_specs(self, specs: list[SentinelSpec]) -> None:
        """Register multiple sentinel specifications."""
        for spec in specs:
            self.register_spec(spec)

    def record_fire(
        self,
        sentinel_id: str,
        condition: str = "",
        result: str = "pass",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record that a sentinel has fired."""
        with self._lock:
            entry = SentinelCoverageEntry(
                sentinel_id=sentinel_id,
                condition=condition,
                fired_at=time.perf_counter(),
                result=result,
                details=details or {},
            )
            self._coverage.append(entry)
            self._fired_ids.add(sentinel_id)

    @property
    def coverage_pct(self) -> float:
        """Percentage of registered sentinels that have been verified."""
        with self._lock:
            if not self._specs:
                return 100.0
            return len(self._fired_ids & self._specs.keys()) / len(self._specs) * 100

    @property
    def critical_coverage_pct(self) -> float:
        """Percentage of critical sentinels that have been verified."""
        with self._lock:
            critical_ids = {sid for sid, spec in self._specs.items() if spec.critical}
            if not critical_ids:
                return 100.0
            covered = self._fired_ids & critical_ids
            return len(covered) / len(critical_ids) * 100

    def get_uncovered(self) -> list[SentinelSpec]:
        """Get specs for sentinels that have never been verified."""
        with self._lock:
            return [
                spec for sid, spec in self._specs.items()
                if sid not in self._fired_ids
            ]

    def get_uncovered_critical(self) -> list[SentinelSpec]:
        """Get specs for critical sentinels that have never been verified."""
        return [spec for spec in self.get_uncovered() if spec.critical]

    def get_results_by_sentinel(self, sentinel_id: str) -> list[SentinelCoverageEntry]:
        """Get all coverage entries for a specific sentinel."""
        with self._lock:
            return [e for e in self._coverage if e.sentinel_id == sentinel_id]

    def get_summary(self) -> dict[str, Any]:
        """Get a coverage summary."""
        with self._lock:
            total = len(self._specs)
            covered = len(self._fired_ids & self._specs.keys())
            critical_total = sum(1 for s in self._specs.values() if s.critical)
            critical_covered = sum(
                1 for sid in self._fired_ids
                if sid in self._specs and self._specs[sid].critical
            )
            by_category: dict[str, dict[str, int]] = {}
            for spec in self._specs.values():
                cat = spec.category
                if cat not in by_category:
                    by_category[cat] = {"total": 0, "covered": 0}
                by_category[cat]["total"] += 1
                if spec.sentinel_id in self._fired_ids:
                    by_category[cat]["covered"] += 1

            return {
                "total_sentinels": total,
                "covered_sentinels": covered,
                "coverage_pct": round(covered / max(1, total) * 100, 1),
                "critical_total": critical_total,
                "critical_covered": critical_covered,
                "critical_coverage_pct": round(
                    critical_covered / max(1, critical_total) * 100, 1
                ),
                "by_category": by_category,
                "total_fires": len(self._coverage),
            }

    def reset(self) -> None:
        """Reset coverage tracking (keep specs)."""
        with self._lock:
            self._coverage.clear()
            self._fired_ids.clear()
