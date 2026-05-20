from __future__ import annotations

import uuid

from core.timebase import Timebase
from reflex.scheduler import ReflexScheduler

from benchmarks.benchmark_types import BenchmarkResult
from benchmarks.reflex_gauntlet.runner import ReflexGauntletRunner
from benchmarks.reflex_gauntlet.scenario import SCENARIOS, ReflexScenario


class ReflexGauntletEvaluator:
    """Evaluates all reflex scenarios and produces a summary."""

    def __init__(
        self,
        scenarios: list[ReflexScenario] | None = None,
        timebase: Timebase | None = None,
    ) -> None:
        self._scenarios = scenarios or SCENARIOS
        self._timebase = timebase or Timebase()
        self._results: list[BenchmarkResult] = []

    def run_all(self) -> list[BenchmarkResult]:
        """Run each scenario and collect results."""
        self._results = []
        for scenario in self._scenarios:
            scheduler = ReflexScheduler(
                danger_threshold=0.5,
                cooldown_frames=10,
                timebase=self._timebase,
            )
            runner = ReflexGauntletRunner(
                scenario=scenario,
                scheduler=scheduler,
                timebase=self._timebase,
            )
            result = runner.run()
            self._results.append(result)
        return self._results

    def summary(self) -> dict[str, object]:
        """Produce a summary dict of all results."""
        if not self._results:
            return {"status": "no_results", "total": 0}

        total = len(self._results)
        passed = sum(1 for r in self._results if r.passed)
        failed = total - passed

        avg_frame_to_obs = 0.0
        avg_obs_to_interrupt = 0.0
        avg_danger_clear = 0.0
        avg_false_clear_rate = 0.0
        avg_resume_success = 0.0
        avg_evidence_coverage = 0.0

        for r in self._results:
            m = r.metrics
            avg_frame_to_obs += m.frame_to_observation_ms
            avg_obs_to_interrupt += m.observation_to_interrupt_ms
            avg_danger_clear += m.danger_clear_time_ms
            avg_false_clear_rate += m.danger_false_clear_rate
            avg_resume_success += m.resume_success_rate
            avg_evidence_coverage += m.evidence_coverage

        n = float(total)
        scenario_results: list[dict[str, object]] = []
        for r in self._results:
            scenario_results.append({
                "name": r.scenario_name,
                "passed": r.passed,
                "dodges": r.report.get("dodges", 0),
                "expected_dodges": r.report.get("expected_dodges", 0),
                "evidence_count": len(r.evidence_ids),
            })

        return {
            "suite": "reflex_gauntlet",
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / n if n > 0 else 0.0,
            "avg_frame_to_observation_ms": avg_frame_to_obs / n,
            "avg_observation_to_interrupt_ms": avg_obs_to_interrupt / n,
            "avg_danger_clear_time_ms": avg_danger_clear / n,
            "avg_false_clear_rate": avg_false_clear_rate / n,
            "avg_resume_success_rate": avg_resume_success / n,
            "avg_evidence_coverage": avg_evidence_coverage / n,
            "scenarios": scenario_results,
        }
