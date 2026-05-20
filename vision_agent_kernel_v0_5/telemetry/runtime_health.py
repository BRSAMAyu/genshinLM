from __future__ import annotations

import json
import queue
import threading
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Literal

from core.timebase import perf_counter_seconds


TelemetryPriority = Literal["low", "critical"]

CRITICAL_EVENT_TYPES = {
    "interrupt",
    "state_transition",
    "transition",
    "skill_result",
    "WATCHDOG_TIMEOUT",
    "TELEMETRY_BACKPRESSURE",
    "STALE_OBSERVATION",
}


@dataclass(frozen=True, slots=True)
class TelemetryRecord:
    timestamp: float
    event_type: str
    priority: TelemetryPriority
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RuntimeHealthSample:
    timestamp: float
    perception_fps: float
    detector_latency_ms: float
    tracker_latency_ms: float
    controller_fps: float
    input_worker_alive: bool
    telemetry_backlog: int
    latest_observation_age_ms: float | None
    focus_ok: bool
    process_memory_mb: float
    thread_count: int


@dataclass(frozen=True, slots=True)
class RuntimeHealthReport:
    max_memory_mb: float
    memory_growth_mb: float
    avg_perception_fps: float
    avg_controller_fps: float
    max_telemetry_backlog: int
    interrupt_count: int
    dropped_low_priority_logs: int
    release_all_called: bool


class PriorityTelemetryQueue:
    """Bounded telemetry writer with critical-event preservation."""

    def __init__(self, path: str | Path, maxsize: int = 4096) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self.path = Path(path)
        self.maxsize = maxsize
        self._queue: queue.Queue[TelemetryRecord | None] = queue.Queue(maxsize=maxsize)
        self._thread: threading.Thread | None = None
        self._closed = threading.Event()
        self._write_lock = threading.RLock()
        self._file = None
        self.dropped_low_priority_logs = 0
        self.synchronous_critical_writes = 0

    @property
    def backlog(self) -> int:
        return self._queue.qsize()

    def start(self) -> None:
        if self._thread is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8")
        self._thread = threading.Thread(target=self._run, name="priority-telemetry", daemon=True)
        self._thread.start()

    def log(
        self,
        event_type: str,
        payload: dict[str, Any] | Any,
        *,
        priority: TelemetryPriority | None = None,
        timestamp: float | None = None,
    ) -> bool:
        if priority is None:
            priority = "critical" if event_type in CRITICAL_EVENT_TYPES else "low"
        record = TelemetryRecord(
            timestamp=perf_counter_seconds() if timestamp is None else timestamp,
            event_type=event_type,
            priority=priority,
            payload=self._to_jsonable(payload),
        )
        if priority == "low":
            return self._put_low(record)
        return self._put_critical(record)

    def close(self, timeout: float | None = 2.0) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            self._make_room_for_stop()
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        with self._write_lock:
            if self._file is not None:
                self._file.close()
                self._file = None

    def _make_room_for_stop(self) -> None:
        try:
            item = self._queue.get_nowait()
        except queue.Empty:
            return
        if item is None:
            return
        if item.priority == "low":
            self.dropped_low_priority_logs += 1
            return
        self._write_sync(item)

    def _put_low(self, record: TelemetryRecord) -> bool:
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            self.dropped_low_priority_logs += 1
            return False
        return True

    def _put_critical(self, record: TelemetryRecord) -> bool:
        try:
            self._queue.put_nowait(record)
            return True
        except queue.Full:
            if self._evict_one_low_priority():
                try:
                    self._queue.put_nowait(record)
                    return True
                except queue.Full:
                    pass
            self._write_sync(record)
            self.synchronous_critical_writes += 1
            return True

    def _evict_one_low_priority(self) -> bool:
        kept: list[TelemetryRecord | None] = []
        evicted = False
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if not evicted and item is not None and item.priority == "low":
                self.dropped_low_priority_logs += 1
                evicted = True
                continue
            kept.append(item)
        for item in kept:
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                if item is not None and item.priority == "low":
                    self.dropped_low_priority_logs += 1
                elif item is not None:
                    self._write_sync(item)
        return evicted

    def _run(self) -> None:
        while True:
            record = self._queue.get()
            if record is None:
                break
            self._write_sync(record)

    def _write_sync(self, record: TelemetryRecord) -> None:
        encoded = json.dumps(asdict(record), ensure_ascii=False, separators=(",", ":"))
        with self._write_lock:
            if self._file is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._file = self.path.open("a", encoding="utf-8")
            self._file.write(encoded + "\n")
            self._file.flush()

    def _to_jsonable(self, value: Any) -> dict[str, Any]:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, dict):
            return {str(key): self._json_value(item) for key, item in value.items()}
        return {"value": self._json_value(value)}

    def _json_value(self, value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, dict):
            return {str(key): self._json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_value(item) for item in value]
        return value


class HealthReportBuilder:
    def __init__(self) -> None:
        self._samples: list[RuntimeHealthSample] = []
        self._interrupt_count = 0

    def add_sample(self, sample: RuntimeHealthSample) -> None:
        self._samples.append(sample)

    def record_interrupt(self) -> None:
        self._interrupt_count += 1

    def build(self, dropped_low_priority_logs: int, release_all_called: bool) -> RuntimeHealthReport:
        if not self._samples:
            return RuntimeHealthReport(
                max_memory_mb=0.0,
                memory_growth_mb=0.0,
                avg_perception_fps=0.0,
                avg_controller_fps=0.0,
                max_telemetry_backlog=0,
                interrupt_count=self._interrupt_count,
                dropped_low_priority_logs=dropped_low_priority_logs,
                release_all_called=release_all_called,
            )
        first = self._samples[0]
        max_memory = max(sample.process_memory_mb for sample in self._samples)
        return RuntimeHealthReport(
            max_memory_mb=max_memory,
            memory_growth_mb=max_memory - first.process_memory_mb,
            avg_perception_fps=sum(sample.perception_fps for sample in self._samples) / len(self._samples),
            avg_controller_fps=sum(sample.controller_fps for sample in self._samples) / len(self._samples),
            max_telemetry_backlog=max(sample.telemetry_backlog for sample in self._samples),
            interrupt_count=self._interrupt_count,
            dropped_low_priority_logs=dropped_low_priority_logs,
            release_all_called=release_all_called,
        )
