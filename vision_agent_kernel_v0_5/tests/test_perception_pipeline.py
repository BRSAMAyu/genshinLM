from __future__ import annotations

import time

import numpy as np

from core.state_bus import StateBus
from core.timebase import Timebase
from perception.capture_base import FramePacket
from perception.pipeline import PerceptionPipeline, PerceptionPipelineConfig


class FakeCapturer:
    def __init__(self, timebase: Timebase) -> None:
        self.timebase = timebase
        self.started = False
        self.stopped = False
        self.frame_id = 0

    def start(self) -> None:
        self.started = True

    def get_latest_frame(self) -> FramePacket:
        self.frame_id += 1
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        return FramePacket(
            frame_id=self.frame_id,
            timestamp=self.timebase.now(),
            image=image,
            source_size=(200, 100),
        )

    def stop(self) -> None:
        self.stopped = True


class FailingCapturer:
    def start(self) -> None:
        pass

    def get_latest_frame(self) -> FramePacket:
        raise RuntimeError("capture failed")

    def stop(self) -> None:
        pass


def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not met before timeout")


def test_perception_pipeline_publishes_latest_observation() -> None:
    timebase = Timebase()
    state_bus = StateBus()
    capturer = FakeCapturer(timebase)
    pipeline = PerceptionPipeline(
        capturer=capturer,
        state_bus=state_bus,
        timebase=timebase,
        config=PerceptionPipelineConfig(max_fps=60.0),
    )

    pipeline.start()
    try:
        _wait_for(lambda: state_bus.latest_observation.get() is not None)
    finally:
        pipeline.stop()

    observation = state_bus.latest_observation.get()
    assert capturer.started
    assert capturer.stopped
    assert observation is not None
    assert observation.viewport_size == (1280, 720)
    assert observation.frame_id >= 1
    assert not hasattr(observation, "image")


def test_perception_pipeline_capture_error_publishes_interrupt() -> None:
    state_bus = StateBus()
    pipeline = PerceptionPipeline(
        capturer=FailingCapturer(),
        state_bus=state_bus,
        config=PerceptionPipelineConfig(max_fps=60.0, continue_on_capture_error=False),
    )

    pipeline.start()
    try:
        _wait_for(lambda: state_bus.event_queue.get_nowait() is not None)
    finally:
        pipeline.stop()
