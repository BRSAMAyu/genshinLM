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
    max_workers: int = 1,
) -> BatchReport:
    """Run every scenario via ``run_one`` and aggregate.

    ``run_one`` is a factory-bound closure (fresh env+policy per scenario) so it
    can be mapped concurrently without shared state. ``max_workers > 1`` runs the
    batch on a thread pool (results stay in scenario order for the baseline diff);
    threads suit the live-game case where steps block on the screen, while the
    deterministic default (``max_workers=1``) keeps offline runs reproducible.
    ``baseline`` maps scenario_id → passed for regression/fixed deltas.
    """
    scenario_list = list(scenarios)
    if max_workers > 1 and len(scenario_list) > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(run_one, scenario_list))
    else:
        results = [run_one(s) for s in scenario_list]
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
