from __future__ import annotations

import json

from telemetry.runtime_health import HealthReportBuilder, PriorityTelemetryQueue, RuntimeHealthSample


def test_priority_telemetry_drops_low_priority_when_full(tmp_path) -> None:
    telemetry = PriorityTelemetryQueue(tmp_path / "events.jsonl", maxsize=1)

    assert telemetry.log("observation_summary", {"frame_id": 1}, priority="low")
    assert not telemetry.log("observation_summary", {"frame_id": 2}, priority="low")

    assert telemetry.dropped_low_priority_logs == 1


def test_priority_telemetry_preserves_critical_by_evicting_low_priority(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    telemetry = PriorityTelemetryQueue(path, maxsize=1)

    assert telemetry.log("observation_summary", {"frame_id": 1}, priority="low")
    assert telemetry.log("interrupt", {"code": "WATCHDOG_TIMEOUT"}, priority="critical")
    telemetry.start()
    telemetry.close()

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert any(record["event_type"] == "interrupt" for record in records)
    assert telemetry.dropped_low_priority_logs >= 1


def test_health_report_builder_aggregates_samples() -> None:
    builder = HealthReportBuilder()
    builder.add_sample(
        RuntimeHealthSample(
            timestamp=1.0,
            perception_fps=55.0,
            detector_latency_ms=2.0,
            tracker_latency_ms=1.0,
            controller_fps=28.0,
            input_worker_alive=True,
            telemetry_backlog=3,
            latest_observation_age_ms=20.0,
            focus_ok=True,
            process_memory_mb=100.0,
            thread_count=8,
        )
    )
    builder.add_sample(
        RuntimeHealthSample(
            timestamp=2.0,
            perception_fps=45.0,
            detector_latency_ms=3.0,
            tracker_latency_ms=1.5,
            controller_fps=30.0,
            input_worker_alive=True,
            telemetry_backlog=7,
            latest_observation_age_ms=25.0,
            focus_ok=True,
            process_memory_mb=112.5,
            thread_count=9,
        )
    )
    builder.record_interrupt()

    report = builder.build(dropped_low_priority_logs=4, release_all_called=True)

    assert report.max_memory_mb == 112.5
    assert report.memory_growth_mb == 12.5
    assert report.avg_perception_fps == 50.0
    assert report.avg_controller_fps == 29.0
    assert report.max_telemetry_backlog == 7
    assert report.interrupt_count == 1
    assert report.dropped_low_priority_logs == 4
    assert report.release_all_called is True
