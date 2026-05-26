"""Tests for Benchmark Curriculum — tasks and metrics."""
from __future__ import annotations

import json

import pytest

from benchmarks.mainline_curriculum.tasks import BenchmarkTask, TASKS, get_task, all_tasks
from benchmarks.mainline_curriculum.metrics import BenchmarkReport, MetricSnapshot


class TestBenchmarkTasks:
    def test_all_12_tasks_exist(self) -> None:
        assert len(TASKS) == 12
        ids = [t.task_id for t in TASKS]
        for i in range(12):
            assert f"C{i}" in ids

    def test_get_task(self) -> None:
        c0 = get_task("C0")
        assert c0 is not None
        assert c0.name == "Bootstrap Startup"

    def test_get_nonexistent(self) -> None:
        assert get_task("C99") is None

    def test_all_tasks_returns_tuple(self) -> None:
        assert isinstance(all_tasks(), tuple)
        assert len(all_tasks()) == 12

    def test_tasks_have_criteria(self) -> None:
        for t in TASKS:
            assert t.success_criteria, f"{t.task_id} has no success criteria"
            assert t.difficulty >= 1
            assert t.difficulty <= 5
            assert t.category

    def test_difficulty_ascending(self) -> None:
        """Generally, later tasks are harder."""
        difficulties = [t.difficulty for t in TASKS]
        assert difficulties[-1] >= difficulties[0]

    def test_time_limits(self) -> None:
        for t in TASKS:
            assert t.time_limit_sec > 0


class TestMetrics:
    def test_metric_snapshot_defaults(self) -> None:
        m = MetricSnapshot()
        assert m.tsr == 0.0
        assert m.hic == 0
        assert m.variant == "full_system"
        assert m.timestamp > 0

    def test_metric_to_dict(self) -> None:
        m = MetricSnapshot(task_id="C0", tsr=1.0, claim_count=5)
        d = m.to_dict()
        assert d["task_id"] == "C0"
        assert d["tsr"] == 1.0
        assert d["claim_count"] == 5

    def test_metric_to_json(self) -> None:
        m = MetricSnapshot(task_id="C1", tsr=0.5)
        j = m.to_json()
        parsed = json.loads(j)
        assert parsed["task_id"] == "C1"

    def test_report_aggregation(self) -> None:
        report = BenchmarkReport(variant="full_system")
        report.add(MetricSnapshot(task_id="C0", tsr=1.0))
        report.add(MetricSnapshot(task_id="C1", tsr=0.5))
        report.add(MetricSnapshot(task_id="C6", tsr=0.0))
        assert report.overall_tsr == pytest.approx(0.5)
        assert report.bottleneck_task == "C6"

    def test_report_empty(self) -> None:
        report = BenchmarkReport()
        assert report.overall_tsr == 0.0
        assert report.bottleneck_task == ""

    def test_report_to_json(self) -> None:
        report = BenchmarkReport()
        report.add(MetricSnapshot(task_id="C0", tsr=1.0))
        j = report.to_json()
        parsed = json.loads(j)
        assert parsed["task_count"] == 1
        assert parsed["tasks"][0]["task_id"] == "C0"

    def test_variant(self) -> None:
        m = MetricSnapshot(variant="no_bagel")
        assert m.variant == "no_bagel"
