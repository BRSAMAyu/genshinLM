from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import FocusState, Observation
from perception.capture_base import FramePacket, ScreenCapturer
from perception.viewport import ViewportTransformer


class FramePostProcessor(Protocol):
    def process(self, frame: np.ndarray, observation: Observation, state_bus: StateBus) -> None: ...


@dataclass(frozen=True, slots=True)
class PerceptionPipelineConfig:
    max_fps: float = 60.0
    stale_threshold_ms: float = 150.0
    continue_on_capture_error: bool = True
    static_visual_triggers: dict[str, bool] = field(default_factory=dict)


class PerceptionPipeline:
    def __init__(
        self,
        capturer: ScreenCapturer,
        state_bus: StateBus,
        viewport: ViewportTransformer | None = None,
        timebase: Timebase | None = None,
        config: PerceptionPipelineConfig | None = None,
        post_processors: list[FramePostProcessor] | None = None,
    ) -> None:
        self._capturer = capturer
        self._state_bus = state_bus
        self._viewport = viewport or ViewportTransformer()
        self._timebase = timebase or Timebase()
        self._config = config or PerceptionPipelineConfig()
        self._post_processors: list[FramePostProcessor] = post_processors or []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._frame_interval = 1.0 / min(max(self._config.max_fps, 1.0), 60.0)

    def add_post_processor(self, processor: FramePostProcessor) -> None:
        self._post_processors.append(processor)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            print("[PerceptionPipeline] start ignored; already running", flush=True)
            return
        print(
            "[PerceptionPipeline] "
            f"starting capture loop max_fps={1.0 / self._frame_interval:.1f}",
            flush=True,
        )
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="perception-pipeline", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = 2.0) -> None:
        print("[PerceptionPipeline] stop requested", flush=True)
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        if self._thread is not None and self._thread.is_alive():
            print("[PerceptionPipeline] thread did not stop before timeout", flush=True)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run_loop(self) -> None:
        print("[PerceptionPipeline] capture loop entered", flush=True)
        try:
            self._capturer.start()
            while not self._stop_event.is_set():
                loop_started = self._timebase.now()
                try:
                    packet = self._capturer.get_latest_frame()
                    if packet is not None:
                        self._publish_packet(packet)
                except Exception as exc:
                    self._publish_capture_error(exc)
                    if not self._config.continue_on_capture_error:
                        break

                elapsed = self._timebase.now() - loop_started
                remaining = max(0.0, self._frame_interval - elapsed)
                self._stop_event.wait(remaining)
        finally:
            self._capturer.stop()
            print("[PerceptionPipeline] capture loop exited", flush=True)

    def _publish_packet(self, packet: FramePacket) -> None:
        normalized = self._viewport.normalize(packet.image)
        t_processed = self._timebase.now()
        latency_ms = (t_processed - packet.timestamp) * 1000.0
        observation = Observation(
            frame_id=packet.frame_id,
            t_capture=packet.timestamp,
            t_processed=t_processed,
            latency_ms=latency_ms,
            viewport_size=self._viewport.size,
            target_track=None,
            obstacle_field=None,
            ui_state=None,
            visual_triggers=dict(self._config.static_visual_triggers),
            os_focus=FocusState(focused=True),
            stale=latency_ms > self._config.stale_threshold_ms,
        )
        for pp in self._post_processors:
            try:
                pp.process(normalized, observation, self._state_bus)
            except Exception:
                pass
        self._state_bus.publish_observation(observation)
        print(
            "[PerceptionPipeline] "
            f"published observation frame_id={packet.frame_id} "
            f"source_size={packet.source_size} viewport_size={observation.viewport_size} "
            f"latency_ms={latency_ms:.3f} stale={observation.stale}",
            flush=True,
        )
        del normalized

    def _publish_capture_error(self, exc: Exception) -> None:
        now = self._timebase.now()
        interrupt = Interrupt(
            priority=1,
            timestamp=now,
            code="CAPTURE_ERROR",
            source="perception_pipeline",
            payload={"error": repr(exc)},
            recoverable=True,
            requires_input_release=False,
        )
        print(
            "[PerceptionPipeline] "
            f"{now:.6f} capture error -> interrupt payload={interrupt.payload}",
            flush=True,
        )
        self._state_bus.publish_interrupt(interrupt)

    def __enter__(self) -> PerceptionPipeline:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.stop()
