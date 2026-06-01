"""Tests for reflex latency benchmark scenarios."""
from __future__ import annotations

from benchmarks.reflex_latency_bench import (
    BenchResult,
    LatencyMeasurement,
    TARGETS,
    bench_detect_decision,
    bench_focus_release,
    bench_lease_submit,
    format_report,
    run_all_benchmarks,
)


class TestBenchLeaseSubmit:

    def test_returns_result(self) -> None:
        result = bench_lease_submit(iterations=50)
        assert isinstance(result, BenchResult)
        assert result.name == "lease_submit"
        assert result.measurement.iterations == 50
        assert len(result.measurement.latencies_ms) == 50

    def test_target_defined(self) -> None:
        assert "lease_submit" in TARGETS
        assert TARGETS["lease_submit"].p95_threshold_ms == 5.0

    def test_latencies_positive(self) -> None:
        result = bench_lease_submit(iterations=50)
        for lat in result.measurement.latencies_ms:
            assert lat >= 0.0


class TestBenchDetectDecision:

    def test_returns_result(self) -> None:
        result = bench_detect_decision(iterations=50)
        assert isinstance(result, BenchResult)
        assert result.name == "detect_decision"
        assert result.measurement.iterations == 50

    def test_target_defined(self) -> None:
        assert "detect_decision" in TARGETS
        assert TARGETS["detect_decision"].p95_threshold_ms == 20.0

    def test_latencies_positive(self) -> None:
        result = bench_detect_decision(iterations=50)
        for lat in result.measurement.latencies_ms:
            assert lat >= 0.0


class TestBenchFocusRelease:

    def test_returns_result(self) -> None:
        result = bench_focus_release(iterations=20)
        assert isinstance(result, BenchResult)
        assert result.name == "focus_release"
        assert result.measurement.iterations == 20

    def test_target_defined(self) -> None:
        assert "focus_release" in TARGETS
        assert TARGETS["focus_release"].p95_threshold_ms == 50.0


class TestLatencyMeasurement:

    def test_percentiles(self) -> None:
        meas = LatencyMeasurement(name="test", iterations=5, latencies_ms=[1.0, 2.0, 3.0, 4.0, 5.0])
        assert meas.p50 == 3.0
        assert meas.p95 == 5.0
        assert meas.p99 == 5.0
        assert meas.mean == 3.0
        assert meas.min == 1.0
        assert meas.max == 5.0

    def test_empty(self) -> None:
        meas = LatencyMeasurement(name="empty", iterations=0)
        assert meas.p50 == 0.0
        assert meas.p95 == 0.0
        assert meas.mean == 0.0


class TestRunAllAndReport:

    def test_run_all_returns_three_results(self) -> None:
        results = run_all_benchmarks()
        assert len(results) == 3
        names = {r.name for r in results}
        assert names == {"lease_submit", "detect_decision", "focus_release"}

    def test_format_report(self) -> None:
        results = run_all_benchmarks()
        report = format_report(results)
        assert "REFLEX LATENCY BENCHMARK REPORT" in report
        assert "OVERALL:" in report

    def test_all_benchmarks_pass_p95(self) -> None:
        results = run_all_benchmarks()
        for r in results:
            assert r.passed, f"{r.name} p95={r.measurement.p95:.3f}ms exceeds {r.target.p95_threshold_ms}ms"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
