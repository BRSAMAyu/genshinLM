from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import FocusState, Observation
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker
from execution.safe_window_backend import SafeWindowInputBackend
from execution.visual_action_block import VisualActionBlockExecutor
from orchestration.graph import COMPLETE, FAILED, INTERRUPTED, OrchestrationGraph
from orchestration.orchestrator import Orchestrator
from orchestration.skills import (
    AcquireTargetSkill,
    EnterTargetRegionSkill,
    ExecuteVisualActionBlockSkill,
    LoadTaskSkill,
    RecoverSkill,
    TrackAndApproachSkill,
    VerifySuccessSkill,
)
from orchestration.task_spec import load_task_spec


DEFAULT_TITLE = "vision_agent_kernel_v0_5 pseudo3d_scene"


def _publish_demo_observation(state_bus: StateBus) -> None:
    now = time.perf_counter()
    state_bus.publish_observation(
        Observation(
            frame_id=1,
            t_capture=now,
            t_processed=now,
            latency_ms=0.0,
            viewport_size=(1280, 720),
            target_track=None,
            obstacle_field=None,
            ui_state=None,
            visual_triggers={
                "target_visible": True,
                "target_visible_and_centered": True,
                "target_color_green": True,
                "in_range_estimated": True,
                "action_sequence_completed": True,
            },
            os_focus=FocusState(focused=True),
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run complete long-horizon task graph demo.")
    parser.add_argument("--task", default=str(ROOT / "configs" / "demo_task.yaml"))
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--mode", choices=["dry-run", "safe-window"], default="dry-run")
    parser.add_argument("--target-window-title", default=DEFAULT_TITLE)
    parser.add_argument("--start-testbed", action="store_true")
    args = parser.parse_args()

    run_id = str(uuid.uuid4())
    run_dir = ROOT / "logs" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    trace_path = run_dir / "task_demo_trace.jsonl"
    timebase = Timebase()
    state_bus = StateBus()
    task_spec = load_task_spec(args.task)
    process: subprocess.Popen | None = None
    backend = ConsoleInputBackend(timebase)
    if args.start_testbed:
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "run_testbed.py"), "--title", args.target_window_title]
        )
        time.sleep(1.0)
    if args.mode == "safe-window":
        try:
            backend = SafeWindowInputBackend(args.target_window_title, timebase=timebase)
        except Exception:
            backend = ConsoleInputBackend(timebase)
    worker = InputWorker(backend, timebase=timebase)
    worker.start()
    executor = VisualActionBlockExecutor(state_bus, worker, timebase=timebase, wait_chunk_ms=50)
    orchestrator = Orchestrator(
        state_bus=state_bus,
        graph=OrchestrationGraph(),
        timebase=timebase,
        skills={
            "load_task": LoadTaskSkill(state_bus, task_spec, timebase),
            "enter_target_region": EnterTargetRegionSkill(state_bus, timebase),
            "acquire_target": AcquireTargetSkill(state_bus, timebase),
            "track_and_approach": TrackAndApproachSkill(state_bus, timebase),
            "execute_visual_action_block": ExecuteVisualActionBlockSkill(executor),
            "verify_success": VerifySuccessSkill(state_bus, timebase),
            "recover": RecoverSkill(state_bus, timebase),
        },
    )
    _publish_demo_observation(state_bus)
    started = timebase.now()
    try:
        with trace_path.open("a", encoding="utf-8") as trace:
            while timebase.now() - started < args.seconds and orchestrator.state not in {
                COMPLETE,
                FAILED,
                INTERRUPTED,
            }:
                transition = orchestrator.run_once()
                result = orchestrator.results_snapshot()[-1] if orchestrator.results_snapshot() else None
                for event in (
                    {"event": "state_transition", **asdict(transition)},
                    {"event": "skill_result", "result": asdict(result) if result else None},
                ):
                    event["timestamp"] = timebase.now()
                    trace.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
                    trace.flush()
                print(
                    "[task_demo] "
                    f"{transition.previous_state}->{transition.next_state} reason={transition.reason}",
                    flush=True,
                )
                time.sleep(0.05)
        print(
            "[task_demo] "
            f"run_id={run_id} final_state={orchestrator.state} trace={trace_path}",
            flush=True,
        )
        return 0 if orchestrator.state == COMPLETE else 2
    finally:
        worker.stop()
        if process is not None and process.poll() is None:
            process.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
