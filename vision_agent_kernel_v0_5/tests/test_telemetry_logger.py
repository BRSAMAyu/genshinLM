from __future__ import annotations

from telemetry.logger import AsyncJsonlLogger


def test_telemetry_logger_drops_instead_of_blocking_when_full(tmp_path) -> None:
    logger = AsyncJsonlLogger(tmp_path / "events.jsonl", max_queue_size=1)

    assert logger.log("first", {"ok": True})
    accepted = logger.log("second", {"ok": True})

    assert not accepted
    assert logger.dropped_count == 1
