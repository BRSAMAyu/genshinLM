"""Batch execution, failure clustering, and regression comparison."""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, Iterable

from harness.core import BatchReport, FailureCluster, Scenario, ScenarioResult


def cluster_failures(results: Iterable[ScenarioResult]) -> list[FailureCluster]:
    """Group failed results by ``failure_code`` + primary tag.

    Clustering lets a fix target a *class* of failure (e.g. "stuck on obstacle")
    rather than chasing individual runs — the unit a fix-agent should consume.
    """
    buckets: dict[str, list[ScenarioResult]] = defaultdict(list)
    for r in results:
        if r.passed:
            continue
        primary_tag = r.tags[0] if r.tags else "-"
        signature = f"{r.failure_code or 'unknown'}::{primary_tag}"
        buckets[signature].append(r)

    clusters = [
        FailureCluster(
            signature=sig,
            count=len(group),
            scenario_ids=tuple(r.scenario_id for r in group),
            example_reason=group[0].reason,
        )
        for sig, group in buckets.items()
    ]
    # Largest clusters first — highest-leverage fixes.
    clusters.sort(key=lambda c: c.count, reverse=True)
    return clusters


def run_batch(
    scenarios: Iterable[Scenario],
    run_one: Callable[[Scenario], ScenarioResult],
    *,
    baseline: dict[str, bool] | None = None,
) -> BatchReport:
    """Run every scenario via ``run_one`` and aggregate.

    ``run_one`` is a factory-bound closure (fresh env+policy per scenario) so a
    later parallel executor can map it concurrently without shared state.
    ``baseline`` maps scenario_id → passed for regression/fixed deltas.
    """
    results = [run_one(s) for s in scenarios]
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    failed = total - passed
    pass_rate = passed / total if total else 0.0

    regressions: tuple[str, ...] = ()
    fixed: tuple[str, ...] = ()
    if baseline is not None:
        now = {r.scenario_id: r.passed for r in results}
        regressions = tuple(sid for sid, was in baseline.items() if was and not now.get(sid, False))
        fixed = tuple(sid for sid, was in baseline.items() if not was and now.get(sid, False))

    return BatchReport(
        total=total,
        passed=passed,
        failed=failed,
        pass_rate=pass_rate,
        clusters=tuple(cluster_failures(results)),
        results=tuple(results),
        regressions=regressions,
        fixed=fixed,
    )
