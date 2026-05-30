"""Tests for runtime/content_version_manager.py: version tracking, change detection, compatibility."""
from __future__ import annotations

from runtime.content_version_manager import (
    AdaptationStatus,
    ChangeType,
    ContentVersionManager,
    GameVersion,
    HealthCheckResult,
    HealthGrade,
    VersionChange,
)


class TestGameVersion:
    def test_parse_major_minor(self):
        v = GameVersion.parse("5.4")
        assert v.major == 5
        assert v.minor == 4
        assert v.patch == 0
        assert str(v) == "5.4"

    def test_parse_with_patch(self):
        v = GameVersion.parse("5.7.1")
        assert v.major == 5
        assert v.minor == 7
        assert v.patch == 1
        assert str(v) == "5.7.1"

    def test_ordering(self):
        v54 = GameVersion.parse("5.4")
        v57 = GameVersion.parse("5.7")
        v60 = GameVersion.parse("6.0")
        assert v54 < v57
        assert v57 < v60
        assert v60 > v54
        assert v54 <= v54
        assert v54 >= v54

    def test_equality(self):
        v1 = GameVersion.parse("5.4")
        v2 = GameVersion(5, 4, 0)
        assert v1 == v2

    def test_parse_single_number(self):
        v = GameVersion.parse("5")
        assert v.major == 5
        assert v.minor == 0


class TestVersionChange:
    def test_auto_timestamp(self):
        vc = VersionChange(
            change_id="vc_1", change_type=ChangeType.UI,
            game_version=GameVersion(5, 7), description="test",
        )
        assert vc.timestamp > 0.0

    def test_fields(self):
        vc = VersionChange(
            change_id="vc_2", change_type=ChangeType.MECHANISM,
            game_version=GameVersion(5, 0), description="dendro reaction",
            affected_capabilities=("combat",), severity="high",
        )
        assert vc.change_type == ChangeType.MECHANISM
        assert vc.severity == "high"
        assert "combat" in vc.affected_capabilities


class TestHealthCheckResult:
    def test_all_healthy(self):
        hc = HealthCheckResult()
        assert hc.average_score == 100.0
        assert hc.grade == HealthGrade.HEALTHY
        assert len(hc.failed_checks) == 0

    def test_degraded(self):
        hc = HealthCheckResult(ui_visibility=40, detector_confidence=45,
                               input_response=50, capture_health=60, clock_sync=70)
        assert hc.average_score < 80
        assert hc.grade == HealthGrade.DEGRADED
        assert "ui_visibility" in hc.failed_checks

    def test_critical(self):
        hc = HealthCheckResult(
            ui_visibility=30, detector_confidence=20,
            input_response=40, capture_health=10, clock_sync=50,
        )
        assert hc.average_score < 50
        assert hc.grade == HealthGrade.CRITICAL
        assert len(hc.failed_checks) == 5


class TestContentVersionManager:
    def test_set_known_version(self):
        mgr = ContentVersionManager()
        status = mgr.set_current_version("5.4")
        assert status == AdaptationStatus.VERIFIED

    def test_set_unknown_version(self):
        mgr = ContentVersionManager()
        status = mgr.set_current_version("99.0")
        assert status == AdaptationStatus.UNKNOWN

    def test_set_unverified_version(self):
        mgr = ContentVersionManager()
        status = mgr.set_current_version("5.7")
        assert status == AdaptationStatus.UNVERIFIED

    def test_version_change_triggers_record(self):
        mgr = ContentVersionManager()
        mgr.set_current_version("5.4")
        mgr.set_current_version("5.7")
        assert len(mgr.change_log) == 1
        assert mgr.change_log[0].change_type == ChangeType.CONTENT

    def test_same_version_no_record(self):
        mgr = ContentVersionManager()
        mgr.set_current_version("5.4")
        mgr.set_current_version("5.4")
        assert len(mgr.change_log) == 0

    def test_version_change_triggers_recalibration(self):
        mgr = ContentVersionManager()
        mgr.set_current_version("5.4")
        mgr.set_current_version("5.7")
        assert mgr.needs_recalibration

    def test_complete_recalibration(self):
        mgr = ContentVersionManager()
        mgr.set_current_version("5.7")
        mgr.trigger_recalibration()
        assert mgr.needs_recalibration
        mgr.complete_recalibration()
        assert not mgr.needs_recalibration
        assert mgr.get_adaptation_status() == AdaptationStatus.VERIFIED


class TestRuntimeAnomalyDetection:
    def test_report_successes(self):
        mgr = ContentVersionManager()
        mgr.set_current_version("5.4")
        for _ in range(10):
            mgr.report_operation_result("click", True)
        assert mgr.get_failure_rate("click") == 0.0

    def test_report_failures_triggers_anomaly(self):
        mgr = ContentVersionManager()
        mgr.set_current_version("5.4")
        for _ in range(15):
            mgr.report_operation_result("click", False)
        assert mgr.get_failure_rate("click") > 0.3
        # Anomaly recorded
        assert any(c.detection_source == "runtime_anomaly" for c in mgr.change_log)

    def test_mixed_results_no_anomaly(self):
        mgr = ContentVersionManager()
        mgr.set_current_version("5.4")
        # 90% success rate — never exceeds 30% threshold even in intermediate windows
        for i in range(20):
            mgr.report_operation_result("click", i % 10 != 0)
        assert mgr.get_failure_rate("click") < 0.3
        runtime_anomalies = [c for c in mgr.change_log if c.detection_source == "runtime_anomaly"]
        assert len(runtime_anomalies) == 0


class TestHealthCheck:
    def test_healthy_result(self):
        mgr = ContentVersionManager()
        result = mgr.run_health_check()
        assert result.grade == HealthGrade.HEALTHY
        assert len(mgr.health_history) == 1

    def test_degraded_result(self):
        mgr = ContentVersionManager()
        result = mgr.run_health_check(ui_visibility=30, detector_confidence=40,
                                      input_response=50, capture_health=60, clock_sync=70)
        assert result.grade == HealthGrade.DEGRADED

    def test_health_history_accumulates(self):
        mgr = ContentVersionManager()
        mgr.run_health_check()
        mgr.run_health_check(ui_visibility=60)
        assert len(mgr.health_history) == 2


class TestCompatibility:
    def test_verified_all_capabilities(self):
        mgr = ContentVersionManager()
        mgr.set_current_version("5.4")
        caps = mgr.get_compatible_capabilities()
        assert "all" in caps
        assert mgr.is_capability_safe("combat")
        assert mgr.is_capability_safe("navigation")

    def test_partial_limited_capabilities(self):
        mgr = ContentVersionManager()
        mgr.set_current_version("4.0")
        caps = mgr.get_compatible_capabilities()
        assert "all" not in caps
        assert "navigation" in caps

    def test_unknown_no_capabilities(self):
        mgr = ContentVersionManager()
        mgr.set_current_version("99.0")
        caps = mgr.get_compatible_capabilities()
        assert caps == []
        assert not mgr.is_capability_safe("combat")

    def test_no_version_no_capabilities(self):
        mgr = ContentVersionManager()
        caps = mgr.get_compatible_capabilities()
        assert caps == []


class TestStatusSummary:
    def test_summary(self):
        mgr = ContentVersionManager()
        mgr.set_current_version("5.4")
        summary = mgr.status_summary()
        assert summary["current_version"] == "5.4"
        assert summary["adaptation_status"] == "verified"
        assert summary["needs_recalibration"] is False

    def test_summary_no_version(self):
        mgr = ContentVersionManager()
        summary = mgr.status_summary()
        assert summary["current_version"] == "unknown"
