"""Full gauntlet test: run all 6 reflex scenarios and verify metrics."""
from __future__ import annotations

from core.timebase import Timebase
from reflex.scheduler import ReflexScheduler

from benchmarks.benchmark_types import BenchmarkMetrics, BenchmarkResult
from benchmarks.reflex_gauntlet.evaluator import ReflexGauntletEvaluator
from benchmarks.reflex_gauntlet.runner import ReflexGauntletRunner
from benchmarks.reflex_gauntlet.scenario import SCENARIOS, ReflexScenario


class TestVerifiedReflexResumeGauntlet:
    """Run each of 6 scenarios, verify dodges, evidence, resume, and metrics."""

    def test_all_scenarios_run(self) -> None:
        """All 6 scenarios produce BenchmarkResult."""
        evaluator = ReflexGauntletEvaluator()
        results = evaluator.run_all()
        assert len(results) == 6
        for r in results:
            assert isinstance(r, BenchmarkResult)
            assert r.suite_name == "reflex_gauntlet"

    def test_ground_danger_scenario(self) -> None:
        """Ground danger triggers at least 1 dodge."""
        scenario = SCENARIOS[0]
        assert scenario.name == "ground_danger"
        runner = ReflexGauntletRunner(scenario)
        result = runner.run()
        assert result.metrics.max_consecutive_dodges >= 1
        assert result.report["dodges"] >= scenario.expected_dodges

    def test_projectile_danger_scenario(self) -> None:
        """Projectile danger triggers at least 1 dodge."""
        scenario = SCENARIOS[1]
        assert scenario.name == "projectile_danger"
        runner = ReflexGauntletRunner(scenario)
        result = runner.run()
        assert result.metrics.max_consecutive_dodges >= 1

    def test_hp_drop_danger_scenario(self) -> None:
        """HP drop danger triggers at least 1 dodge."""
        scenario = SCENARIOS[2]
        assert scenario.name == "hp_drop_danger"
        runner = ReflexGauntletRunner(scenario)
        result = runner.run()
        assert result.metrics.max_consecutive_dodges >= 1

    def test_target_occlusion_scenario(self) -> None:
        """Occlusion danger triggers at least 1 dodge."""
        scenario = SCENARIOS[3]
        assert scenario.name == "target_occlusion"
        runner = ReflexGauntletRunner(scenario)
        result = runner.run()
        assert result.metrics.max_consecutive_dodges >= 1

    def test_repeated_danger_scenario(self) -> None:
        """Repeated danger triggers multiple dodges."""
        scenario = SCENARIOS[4]
        assert scenario.name == "repeated_danger"
        runner = ReflexGauntletRunner(scenario)
        result = runner.run()
        assert result.report["dodges"] >= scenario.expected_dodges

    def test_false_positive_scenario(self) -> None:
        """False positive scenario produces zero dodges."""
        scenario = SCENARIOS[5]
        assert scenario.name == "false_positive"
        runner = ReflexGauntletRunner(scenario)
        result = runner.run()
        assert result.report["dodges"] == 0

    def test_evidence_chain_present(self) -> None:
        """Each dodge scenario produces evidence IDs."""
        for scenario in SCENARIOS[:5]:
            runner = ReflexGauntletRunner(scenario)
            result = runner.run()
            if result.report.get("dodges", 0) > 0:
                assert len(result.evidence_ids) > 0, (
                    f"No evidence for scenario {scenario.name}"
                )

    def test_resume_contract_after_danger_clears(self) -> None:
        """Danger scenarios that produce a dodge should eventually get a resume contract."""
        scheduler = ReflexScheduler(
            danger_threshold=0.5, cooldown_frames=10, timebase=Timebase()
        )
        # Simulate danger -> preempt -> clear
        from reflex.scheduler import PreemptionToken

        token = scheduler.evaluate(0.8, "ground", frame_id=1)
        assert token is not None
        # Danger clears
        contract = None
        for _ in range(10):
            contract = scheduler.verify_danger_cleared(token, 0.1)
            if contract is not None:
                break
        assert contract is not None

    def test_metrics_collected(self) -> None:
        """All results have populated metrics."""
        evaluator = ReflexGauntletEvaluator()
        results = evaluator.run_all()
        for r in results:
            assert isinstance(r.metrics, BenchmarkMetrics)
            # Metrics fields should be numeric
            assert isinstance(r.metrics.frame_to_observation_ms, float)
            assert isinstance(r.metrics.observation_to_interrupt_ms, float)
            assert isinstance(r.metrics.interrupt_to_lease_ms, float)
            assert isinstance(r.metrics.danger_clear_time_ms, float)
            assert isinstance(r.metrics.danger_false_clear_rate, float)
            assert isinstance(r.metrics.resume_success_rate, float)
            assert isinstance(r.metrics.max_consecutive_dodges, int)
            assert isinstance(r.metrics.final_task_success, bool)
            assert isinstance(r.metrics.evidence_coverage, float)

    def test_evaluator_summary(self) -> None:
        """Evaluator produces a valid summary."""
        evaluator = ReflexGauntletEvaluator()
        evaluator.run_all()
        summary = evaluator.summary()
        assert summary["suite"] == "reflex_gauntlet"
        assert summary["total"] == 6
        assert isinstance(summary["passed"], int)
        assert isinstance(summary["failed"], int)
        assert isinstance(summary["scenarios"], list)
        assert len(summary["scenarios"]) == 6
