from __future__ import annotations

import argparse
import ctypes
import json
import math
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.camera_servo import CameraServo, CameraServoConfig
from control.progress_supervisor import ProgressSupervisor
from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import CameraIntent, CameraModel, FocusState, Observation, ProgressState, TargetTrack
from execution.console_backend import ConsoleInputBackend
from execution.safe_window_backend import SafeWindowInputBackend, SafeWindowInputError, WindowRect
from perception.capture_base import CaptureConfig
from perception.dxcam_capture import DxcamCapturer
from perception.viewport import ViewportTransformer
from perception.visual_trigger_detector import ColorTargetTracker, VisualTriggerDetector


DEFAULT_TITLE = "vision_agent_kernel_v0_5 pseudo3d_scene"
VK_F9 = 0x78


@dataclass(slots=True)
class ServoSample:
    timestamp: float
    frame_id: int
    target_state: str
    target_center: tuple[float, float] | None
    center_error_px: tuple[float, float] | None
    yaw_error_deg: float | None
    pitch_error_deg: float | None
    camera_intent: dict[str, Any] | None
    progress: float | None
    frustration: float | None
    interrupt: dict[str, Any] | None


class RedTargetDetector:
    def detect(self, frame: np.ndarray, frame_id: int, timestamp: float) -> TargetTrack | None:
        if frame.ndim != 3 or frame.shape[2] < 3:
            return None
        red = frame[:, :, 0].astype(np.int16)
        green = frame[:, :, 1].astype(np.int16)
        blue = frame[:, :, 2].astype(np.int16)
        mask = (red > 150) & (red > green * 2) & (red > blue * 2)
        y_indices, x_indices = np.where(mask)
        if len(x_indices) < 20:
            return None
        x1 = float(x_indices.min())
        x2 = float(x_indices.max())
        y1 = float(y_indices.min())
        y2 = float(y_indices.max())
        center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
        confidence = min(1.0, len(x_indices) / max(64.0 * 64.0, 1.0))
        return TargetTrack(
            track_id="red-target",
            class_id="red_block",
            state="TRACKED",
            bbox_xyxy=(x1, y1, x2, y2),
            smoothed_center_px=center,
            velocity_px_s=(0.0, 0.0),
            confidence=confidence,
            identity_confidence=confidence,
            missing_duration_ms=0.0,
            bearing_deg=None,
            pitch_deg=None,
            estimated_range=None,
            last_seen_frame_id=frame_id,
        )


class RedTargetTracker:
    def __init__(self, lost_timeout_ms: float = 3000.0) -> None:
        self._last_track: TargetTrack | None = None
        self._last_timestamp: float | None = None
        self._lost_timeout_ms = lost_timeout_ms

    def update(self, detection: TargetTrack | None, frame_id: int, timestamp: float) -> TargetTrack | None:
        if detection is not None:
            velocity = self._velocity(detection.smoothed_center_px, timestamp)
            track = TargetTrack(
                track_id=detection.track_id,
                class_id=detection.class_id,
                state="TRACKED",
                bbox_xyxy=detection.bbox_xyxy,
                smoothed_center_px=detection.smoothed_center_px,
                velocity_px_s=velocity,
                confidence=detection.confidence,
                identity_confidence=detection.identity_confidence,
                missing_duration_ms=0.0,
                bearing_deg=None,
                pitch_deg=None,
                estimated_range=None,
                last_seen_frame_id=frame_id,
            )
            self._last_track = track
            self._last_timestamp = timestamp
            return track
        if self._last_track is None or self._last_timestamp is None:
            return None
        missing_ms = (timestamp - self._last_timestamp) * 1000.0
        state = "COASTING" if missing_ms <= self._lost_timeout_ms else "LOST"
        center = self._last_track.smoothed_center_px
        if center is not None and state == "COASTING":
            dt = missing_ms / 1000.0
            center = (
                center[0] + self._last_track.velocity_px_s[0] * dt,
                center[1] + self._last_track.velocity_px_s[1] * dt,
            )
        return TargetTrack(
            track_id=self._last_track.track_id,
            class_id=self._last_track.class_id,
            state=state,
            bbox_xyxy=self._last_track.bbox_xyxy,
            smoothed_center_px=center,
            velocity_px_s=self._last_track.velocity_px_s,
            confidence=max(0.0, self._last_track.confidence * 0.5),
            identity_confidence=max(0.0, self._last_track.identity_confidence * 0.5),
            missing_duration_ms=missing_ms,
            bearing_deg=None,
            pitch_deg=None,
            estimated_range=None,
            last_seen_frame_id=frame_id,
        )

    def _velocity(self, center: tuple[float, float] | None, timestamp: float) -> tuple[float, float]:
        if (
            center is None
            or self._last_track is None
            or self._last_track.smoothed_center_px is None
            or self._last_timestamp is None
        ):
            return (0.0, 0.0)
        dt = max(timestamp - self._last_timestamp, 1e-6)
        previous = self._last_track.smoothed_center_px
        return ((center[0] - previous[0]) / dt, (center[1] - previous[1]) / dt)


class ServoTraceWriter:
    def __init__(self, run_id: str) -> None:
        self.run_dir = ROOT / "logs" / "runs" / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.run_dir / "servo_trace.jsonl"
        self._file = self.path.open("a", encoding="utf-8")

    def write(self, sample: ServoSample) -> None:
        self._file.write(json.dumps(asdict(sample), ensure_ascii=False, separators=(",", ":")) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()


class F9Emergency:
    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._was_down = False

    def pressed(self) -> bool:
        down = bool(self._user32.GetAsyncKeyState(VK_F9) & 0x8000)
        pressed_now = down and not self._was_down
        self._was_down = down
        return pressed_now


def find_or_start_testbed(title: str, timeout_sec: float = 5.0) -> subprocess.Popen | None:
    backend = SafeWindowInputBackend(title)
    if _window_exists(backend):
        return None
    print(f"[visual_servo] target window not found; starting testbed title={title!r}", flush=True)
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


def _make_observation(
    frame_id: int,
    timestamp: float,
    latency_ms: float,
    track: TargetTrack | None,
    interrupt: Interrupt | None,
    visual_triggers: dict[str, bool] | None = None,
) -> Observation:
    triggers = dict(visual_triggers or {})
    triggers.setdefault("target_visible", track is not None and track.state != "LOST")
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


def _center_error(track: TargetTrack | None) -> tuple[float, float] | None:
    if track is None or track.smoothed_center_px is None:
        return None
    return (track.smoothed_center_px[0] - 640.0, track.smoothed_center_px[1] - 360.0)


def _direction_text(intent: CameraIntent | None) -> str:
    if intent is None:
        return "none"
    yaw = "center" if abs(intent.yaw_delta) < 1e-6 else "right" if intent.yaw_delta > 0 else "left"
    pitch = "center" if abs(intent.pitch_delta) < 1e-6 else "down" if intent.pitch_delta > 0 else "up"
    return f"yaw={yaw}({intent.yaw_delta:.3f}) pitch={pitch}({intent.pitch_delta:.3f})"


def _print_panel(sample: ServoSample, backend_name: str) -> None:
    print(
        "[servo_panel] "
        f"frame_id={sample.frame_id} "
        f"target_state={sample.target_state} "
        f"target_center={sample.target_center} "
        f"center_error_px={sample.center_error_px} "
        f"yaw_error_deg={sample.yaw_error_deg} "
        f"pitch_error_deg={sample.pitch_error_deg} "
        f"camera_intent={sample.camera_intent} "
        f"ewma_progress={sample.progress} "
        f"frustration={sample.frustration} "
        f"active_interrupt={sample.interrupt} "
        f"input_backend={backend_name}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Stage 10 visual servo integration test.")
    parser.add_argument("--mode", choices=["sensor-only", "dry-run", "safe-window"], required=True)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--target-window-title", default=DEFAULT_TITLE)
    parser.add_argument("--kp-yaw", type=float, default=0.65)
    parser.add_argument("--kp-pitch", type=float, default=0.45)
    parser.add_argument("--dead-zone-deg", type=float, default=1.5)
    parser.add_argument("--smoothing-alpha", type=float, default=0.35)
    parser.add_argument("--invert-yaw", action="store_true")
    parser.add_argument("--invert-pitch", action="store_true")
    args = parser.parse_args()

    run_id = str(uuid.uuid4())
    timebase = Timebase()
    state_bus = StateBus()
    testbed_process: subprocess.Popen | None = None
    backend_name = "console"
    input_backend: ConsoleInputBackend | SafeWindowInputBackend | None = None
    capturer: DxcamCapturer | None = None
    trace: ServoTraceWriter | None = None
    safe_backend = SafeWindowInputBackend(args.target_window_title, timebase=timebase)
    stop_requested = False
    active_interrupt: Interrupt | None = None

    def request_stop(signum: int, frame: object) -> None:
        nonlocal stop_requested, active_interrupt
        stop_requested = True
        active_interrupt = Interrupt(
            priority=0,
            timestamp=timebase.now(),
            code="CTRL_C_OR_TERMINATE",
            source="run_visual_servo_test",
            requires_input_release=True,
        )
        print(f"[visual_servo] stop signal received signum={signum}", flush=True)

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        testbed_process = find_or_start_testbed(args.target_window_title)
        rect = safe_backend.client_rect()
        if args.mode == "safe-window":
            safe_backend.focus_target_window()
            input_backend = safe_backend
            backend_name = "safe-window"
        else:
            input_backend = ConsoleInputBackend(timebase)
            backend_name = "console"
        capturer = DxcamCapturer(
            CaptureConfig(target_fps=60.0, output_color="RGB", region=_rect_to_region(rect)),
            timebase=timebase,
        )
        viewport = ViewportTransformer()
        detector = VisualTriggerDetector()
        tracker = ColorTargetTracker()
        servo = CameraServo(
            CameraServoConfig(
                kp_yaw=args.kp_yaw,
                kp_pitch=args.kp_pitch,
                dead_zone_deg=args.dead_zone_deg,
                smoothing_alpha=args.smoothing_alpha,
                invert_yaw=args.invert_yaw,
                invert_pitch=args.invert_pitch,
            )
        )
        camera = CameraModel()
        progress_supervisor = ProgressSupervisor(state_bus)
        trace = ServoTraceWriter(run_id)
        f9 = F9Emergency()
        capturer.start()
        started = timebase.now()
        last_panel = 0.0
        last_loop = started
        print(f"[visual_servo] run_id={run_id} trace={trace.path}", flush=True)

        while not stop_requested and timebase.now() - started < args.seconds:
            if f9.pressed():
                active_interrupt = Interrupt(
                    priority=0,
                    timestamp=timebase.now(),
                    code="EMERGENCY_STOP",
                    source="F9",
                    requires_input_release=True,
                )
                print("[visual_servo] F9 emergency stop detected", flush=True)
                break
            if args.mode == "safe-window" and not safe_backend.is_target_focused():
                active_interrupt = Interrupt(
                    priority=0,
                    timestamp=timebase.now(),
                    code="ENVIRONMENT_LOST_FOCUS",
                    source="safe_window_backend",
                    requires_input_release=True,
                )
                print("[visual_servo] target window lost focus", flush=True)
                break

            packet = capturer.get_latest_frame()
            if packet is None:
                time.sleep(0.005)
                continue
            normalized = viewport.normalize(packet.image)
            detection = detector.detect_target(normalized, packet.frame_id, packet.timestamp)
            track = tracker.update(detection, packet.frame_id, packet.timestamp)
            visual_triggers = detector.detect_triggers(normalized, track)
            observation = _make_observation(
                packet.frame_id,
                packet.timestamp,
                (timebase.now() - packet.timestamp) * 1000.0,
                track,
                active_interrupt,
                visual_triggers,
            )
            state_bus.publish_observation(observation)
            progress = progress_supervisor.update(observation)
            intent: CameraIntent | None = None
            yaw_error: float | None = None
            pitch_error: float | None = None
            if track is not None and track.smoothed_center_px is not None:
                error = servo.compute_error(track, camera)
                yaw_error = error.yaw_error_deg
                pitch_error = error.pitch_error_deg
                dt = max(timebase.now() - last_loop, 1e-3)
                intent = servo.step(error, dt=dt)
                if args.mode in {"dry-run", "safe-window"}:
                    assert input_backend is not None
                    input_backend.mouse_move(
                        intent.yaw_delta,
                        intent.pitch_delta,
                        reason=f"servo {_direction_text(intent)}",
                    )
                    if args.debug:
                        print(f"[visual_servo] dry direction {_direction_text(intent)}", flush=True)
            last_loop = timebase.now()

            sample = ServoSample(
                timestamp=timebase.now(),
                frame_id=packet.frame_id,
                target_state=track.state if track else "LOST",
                target_center=track.smoothed_center_px if track else None,
                center_error_px=_center_error(track),
                yaw_error_deg=yaw_error,
                pitch_error_deg=pitch_error,
                camera_intent=asdict(intent) if intent is not None else None,
                progress=progress.ewma_progress,
                frustration=progress.frustration,
                interrupt=asdict(active_interrupt) if active_interrupt is not None else None,
            )
            trace.write(sample)
            if timebase.now() - last_panel >= 0.2:
                _print_panel(sample, backend_name)
                last_panel = timebase.now()

        return 0
    finally:
        if input_backend is not None:
            try:
                input_backend.release_all(reason="run_visual_servo_test_exit")
            except Exception as exc:
                print(f"[visual_servo] release_all failed: {exc!r}", flush=True)
        if capturer is not None:
            try:
                capturer.stop()
            except Exception:
                pass
        if trace is not None:
            try:
                trace.close()
                print(f"[visual_servo] trace closed path={trace.path}", flush=True)
            except Exception:
                pass
        if testbed_process is not None and testbed_process.poll() is None:
            testbed_process.terminate()


def _rect_to_region(rect: WindowRect) -> tuple[int, int, int, int]:
    return (rect.left, rect.top, rect.right, rect.bottom)


if __name__ == "__main__":
    raise SystemExit(main())
