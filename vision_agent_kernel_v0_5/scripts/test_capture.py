from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.state_bus import StateBus
from core.timebase import Timebase
from perception.capture_base import CaptureConfig, FramePacket
from perception.dxcam_capture import DxcamCapturer
from perception.pipeline import PerceptionPipeline, PerceptionPipelineConfig


class FakeCapturer:
    def __init__(self, timebase: Timebase) -> None:
        self._timebase = timebase
        self._frame_id = 0

    def start(self) -> None:
        print("[FakeCapturer] started", flush=True)

    def get_latest_frame(self) -> FramePacket:
        self._frame_id += 1
        image = np.zeros((360, 640, 3), dtype=np.uint8)
        image[:, :, 0] = self._frame_id % 255
        return FramePacket(
            frame_id=self._frame_id,
            timestamp=self._timebase.now(),
            image=image,
            source_size=(640, 360),
        )

    def stop(self) -> None:
        print("[FakeCapturer] stopped", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a minimal Phase 3 capture pipeline smoke test.")
    parser.add_argument("--dxcam", action="store_true", help="Use real dxcam capture instead of fake frames.")
    parser.add_argument("--seconds", type=float, default=1.0)
    args = parser.parse_args()

    timebase = Timebase()
    state_bus = StateBus()
    capturer = (
        DxcamCapturer(CaptureConfig(target_fps=60.0), timebase=timebase)
        if args.dxcam
        else FakeCapturer(timebase)
    )
    pipeline = PerceptionPipeline(
        capturer=capturer,
        state_bus=state_bus,
        timebase=timebase,
        config=PerceptionPipelineConfig(max_fps=60.0),
    )

    pipeline.start()
    try:
        time.sleep(args.seconds)
    finally:
        pipeline.stop()

    snapshot = state_bus.latest_observation_snapshot()
    print(f"[test_capture] latest_version={snapshot.version} observation={snapshot.value}", flush=True)
    return 0 if snapshot.value is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
