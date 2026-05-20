from __future__ import annotations

import argparse
import ctypes
import json
import signal
import subprocess
import sys
import threading
import time
import tracemalloc
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.camera_servo import CameraServo, CameraServoConfig
from control.progress_supervisor import ProgressSupervisor
from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import CameraIntent, CameraModel, FocusState, InputLease, Observation, TargetTrack
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker
from execution.safe_window_backend import SafeWindowInputBackend, SafeWindowInputError, WindowRect
from perception.capture_base import CaptureConfig
from perception.dxcam_capture import DxcamCapturer
from perception.viewport import ViewportTransformer
from perception.visual_trigger_detector import ColorTargetTracker, VisualTriggerDetector
from telemetry.runtime_health import HealthReportBuilder, PriorityTelemetryQueue, RuntimeHealthSample


DEFAULT_TITLE = "vision_agent_kernel_v0_5 pseudo3d_scene"
VK_F9 = 0x78
CHAOS_KEYS = {
    "disappear": 0x20,
    "teleport": ord("T"),
    "occlusion": ord("O"),
    "distractor": ord("M"),
}


class F9Emergency:
    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._was_down = False

    def pressed(self) -> bool:
        down = bool(self._user32.GetAsyncKeyState(VK_F9) & 0x8000)
        pressed_now = down and not self._was_down
        self._was_down = down
        return pressed_now


class KeySender:
    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32

    def press(self, vk_code: int) -> None:
        self._user32.keybd_event(vk_code, 0, 0, 0)
        time.sleep(0.03)
        self._user32.keybd_event(vk_code, 0, 0x0002, 0)


class ProcessMemorySampler:
    def __init__(self) -> None:
        self._psutil_process = None
        try:
            import psutil  # type: ignore[import-not-found]

            self._psutil_process = psutil.Process()
            self.source = "psutil"
        except Exception:
            tracemalloc.start()
            self.source = "tracemalloc"

    def memory_mb(self) -> float:
        if self._psutil_process is not None:
            return float(self._psutil_process.memory_info().rss) / 1048576.0
        current, _peak = tracemalloc.get_traced_memory()
        return float(current) / 1048576.0

    def thread_count(self) -> int:
        if self._psutil_process is not None:
            return int(self._psutil_process.num_threads())
        return threading.active_count()


def find_or_start_testbed(title: str, timeout_sec: float = 5.0) -> tuple[subprocess.Popen | None, bool]:
    backend = SafeWindowInputBackend(title)
    if _window_exists(backend):
        return (None, False)
    print(f"[endurance] target window not found; starting testbed title={title!r}", flush=True)
    process = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "run_testbed.py"), "--title", title])
    deadline = time.perf_counter() + timeout_sec
    while time.perf_counter() < deadline:
        if _window_exists(backend):
            return (process, True)
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
    track: TargetTrack | None,
    triggers: dict[str, bool],
    focus_ok: bool,
    stale: bool,
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
        os_focus=FocusState(focused=focus_ok),
        stale=stale,
    )


def _track_summary(track: TargetTrack | None) -> dict[str, Any] | None:
    if track is None:
        return None
    return {
        "track_id": track.track_id,
        "state": track.state,
        "center": track.smoothed_center_px,
        "confidence": track.confidence,
        "identity_confidence": track.identity_confidence,
        "missing_duration_ms": track.missing_duration_ms,
        "last_seen_frame_id": track.last_seen_frame_id,
    }


def _intent_summary(intent: CameraIntent | None) -> dict[str, Any] | None:
    return asdict(intent) if intent is not None else None


def _center_error(track: TargetTrack | None) -> tuple[float, float] | None:
    if track is None or track.smoothed_center_px is None:
        return None
    return (track.smoothed_center_px[0] - 640.0, track.smoothed_center_px[1] - 360.0)


def _submit_camera_intent(
    worker: InputWorker,
    intent: CameraIntent,
    timebase: Timebase,
    sequence: int,
) -> None:
    now = timebase.now()
    lease = InputLease(
        lease_id=f"endurance-camera-{sequence}",
        owner="endurance_controller",
        priority=3,
        key_states={},
        mouse_delta=(intent.yaw_delta, intent.pitch_delta),
        created_at=now,
        expires_at=now + max(intent.duration_ms, 80) / 1000.0,
        reason=intent.reason,
    )
    worker.submit_lease(lease)


def _emit_interrupt(
    state_bus: StateBus,
    worker: InputWorker,
    telemetry: PriorityTelemetryQueue,
    report: HealthReportBuilder,
    timebase: Timebase,
    code: str,
    source: str,
    priority: int,
    payload: dict[str, Any] | None = None,
    release_input: bool = False,
) -> Interrupt:
    interrupt = Interrupt(
        priority=priority,
        timestamp=timebase.now(),
        code=code,
        source=source,
        payload=payload or {},
        requires_input_release=release_input,
    )
    state_bus.publish_interrupt(interrupt)
    worker.submit_interrupt(interrupt)
    telemetry.log("interrupt", asdict(interrupt), priority="critical", timestamp=interrupt.timestamp)
    report.record_interrupt()
    return interrupt


def _chaos_plan(mode: str) -> list[tuple[float, str]]:
    if mode == "none":
        return []
    if mode == "mild":
        return [(45.0, "occlusion"), (90.0, "distractor"), (135.0, "disappear")]
    return [
        (20.0, "occlusion"),
        (40.0, "distractor"),
        (60.0, "disappear"),
        (90.0, "teleport"),
        (120.0, "occlusion"),
        (150.0, "distractor"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Stage 13 runtime health endurance test.")
    parser.add_argument("--seconds", type=float, default=180.0)
    parser.add_argument("--mode", choices=["dry-run", "safe-window"], default="dry-run")
    parser.add_argument("--chaos", choices=["none", "mild", "heavy"], default="none")
    parser.add_argument("--save-report", action="store_true")
    parser.add_argument("--target-window-title", default=DEFAULT_TITLE)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    run_id = str(uuid.uuid4())
    run_dir = ROOT / "logs" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    telemetry = PriorityTelemetryQueue(run_dir / "endurance_trace.jsonl", maxsize=2048)
    health_builder = HealthReportBuilder()
    memory_sampler = ProcessMemorySampler()
    timebase = Timebase()
    state_bus = StateBus(observation_history_capacity=5, progress_history_capacity=180, event_queue_capacity=256)
    worker: InputWorker | None = None
    capturer: DxcamCapturer | None = None
    testbed_process: subprocess.Popen | None = None
    input_backend: ConsoleInputBackend | SafeWindowInputBackend | None = None
    release_all_called = False
    stop_requested = False
    active_interrupt: Interrupt | None = None

    def request_stop(signum: int, frame: object) -> None:
        del frame
        nonlocal stop_requested, active_interrupt
        stop_requested = True
        if worker is not None:
            active_interrupt = _emit_interrupt(
                state_bus,
                worker,
                telemetry,
                health_builder,
                timebase,
                code="CTRL_C_OR_TERMINATE",
                source="run_endurance_test",
                priority=0,
                release_input=True,
            )
        print(f"[endurance] stop signal received signum={signum}", flush=True)

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        telemetry.start()
        testbed_process, started_testbed = find_or_start_testbed(args.target_window_title)
        safe_backend = SafeWindowInputBackend(args.target_window_title, timebase=timebase)
        safe_backend.focus_target_window()
        rect = safe_backend.client_rect()
        if args.mode == "safe-window":
            input_backend = safe_backend
            backend_name = "safe-window"
        else:
            input_backend = ConsoleInputBackend(timebase)
            backend_name = "console"
        worker = InputWorker(input_backend, timebase=timebase, tick_seconds=0.005)
        worker.start()

        capturer = DxcamCapturer(
            CaptureConfig(target_fps=60.0, output_color="RGB", region=_rect_to_region(rect)),
            timebase=timebase,
        )
        viewport = ViewportTransformer()
        detector = VisualTriggerDetector()
        tracker = ColorTargetTracker()
        servo = CameraServo(CameraServoConfig(kp_yaw=0.65, kp_pitch=0.45, smoothing_alpha=0.35))
        camera = CameraModel()
        progress_supervisor = ProgressSupervisor(state_bus)
        key_sender = KeySender()
        f9 = F9Emergency()
        capturer.start()

        started = timebase.now()
        last_health_at = started
        last_panel_at = 0.0
        last_controller_at = started
        last_heartbeat_check_at = started
        frame_count_window = 0
        controller_count_window = 0
        detector_latency_window: list[float] = []
        tracker_latency_window: list[float] = []
        lease_sequence = 0
        chaos_items = _chaos_plan(args.chaos)
        chaos_index = 0
        last_drop_count = 0

        state_bus.update_heartbeat("input_worker", timebase.now())
        print(
            "[endurance] "
            f"run_id={run_id} mode={args.mode} chaos={args.chaos} "
            f"seconds={args.seconds} input_backend={backend_name} "
            f"memory_source={memory_sampler.source} trace={telemetry.path}",
            flush=True,
        )
        telemetry.log(
            "run_start",
            {
                "run_id": run_id,
                "mode": args.mode,
                "chaos": args.chaos,
                "seconds": args.seconds,
                "started_testbed": started_testbed,
                "input_backend": backend_name,
                "memory_source": memory_sampler.source,
            },
        )

        while not stop_requested and timebase.now() - started < args.seconds:
            now = timebase.now()
            if f9.pressed():
                active_interrupt = _emit_interrupt(
                    state_bus,
                    worker,
                    telemetry,
                    health_builder,
                    timebase,
                    code="EMERGENCY_STOP",
                    source="F9",
                    priority=0,
                    release_input=True,
                )
                print("[endurance] F9 emergency stop detected", flush=True)
                break

            focus_ok = True
            if args.mode == "safe-window":
                focus_ok = safe_backend.is_target_focused()
                if not focus_ok:
                    active_interrupt = _emit_interrupt(
                        state_bus,
                        worker,
                        telemetry,
                        health_builder,
                        timebase,
                        code="ENVIRONMENT_LOST_FOCUS",
                        source="safe_window_backend",
                        priority=0,
                        release_input=True,
                    )
                    print("[endurance] target window lost focus", flush=True)
                    break

            if chaos_index < len(chaos_items) and now - started >= chaos_items[chaos_index][0]:
                scenario = chaos_items[chaos_index][1]
                safe_backend.focus_target_window()
                time.sleep(0.05)
                key_sender.press(CHAOS_KEYS[scenario])
                telemetry.log(
                    "chaos_event",
                    {"scenario": scenario, "elapsed_sec": now - started},
                    priority="critical",
                )
                print(f"[endurance] chaos_event scenario={scenario}", flush=True)
                chaos_index += 1

            packet = capturer.get_latest_frame()
            if packet is None:
                time.sleep(0.005)
                continue

            state_bus.update_heartbeat("perception", now)
            normalized = viewport.normalize(packet.image)
            detector_started = timebase.now()
            detections = detector.detect_targets(normalized, packet.frame_id, packet.timestamp)
            detector_latency = (timebase.now() - detector_started) * 1000.0
            tracker_started = timebase.now()
            track = tracker.update(detections, packet.frame_id, packet.timestamp)
            tracker_latency = (timebase.now() - tracker_started) * 1000.0
            triggers = detector.detect_triggers(normalized, track)
            observation_age_ms = (timebase.now() - packet.timestamp) * 1000.0
            stale = observation_age_ms > 500.0
            observation = _observation(
                packet.frame_id,
                packet.timestamp,
                observation_age_ms,
                track,
                triggers,
                focus_ok,
                stale,
            )
            state_bus.publish_observation(observation)
            progress = progress_supervisor.update(observation)
            frame_count_window += 1
            detector_latency_window.append(detector_latency)
            tracker_latency_window.append(tracker_latency)

            intent: CameraIntent | None = None
            if track is not None and track.smoothed_center_px is not None and now - last_controller_at >= 1.0 / 30.0:
                error = servo.compute_error(track, camera)
                intent = servo.step(error, dt=max(now - last_controller_at, 1e-3))
                lease_sequence += 1
                _submit_camera_intent(worker, intent, timebase, lease_sequence)
                state_bus.update_heartbeat("controller", now)
                state_bus.update_heartbeat("input_worker", now)
                controller_count_window += 1
                last_controller_at = now

            if stale:
                active_interrupt = _emit_interrupt(
                    state_bus,
                    worker,
                    telemetry,
                    health_builder,
                    timebase,
                    code="STALE_OBSERVATION",
                    source="runtime_health",
                    priority=2,
                    payload={"latest_observation_age_ms": observation_age_ms},
                )

            if progress.active_interrupt is not None:
                active_interrupt = progress.active_interrupt
                telemetry.log("interrupt", asdict(active_interrupt), priority="critical")
                health_builder.record_interrupt()

            telemetry.log(
                "observation_summary",
                {
                    "frame_id": packet.frame_id,
                    "track": _track_summary(track),
                    "center_error_px": _center_error(track),
                    "camera_intent": _intent_summary(intent),
                    "progress": {
                        "ewma_progress": progress.ewma_progress,
                        "progress_slope_2s": progress.progress_slope_2s,
                        "visibility_ratio_1s": progress.visibility_ratio_1s,
                        "frustration": progress.frustration,
                        "trend": progress.trend,
                    },
                    "active_interrupt": asdict(active_interrupt) if active_interrupt is not None else None,
                },
                priority="low",
            )

            if telemetry.dropped_low_priority_logs > last_drop_count:
                telemetry.log(
                    "TELEMETRY_BACKPRESSURE",
                    {
                        "dropped_low_priority_logs": telemetry.dropped_low_priority_logs,
                        "backlog": telemetry.backlog,
                    },
                    priority="critical",
                )
                last_drop_count = telemetry.dropped_low_priority_logs

            if now - last_heartbeat_check_at >= 1.0:
                heartbeat = state_bus.heartbeat_snapshot()
                missing = [
                    owner
                    for owner in ("perception", "controller", "input_worker")
                    if now - heartbeat.get(owner, 0.0) > 2.0
                ]
                if missing:
                    active_interrupt = _emit_interrupt(
                        state_bus,
                        worker,
                        telemetry,
                        health_builder,
                        timebase,
                        code="WATCHDOG_TIMEOUT",
                        source="runtime_health",
                        priority=0,
                        payload={"missing_heartbeats": missing},
                        release_input=True,
                    )
                    print(f"[endurance] heartbeat timeout missing={missing}", flush=True)
                last_heartbeat_check_at = now

            if now - last_health_at >= 1.0:
                elapsed = max(now - last_health_at, 1e-6)
                sample = RuntimeHealthSample(
                    timestamp=now,
                    perception_fps=frame_count_window / elapsed,
                    detector_latency_ms=(
                        sum(detector_latency_window) / len(detector_latency_window)
                        if detector_latency_window
                        else 0.0
                    ),
                    tracker_latency_ms=(
                        sum(tracker_latency_window) / len(tracker_latency_window)
                        if tracker_latency_window
                        else 0.0
                    ),
                    controller_fps=controller_count_window / elapsed,
                    input_worker_alive=worker.is_alive,
                    telemetry_backlog=telemetry.backlog,
                    latest_observation_age_ms=observation_age_ms,
                    focus_ok=focus_ok,
                    process_memory_mb=memory_sampler.memory_mb(),
                    thread_count=memory_sampler.thread_count(),
                )
                health_builder.add_sample(sample)
                telemetry.log("runtime_health", asdict(sample), priority="low", timestamp=now)
                frame_count_window = 0
                controller_count_window = 0
                detector_latency_window.clear()
                tracker_latency_window.clear()
                last_health_at = now

            if now - last_panel_at >= 1.0:
                latest_health = health_builder._samples[-1] if health_builder._samples else None
                fps_display = latest_health.perception_fps if latest_health is not None else 0.0
                controller_fps_display = latest_health.controller_fps if latest_health is not None else 0.0
                print(
                    "[health_panel] "
                    f"elapsed={now - started:.1f}s "
                    f"frame_id={packet.frame_id} "
                    f"target_state={track.state if track else 'NONE'} "
                    f"center_error_px={_center_error(track)} "
                    f"progress={progress.ewma_progress:.3f} "
                    f"frustration={progress.frustration:.1f} "
                    f"fps={fps_display:.1f} "
                    f"controller_fps={controller_fps_display:.1f} "
                    f"backlog={telemetry.backlog} "
                    f"dropped={telemetry.dropped_low_priority_logs} "
                    f"worker_alive={worker.is_alive} "
                    f"focus_ok={focus_ok}",
                    flush=True,
                )
                last_panel_at = now

        return_code = 0
        return return_code
    finally:
        if worker is not None:
            try:
                worker.stop()
                release_all_called = True
            except Exception as exc:
                print(f"[endurance] worker stop failed: {exc!r}", flush=True)
        elif input_backend is not None:
            try:
                input_backend.release_all(reason="run_endurance_test_exit")
                release_all_called = True
            except Exception as exc:
                print(f"[endurance] release_all failed: {exc!r}", flush=True)
        if capturer is not None:
            try:
                capturer.stop()
            except Exception:
                pass
        report = health_builder.build(
            dropped_low_priority_logs=telemetry.dropped_low_priority_logs,
            release_all_called=release_all_called,
        )
        report_path = run_dir / "health_report.json"
        report_payload = asdict(report) | {
            "run_id": run_id,
            "seconds_requested": args.seconds,
            "mode": args.mode,
            "chaos": args.chaos,
            "memory_source": memory_sampler.source,
            "trace_path": str(telemetry.path),
        }
        if args.save_report:
            report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        telemetry.log("health_report", report_payload, priority="critical")
        telemetry.close()
        print(f"[endurance] health_report={report_payload}", flush=True)
        if args.save_report:
            print(f"[endurance] report_path={report_path}", flush=True)
        if testbed_process is not None and testbed_process.poll() is None:
            testbed_process.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
