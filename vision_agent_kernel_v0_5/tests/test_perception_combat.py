"""Tests for perception AoE timing estimator and enemy weak state detector."""
from __future__ import annotations

import time

import pytest

from perception.aoe_timing_estimator import (
    AoETimingEstimator,
    AoEWarning,
    DodgeWindow,
)
from perception.enemy_weak_state_detector import (
    EnemyWeakStateDetector,
    WeakStateEvent,
    WeakStateType,
)


class TestAoETimingEstimator:
    def test_empty_update(self):
        est = AoETimingEstimator()
        windows = est.update([])
        assert windows == []

    def test_circle_warning_estimate(self):
        est = AoETimingEstimator()
        now = time.perf_counter()
        warning = AoEWarning(
            center_x=0.5, center_y=0.5, radius=50.0,
            fill_ratio=0.4, aoe_type="circle", timestamp=now,
        )
        windows = est.update([warning])
        assert len(windows) >= 1
        assert windows[0].time_to_impact > 0
        assert windows[0].urgency in ("immediate", "soon", "caution")

    def test_immediate_urgency(self):
        est = AoETimingEstimator()
        now = time.perf_counter()
        warning = AoEWarning(
            center_x=0.5, center_y=0.5, radius=50.0,
            fill_ratio=0.95, aoe_type="circle", timestamp=now,
        )
        windows = est.update([warning])
        assert windows[0].urgency == "immediate"

    def test_dodge_direction_left(self):
        est = AoETimingEstimator()
        now = time.perf_counter()
        warning = AoEWarning(
            center_x=0.7, center_y=0.5, radius=30.0,
            fill_ratio=0.5, aoe_type="circle", timestamp=now,
        )
        windows = est.update([warning])
        assert windows[0].safe_direction == "left"

    def test_dodge_direction_right(self):
        est = AoETimingEstimator()
        now = time.perf_counter()
        warning = AoEWarning(
            center_x=0.3, center_y=0.5, radius=30.0,
            fill_ratio=0.5, aoe_type="circle", timestamp=now,
        )
        windows = est.update([warning])
        assert windows[0].safe_direction == "right"

    def test_record_dodge(self):
        est = AoETimingEstimator()
        est.record_dodge(True)
        est.record_dodge(True)
        est.record_dodge(False)
        assert est.dodge_rate == pytest.approx(2 / 3)

    def test_stats(self):
        est = AoETimingEstimator()
        est.record_dodge(True)
        assert est.stats["dodges"] == 1
        assert est.stats["hits"] == 0

    def test_multiple_warnings_sorted(self):
        est = AoETimingEstimator()
        now = time.perf_counter()
        w1 = AoEWarning(0.5, 0.5, 50.0, 0.3, "circle", timestamp=now)
        w2 = AoEWarning(0.3, 0.5, 30.0, 0.9, "circle", timestamp=now)
        windows = est.update([w1, w2])
        assert windows[0].time_to_impact <= windows[1].time_to_impact


class TestEnemyWeakStateDetector:
    def test_detect_no_state(self):
        det = EnemyWeakStateDetector()
        events = det.detect(None)
        assert events == []

    def test_detect_shield_broken(self):
        det = EnemyWeakStateDetector()
        events = det.detect({"shield_broken": True}, target_id="boss_1")
        assert len(events) == 1
        assert events[0].state_type == WeakStateType.SHIELD_BROKEN

    def test_detect_frozen(self):
        det = EnemyWeakStateDetector()
        events = det.detect({"frozen": True}, target_id="enemy_1")
        assert len(events) == 1
        assert events[0].state_type == WeakStateType.FROZEN

    def test_detect_multiple_states(self):
        det = EnemyWeakStateDetector()
        events = det.detect(
            {"frozen": True, "downed": True},
            target_id="boss",
        )
        assert len(events) == 2

    def test_burst_window_available(self):
        det = EnemyWeakStateDetector()
        det.detect({"core_exposed": True}, target_id="boss")
        assert det.tracker.has_burst_window

    def test_best_window_selects_longest(self):
        det = EnemyWeakStateDetector()
        det.detect({"staggered": True, "core_exposed": True}, target_id="boss")
        best = det.tracker.best_window
        assert best is not None
        assert best.state_type == WeakStateType.EXPOSED_CORE

    def test_burst_efficiency(self):
        det = EnemyWeakStateDetector()
        det.record_burst(True)
        det.record_burst(True)
        det.record_burst(False)
        assert det.burst_efficiency == pytest.approx(2 / 3)

    def test_states_expire(self):
        det = EnemyWeakStateDetector()
        det.detect({"staggered": True}, target_id="e")
        assert len(det.tracker.active_states) == 1
        # After duration, detect with no new states should expire old
        time.sleep(0.1)
        det.detect({}, target_id="e")
        # staggered duration is 2s, should still be alive
        assert len(det.tracker.active_states) == 1

    def test_duration_map(self):
        det = EnemyWeakStateDetector()
        events = det.detect({"core_exposed": True}, target_id="boss")
        assert events[0].estimated_duration == 15.0
