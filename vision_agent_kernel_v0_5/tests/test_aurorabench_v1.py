"""Tests for AuroraBench v1: BenchmarkRunner, suites, reports, and CLI."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.benchmark_types import (
    BenchmarkMetrics,
    BenchmarkReport,
    BenchmarkResult,
    BenchmarkSuiteConfig,
)
from benchmarks.benchmark_runner import BenchmarkRunner
from benchmarks.report_builder import ReportBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(name: str, passed: bool, evidence_count: int = 3) -> BenchmarkResult:
    return BenchmarkResult(
        benchmark_id=f"test_{name}",
        run_id="test_run",
        suite_name="test_suite",
        scenario_name=name,
        passed=passed,
        metrics=BenchmarkMetrics(
            evidence_coverage=evidence_count / 5.0,
            final_task_success=passed,
        ),
        evidence_ids=[f"ev_{name}_{i}" for i in range(evidence_count)],
        report={"test_key": "test_value"},
    )


# ---------------------------------------------------------------------------
# BenchmarkRunner tests
# ---------------------------------------------------------------------------

class TestBenchmarkRunner:
    def test_register_and_list_suites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = BenchmarkSuiteConfig(suite_name="test", output_dir=tmp)
            runner = BenchmarkRunner(config=config)
            runner.register_suite("suite_a", lambda: [])
            runner.register_suite("suite_b", lambda: [])
            suites = runner.registered_suites()
            assert suites == ["suite_a", "suite_b"]

    def test_run_suite_returns_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = BenchmarkSuiteConfig(suite_name="test", output_dir=tmp)
            runner = BenchmarkRunner(config=config)
            results = [_make_result("s1", True), _make_result("s2", False)]
            runner.register_suite("demo", lambda: results)
            report = runner.run_suite("demo")

            assert isinstance(report, BenchmarkReport)
            assert report.suite_name == "demo"
            assert report.total_scenarios == 2
            assert report.passed_scenarios == 1
            assert report.failed_scenarios == 1
            assert len(report.results) == 2
            assert report.evidence_coverage_rate > 0.0

    def test_run_suite_raises_on_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = BenchmarkSuiteConfig(suite_name="test", output_dir=tmp)
            runner = BenchmarkRunner(config=config)
            with pytest.raises(KeyError, match="not registered"):
                runner.run_suite("nonexistent")

    def test_run_all_runs_every_suite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = BenchmarkSuiteConfig(suite_name="test", output_dir=tmp)
            runner = BenchmarkRunner(config=config)
            runner.register_suite("a", lambda: [_make_result("a1", True)])
            runner.register_suite("b", lambda: [_make_result("b1", True)])
            reports = runner.run_all()
            assert len(reports) == 2
            assert all(isinstance(r, BenchmarkReport) for r in reports)

    def test_json_report_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = BenchmarkSuiteConfig(suite_name="test", output_dir=tmp)
            runner = BenchmarkRunner(config=config)
            runner.register_suite("json_test", lambda: [_make_result("x", True)])
            report = runner.run_suite("json_test")

            # Find the JSON file
            json_files = list(Path(tmp).glob("json_test_*.json"))
            assert len(json_files) == 1

            data = json.loads(json_files[0].read_text(encoding="utf-8"))
            assert data["suite_name"] == "json_test"
            assert data["total_scenarios"] == 1
            assert data["passed_scenarios"] == 1

    def test_evidence_coverage_rate_computed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = BenchmarkSuiteConfig(suite_name="test", output_dir=tmp)
            runner = BenchmarkRunner(config=config)
            r1 = _make_result("a", True, evidence_count=4)
            r2 = _make_result("b", True, evidence_count=2)
            runner.register_suite("cov", lambda: [r1, r2])
            report = runner.run_suite("cov")

            # coverage = (4/5 + 2/5) / 2 = 0.6
            assert abs(report.evidence_coverage_rate - 0.6) < 0.01


# ---------------------------------------------------------------------------
# Long-horizon suite tests
# ---------------------------------------------------------------------------

class TestLongHorizonSuite:
    def test_run_all_produces_results(self) -> None:
        from benchmarks.long_horizon_route_fight_collect_resume.runner import run_all_long_horizon
        results = run_all_long_horizon()
        assert len(results) == 4
        assert all(isinstance(r, BenchmarkResult) for r in results)

    def test_full_chain_happy_path_passes(self) -> None:
        from benchmarks.long_horizon_route_fight_collect_resume.runner import run_all_long_horizon
        results = run_all_long_horizon()
        happy = [r for r in results if r.scenario_name == "full_chain_happy_path"]
        assert len(happy) == 1
        assert happy[0].passed is True
        assert len(happy[0].evidence_ids) > 0
        assert "phases_completed" in happy[0].report

    def test_resume_skips_verified_nodes(self) -> None:
        from benchmarks.long_horizon_route_fight_collect_resume.runner import run_all_long_horizon
        results = run_all_long_horizon()
        recovery = [r for r in results if r.scenario_name == "combat_recovery_resume"]
        assert len(recovery) == 1
        result = recovery[0]
        assert result.passed is True
        assert isinstance(result.report.get("resume_skips"), list)
        assert len(result.report["resume_skips"]) > 0

    def test_evidence_at_terminal_nodes(self) -> None:
        from benchmarks.long_horizon_route_fight_collect_resume.runner import run_all_long_horizon
        results = run_all_long_horizon()
        for result in results:
            if result.passed:
                assert result.metrics.evidence_coverage > 0.0


# ---------------------------------------------------------------------------
# Failure-to-skill-repair suite tests
# ---------------------------------------------------------------------------

class TestRepairSuite:
    def test_run_all_produces_results(self) -> None:
        from benchmarks.failure_to_skill_repair.runner import run_all_repair
        results = run_all_repair()
        assert len(results) == 4
        assert all(isinstance(r, BenchmarkResult) for r in results)

    def test_target_lost_repair_passes(self) -> None:
        from benchmarks.failure_to_skill_repair.runner import run_all_repair
        results = run_all_repair()
        tl = [r for r in results if r.scenario_name == "target_lost_repair"]
        assert len(tl) == 1
        assert tl[0].passed is True
        assert tl[0].report.get("patch_created") is True

    def test_patch_verified_and_approved(self) -> None:
        from benchmarks.failure_to_skill_repair.runner import run_all_repair
        results = run_all_repair()
        for r in results:
            assert r.report.get("patch_verified") is True
            assert r.report.get("patch_approved") is True

    def test_benchmark_delta_computed(self) -> None:
        from benchmarks.failure_to_skill_repair.runner import run_all_repair
        results = run_all_repair()
        for r in results:
            assert r.report.get("benchmark_delta") is True

    def test_repair_sessions_created(self) -> None:
        from benchmarks.failure_to_skill_repair.runner import run_all_repair
        results = run_all_repair()
        for r in results:
            assert r.report.get("repair_sessions_created", 0) >= 1


# ---------------------------------------------------------------------------
# UI safety suite tests
# ---------------------------------------------------------------------------

class TestUISafetySuite:
    def test_run_all_produces_results(self) -> None:
        from benchmarks.high_res_ui_safety_grounding.runner import run_all_ui_safety
        results = run_all_ui_safety()
        assert len(results) == 5
        assert all(isinstance(r, BenchmarkResult) for r in results)

    def test_safe_button_executes(self) -> None:
        from benchmarks.high_res_ui_safety_grounding.runner import run_all_ui_safety
        results = run_all_ui_safety()
        safe = [r for r in results if r.scenario_name == "safe_button_execute"]
        assert len(safe) == 1
        assert safe[0].passed is True
        assert "btn_start" in safe[0].report["executed_elements"]

    def test_destructive_action_blocked(self) -> None:
        from benchmarks.high_res_ui_safety_grounding.runner import run_all_ui_safety
        results = run_all_ui_safety()
        destr = [r for r in results if r.scenario_name == "destructive_action_blocked"]
        assert len(destr) == 1
        assert destr[0].passed is True
        assert "btn_delete" in destr[0].report["blocked_actions"]

    def test_low_confidence_requires_confirmation(self) -> None:
        from benchmarks.high_res_ui_safety_grounding.runner import run_all_ui_safety
        results = run_all_ui_safety()
        low = [r for r in results if r.scenario_name == "low_confidence_requires_confirmation"]
        assert len(low) == 1
        assert low[0].passed is True
        assert "btn_confirm" in low[0].report["confirm_elements"]

    def test_mixed_safety_chain(self) -> None:
        from benchmarks.high_res_ui_safety_grounding.runner import run_all_ui_safety
        results = run_all_ui_safety()
        mixed = [r for r in results if r.scenario_name == "mixed_safety_chain"]
        assert len(mixed) == 1
        assert mixed[0].passed is True
        assert mixed[0].report["safety_blocks"] == 1

    def test_evidence_links_frame_roi_element(self) -> None:
        from benchmarks.high_res_ui_safety_grounding.runner import run_all_ui_safety
        results = run_all_ui_safety()
        for r in results:
            # Each element should produce at least 3 evidence nodes
            assert len(r.evidence_ids) >= len(SCENARIOS_FOR_COUNT(r)) * 3


def SCENARIOS_FOR_COUNT(r: BenchmarkResult) -> list[object]:
    """Get the scenario element count from the report."""
    elements = r.report.get("element_results")
    if isinstance(elements, list):
        return elements
    return []


# ---------------------------------------------------------------------------
# ReportBuilder tests
# ---------------------------------------------------------------------------

class TestReportBuilder:
    def test_json_report_has_required_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            builder = ReportBuilder(output_dir=tmp)
            results = [_make_result("s1", True)]
            report = BenchmarkReport(
                suite_name="test",
                run_id="r1",
                timestamp="2025-01-01T00:00:00Z",
                total_scenarios=1,
                passed_scenarios=1,
                failed_scenarios=0,
                evidence_coverage_rate=0.8,
                results=results,
                summary={"suite": "test"},
            )
            json_path = builder.build_json_report(report)
            data = json.loads(json_path.read_text(encoding="utf-8"))

            assert "suite_name" in data
            assert "results" in data
            assert "summary" in data
            assert "evidence_coverage_rate" in data
            assert data["total_scenarios"] == 1

    def test_markdown_report_has_summary_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            builder = ReportBuilder(output_dir=tmp)
            results = [_make_result("s1", True), _make_result("s2", False)]
            report = BenchmarkReport(
                suite_name="md_test",
                run_id="r2",
                timestamp="2025-01-01T00:00:00Z",
                total_scenarios=2,
                passed_scenarios=1,
                failed_scenarios=1,
                evidence_coverage_rate=0.5,
                results=results,
                summary={"suite": "md_test"},
            )
            md_path = builder.build_markdown_report(report)
            md_content = md_path.read_text(encoding="utf-8")

            assert "# Benchmark Report: md_test" in md_content
            assert "PASS" in md_content
            assert "FAIL" in md_content
            assert "Evidence Coverage" in md_content
            assert "Detailed Metrics" in md_content

    def test_build_all_returns_both_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            builder = ReportBuilder(output_dir=tmp)
            report = BenchmarkReport(
                suite_name="both",
                run_id="r3",
                timestamp="2025-01-01T00:00:00Z",
                total_scenarios=0,
                passed_scenarios=0,
                failed_scenarios=0,
                evidence_coverage_rate=0.0,
                results=[],
                summary={},
            )
            json_path, md_path = builder.build_all(report)
            assert json_path.exists()
            assert md_path.exists()
            assert json_path.suffix == ".json"
            assert md_path.suffix == ".md"


# ---------------------------------------------------------------------------
# BenchmarkTypes tests
# ---------------------------------------------------------------------------

class TestBenchmarkTypes:
    def test_benchmark_report_dataclass(self) -> None:
        report = BenchmarkReport(
            suite_name="t",
            run_id="r",
            timestamp="ts",
            total_scenarios=1,
            passed_scenarios=1,
            failed_scenarios=0,
            evidence_coverage_rate=1.0,
            results=[],
            summary={},
        )
        assert report.suite_name == "t"
        assert report.total_scenarios == 1

    def test_benchmark_suite_config_defaults(self) -> None:
        config = BenchmarkSuiteConfig(suite_name="default")
        assert config.dry_run is True
        assert config.max_iterations == 1
        assert config.output_dir == "benchmark_reports"


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

class TestCLI:
    def test_dry_run_all_completes(self) -> None:
        """Run run_aurorabench.py --suite all --mode dry-run and verify exit 0."""
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "run_aurorabench.py"),
                 "--suite", "all", "--mode", "dry-run", "--output-dir", tmp],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(ROOT),
            )
            # Should complete with exit code 0 (all synthetic scenarios pass)
            assert result.returncode == 0, (
                f"Exit code {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )
            assert "AuroraBench complete" in result.stdout

    def test_dry_run_single_suite(self) -> None:
        """Run a single suite via CLI."""
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "run_aurorabench.py"),
                 "--suite", "ui_safety", "--mode", "dry-run", "--output-dir", tmp],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(ROOT),
            )
            assert result.returncode == 0, (
                f"Exit code {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )
            assert "ui_safety" in result.stdout
