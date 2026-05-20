from __future__ import annotations

import argparse
import ctypes
import json
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.camera_servo import CameraServo, CameraServoConfig
from control.progress_supervisor import ProgressSupervisor
from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import CameraIntent, CameraModel, FocusState, Observation, SkillResult
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker
from execution.safe_window_backend import SafeWindowInputBackend, SafeWindowInputError, WindowRect
from execution.visual_action_block import (
    VisualActionBlock,
    VisualActionBlockExecutor,
    VisualActionStep,
)
from perception.capture_base import CaptureConfig
from perception.dxcam_capture import DxcamCapturer
from perception.viewport import ViewportTransformer
from perception.visual_trigger_detector import ColorTargetTracker, VisualTriggerDetector


DEFAULT_TITLE = "vision_agent_kernel_v0_5 pseudo3d_scene"
VK_F9 = 0x78


class F9Emergency:
    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._was_down = False

    def pressed(self) -> bool:
        down = bool(self._user32.GetAsyncKeyState(VK_F9) & 0x8000)
        pressed_now = down and not self._was_down
        self._was_down = down
        return pressed_now


class ActionTraceWriter:
    def __init__(self, run_id: str) -> None:
        self.run_dir = ROOT / "logs" / "runs" / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.run_dir / "action_block_trace.jsonl"
        self._lock = threading.RLock()
        self._file = self.path.open("a", encoding="utf-8")

    def write(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._file.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._file.flush()

    def close(self) -> None:
        with self._lock:
            self._file.close()


def load_action_block(path: Path) -> VisualActionBlock:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = [
        VisualActionStep(
            type=str(step["type"]),
            key=step.get("key"),
            lease_ms=int(step.get("lease_ms", 120)),
            trigger=step.get("trigger"),
            timeout_ms=int(step.get("timeout_ms", 1000)),
            min_confidence=float(step.get("min_confidence", 0.0)),
            intent=step.get("intent"),
        )
        for step in data.get("steps", [])
    ]
    return VisualActionBlock(
        name=str(data["name"]),
        precondition=list(data.get("precondition", [])),
        steps=steps,
        success_criteria=list(data.get("success_criteria", [])),
    )


def find_or_start_testbed(title: str, timeout_sec: float = 5.0) -> subprocess.Popen | None:
    backend = SafeWindowInputBackend(title)
    if _window_exists(backend):
        return None
    print(f"[visual_action_test] target window not found; starting testbed title={title!r}", flush=True)
    process = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "run_testbed.py")])
    deadline = time.perf_counter() + timeout_sec
    while time.perf_counter() < deadline:
        if _window_exists(backend):
            return process
        time.sleep(0.1)
    raise RuntimeError(f"testbed window did not appear within {timeout_sec}s")


def _window_exists(backend: SafeWindowInputBackend) -> bool:
    try:
        backend.client_rect()
    except SafeWindowInputError:
        return False
    return True


def _rect_to_region(rect: WindowRect) -> tuple[int, int, int, int]:
    return (rect.left, rect.top, rect.right, rect.bottom)


def _observation(
    frame_id: int,
    timestamp: float,
    latency_ms: float,
    track: object,
    triggers: dict[str, bool],
    interrupt: Interrupt | None,
) -> Observation:
    return Observation(
        frame_id=frame_id,
        t_capture=timestamp,
        t_processed=time.perf_counter(),
        latency_ms=latency_ms,
        viewport_size=(1280, 720),
        target_track=track,
        obstacle_field=None,
        ui_state=None,
        visual_triggers=triggers,
        os_focus=FocusState(focused=True),
        stale=latency_ms > 150.0 or interrupt is not None,
    )


def _direction_text(intent: CameraIntent | None) -> str:
    if intent is None:
        return "none"
    yaw = "center" if abs(intent.yaw_delta) < 1e-6 else "right" if intent.yaw_delta > 0 else "left"
    pitch = "center" if abs(intent.pitch_delta) < 1e-6 else "down" if intent.pitch_delta > 0 else "up"
    return f"yaw={yaw}({intent.yaw_delta:.3f}) pitch={pitch}({intent.pitch_delta:.3f})"


def _result_event(timebase: Timebase, result: SkillResult) -> dict[str, Any]:
    return {
        "timestamp": timebase.now(),
        "event": "skill_result",
        "skill_name": result.skill_name,
        "status": result.status,
        "failure_code": result.failure_code,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "payload": result.payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Stage 11 visual action block integration test.")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--mode", choices=["dry-run", "safe-window"], required=True)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--target-window-title", default=DEFAULT_TITLE)
    parser.add_argument("--action-block", default=str(ROOT / "action_blocks" / "demo_visual_action_block.yaml"))
    args = parser.parse_args()

    run_id = str(uuid.uuid4())
    timebase = Timebase()
    state_bus = StateBus()
    block = load_action_block(Path(args.action_block))
    testbed_process: subprocess.Popen | None = None
    capturer: DxcamCapturer | None = None
    trace: ActionTraceWriter | None = None
    servo_backend: ConsoleInputBackend | SafeWindowInputBackend | None = None
    action_worker: InputWorker | None = None
    action_thread: threading.Thread | None = None
    result_holder: dict[str, SkillResult] = {}
    stop_requested = False
    active_interrupt: Interrupt | None = None

    def request_stop(signum: int, frame: object) -> None:
        del frame
        nonlocal stop_requested, active_interrupt
        stop_requested = True
        active_interrupt = Interrupt(
            priority=0,
            timestamp=timebase.now(),
            code="CTRL_C_OR_TERMINATE",
            source="run_visual_action_block_test",
            requires_input_release=True,
        )
        state_bus.publish_interrupt(active_interrupt)
        if action_worker is not None:
            action_worker.submit_interrupt(active_interrupt)
        print(f"[visual_action_test] stop signal received signum={signum}", flush=True)

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        testbed_process = find_or_start_testbed(args.target_window_title)
        safe_backend = SafeWindowInputBackend(args.target_window_title, timebase=timebase)
        rect = safe_backend.client_rect()
        if args.mode == "safe-window":
            safe_backend.focus_target_window()
            servo_backend = safe_backend
        else:
            safe_backend.focus_target_window()
            servo_backend = ConsoleInputBackend(timebase)

        action_backend = ConsoleInputBackend(timebase)
        action_worker = InputWorker(backend=action_backend, timebase=timebase, tick_seconds=0.005)
        action_worker.start()
        trace = ActionTraceWriter(run_id)

        def telemetry_sink(event_type: str, event: dict[str, Any]) -> None:
            del event_type
            if trace is not None:
                trace.write(event)

        executor = VisualActionBlockExecutor(
            state_bus=state_bus,
            input_worker=action_worker,
            timebase=timebase,
            wait_chunk_ms=50,
            telemetry_sink=telemetry_sink,
        )

        capturer = DxcamCapturer(
            CaptureConfig(target_fps=60.0, output_color="RGB", region=_rect_to_region(rect)),
            timebase=timebase,
        )
        viewport = ViewportTransformer()
        trigger_detector = VisualTriggerDetector()
        tracker = ColorTargetTracker()
        servo = CameraServo(CameraServoConfig(kp_yaw=0.65, kp_pitch=0.45, smoothing_alpha=0.35))
        camera = CameraModel()
        progress_supervisor = ProgressSupervisor(state_bus)
        f9 = F9Emergency()
        capturer.start()
        started = timebase.now()
        last_loop = started
        last_panel = 0.0
        debug_saved = False
        centered_since: float | None = None
        print(
            "[visual_action_test] "
            f"run_id={run_id} mode={args.mode} trace={trace.path}",
            flush=True,
        )

        def run_block() -> None:
            result_holder["result"] = executor.execute(block)

        while not stop_requested and timebase.now() - started < args.seconds:
            if f9.pressed():
                active_interrupt = Interrupt(
                    priority=0,
                    timestamp=timebase.now(),
                    code="EMERGENCY_STOP",
                    source="F9",
                    requires_input_release=True,
                )
                state_bus.publish_interrupt(active_interrupt)
                if action_worker is not None:
                    action_worker.submit_interrupt(active_interrupt)
                print("[visual_action_test] F9 emergency stop detected", flush=True)
                break
            if args.mode == "safe-window" and not safe_backend.is_target_focused():
                active_interrupt = Interrupt(
                    priority=0,
                    timestamp=timebase.now(),
                    code="ENVIRONMENT_LOST_FOCUS",
                    source="safe_window_backend",
                    requires_input_release=True,
                )
                state_bus.publish_interrupt(active_interrupt)
                if action_worker is not None:
                    action_worker.submit_interrupt(active_interrupt)
                print("[visual_action_test] target window lost focus", flush=True)
                break

            packet = capturer.get_latest_frame()
            if packet is None:
                time.sleep(0.005)
                continue
            normalized = viewport.normalize(packet.image)
            if args.debug and not debug_saved:
                try:
                    from PIL import Image

                    debug_path = ROOT / "logs" / "debug_action_capture.png"
                    Image.fromarray(normalized).save(debug_path)
                    print(f"[visual_action_test] debug frame saved path={debug_path}", flush=True)
                except Exception as exc:
                    print(f"[visual_action_test] debug frame save failed: {exc!r}", flush=True)
                debug_saved = True
            detection = trigger_detector.detect_target(normalized, packet.frame_id, packet.timestamp)
            track = tracker.update(detection, packet.frame_id, packet.timestamp)
            triggers = trigger_detector.detect_triggers(normalized, track)
            now = timebase.now()
            if triggers.get("target_visible_and_centered", False):
                if centered_since is None:
                    centered_since = now
            else:
                centered_since = None
            observation = _observation(
                packet.frame_id,
                packet.timestamp,
                (now - packet.timestamp) * 1000.0,
                track,
                triggers,
                active_interrupt,
            )
            state_bus.publish_observation(observation)
            progress = progress_supervisor.update(observation)

            intent: CameraIntent | None = None
            if track is not None and track.smoothed_center_px is not None:
                error = servo.compute_error(track, camera)
                dt = max(timebase.now() - last_loop, 1e-3)
                intent = servo.step(error, dt=dt)
                servo_backend.mouse_move(
                    intent.yaw_delta,
                    intent.pitch_delta,
                    reason=f"visual_action_servo {_direction_text(intent)}",
                )
            last_loop = timebase.now()

            if (
                action_thread is None
                and (
                    triggers.get("target_color_green", False)
                    or centered_since is not None
                    and now - centered_since >= 1.0
                )
            ):
                print(
                    "[visual_action_test] centered stability reached; starting action block",
                    flush=True,
                )
                action_thread = threading.Thread(target=run_block, name="visual-action-block", daemon=True)
                action_thread.start()

            if timebase.now() - last_panel >= 0.2:
                print(
                    "[visual_action_panel] "
                    f"frame_id={packet.frame_id} "
                    f"target_state={track.state if track else 'LOST'} "
                    f"target_center={track.smoothed_center_px if track else None} "
                    f"triggers={triggers} "
                    f"camera_intent={asdict(intent) if intent is not None else None} "
                    f"progress={progress.ewma_progress:.3f} "
                    f"frustration={progress.frustration:.3f}",
                    flush=True,
                )
                last_panel = timebase.now()

            if "result" in result_holder:
                break

        if action_thread is not None:
            action_thread.join(timeout=1.0)
        if "result" not in result_holder:
            result_holder["result"] = SkillResult(
                skill_name=block.name,
                status="TIMEOUT",
                failure_code="visual_action_block_test_timeout",
                started_at=started,
                finished_at=timebase.now(),
                payload={"block_started": action_thread is not None},
            )
            if trace is not None:
                trace.write(
                    {
                        "timestamp": timebase.now(),
                        "event": "action_block_timeout",
                        "block": block.name,
                        "failure_code": "visual_action_block_test_timeout",
                    }
                )
                trace.write(_result_event(timebase, result_holder["result"]))

        result = result_holder["result"]
        print(f"[visual_action_test] SkillResult={result}", flush=True)
        return 0 if result.status == "SUCCESS" else 2
    finally:
        if servo_backend is not None:
            try:
                servo_backend.release_all(reason="run_visual_action_block_test_exit")
            except Exception as exc:
                print(f"[visual_action_test] servo release_all failed: {exc!r}", flush=True)
        if action_worker is not None:
            action_worker.stop()
        if capturer is not None:
            try:
                capturer.stop()
            except Exception:
                pass
        if trace is not None:
            try:
                trace.close()
                print(f"[visual_action_test] trace closed path={trace.path}", flush=True)
            except Exception:
                pass
        if testbed_process is not None and testbed_process.poll() is None:
            testbed_process.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
