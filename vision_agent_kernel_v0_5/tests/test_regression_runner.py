"""Tests for planning/regression_runner.py — M7 regression framework."""
from __future__ import annotations

import os
import json
import tempfile

import pytest

from planning.regression_runner import (
    RegressionConfig,
    RegressionReport,
    RegressionRunner,
)


# ---------------------------------------------------------------------------
# RegressionReport
# ---------------------------------------------------------------------------

class TestRegressionReport:

    def test_empty_report(self) -> None:
        report = RegressionReport(regression_type="dry_run", run_id="test")
        assert report.total == 0
        assert report.passed_count == 0
        assert report.failed_count == 0
        assert not report.failed

    def test_pass_rate_zero_cases(self) -> None:
        report = RegressionReport(regression_type="dry_run", run_id="test")
        assert report.pass_rate == 0.0

    def test_report_with_passing_cases(self) -> None:
        from planning.regression_runner import RegressionCaseResult
        report = RegressionReport(
            regression_type="dry_run",
            run_id="test",
            cases=[
                RegressionCaseResult(case_id="c1", passed=True),
                RegressionCaseResult(case_id="c2", passed=True),
            ],
        )
        assert report.total == 2
        assert report.passed_count == 2
        assert not report.failed
        assert report.pass_rate == 1.0

    def test_report_with_failing_cases(self) -> None:
        from planning.regression_runner import RegressionCaseResult
        report = RegressionReport(
            regression_type="dry_run",
            run_id="test",
            cases=[
                RegressionCaseResult(case_id="c1", passed=True),
                RegressionCaseResult(case_id="c2", passed=False, error="broken"),
            ],
        )
        assert report.failed
        assert report.failed_count == 1

    def test_summary_contains_pass_fail(self) -> None:
        from planning.regression_runner import RegressionCaseResult
        report = RegressionReport(
            regression_type="dry_run",
            run_id="test",
            cases=[RegressionCaseResult(case_id="c1", passed=True)],
        )
        summary = report.summary()
        assert "PASS" in summary
        assert "dry_run" in summary

    def test_summary_shows_fail(self) -> None:
        from planning.regression_runner import RegressionCaseResult
        report = RegressionReport(
            regression_type="replay",
            run_id="test",
            cases=[RegressionCaseResult(case_id="c1", passed=False, error="x")],
        )
        summary = report.summary()
        assert "FAIL" in summary
        assert "x" in summary

    def test_to_dict(self) -> None:
        from planning.regression_runner import RegressionCaseResult
        report = RegressionReport(
            regression_type="dry_run",
            run_id="test_123",
            cases=[RegressionCaseResult(case_id="c1", passed=True)],
        )
        d = report.to_dict()
        assert d["regression_type"] == "dry_run"
        assert d["run_id"] == "test_123"
        assert d["total"] == 1
        assert d["passed"] == 1

    def test_error_makes_report_fail(self) -> None:
        report = RegressionReport(regression_type="dry_run", run_id="test", error="crashed")
        assert report.failed


# ---------------------------------------------------------------------------
# Dry-run regression
# ---------------------------------------------------------------------------

class TestDryRunRegression:

    def test_dry_run_passes(self) -> None:
        runner = RegressionRunner()
        report = runner.run_dry_run_regression()
        assert report.regression_type == "dry_run"
        assert report.total > 0
        assert report.passed_count > 0

    def test_dry_run_checks_all_capsules(self) -> None:
        runner = RegressionRunner()
        report = runner.run_dry_run_regression()
        capsule_ids = {c.case_id.split("/")[0] for c in report.cases}
        assert "genshin" in capsule_ids
        assert "hsr" in capsule_ids

    def test_dry_run_validates_recipe_structure(self) -> None:
        runner = RegressionRunner()
        report = runner.run_dry_run_regression()
        for case in report.cases:
            assert case.passed, f"Skill failed: {case.case_id} — {case.error}"


# ---------------------------------------------------------------------------
# Replay regression
# ---------------------------------------------------------------------------

class TestReplayRegression:

    def test_replay_no_trace_dir(self) -> None:
        runner = RegressionRunner(RegressionConfig(replay_trace_dir="/nonexistent"))
        report = runner.run_replay_regression()
        assert report.error is not None or report.total > 0

    def test_replay_empty_trace_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = RegressionRunner(RegressionConfig(replay_trace_dir=tmpdir))
            report = runner.run_replay_regression()
            assert report.total > 0  # Should have a "no traces" case
            assert report.passed_count > 0

    def test_replay_valid_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = os.path.join(tmpdir, "test_trace.jsonl")
            with open(trace_path, "w", encoding="utf-8") as f:
                f.write(json.dumps({"event": "action", "timestamp": 1.0}) + "\n")
                f.write(json.dumps({"event": "verify", "timestamp": 2.0}) + "\n")
            runner = RegressionRunner(RegressionConfig(replay_trace_dir=tmpdir))
            report = runner.run_replay_regression()
            assert report.total == 1
            assert report.passed_count == 1


# ---------------------------------------------------------------------------
# Model cost regression
# ---------------------------------------------------------------------------

class TestModelCostRegression:

    def test_model_cost_passes_by_default(self) -> None:
        runner = RegressionRunner()
        report = runner.run_model_cost_regression()
        assert report.regression_type == "model_cost"
        assert report.total > 0


# ---------------------------------------------------------------------------
# Version drift regression
# ---------------------------------------------------------------------------

class TestVersionDriftRegression:

    def test_drift_no_baseline(self) -> None:
        runner = RegressionRunner(RegressionConfig(drift_baseline_dir="/nonexistent"))
        report = runner.run_version_drift_regression()
        assert report.regression_type == "version_drift"
        assert report.total > 0

    def test_drift_with_baseline_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = RegressionRunner(RegressionConfig(drift_baseline_dir=tmpdir))
            report = runner.run_version_drift_regression()
            assert report.total > 0
            # All skills healthy (loaded successfully)
            assert report.passed_count > 0


# ---------------------------------------------------------------------------
# Run all
# ---------------------------------------------------------------------------

class TestRunAll:

    def test_run_all_returns_4_reports(self) -> None:
        runner = RegressionRunner()
        reports = runner.run_all()
        assert len(reports) == 4
        types = {r.regression_type for r in reports}
        assert "dry_run" in types
        assert "replay" in types
        assert "model_cost" in types
        assert "version_drift" in types
