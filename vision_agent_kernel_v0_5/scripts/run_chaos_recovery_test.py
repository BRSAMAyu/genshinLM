from __future__ import annotations

import argparse
import ctypes
import json
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.progress_supervisor import ProgressSupervisor
from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import FocusState, Observation, TargetTrack
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker
from execution.visual_action_block import VisualActionBlockExecutor
from orchestration.graph import OrchestrationGraph
from orchestration.graph import TRACK_AND_APPROACH
from orchestration.orchestrator import Orchestrator
from orchestration.skills import (
    AcquireTargetSkill,
    ExecuteVisualActionBlockSkill,
    RecoverSkill,
    TrackAndApproachSkill,
    VerifySuccessSkill,
)
from perception.capture_base import CaptureConfig
from perception.dxcam_capture import DxcamCapturer
from perception.viewport import ViewportTransformer
from perception.visual_trigger_detector import ColorTargetTracker, VisualTriggerDetector
from scripts.run_visual_action_block_test import DEFAULT_TITLE, _rect_to_region
from execution.safe_window_backend import SafeWindowInputBackend, SafeWindowInputError


KEYS = {
    "disappear": 0x20,
    "teleport": ord("T"),
    "occlusion": ord("O"),
    "distractor": ord("M"),
}

AUTO_CHAOS_DELAY_SEC = 3.0


class TraceWriter:
    def __init__(self, run_id: str) -> None:
        self.run_dir = ROOT / "logs" / "runs" / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.run_dir / "chaos_recovery_trace.jsonl"
        self._file = self.path.open("a", encoding="utf-8")

    def write(self, event: dict[str, Any]) -> None:
        self._file.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()


class KeySender:
    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32

    def press(self, vk_code: int) -> None:
        self._user32.keybd_event(vk_code, 0, 0, 0)
        time.sleep(0.03)
        self._user32.keybd_event(vk_code, 0, 0x0002, 0)


def find_or_start_chaos_testbed(
    title: str,
    scenario: str,
    timeout_sec: float = 5.0,
) -> tuple[subprocess.Popen | None, bool]:
    backend = SafeWindowInputBackend(title)
    if _window_exists(backend):
        return (None, False)
    print(f"[chaos_test] target window not found; starting auto-chaos testbed title={title!r}", flush=True)
    process = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_testbed.py"),
            "--title",
            title,
            "--auto-chaos",
            scenario,
            "--auto-chaos-delay",
            str(AUTO_CHAOS_DELAY_SEC),
        ]
    )
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


def _drain_interrupts(state_bus: StateBus) -> list[Interrupt]:
    drained: list[Interrupt] = []
    while True:
        interrupt = state_bus.next_interrupt(timeout=0.0)
        if interrupt is None:
            return drained
        drained.append(interrupt)


def _observation(
    frame_id: int,
    timestamp: float,
    latency_ms: float,
    track: TargetTrack | None,
    triggers: dict[str, bool],
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
        stale=latency_ms > 150.0 or track is None or track.state != "TRACKED",
    )


def _make_orchestrator(state_bus: StateBus, timebase: Timebase, worker: InputWorker) -> Orchestrator:
    executor = VisualActionBlockExecutor(state_bus, worker, timebase=timebase, wait_chunk_ms=50)
    return Orchestrator(
        state_bus=state_bus,
        skills={
            "acquire_target": AcquireTargetSkill(state_bus, timebase),
            "track_and_approach": TrackAndApproachSkill(state_bus, timebase),
            "execute_visual_action_block": ExecuteVisualActionBlockSkill(executor),
            "verify_success": VerifySuccessSkill(state_bus, timebase),
            "recover": RecoverSkill(state_bus, timebase),
        },
        graph=OrchestrationGraph(),
        timebase=timebase,
    )


def _track_dict(track: TargetTrack | None) -> dict[str, Any] | None:
    if track is None:
        return None
    return {
        "track_id": track.track_id,
        "state": track.state,
        "center": track.smoothed_center_px,
        "velocity_px_s": track.velocity_px_s,
        "confidence": track.confidence,
        "identity_confidence": track.identity_confidence,
        "missing_duration_ms": track.missing_duration_ms,
        "appearance_signature": track.appearance_signature,
    }


def _crop_to_client_frame(image: Any, rect: Any) -> Any:
    height, width = image.shape[:2]
    expected_width = rect.width
    expected_height = rect.height
    if width == expected_width and height == expected_height:
        return image
    if width >= rect.right and height >= rect.bottom:
        return image[rect.top:rect.bottom, rect.left:rect.right]
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Stage 12 target lost / chaos recovery test.")
    parser.add_argument("--scenario", choices=sorted(KEYS), required=True)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--target-window-title", default=DEFAULT_TITLE)
    args = parser.parse_args()

    run_id = str(uuid.uuid4())
    timebase = Timebase()
    state_bus = StateBus()
    process: subprocess.Popen | None = None
    capturer: DxcamCapturer | None = None
    trace: TraceWriter | None = None
    worker: InputWorker | None = None
    stop_requested = False

    def request_stop(signum: int, frame: object) -> None:
        del frame
        nonlocal stop_requested
        stop_requested = True
        state_bus.publish_interrupt(
            Interrupt(priority=0, timestamp=timebase.now(), code="CTRL_C", source="chaos_test")
        )
        print(f"[chaos_test] stop signal received signum={signum}", flush=True)

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        process, auto_chaos = find_or_start_chaos_testbed(args.target_window_title, args.scenario)
        safe_backend = SafeWindowInputBackend(args.target_window_title, timebase=timebase)
        safe_backend.focus_target_window()
        key_sender = KeySender()
        if not auto_chaos:
            time.sleep(0.1)
            key_sender.press(ord("R"))
            time.sleep(0.15)
        rect = safe_backend.client_rect()
        capturer = DxcamCapturer(
            CaptureConfig(target_fps=60.0, output_color="RGB", region=_rect_to_region(rect)),
            timebase=timebase,
        )
        viewport = ViewportTransformer()
        detector = VisualTriggerDetector()
        tracker = ColorTargetTracker()
        progress = ProgressSupervisor(state_bus)
        worker = InputWorker(ConsoleInputBackend(timebase), timebase=timebase)
        worker.start()
        orchestrator = _make_orchestrator(state_bus, timebase, worker)
        orchestrator.force_state(TRACK_AND_APPROACH, reason="chaos_test_start")
        trace = TraceWriter(run_id)
        capturer.start()
        print(f"[chaos_test] run_id={run_id} trace={trace.path}", flush=True)

        started = timebase.now()
        chaos_sent = False
        first_tracked_at: float | None = None
        last_track_state: str | None = None
        last_panel = 0.0
        transition_chain: list[str] = []

        while not stop_requested and timebase.now() - started < args.seconds:
            now = timebase.now()
            if auto_chaos and not chaos_sent and now - started >= AUTO_CHAOS_DELAY_SEC:
                event = {
                    "timestamp": now,
                    "event": "chaos_event",
                    "scenario": args.scenario,
                    "key": "auto",
                }
                trace.write(event)
                print(f"[chaos_test] chaos_event scenario={args.scenario} source=auto", flush=True)
                chaos_sent = True
            elif not chaos_sent and first_tracked_at is not None and now - first_tracked_at >= 0.5:
                safe_backend.focus_target_window()
                time.sleep(0.1)
                key_sender.press(KEYS[args.scenario])
                event = {
                    "timestamp": now,
                    "event": "chaos_event",
                    "scenario": args.scenario,
                    "key": args.scenario,
                }
                trace.write(event)
                print(f"[chaos_test] chaos_event scenario={args.scenario}", flush=True)
                chaos_sent = True

            packet = capturer.get_latest_frame()
            if packet is None:
                time.sleep(0.005)
                continue
            frame = viewport.normalize(_crop_to_client_frame(packet.image, rect))
            detections = detector.detect_targets(frame, packet.frame_id, packet.timestamp)
            track = tracker.update(detections, packet.frame_id, packet.timestamp)
            triggers = detector.detect_triggers(frame, track)
            observation = _observation(
                packet.frame_id,
                packet.timestamp,
                (timebase.now() - packet.timestamp) * 1000.0,
                track,
                triggers,
            )
            state_bus.publish_observation(observation)
            progress_state = progress.update(observation)
            if (
                first_tracked_at is None
                and track is not None
                and track.state == "TRACKED"
            ):
                first_tracked_at = timebase.now()

            state = track.state if track is not None else "NONE"
            if state != last_track_state:
                event = {
                    "timestamp": timebase.now(),
                    "event": "track_state_change",
                    "previous_state": last_track_state,
                    "next_state": state,
                    "track": _track_dict(track),
                }
                trace.write(event)
                print(f"[chaos_test] track_state_change {last_track_state}->{state}", flush=True)
                last_track_state = state

            if progress_state.active_interrupt is not None and chaos_sent:
                interrupt = progress_state.active_interrupt
                trace.write({"timestamp": timebase.now(), "event": "interrupt", **asdict(interrupt)})
                for queued_interrupt in _drain_interrupts(state_bus):
                    trace.write(
                        {
                            "timestamp": timebase.now(),
                            "event": "interrupt",
                            "dequeued_before_orchestration": True,
                            **asdict(queued_interrupt),
                        }
                    )
                if args.scenario in {"disappear", "teleport"} and interrupt.code != "TARGET_LOST":
                    continue
                state_bus.publish_interrupt(interrupt)
                transition = orchestrator.run_once()
                transition_chain.append(transition.next_state)
                trace.write(
                    {
                        "timestamp": timebase.now(),
                        "event": "state_transition",
                        "previous_state": transition.previous_state,
                        "next_state": transition.next_state,
                        "reason": transition.reason,
                    }
                )
                print(
                    "[chaos_test] "
                    f"interrupt={interrupt.code} transition="
                    f"{transition.previous_state}->{transition.next_state}",
                    flush=True,
                )

            sample = {
                "timestamp": timebase.now(),
                "event": "sample",
                "frame_id": packet.frame_id,
                "scenario": args.scenario,
                "track": _track_dict(track),
                "candidate_count": len(detections),
                "triggers": triggers,
                "progress": {
                    "ewma_progress": progress_state.ewma_progress,
                    "progress_slope_2s": progress_state.progress_slope_2s,
                    "visibility_ratio_1s": progress_state.visibility_ratio_1s,
                    "frustration": progress_state.frustration,
                    "trend": progress_state.trend,
                },
                "orchestrator_state": orchestrator.state,
            }
            trace.write(sample)
            if timebase.now() - last_panel >= 0.2:
                print(
                    "[chaos_panel] "
                    f"frame_id={packet.frame_id} scenario={args.scenario} "
                    f"track={_track_dict(track)} "
                    f"frustration={progress_state.frustration:.1f} "
                    f"visibility={progress_state.visibility_ratio_1s:.2f} "
                    f"orchestrator={orchestrator.state}",
                    flush=True,
                )
                last_panel = timebase.now()

            if args.scenario in {"disappear", "teleport"} and orchestrator.state in {"ACQUIRE_TARGET", "RECOVER"}:
                if track is not None and track.state == "LOST":
                    break
            if args.scenario in {"occlusion", "distractor"} and chaos_sent and now - started > 6.0:
                break

        print(
            "[chaos_test] "
            f"state_transition_chain={transition_chain} final_state={orchestrator.state}",
            flush=True,
        )
        return 0
    finally:
        try:
            if worker is not None:
                worker.stop()
        finally:
            if capturer is not None:
                capturer.stop()
            if trace is not None:
                trace.close()
                print(f"[chaos_test] trace closed path={trace.path}", flush=True)
            if process is not None and process.poll() is None:
                process.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
