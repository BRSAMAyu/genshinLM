from __future__ import annotations

from dataclasses import asdict
from statistics import mean
from typing import Any

from benchmarks.benchmark_types import BenchmarkReport, BenchmarkResult


_RATE_FIELDS = (
    "task_success_rate",
    "verifier_false_accept_rate",
    "anchor_resolution_rate",
    "click_success_rate",
    "navigation_drift_rate",
    "stuck_recovery_rate",
    "release_all_success_rate",
    "context_compaction_success_rate",
)


class AuroraBenchV2Summary:
    """Aggregate user-facing v2 runtime quality metrics."""

    def summarize_results(self, results: list[BenchmarkResult]) -> dict[str, Any]:
        if not results:
            return {"total": 0, "passed": 0, "pass_rate": 0.0, "metrics": {}}
        metrics: dict[str, float] = {}
        for field_name in _RATE_FIELDS:
            values = [float(getattr(result.metrics, field_name)) for result in results]
            metrics[field_name] = round(mean(values), 4)
        metrics["reflex_latency_p95"] = round(max(float(r.metrics.reflex_latency_p95) for r in results), 4)
        metrics["human_interventions"] = sum(int(r.metrics.human_interventions) for r in results)
        metrics["mean_time_to_recover_ms"] = round(mean(float(r.metrics.mean_time_to_recover_ms) for r in results), 4)
        metrics["memory_growth_mb_per_hour"] = round(max(float(r.metrics.memory_growth_mb_per_hour) for r in results), 4)
        passed = sum(1 for result in results if result.passed)
        return {
            "total": len(results),
            "passed": passed,
            "pass_rate": round(passed / len(results), 4),
            "metrics": metrics,
        }

    def summarize_report(self, report: BenchmarkReport) -> dict[str, Any]:
        summary = self.summarize_results(report.results)
        summary["suite_name"] = report.suite_name
        summary["run_id"] = report.run_id
        return summary


def benchmark_result_to_dict_v2(result: BenchmarkResult) -> dict[str, Any]:
    return {
        "benchmark_id": result.benchmark_id,
        "run_id": result.run_id,
        "suite_name": result.suite_name,
        "scenario_name": result.scenario_name,
        "passed": result.passed,
        "evidence_ids": result.evidence_ids,
        "report": result.report,
        "metrics": asdict(result.metrics),
    }
