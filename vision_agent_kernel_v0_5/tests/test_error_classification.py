"""Tests for runtime/error_classification.py: 7-category × 4-severity taxonomy + RecoveryStateMachine."""
from __future__ import annotations

import time

from runtime.error_classification import (
    ErrorCategory,
    ErrorEvent,
    ErrorSeverity,
    RecoveryPhase,
    RecoveryStateMachine,
    RecoveryWatchdog,
    classify_error,
)


# ---------------------------------------------------------------------------
# ErrorCategory / ErrorSeverity enums
# ---------------------------------------------------------------------------

def test_error_category_has_7_members():
    assert len(ErrorCategory) == 7
    expected = {"PERCEPTION", "NAVIGATION", "COMBAT", "UI", "INPUT", "SYSTEM", "ENVIRONMENT"}
    assert {e.name for e in ErrorCategory} == expected


def test_error_severity_ordering():
    assert ErrorSeverity.P0_CRITICAL.value < ErrorSeverity.P1_SEVERE.value
    assert ErrorSeverity.P1_SEVERE.value < ErrorSeverity.P2_MODERATE.value
    assert ErrorSeverity.P2_MODERATE.value < ErrorSeverity.P3_MINOR.value


def test_recovery_phase_has_6_members():
    assert len(RecoveryPhase) == 6
    expected = {"NORMAL", "ANOMALY", "DIAGNOSE", "PLAN", "RECOVER", "ESCALATE"}
    assert {e.name for e in RecoveryPhase} == expected


# ---------------------------------------------------------------------------
# ErrorEvent dataclass
# ---------------------------------------------------------------------------

def test_error_event_frozen():
    ev = ErrorEvent(category=ErrorCategory.SYSTEM, severity=ErrorSeverity.P3_MINOR, code="TEST", source="ut")
    mutated = False
    try:
        ev.code = "OTHER"  # type: ignore[misc]
    except AttributeError:
        mutated = True
    assert mutated


def test_error_event_auto_timestamp():
    before = time.perf_counter()
    ev = ErrorEvent(category=ErrorCategory.UI, severity=ErrorSeverity.P2_MODERATE, code="BTN", source="ut")
    after = time.perf_counter()
    assert before <= ev.timestamp <= after


def test_error_event_explicit_timestamp():
    ev = ErrorEvent(
        category=ErrorCategory.UI, severity=ErrorSeverity.P2_MODERATE,
        code="BTN", source="ut", timestamp=1234.5,
    )
    assert ev.timestamp == 1234.5


def test_error_event_priority():
    ev_p0 = ErrorEvent(category=ErrorCategory.SYSTEM, severity=ErrorSeverity.P0_CRITICAL, code="X", source="ut")
    ev_p3 = ErrorEvent(category=ErrorCategory.SYSTEM, severity=ErrorSeverity.P3_MINOR, code="X", source="ut")
    assert ev_p0.priority < ev_p3.priority


def test_error_event_context():
    ev = ErrorEvent(
        category=ErrorCategory.COMBAT, severity=ErrorSeverity.P1_SEVERE,
        code="WIPE", source="ut", context={"boss": "childe", "phase": 2},
    )
    assert ev.context["boss"] == "childe"


# ---------------------------------------------------------------------------
# classify_error — category mapping
# ---------------------------------------------------------------------------

def test_classify_perception_codes():
    for code in ("LOW_CONFIDENCE", "TRACKER_DIVERGED", "OCR_MISREAD", "VLM_TIMEOUT", "SCREEN_CLASSIFY_LOW"):
        ev = classify_error(code)
        assert ev.category == ErrorCategory.PERCEPTION, f"{code} → {ev.category}"


def test_classify_navigation_codes():
    for code in ("STUCK", "TARGET_LOST", "PATH_FAILED", "TELEPORT_FAILED", "WAYPOINT_NOT_FOUND"):
        ev = classify_error(code)
        assert ev.category == ErrorCategory.NAVIGATION, f"{code} → {ev.category}"


def test_classify_combat_codes():
    for code in ("CHARACTER_DIED", "TEAM_WIPE", "COMBO_INTERRUPTED", "REACTION_ERROR", "BOSS_MECHANIC_FAILED", "RESIN_EMPTY"):
        ev = classify_error(code)
        assert ev.category == ErrorCategory.COMBAT, f"{code} → {ev.category}"


def test_classify_ui_codes():
    for code in ("BUTTON_NOT_FOUND", "UNKNOWN_POPUP", "UI_DEPTH_MISMATCH", "INPUT_TIMEOUT", "BLOCKING_NOTIFICATION", "LOADING_STUCK"):
        ev = classify_error(code)
        assert ev.category == ErrorCategory.UI, f"{code} → {ev.category}"


def test_classify_input_codes():
    for code in ("FOCUS_LOST", "LEASE_EXPIRED", "DEADLOCK", "INPUT_QUEUE_FULL"):
        ev = classify_error(code)
        assert ev.category == ErrorCategory.INPUT, f"{code} → {ev.category}"


def test_classify_system_codes():
    for code in ("GAME_CRASHED", "GPU_FAILURE", "NETWORK_DISCONNECT", "OOM", "VERSION_UPDATE"):
        ev = classify_error(code)
        assert ev.category == ErrorCategory.SYSTEM, f"{code} → {ev.category}"


def test_classify_environment_codes():
    for code in ("STAMINA_DEPLETED", "HAZARD_DANGER", "DROWNING", "TERRAIN_SHIFT", "WEATHER_LOW_VIS"):
        ev = classify_error(code)
        assert ev.category == ErrorCategory.ENVIRONMENT, f"{code} → {ev.category}"


def test_classify_unknown_code_defaults_to_system():
    ev = classify_error("UNKNOWN_ERROR_XYZ")
    assert ev.category == ErrorCategory.SYSTEM


# ---------------------------------------------------------------------------
# classify_error — severity mapping
# ---------------------------------------------------------------------------

def test_critical_codes_p0():
    for code in ("FOCUS_LOST", "GAME_CRASHED", "GPU_FAILURE", "DEADLOCK"):
        ev = classify_error(code)
        assert ev.severity == ErrorSeverity.P0_CRITICAL, f"{code} → {ev.severity}"
        assert ev.recoverable is False
        assert ev.requires_input_release is True


def test_severe_codes_p1():
    for code in ("TEAM_WIPE", "LOADING_STUCK", "NETWORK_DISCONNECT", "OOM", "DROWNING", "LEASE_EXPIRED"):
        ev = classify_error(code)
        assert ev.severity == ErrorSeverity.P1_SEVERE, f"{code} → {ev.severity}"
        assert ev.recoverable is True


def test_team_wipe_requires_release():
    ev = classify_error("TEAM_WIPE")
    assert ev.requires_input_release is True


def test_perception_navigation_p2():
    for code in ("LOW_CONFIDENCE", "STUCK", "TARGET_LOST", "OCR_MISREAD"):
        ev = classify_error(code)
        assert ev.severity == ErrorSeverity.P2_MODERATE, f"{code} → {ev.severity}"
        assert ev.requires_input_release is False


def test_other_codes_p3():
    for code in ("CHARACTER_DIED", "COMBO_INTERRUPTED", "STAMINA_DEPLETED", "HAZARD_DANGER"):
        ev = classify_error(code)
        assert ev.severity == ErrorSeverity.P3_MINOR, f"{code} → {ev.severity}"


def test_classify_error_passes_source_and_context():
    ev = classify_error("STUCK", source="navigator", waypoint="monstadt", distance=120.5)
    assert ev.source == "navigator"
    assert ev.context["waypoint"] == "monstadt"
    assert ev.context["distance"] == 120.5


# ---------------------------------------------------------------------------
# RecoveryStateMachine — transitions
# ---------------------------------------------------------------------------

def _make_sm() -> RecoveryStateMachine:
    return RecoveryStateMachine()


def test_sm_starts_normal():
    sm = _make_sm()
    assert sm.phase == RecoveryPhase.NORMAL
    assert sm.is_recovering is False
    assert sm.should_abort is False
    assert sm.escalation_count == 0


def test_sm_normal_to_anomaly():
    sm = _make_sm()
    result = sm.transition("anomaly_detected")
    assert result == RecoveryPhase.ANOMALY
    assert sm.phase == RecoveryPhase.ANOMALY
    assert sm.is_recovering is True


def test_sm_normal_to_anomaly_via_interrupt():
    sm = _make_sm()
    result = sm.transition("interrupt_received")
    assert result == RecoveryPhase.ANOMALY


def test_sm_full_recovery_flow():
    sm = _make_sm()
    sm.transition("anomaly_detected")
    assert sm.phase == RecoveryPhase.ANOMALY
    sm.transition("diagnosis_complete")
    assert sm.phase == RecoveryPhase.DIAGNOSE
    sm.transition("strategy_selected")
    assert sm.phase == RecoveryPhase.PLAN
    sm.transition("recovery_executed")
    assert sm.phase == RecoveryPhase.RECOVER
    # verification_success resets escalation_count
    sm.escalation_count = 2  # simulate prior escalations
    sm.transition("verification_success")
    assert sm.phase == RecoveryPhase.NORMAL
    assert sm.escalation_count == 0


def test_sm_escalate_on_verification_failed():
    sm = _make_sm()
    sm.transition("anomaly_detected")
    sm.transition("diagnosis_complete")
    sm.transition("strategy_selected")
    sm.transition("recovery_executed")
    result = sm.transition("verification_failed")
    assert result == RecoveryPhase.ESCALATE
    assert sm.escalation_count == 1


def test_sm_escalate_on_budget_exhausted():
    sm = _make_sm()
    sm.transition("anomaly_detected")
    sm.transition("diagnosis_complete")
    sm.transition("strategy_selected")
    sm.transition("recovery_executed")
    sm.transition("budget_exhausted")
    assert sm.phase == RecoveryPhase.ESCALATE
    assert sm.escalation_count == 1


def test_sm_escalate_to_normal_via_manual():
    sm = _make_sm()
    sm.transition("anomaly_detected")
    sm.transition("diagnosis_complete")
    sm.transition("strategy_selected")
    sm.transition("recovery_executed")
    sm.transition("verification_failed")
    assert sm.phase == RecoveryPhase.ESCALATE
    assert sm.escalation_count == 1
    sm.transition("manual_intervention")
    assert sm.phase == RecoveryPhase.NORMAL
    # manual_intervention does NOT reset escalation_count — only verification_success does
    assert sm.escalation_count == 1


def test_sm_invalid_transition_noop():
    sm = _make_sm()
    result = sm.transition("strategy_selected")  # invalid from NORMAL
    assert result == RecoveryPhase.NORMAL
    assert sm.phase == RecoveryPhase.NORMAL


def test_sm_should_abort_after_max_escalations():
    """should_abort triggers when escalation_count accumulates across cycles."""
    sm = _make_sm()
    for _ in range(sm.max_escalations):
        sm.transition("anomaly_detected")
        sm.transition("diagnosis_complete")
        sm.transition("strategy_selected")
        sm.transition("recovery_executed")
        sm.transition("verification_failed")
        assert sm.phase == RecoveryPhase.ESCALATE
        # manual_intervention goes to NORMAL but does NOT reset escalation_count
        sm.transition("manual_intervention")
        assert sm.phase == RecoveryPhase.NORMAL
    assert sm.escalation_count == sm.max_escalations
    assert sm.should_abort is True


def test_sm_accept_error_p0_interrupts():
    sm = _make_sm()
    error = ErrorEvent(
        category=ErrorCategory.INPUT, severity=ErrorSeverity.P0_CRITICAL,
        code="FOCUS_LOST", source="ut",
    )
    result = sm.accept_error(error)
    assert result == RecoveryPhase.ANOMALY


def test_sm_accept_error_p1_interrupts():
    sm = _make_sm()
    error = ErrorEvent(
        category=ErrorCategory.COMBAT, severity=ErrorSeverity.P1_SEVERE,
        code="TEAM_WIPE", source="ut",
    )
    result = sm.accept_error(error)
    assert result == RecoveryPhase.ANOMALY


def test_sm_accept_error_p2_anomaly():
    sm = _make_sm()
    error = ErrorEvent(
        category=ErrorCategory.NAVIGATION, severity=ErrorSeverity.P2_MODERATE,
        code="STUCK", source="ut",
    )
    result = sm.accept_error(error)
    assert result == RecoveryPhase.ANOMALY


def test_sm_accept_error_in_recovery_stays():
    sm = _make_sm()
    sm.transition("anomaly_detected")
    assert sm.phase == RecoveryPhase.ANOMALY
    error = ErrorEvent(
        category=ErrorCategory.NAVIGATION, severity=ErrorSeverity.P2_MODERATE,
        code="STUCK", source="ut",
    )
    result = sm.accept_error(error)
    # Already in ANOMALY — stays in ANOMALY
    assert result == RecoveryPhase.ANOMALY


def test_sm_error_history_trims_at_100():
    sm = _make_sm()
    for i in range(150):
        error = ErrorEvent(
            category=ErrorCategory.NAVIGATION, severity=ErrorSeverity.P2_MODERATE,
            code="STUCK", source="ut",
        )
        sm.accept_error(error)
    # After 150 calls: trims at 101→50, then grows 49 more → 99
    assert len(sm.error_history) == 99


def test_sm_duration_in_phase():
    sm = _make_sm()
    before = sm.duration_in_phase_sec
    assert before >= 0.0
    time.sleep(0.05)
    after = sm.duration_in_phase_sec
    assert after > before


# ---------------------------------------------------------------------------
# Integration: classify + state machine
# ---------------------------------------------------------------------------

def test_classify_and_drive_sm_critical():
    sm = _make_sm()
    ev = classify_error("GAME_CRASHED", source="watchdog")
    assert ev.severity == ErrorSeverity.P0_CRITICAL
    assert ev.recoverable is False
    sm.accept_error(ev)
    assert sm.phase == RecoveryPhase.ANOMALY


def test_classify_and_drive_sm_navigation():
    sm = _make_sm()
    ev = classify_error("STUCK", source="navigator")
    assert ev.category == ErrorCategory.NAVIGATION
    sm.accept_error(ev)
    assert sm.phase == RecoveryPhase.ANOMALY


def test_all_codes_classify_without_error():
    """Ensure every defined error code classifies cleanly."""
    all_codes = [
        "LOW_CONFIDENCE", "TRACKER_DIVERGED", "OCR_MISREAD", "VLM_TIMEOUT", "SCREEN_CLASSIFY_LOW",
        "STUCK", "TARGET_LOST", "PATH_FAILED", "TELEPORT_FAILED", "WAYPOINT_NOT_FOUND",
        "CHARACTER_DIED", "TEAM_WIPE", "COMBO_INTERRUPTED", "REACTION_ERROR", "BOSS_MECHANIC_FAILED", "RESIN_EMPTY",
        "BUTTON_NOT_FOUND", "UNKNOWN_POPUP", "UI_DEPTH_MISMATCH", "INPUT_TIMEOUT", "BLOCKING_NOTIFICATION", "LOADING_STUCK",
        "FOCUS_LOST", "LEASE_EXPIRED", "DEADLOCK", "INPUT_QUEUE_FULL",
        "GAME_CRASHED", "GPU_FAILURE", "NETWORK_DISCONNECT", "OOM", "VERSION_UPDATE",
        "STAMINA_DEPLETED", "HAZARD_DANGER", "DROWNING", "TERRAIN_SHIFT", "WEATHER_LOW_VIS",
    ]
    for code in all_codes:
        ev = classify_error(code)
        assert isinstance(ev, ErrorEvent)
        assert ev.code == code


# ---------------------------------------------------------------------------
# RecoveryWatchdog
# ---------------------------------------------------------------------------

class TestRecoveryWatchdog:
    def test_starts_healthy(self):
        wd = RecoveryWatchdog()
        assert wd.is_healthy
        assert wd.stats["phase"] == "normal"

    def test_submit_error_classifies(self):
        wd = RecoveryWatchdog()
        ev = wd.submit_error("STUCK", source="nav")
        assert ev.category == ErrorCategory.NAVIGATION
        assert len(wd.pending_errors) == 1

    def test_tick_idle_when_no_errors(self):
        wd = RecoveryWatchdog()
        result = wd.tick()
        assert result["action"] == "idle"

    def test_tick_processes_error(self):
        wd = RecoveryWatchdog()
        wd.submit_error("STUCK", source="nav")
        result = wd.tick()
        # Fast-path drives through full cycle; without recovery_fn defaults to escalated
        assert result["action"] in ("recovered", "escalated", "idle")

    def test_full_recovery_cycle(self):
        recovered_errors: list[ErrorEvent] = []
        wd = RecoveryWatchdog(recovery_fn=lambda e: (recovered_errors.append(e), True)[1])
        wd.submit_error("STUCK", source="nav")
        result = wd.tick()
        assert result["action"] == "recovered"
        assert len(recovered_errors) == 1
        assert wd.is_healthy
        assert wd.stats["total_recovered"] == 1

    def test_escalation_on_recovery_failure(self):
        wd = RecoveryWatchdog(recovery_fn=lambda e: False)
        wd.submit_error("STUCK", source="nav")
        result = wd.tick()
        assert result["action"] == "escalated"
        assert wd.stats["total_escalated"] == 1

    def test_stats_tracking(self):
        wd = RecoveryWatchdog()
        wd.submit_error("STUCK")
        assert wd.stats["total_submitted"] == 1
        assert wd.stats["pending"] == 1

    def test_pending_trim(self):
        wd = RecoveryWatchdog(max_pending=10)
        for i in range(20):
            wd.submit_error("STUCK", source=f"test_{i}")
        assert len(wd.pending_errors) <= 10

    def test_recovery_fn_exception_handled(self):
        def bad_fn(e: ErrorEvent) -> bool:
            raise RuntimeError("test error")
        wd = RecoveryWatchdog(recovery_fn=bad_fn)
        wd.submit_error("STUCK")
        while wd.pending_errors or wd.state_machine.is_recovering:
            result = wd.tick()
            if result["action"] in ("escalated", "abort", "idle"):
                break
        # Should not crash, just escalate
