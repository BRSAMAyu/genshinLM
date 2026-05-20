"""Benchmark runner: registers suites, runs them, and produces BenchmarkReports."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from benchmarks.benchmark_types import BenchmarkReport, BenchmarkResult, BenchmarkSuiteConfig


SuiteFactory = Callable[[], list[BenchmarkResult]]


class BenchmarkRunner:
    """Registry and executor for benchmark suites.

    Each suite is registered with a name and a factory callable that returns
    ``list[BenchmarkResult]``.  Running a suite produces a
    :class:`BenchmarkReport` and optionally writes a JSON report to disk.
    """

    def __init__(self, config: BenchmarkSuiteConfig | None = None) -> None:
        self._config = config or BenchmarkSuiteConfig(suite_name="all")
        self._registry: dict[str, SuiteFactory] = {}

    # -- registration -------------------------------------------------------

    def register_suite(self, name: str, factory: SuiteFactory) -> None:
        """Register a suite factory under *name*."""
        self._registry[name] = factory

    def registered_suites(self) -> list[str]:
        """Return sorted list of registered suite names."""
        return sorted(self._registry.keys())

    # -- execution ----------------------------------------------------------

    def run_suite(self, name: str) -> BenchmarkReport:
        """Run a single suite by name and return a :class:`BenchmarkReport`."""
        if name not in self._registry:
            raise KeyError(f"Suite '{name}' not registered. Available: {list(self._registry.keys())}")

        factory = self._registry[name]
        results: list[BenchmarkResult] = factory()

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed

        # Evidence coverage rate: average across all results
        evidence_coverage_rate = 0.0
        if total > 0:
            evidence_coverage_rate = sum(r.metrics.evidence_coverage for r in results) / total

        report = BenchmarkReport(
            suite_name=name,
            run_id=uuid.uuid4().hex[:12],
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_scenarios=total,
            passed_scenarios=passed,
            failed_scenarios=failed,
            evidence_coverage_rate=evidence_coverage_rate,
            results=results,
            summary=_build_summary(name, results),
        )

        # Persist JSON report
        output_dir = Path(self._config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"{name}_{report.run_id}.json"
        report_path.write_text(
            json.dumps(_report_to_dict(report), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return report

    def run_all(self) -> list[BenchmarkReport]:
        """Run every registered suite and return a list of reports."""
        reports: list[BenchmarkReport] = []
        for name in self.registered_suites():
            reports.append(self.run_suite(name))
        return reports


# -- helpers ----------------------------------------------------------------


def _build_summary(suite_name: str, results: list[BenchmarkResult]) -> dict[str, object]:
    """Build a summary dict from a list of results."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    scenarios: list[dict[str, object]] = []
    for r in results:
        scenarios.append({
            "scenario_name": r.scenario_name,
            "passed": r.passed,
            "evidence_count": len(r.evidence_ids),
            "report_keys": list(r.report.keys()),
        })

    return {
        "suite": suite_name,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total > 0 else 0.0,
        "scenarios": scenarios,
    }


def _report_to_dict(report: BenchmarkReport) -> dict[str, object]:
    """Serialize a BenchmarkReport to a JSON-friendly dict."""
    results_dicts: list[dict[str, object]] = []
    for r in report.results:
        results_dicts.append({
            "benchmark_id": r.benchmark_id,
            "run_id": r.run_id,
            "suite_name": r.suite_name,
            "scenario_name": r.scenario_name,
            "passed": r.passed,
            "evidence_ids": r.evidence_ids,
            "report": r.report,
            "metrics": {
                "frame_to_observation_ms": r.metrics.frame_to_observation_ms,
                "observation_to_interrupt_ms": r.metrics.observation_to_interrupt_ms,
                "interrupt_to_lease_ms": r.metrics.interrupt_to_lease_ms,
                "danger_clear_time_ms": r.metrics.danger_clear_time_ms,
                "danger_false_clear_rate": r.metrics.danger_false_clear_rate,
                "resume_success_rate": r.metrics.resume_success_rate,
                "max_consecutive_dodges": r.metrics.max_consecutive_dodges,
                "final_task_success": r.metrics.final_task_success,
                "evidence_coverage": r.metrics.evidence_coverage,
            },
        })

    return {
        "suite_name": report.suite_name,
        "run_id": report.run_id,
        "timestamp": report.timestamp,
        "total_scenarios": report.total_scenarios,
        "passed_scenarios": report.passed_scenarios,
        "failed_scenarios": report.failed_scenarios,
        "evidence_coverage_rate": report.evidence_coverage_rate,
        "results": results_dicts,
        "summary": report.summary,
    }
