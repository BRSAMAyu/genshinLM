from __future__ import annotations

import json
import queue
import threading
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from core.timebase import perf_counter_seconds


class AsyncJsonlLogger:
    def __init__(self, path: str | Path, max_queue_size: int = 4096) -> None:
        self._path = Path(path)
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=max_queue_size)
        self._thread: threading.Thread | None = None
        self._closed = threading.Event()
        self.dropped_count = 0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=self._run, name="telemetry-jsonl", daemon=True)
        self._thread.start()

    def log(self, event_type: str, payload: Any, timestamp: float | None = None) -> bool:
        record = {
            "timestamp": perf_counter_seconds() if timestamp is None else timestamp,
            "event_type": event_type,
            "payload": self._to_jsonable(payload),
        }
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            self.dropped_count += 1
            return False
        return True

    def close(self, timeout: float | None = 2.0) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        with self._path.open("a", encoding="utf-8") as output:
            while True:
                record = self._queue.get()
                if record is None:
                    break
                output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                output.flush()

    def _to_jsonable(self, value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, dict):
            return {str(key): self._to_jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._to_jsonable(item) for item in value]
        return value

    def __enter__(self) -> AsyncJsonlLogger:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()
