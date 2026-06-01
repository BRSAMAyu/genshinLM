"""Analytics consumer: reads observation_ring and emits health metrics to StateBus.

Implements the AUTONOMY_RUNTIME_CONTRACT.md slot mapping:
    observation_ring (300 frames) → AnalyticsConsumer → StateBus.runtime_health
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from core.state_bus import RuntimeHealth, StateBus
from core.timebase import Timebase

if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FrameMetrics:
    """Aggregate metrics from a window of observations."""
    total_frames: int = 0
    stale_count: int = 0
    staleness_rate: float = 0.0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    quality_score_avg: float = 0.0


class AnalyticsConsumer:
    """Consume observation_ring and publish runtime_health.

    Runs in a background thread. Reads observation_ring at regular intervals
    and publishes RuntimeHealth to StateBus.
    """

    def __init__(
        self,
        state_bus: StateBus,
        window_size: int = 30,
        publish_interval_sec: float = 2.0,
        timebase: Timebase | None = None,
    ) -> None:
        self._bus = state_bus
        self._window_size = window_size
        self._interval = publish_interval_sec
        self._timebase = timebase or Timebase()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="analytics-consumer", daemon=True)
        self._thread.start()
        log.info("[AnalyticsConsumer] started")

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        log.info("[AnalyticsConsumer] stopped")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                metrics = self._compute_metrics()
                health = RuntimeHealth(
                    healthy=metrics.staleness_rate < 0.5,
                    last_error=self._last_error,
                    last_update=self._timebase.now(),
                )
                self._bus.runtime_health.put(health)
                self._last_error = None
            except Exception as exc:
                self._last_error = f"{exc.__class__.__name__}:{exc}"
                log.debug("[AnalyticsConsumer] compute_metrics failed: %s", exc)
            self._stop.wait(self._interval)

    def _compute_metrics(self) -> FrameMetrics:
        """Pull up to window_size frames from observation_ring and compute aggregates."""
        ring = self._bus.observation_ring
        frames = ring.snapshot()
        window = frames[-self._window_size:] if len(frames) > self._window_size else frames

        if not window:
            return FrameMetrics()

        stale = sum(1 for f in window if getattr(f, "stale", False))
        latencies = [getattr(f, "latency_ms", 0.0) for f in window]
        quality_scores = []
        for f in window:
            fq = self._bus.frame_quality.get()
            if fq is not None:
                quality_scores.append(getattr(fq, "quality_score", 0.0))
            else:
                quality_scores.append(0.0)

        return FrameMetrics(
            total_frames=len(window),
            stale_count=stale,
            staleness_rate=stale / len(window),
            avg_latency_ms=sum(latencies) / len(latencies),
            max_latency_ms=max(latencies) if latencies else 0.0,
            quality_score_avg=sum(quality_scores) / len(quality_scores) if quality_scores else 0.0,
        )


# ---------------------------------------------------------------------------
# ClaimGraphWorker integration: also subscribe to observation_ring changes
# ---------------------------------------------------------------------------

def start_claim_graph_observer(state_bus: StateBus) -> threading.Thread:
    """Start a background thread that feeds observations to ClaimGraphWorker via StateBus.

    This makes ClaimGraphWorker the consumer of observation_ring as specified
    in AUTONOMY_RUNTIME_CONTRACT.md.
    """
    from runtime.claim_events import ClaimEventPublisher
    from runtime.claim_worker import ClaimGraphWorker

    publisher = ClaimEventPublisher(state_bus)
    worker = ClaimGraphWorker(publisher=publisher, mission_id="observation_observer")
    worker.start()

    # Subscribe to state changes so external consumers see claim graph updates
    state_bus.subscribe("claim_graph_state", lambda s: None)  # register interest

    def observer_loop() -> None:
        last_idx = 0
        while not threading.current_thread().is_shutdown:
            ring = state_bus.observation_ring
            frames = ring.snapshot()
            new_frames = frames[last_idx:]
            last_idx = len(frames)

            for frame in new_frames:
                from runtime.claim_runtime import ObservationClaim
                obs_claim = ObservationClaim(
                    observation_id=f"obs_{getattr(frame, 'frame_id', 0)}",
                    frame_id=getattr(frame, 'frame_id', 0),
                    timestamp=getattr(frame, 't_capture', 0.0),
                    screen_state=str(getattr(getattr(frame, 'ui_state', None), 'state', 'unknown') if hasattr(frame, 'ui_state') and frame.ui_state else 'unknown'),
                    confidence=getattr(getattr(frame, 'ui_state', None), 'confidence', 0.5) if hasattr(frame, 'ui_state') and frame.ui_state else 0.5,
                )
                worker.submit(
                    __import__('runtime.claim_worker', fromlist=['ClaimGraphCommand']).ClaimGraphCommand(
                        command_type="add_observation",
                        observation=obs_claim,
                    ),
                    timeout=2.0,
                )

            time.sleep(0.1)

    thread = threading.Thread(target=observer_loop, name="claim-graph-observer", daemon=True)
    thread.start()
    return thread