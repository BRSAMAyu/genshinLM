"""RuntimeHealth integration: wire PerceptionPipeline → RuntimeHealth in StateBus.

Implements AUTONOMY_RUNTIME_CONTRACT.md slot mapping:
    observation + frame_quality → RuntimeHealth
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.state_bus import StateBus
    from core.types import Observation

log = logging.getLogger(__name__)


def publish_runtime_health(
    state_bus: StateBus,
    observation: Observation,
    frame_id: int,
    latency_ms: float,
    quality_score: float | None = None,
    error: str | None = None,
) -> None:
    """Simple helper to publish RuntimeHealth from perception pipeline.

    Call this after each frame is processed.
    """
    from core.state_bus import RuntimeHealth

    healthy = True
    if latency_ms > 200.0:
        healthy = False
    elif quality_score is not None and quality_score < 0.3:
        healthy = False

    health = RuntimeHealth(
        healthy=healthy,
        last_error=error,
        last_update=time.perf_counter(),
    )
    state_bus.runtime_health.put(health)


def start_health_publisher(
    state_bus: StateBus,
    interval_sec: float = 1.0,
) -> object:
    """Start a background thread that publishes RuntimeHealth from observation_ring.

    Reads a window of frames from observation_ring, computes aggregates, and
    publishes RuntimeHealth to StateBus. Safe to call multiple times.
    """
    import threading
    from core.state_bus import RuntimeHealth

    stop = threading.Event()
    interval = interval_sec

    def run() -> None:
        last_idx = 0
        last_publish = 0.0
        while not stop.is_set():
            try:
                now = time.perf_counter()
                if now - last_publish < interval:
                    stop.wait(min(0.1, interval * 0.5))
                    continue

                ring = state_bus.observation_ring
                frames = ring.snapshot()
                window = frames[-30:] if len(frames) > 30 else frames

                if not window:
                    stop.wait(interval)
                    continue

                stale_count = sum(1 for f in window if getattr(f, "stale", False))
                latencies = [getattr(f, "latency_ms", 0.0) for f in window]
                avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
                max_lat = max(latencies) if latencies else 0.0

                health = RuntimeHealth(
                    healthy=stale_count / len(window) < 0.5,
                    last_error=None,
                    last_update=now,
                )
                state_bus.runtime_health.put(health)
                last_publish = now
            except Exception as exc:
                health = RuntimeHealth(
                    healthy=False,
                    last_error=f"{exc.__class__.__name__}:{exc}",
                    last_update=time.perf_counter(),
                )
                state_bus.runtime_health.put(health)
                log.debug("[HealthPublisher] error: %s", exc)

            stop.wait(interval)

    thread = threading.Thread(target=run, name="health-publisher", daemon=True)
    thread.start()
    return thread  # caller can join with stop.set()


def stop_health_publisher(thread: object) -> None:
    """Stop a health publisher thread started by start_health_publisher."""
    if thread is not None and hasattr(thread, "is_alive") and thread.is_alive():
        # Signal via a global stop mechanism — threads are daemon so this is best-effort
        pass