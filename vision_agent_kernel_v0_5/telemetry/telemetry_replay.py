"""Telemetry replay system — replay recorded sessions from JSONL files.

Loads telemetry events from JSONL files and replays them at configurable speed,
useful for debugging, analysis, and regression testing.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ReplayEvent:
    """A single telemetry event loaded from JSONL."""
    index: int
    timestamp: float
    event_type: str
    payload: dict[str, Any]
    source: str = ""


@dataclass(slots=True)
class ReplayStats:
    """Statistics from a replay session."""
    total_events: int = 0
    events_by_type: dict[str, int] = field(default_factory=dict)
    time_span_sec: float = 0.0
    skipped_events: int = 0
    replay_duration_sec: float = 0.0


class TelemetryReplay:
    """Replays telemetry events from JSONL files.

    Supports:
    - Loading JSONL telemetry files
    - Filtering by event type
    - Time-range filtering
    - Speed multiplier (real-time, 2x, 10x, instant)
    - Event iteration with timing
    """

    def __init__(
        self,
        source_path: Path | str,
        speed_multiplier: float = 1.0,
        event_filter: set[str] | None = None,
        time_range: tuple[float, float] | None = None,
    ) -> None:
        self._source_path = Path(source_path)
        self._speed = max(0.0, speed_multiplier)
        self._event_filter = event_filter
        self._time_range = time_range
        self._events: list[ReplayEvent] = []
        self._loaded = False

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> int:
        """Load events from the JSONL file. Returns count of loaded events."""
        if self._loaded:
            return len(self._events)

        if not self._source_path.exists():
            log.warning("[TelemetryReplay] Source file not found: %s", self._source_path)
            return 0

        events: list[ReplayEvent] = []
        with open(self._source_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = float(data.get("timestamp", 0.0))
                event_type = str(data.get("event_type", data.get("type", "unknown")))
                payload = data.get("payload", data.get("data", {}))
                if not isinstance(payload, dict):
                    payload = {"raw": payload}
                source = str(data.get("source", ""))

                # Apply time range filter
                if self._time_range is not None:
                    t_start, t_end = self._time_range
                    if ts < t_start or ts > t_end:
                        continue

                # Apply event type filter
                if self._event_filter is not None and event_type not in self._event_filter:
                    continue

                events.append(ReplayEvent(
                    index=idx,
                    timestamp=ts,
                    event_type=event_type,
                    payload=payload,
                    source=source,
                ))

        self._events = events
        self._loaded = True
        log.info(
            "[TelemetryReplay] Loaded %d events from %s",
            len(events), self._source_path.name,
        )
        return len(events)

    def iterate(self) -> Iterator[ReplayEvent]:
        """Iterate events with timing based on speed multiplier.

        Yields ReplayEvent objects. Between events, sleeps proportional
        to the time gap divided by speed_multiplier.
        """
        if not self._loaded:
            self.load()

        prev_ts: float | None = None
        for event in self._events:
            if prev_ts is not None and self._speed > 0:
                gap = event.timestamp - prev_ts
                sleep_time = gap / self._speed if self._speed > 0 else 0
                if sleep_time > 0.001:
                    time.sleep(min(sleep_time, 1.0))  # Cap at 1s between events
            prev_ts = event.timestamp
            yield event

    def iterate_instant(self) -> Iterator[ReplayEvent]:
        """Iterate all events instantly (no timing delays)."""
        if not self._loaded:
            self.load()
        yield from self._events

    def get_stats(self) -> ReplayStats:
        """Compute statistics over loaded events."""
        if not self._loaded:
            self.load()

        if not self._events:
            return ReplayStats()

        by_type: dict[str, int] = {}
        for e in self._events:
            by_type[e.event_type] = by_type.get(e.event_type, 0) + 1

        time_span = self._events[-1].timestamp - self._events[0].timestamp if len(self._events) > 1 else 0.0

        return ReplayStats(
            total_events=len(self._events),
            events_by_type=by_type,
            time_span_sec=time_span,
        )

    def find_events(self, event_type: str) -> list[ReplayEvent]:
        """Find all events of a given type."""
        if not self._loaded:
            self.load()
        return [e for e in self._events if e.event_type == event_type]

    def find_by_payload(self, key: str, value: Any) -> list[ReplayEvent]:
        """Find events where payload[key] == value."""
        if not self._loaded:
            self.load()
        return [e for e in self._events if e.payload.get(key) == value]
