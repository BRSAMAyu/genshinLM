from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.controller_loop import ControllerLoop
from core.state_bus import StateBus
from core.timebase import Timebase
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker
from execution.visual_action_block import VisualActionBlockExecutor
from orchestration.orchestrator import Orchestrator
from orchestration.skills import (
    AcquireTargetSkill,
    ExecuteVisualActionBlockSkill,
    RecoverSkill,
    TrackAndApproachSkill,
    VerifySuccessSkill,
)
from perception.capture_base import CaptureConfig, FramePacket
from perception.dxcam_capture import DxcamCapturer
from perception.pipeline import PerceptionPipeline, PerceptionPipelineConfig


class DemoCapturer:
    def __init__(self, timebase: Timebase) -> None:
        self._timebase = timebase
        self._frame_id = 0

    def start(self) -> None:
        print("[DemoCapturer] started", flush=True)

    def get_latest_frame(self) -> FramePacket:
        self._frame_id += 1
        image = np.zeros((360, 640, 3), dtype=np.uint8)
        x = 40 + (self._frame_id * 8) % 560
        image[140:220, x : x + 80, 0] = 255
        return FramePacket(
            frame_id=self._frame_id,
            timestamp=self._timebase.now(),
            image=image,
            source_size=(640, 360),
        )

    def stop(self) -> None:
        print("[DemoCapturer] stopped", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the v0.5 kernel thread skeleton.")
    parser.add_argument("--dxcam", action="store_true", help="Use real dxcam capture instead of demo frames.")
    parser.add_argument("--seconds", type=float, default=3.0)
    args = parser.parse_args()

    timebase = Timebase()
    state_bus = StateBus()
    capturer = (
        DxcamCapturer(CaptureConfig(target_fps=60.0), timebase=timebase)
        if args.dxcam
        else DemoCapturer(timebase)
    )
    perception = PerceptionPipeline(
        capturer=capturer,
        state_bus=state_bus,
        timebase=timebase,
        config=PerceptionPipelineConfig(
            max_fps=60.0,
            static_visual_triggers={}
            if args.dxcam
            else {
                "target_visible": True,
                "in_range_estimated": True,
                "action_sequence_completed": True,
            },
        ),
    )
    backend = ConsoleInputBackend(timebase)
    input_worker = InputWorker(backend=backend, timebase=timebase)
    controller = ControllerLoop(state_bus=state_bus)
    action_executor = VisualActionBlockExecutor(
        state_bus=state_bus,
        input_worker=input_worker,
        timebase=timebase,
        wait_chunk_ms=50,
    )
    orchestrator = Orchestrator(
        state_bus=state_bus,
        skills={
            "acquire_target": AcquireTargetSkill(state_bus, timebase),
            "track_and_approach": TrackAndApproachSkill(state_bus, timebase),
            "execute_visual_action_block": ExecuteVisualActionBlockSkill(action_executor),
            "verify_success": VerifySuccessSkill(state_bus, timebase),
            "recover": RecoverSkill(state_bus, timebase),
        },
        timebase=timebase,
    )

    stop_requested = False

    def request_stop(signum: int, frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True
        state_bus.request_shutdown()
        print(f"[run_kernel] stop signal received signum={signum}", flush=True)

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    input_worker.start()
    perception.start()
    controller.start()
    orchestrator.start()
    started = timebase.now()
    try:
        while not stop_requested and timebase.now() - started < args.seconds:
            state_bus.update_heartbeat("run_kernel", timebase.now())
            time.sleep(0.1)
    finally:
        print("[run_kernel] shutting down threads", flush=True)
        orchestrator.stop()
        controller.stop()
        perception.stop()
        input_worker.stop()
        print(
            "[run_kernel] "
            f"final_mode={state_bus.current_mode.get()} "
            f"latest_observation_version={state_bus.latest_observation.version}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
