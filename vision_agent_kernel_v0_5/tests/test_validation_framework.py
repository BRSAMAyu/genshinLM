"""Tests for runtime/validation_framework.py: test pyramid, registry, metrics, dashboard."""
from __future__ import annotations

from runtime.validation_framework import (
    CapabilityDomain,
    EnvironmentRequirement,
    TestCase,
    TestResult,
    TestStatus,
    TestTier,
    TierMetrics,
    ValidationFramework,
)


def _make_case(test_id: str = "T-001", tier: TestTier = TestTier.UNIT,
               domain: CapabilityDomain = CapabilityDomain.PERCEPTION) -> TestCase:
    return TestCase(
        test_id=test_id, name=f"test_{test_id}", tier=tier, domain=domain,
        description="sample test", environment=EnvironmentRequirement.MOCK_ONLY,
    )


class TestTestCase:
    def test_creation(self):
        tc = _make_case()
        assert tc.test_id == "T-001"
        assert tc.tier == TestTier.UNIT
        assert tc.domain == CapabilityDomain.PERCEPTION

    def test_environment_types(self):
        assert EnvironmentRequirement.MOCK_ONLY.value == "mock_only"
        assert EnvironmentRequirement.PRODUCTION.value == "production"


class TestTestResult:
    def test_auto_timestamp(self):
        result = TestResult(test_id="T-001", status=TestStatus.PASSED)
        assert result.timestamp > 0.0

    def test_with_metrics(self):
        result = TestResult(
            test_id="T-001", status=TestStatus.PASSED,
            duration_sec=1.5, metrics={"accuracy": 0.97},
        )
        assert result.metrics["accuracy"] == 0.97


class TestTierMetrics:
    def test_pass_rate_all_passed(self):
        m = TierMetrics(tier=TestTier.UNIT, total=10, passed=10)
        assert m.pass_rate == 1.0

    def test_pass_rate_mixed(self):
        m = TierMetrics(tier=TestTier.UNIT, total=10, passed=7, failed=3)
        assert m.pass_rate == 0.7

    def test_pass_rate_no_runs(self):
        m = TierMetrics(tier=TestTier.UNIT)
        assert m.pass_rate == 0.0

    def test_to_dict(self):
        m = TierMetrics(tier=TestTier.UNIT, total=5, passed=4, failed=1)
        d = m.to_dict()
        assert d["tier"] == "unit"
        assert d["passed"] == 4
        assert "80.0%" in d["pass_rate"]


class TestValidationFramework:
    def test_register_and_get(self):
        fw = ValidationFramework()
        tc = _make_case("P-UT-001")
        fw.register(tc)
        assert fw.get_test("P-UT-001") is tc

    def test_register_batch(self):
        fw = ValidationFramework()
        cases = [_make_case(f"T-{i}") for i in range(5)]
        fw.register_batch(cases)
        assert len(fw.test_cases) == 5

    def test_record_result(self):
        fw = ValidationFramework()
        fw.register(_make_case("T-001"))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED, duration_sec=0.5))
        latest = fw.get_latest_result("T-001")
        assert latest is not None
        assert latest.status == TestStatus.PASSED

    def test_multiple_results_keeps_history(self):
        fw = ValidationFramework()
        fw.register(_make_case("T-001"))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.FAILED))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED))
        assert len(fw.results["T-001"]) == 2
        assert fw.get_latest_result("T-001").status == TestStatus.PASSED

    def test_consecutive_passes(self):
        fw = ValidationFramework()
        fw.register(_make_case("T-001"))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED))
        assert fw.get_consecutive_passes("T-001") == 3

    def test_consecutive_passes_broken_by_failure(self):
        fw = ValidationFramework()
        fw.register(_make_case("T-001"))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.FAILED))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED))
        assert fw.get_consecutive_passes("T-001") == 1

    def test_is_test_verified_unit(self):
        fw = ValidationFramework()
        fw.register(_make_case("T-001", tier=TestTier.UNIT))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED))
        # Unit tier requires 1 consecutive pass
        assert fw.is_test_verified("T-001")

    def test_is_test_not_verified_scenario(self):
        fw = ValidationFramework()
        fw.register(_make_case("T-001", tier=TestTier.SCENARIO))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED))
        # Scenario tier requires 3 consecutive passes
        assert not fw.is_test_verified("T-001")

    def test_is_test_verified_scenario_after_3_passes(self):
        fw = ValidationFramework()
        fw.register(_make_case("T-001", tier=TestTier.SCENARIO))
        for _ in range(3):
            fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED))
        assert fw.is_test_verified("T-001")

    def test_unknown_test_not_verified(self):
        fw = ValidationFramework()
        assert not fw.is_test_verified("nonexistent")


class TestMetrics:
    def test_compute_tier_metrics(self):
        fw = ValidationFramework()
        fw.register(_make_case("T-001", tier=TestTier.UNIT))
        fw.register(_make_case("T-002", tier=TestTier.UNIT))
        fw.register(_make_case("T-003", tier=TestTier.INTEGRATION))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED, duration_sec=0.5))
        fw.record_result(TestResult(test_id="T-002", status=TestStatus.FAILED, duration_sec=0.3))
        fw.record_result(TestResult(test_id="T-003", status=TestStatus.PASSED, duration_sec=2.0))

        unit_metrics = fw.compute_tier_metrics(TestTier.UNIT)
        assert unit_metrics.total == 2
        assert unit_metrics.passed == 1
        assert unit_metrics.failed == 1
        assert unit_metrics.pass_rate == 0.5

        int_metrics = fw.compute_tier_metrics(TestTier.INTEGRATION)
        assert int_metrics.total == 1
        assert int_metrics.passed == 1

    def test_compute_domain_metrics(self):
        fw = ValidationFramework()
        fw.register(_make_case("T-001", domain=CapabilityDomain.COMBAT))
        fw.register(_make_case("T-002", domain=CapabilityDomain.COMBAT))
        fw.register(_make_case("T-003", domain=CapabilityDomain.NAVIGATION))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED))
        fw.record_result(TestResult(test_id="T-002", status=TestStatus.PASSED))
        fw.record_result(TestResult(test_id="T-003", status=TestStatus.FAILED))

        combat = fw.compute_domain_metrics(CapabilityDomain.COMBAT)
        assert combat.total == 2
        assert combat.passed == 2


class TestDashboard:
    def test_dashboard_empty(self):
        fw = ValidationFramework()
        d = fw.dashboard()
        assert d["total_registered"] == 0
        assert d["total_verified"] == 0

    def test_dashboard_with_data(self):
        fw = ValidationFramework()
        fw.register(_make_case("T-001", tier=TestTier.UNIT, domain=CapabilityDomain.COMBAT))
        fw.register(_make_case("T-002", tier=TestTier.UNIT, domain=CapabilityDomain.COMBAT))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED))
        fw.record_result(TestResult(test_id="T-002", status=TestStatus.PASSED))

        d = fw.dashboard()
        assert d["total_registered"] == 2
        assert d["total_with_results"] == 2
        assert d["total_verified"] == 2
        assert "unit" in d["by_tier"]
        assert "combat" in d["by_domain"]


class TestCoverage:
    def test_tier_coverage_full(self):
        fw = ValidationFramework()
        fw.register(_make_case("T-001", tier=TestTier.UNIT))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED))
        assert fw.tier_coverage(TestTier.UNIT) == 1.0

    def test_tier_coverage_partial(self):
        fw = ValidationFramework()
        fw.register(_make_case("T-001", tier=TestTier.UNIT))
        fw.register(_make_case("T-002", tier=TestTier.UNIT))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED))
        assert fw.tier_coverage(TestTier.UNIT) == 0.5

    def test_domain_coverage(self):
        fw = ValidationFramework()
        fw.register(_make_case("T-001", domain=CapabilityDomain.NAVIGATION))
        fw.register(_make_case("T-002", domain=CapabilityDomain.NAVIGATION))
        fw.record_result(TestResult(test_id="T-001", status=TestStatus.PASSED))
        assert fw.domain_coverage(CapabilityDomain.NAVIGATION) == 0.5

    def test_empty_tier_coverage(self):
        fw = ValidationFramework()
        assert fw.tier_coverage(TestTier.MILESTONE) == 0.0
