"""E2E validation framework: 4-tier test pyramid, test registry, metrics collection.

Implements the validation framework from GENSHIN_E2E_VALIDATION_FRAMEWORK.md:
- 4-tier test pyramid: Unit → Integration → Scenario → Milestone
- Test case registry with pass/fail criteria
- Metrics collection and dashboard data
- Environment requirement tracking
- Pass criteria enforcement per tier
"""
from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


class TestTier(enum.Enum):
    UNIT = "unit"                   # Bottom of pyramid, most tests, pure mock
    INTEGRATION = "integration"     # Multi-capability coordination
    SCENARIO = "scenario"           # End-to-end game scenario
    MILESTONE = "milestone"         # Cross-scenario long-running validation


class TestStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class EnvironmentRequirement(enum.Enum):
    MOCK_ONLY = "mock_only"             # Pure simulation, no game needed
    RECORDED_PLAYBACK = "recorded"      # Recorded gameplay data
    SANDBOX = "sandbox"                 # Test account in sandbox
    PRODUCTION = "production"           # Real game + human supervision


class CapabilityDomain(enum.Enum):
    PERCEPTION = "perception"
    NAVIGATION = "navigation"
    COMBAT = "combat"
    UI = "ui"
    EXPLORATION = "exploration"
    QUEST = "quest"
    DAILY_ROUTINE = "daily_routine"
    CHARACTER_PROGRESSION = "character_progression"
    SESSION = "session"
    ERROR_RECOVERY = "error_recovery"
    COLLABORATION = "collaboration"
    VERSIONING = "versioning"


# ---------------------------------------------------------------------------
# Test case definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TestCase:
    test_id: str
    name: str
    tier: TestTier
    domain: CapabilityDomain
    description: str = ""
    environment: EnvironmentRequirement = EnvironmentRequirement.MOCK_ONLY
    pass_criteria: str = ""           # e.g., "accuracy >= 0.95"
    max_duration_sec: float = 60.0
    capability_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class TestResult:
    test_id: str
    status: TestStatus
    duration_sec: float = 0.0
    message: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.perf_counter()


# ---------------------------------------------------------------------------
# Pass criteria per tier
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TierPassCriteria:
    tier: TestTier
    single_run_accuracy: float = 0.95
    single_run_success_rate: float = 0.80
    max_latency_ms: float = 100.0
    consecutive_passes_required: int = 1
    no_p0_p1_errors: bool = False


DEFAULT_TIER_CRITERIA: dict[TestTier, TierPassCriteria] = {
    TestTier.UNIT: TierPassCriteria(
        tier=TestTier.UNIT,
        single_run_accuracy=0.95,
        single_run_success_rate=0.80,
        max_latency_ms=100.0,
        consecutive_passes_required=1,
    ),
    TestTier.INTEGRATION: TierPassCriteria(
        tier=TestTier.INTEGRATION,
        single_run_accuracy=0.90,
        single_run_success_rate=0.85,
        max_latency_ms=500.0,
        consecutive_passes_required=1,
    ),
    TestTier.SCENARIO: TierPassCriteria(
        tier=TestTier.SCENARIO,
        single_run_accuracy=0.80,
        single_run_success_rate=0.75,
        max_latency_ms=5000.0,
        consecutive_passes_required=3,
    ),
    TestTier.MILESTONE: TierPassCriteria(
        tier=TestTier.MILESTONE,
        single_run_accuracy=0.90,
        single_run_success_rate=0.90,
        max_latency_ms=60000.0,
        consecutive_passes_required=2,
        no_p0_p1_errors=True,
    ),
}


# ---------------------------------------------------------------------------
# Metrics collection
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class TierMetrics:
    tier: TestTier
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    blocked: int = 0
    total_duration_sec: float = 0.0

    @property
    def pass_rate(self) -> float:
        run = self.passed + self.failed
        return self.passed / run if run > 0 else 0.0

    @property
    def avg_duration_sec(self) -> float:
        return self.total_duration_sec / self.total if self.total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier.value,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "pass_rate": f"{self.pass_rate:.1%}",
            "avg_duration_sec": f"{self.avg_duration_sec:.2f}",
        }


# ---------------------------------------------------------------------------
# Test registry and runner
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ValidationFramework:
    """Central registry for test cases and results.

    Usage::

        fw = ValidationFramework()
        fw.register(TestCase(test_id="P-UT-001", name="screen_classify", ...))
        fw.record_result(TestResult(test_id="P-UT-001", status=TestStatus.PASSED))
        report = fw.dashboard()
    """

    test_cases: dict[str, TestCase] = field(default_factory=dict)
    results: dict[str, list[TestResult]] = field(default_factory=dict)
    tier_criteria: dict[TestTier, TierPassCriteria] = field(
        default_factory=lambda: dict(DEFAULT_TIER_CRITERIA)
    )

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, test_case: TestCase) -> None:
        self.test_cases[test_case.test_id] = test_case

    def register_batch(self, cases: list[TestCase]) -> None:
        for tc in cases:
            self.register(tc)

    def get_test(self, test_id: str) -> TestCase | None:
        return self.test_cases.get(test_id)

    # ------------------------------------------------------------------
    # Result recording
    # ------------------------------------------------------------------

    def record_result(self, result: TestResult) -> None:
        if result.test_id not in self.results:
            self.results[result.test_id] = []
        self.results[result.test_id].append(result)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_latest_result(self, test_id: str) -> TestResult | None:
        history = self.results.get(test_id, [])
        return history[-1] if history else None

    def get_consecutive_passes(self, test_id: str) -> int:
        history = self.results.get(test_id, [])
        count = 0
        for result in reversed(history):
            if result.status == TestStatus.PASSED:
                count += 1
            else:
                break
        return count

    def is_test_verified(self, test_id: str) -> bool:
        tc = self.test_cases.get(test_id)
        if tc is None:
            return False
        criteria = self.tier_criteria.get(tc.tier)
        if criteria is None:
            latest = self.get_latest_result(test_id)
            return latest is not None and latest.status == TestStatus.PASSED
        consecutive = self.get_consecutive_passes(test_id)
        return consecutive >= criteria.consecutive_passes_required

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def compute_tier_metrics(self, tier: TestTier) -> TierMetrics:
        metrics = TierMetrics(tier=tier)
        for test_id, tc in self.test_cases.items():
            if tc.tier != tier:
                continue
            metrics.total += 1
            latest = self.get_latest_result(test_id)
            if latest is None:
                continue
            if latest.status == TestStatus.PASSED:
                metrics.passed += 1
                metrics.total_duration_sec += latest.duration_sec
            elif latest.status == TestStatus.FAILED:
                metrics.failed += 1
                metrics.total_duration_sec += latest.duration_sec
            elif latest.status == TestStatus.SKIPPED:
                metrics.skipped += 1
            elif latest.status == TestStatus.BLOCKED:
                metrics.blocked += 1
        return metrics

    def compute_domain_metrics(self, domain: CapabilityDomain) -> TierMetrics:
        metrics = TierMetrics(tier=TestTier.UNIT)  # reuse struct
        for test_id, tc in self.test_cases.items():
            if tc.domain != domain:
                continue
            metrics.total += 1
            latest = self.get_latest_result(test_id)
            if latest is None:
                continue
            if latest.status == TestStatus.PASSED:
                metrics.passed += 1
            elif latest.status == TestStatus.FAILED:
                metrics.failed += 1
            elif latest.status == TestStatus.SKIPPED:
                metrics.skipped += 1
        return metrics

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def dashboard(self) -> dict[str, Any]:
        tier_data = {}
        for tier in TestTier:
            m = self.compute_tier_metrics(tier)
            tier_data[tier.value] = m.to_dict()

        domain_data = {}
        for domain in CapabilityDomain:
            m = self.compute_domain_metrics(domain)
            if m.total > 0:
                domain_data[domain.value] = m.to_dict()

        total_tests = len(self.test_cases)
        total_with_results = sum(1 for tid in self.test_cases if self.get_latest_result(tid) is not None)
        verified = sum(1 for tid in self.test_cases if self.is_test_verified(tid))

        return {
            "total_registered": total_tests,
            "total_with_results": total_with_results,
            "total_verified": verified,
            "verification_rate": f"{verified / total_tests:.1%}" if total_tests > 0 else "N/A",
            "by_tier": tier_data,
            "by_domain": domain_data,
        }

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------

    def tier_coverage(self, tier: TestTier) -> float:
        tier_tests = [tc for tc in self.test_cases.values() if tc.tier == tier]
        if not tier_tests:
            return 0.0
        with_results = sum(1 for tc in tier_tests if self.get_latest_result(tc.test_id) is not None)
        return with_results / len(tier_tests)

    def domain_coverage(self, domain: CapabilityDomain) -> float:
        domain_tests = [tc for tc in self.test_cases.values() if tc.domain == domain]
        if not domain_tests:
            return 0.0
        with_results = sum(1 for tc in domain_tests if self.get_latest_result(tc.test_id) is not None)
        return with_results / len(domain_tests)
