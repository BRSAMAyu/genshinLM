"""Run the full Aurora kernel with all 5 planes connected.

Usage:
    # Dry-run (default — all input goes to console)
    python scripts/run_kernel.py

    # With real screen capture
    python scripts/run_kernel.py --dxcam

    # With YOLO detection + tracking
    python scripts/run_kernel.py --dxcam --model-path models/yolo_nano.pt

    # Full real-game mode (capture + detection + real input)
    python scripts/run_kernel.py --dxcam --model-path models/yolo_nano.pt \
        --real-input --window-title "原神"
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.camera_servo import CameraServo, CameraServoConfig, genshin_camera_servo_config
from control.controller_loop import ControllerLoop
from core.local_secret_store import get_secret
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import CameraModel
from execution.console_backend import ConsoleInputBackend
from execution.intent_bridge import IntentBridge
from execution.input_worker import InputWorker
from execution.safe_window_backend import SafeWindowInputBackend
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
from perception.detector_post_processor import DetectionTrackingPostProcessor
from perception.dxcam_capture import DxcamCapturer
from perception.pipeline import PerceptionPipeline, PerceptionPipelineConfig
from perception.yolo_detector import YoloDetectorConfig
from perception.ultralytics_tracker import UltralyticsTrackerConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("run_kernel")


class DemoCapturer:
    def __init__(self, timebase: Timebase) -> None:
        self._timebase = timebase
        self._frame_id = 0

    def start(self) -> None:
        log.info("[DemoCapturer] started")

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
        log.info("[DemoCapturer] stopped")


def _build_backend(args: argparse.Namespace, timebase: Timebase) -> ConsoleInputBackend | SafeWindowInputBackend:
    if args.real_input:
        if not args.window_title:
            print("ERROR: --window-title is required with --real-input", file=sys.stderr)
            raise SystemExit(1)
        os.environ.setdefault("AURORA_ENABLE_AUTHORIZED_SAFE_WINDOW", "1")
        return SafeWindowInputBackend(
            target_window_title=args.window_title,
            pixels_per_degree=args.pixels_per_degree,
            timebase=timebase,
            alt_window_titles=args.alt_window_titles.split(",") if args.alt_window_titles else [],
        )
    return ConsoleInputBackend(timebase)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the v0.5 kernel with all 5 planes connected.")
    parser.add_argument("--dxcam", action="store_true", help="Use real dxcam capture")
    parser.add_argument("--seconds", type=float, default=0, help="Run duration (0=infinite)")
    parser.add_argument("--model-path", type=str, default="", help="YOLO model path for detection+tracking")
    parser.add_argument("--game", choices=["genshin", "hsr", "general"], default="general")
    # Real input options
    parser.add_argument("--real-input", action="store_true", help="Use SafeWindowInputBackend")
    parser.add_argument("--window-title", type=str, default="", help="Target window title for real input")
    parser.add_argument("--alt-window-titles", type=str, default="", help="Comma-separated alt window titles")
    parser.add_argument("--pixels-per-degree", type=float, default=8.0)
    # Perception options
    parser.add_argument("--capture-fps", type=float, default=30.0, help="Screen capture FPS")
    args = parser.parse_args()

    timebase = Timebase()
    state_bus = StateBus()

    # ── 1. Perception Plane ──
    capturer = (
        DxcamCapturer(CaptureConfig(target_fps=args.capture_fps), timebase=timebase)
        if args.dxcam
        else DemoCapturer(timebase)
    )

    post_processors = []

    # YOLO + Tracker post-processor
    if args.model_path:
        tracker_config = UltralyticsTrackerConfig(
            model_path=args.model_path,
            conf_threshold=0.35,
            iou_threshold=0.5,
            tracker="botsort.yaml",
            persist=True,
        )
        detector_pp = DetectionTrackingPostProcessor(
            tracker_config=tracker_config,
            timebase=timebase,
        )
        post_processors.append(detector_pp)
        log.info("YOLO + Tracker post-processor enabled: %s", args.model_path)

    perception = PerceptionPipeline(
        capturer=capturer,
        state_bus=state_bus,
        timebase=timebase,
        config=PerceptionPipelineConfig(
            max_fps=args.capture_fps,
            static_visual_triggers={}
            if args.dxcam
            else {
                "target_visible": True,
                "in_range_estimated": True,
                "action_sequence_completed": True,
            },
        ),
        post_processors=post_processors,
    )

    # ── 2. Execution Plane ──
    backend = _build_backend(args, timebase)
    input_worker = InputWorker(
        backend=backend,
        timebase=timebase,
        state_bus=state_bus,
        target_window_title=args.window_title or None,
    )

    # ── 3. Intent Bridge (Control → Execution) ──
    intent_bridge = IntentBridge(
        state_bus=state_bus,
        input_worker=input_worker,
        timebase=timebase,
        pixels_per_degree=args.pixels_per_degree,
    )

    # ── 4. Control Plane ──
    camera_model = CameraModel(
        viewport_width=1280,
        viewport_height=720,
        horizontal_fov_deg=90.0,
    )

    servo_config = genshin_camera_servo_config() if args.game == "genshin" else CameraServoConfig()
    camera_servo = CameraServo(config=servo_config)

    controller = ControllerLoop(
        state_bus=state_bus,
        camera_servo=camera_servo,
        tick_seconds=1.0 / 30.0,
    )
    # Wire camera model so ControllerLoop can compute servo error
    controller._camera_model = camera_model  # noqa: SLF001

    action_executor = VisualActionBlockExecutor(
        state_bus=state_bus,
        input_worker=input_worker,
        timebase=timebase,
        wait_chunk_ms=50,
    )

    # ── 5. Orchestration Plane ──
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

    # ── Signal handling ──
    stop_requested = False

    def request_stop(signum: int, frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True
        state_bus.request_shutdown()
        log.info("stop signal received signum=%d", signum)

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    # ── Start all planes ──
    log.info("=" * 60)
    log.info("  Aurora Kernel v0.5 — Full Pipeline")
    log.info("=" * 60)
    log.info("  Capture: %s", "dxcam" if args.dxcam else "demo")
    log.info("  Detection: %s", args.model_path or "none")
    log.info("  Input: %s", "SafeWindow" if args.real_input else "Console")
    log.info("  Game: %s", args.game)
    log.info("  Duration: %s", f"{args.seconds}s" if args.seconds > 0 else "infinite")
    log.info("=" * 60)

    input_worker.start()
    intent_bridge.start()
    perception.start()
    controller.start()
    orchestrator.start()

    started = timebase.now()
    try:
        while not stop_requested:
            if args.seconds > 0 and timebase.now() - started >= args.seconds:
                break
            state_bus.update_heartbeat("run_kernel", timebase.now())
            time.sleep(0.1)
    finally:
        log.info("shutting down all planes")
        orchestrator.stop()
        controller.stop()
        intent_bridge.stop()
        perception.stop()
        input_worker.stop()
        log.info(
            "final_mode=%s latest_observation_version=%d",
            state_bus.current_mode.get(),
            state_bus.latest_observation.version,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
