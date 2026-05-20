from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.obstacle_policy import ObstaclePolicy
from control.progress_supervisor import ProgressSupervisor
from control.recovery_policy import RecoveryPolicy
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import FocusState, Observation, TargetTrack
from orchestration.graph import RECOVER, TRACK_AND_APPROACH, OrchestrationGraph
from perception.depth_base import HeuristicObstacleEstimator


def _frame(scenario: str, step: int) -> np.ndarray:
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    if scenario == "simple":
        return image
    if scenario == "blocked":
        image[280:560, 540:680, :] = (90, 100, 140)
        if step > 35:
            image[280:560, 540:680, :] = (0, 0, 0)
    elif scenario == "impossible":
        image[240:620, 420:820, :] = (120, 120, 120)
    return image


def _observation(frame_id: int, timestamp: float, obstacle_field, visible: bool) -> Observation:
    track = (
        TargetTrack(
            track_id="demo-target",
            class_id="target",
            state="TRACKED",
            bbox_xyxy=(600.0, 320.0, 680.0, 400.0),
            smoothed_center_px=(640.0, 360.0),
            velocity_px_s=(0.0, 0.0),
            confidence=0.9,
            identity_confidence=0.9,
            missing_duration_ms=0.0,
            bearing_deg=None,
            pitch_deg=None,
            estimated_range=None,
            last_seen_frame_id=frame_id,
        )
        if visible
        else None
    )
    return Observation(
        frame_id=frame_id,
        t_capture=timestamp,
        t_processed=timestamp,
        latency_ms=0.0,
        viewport_size=(1280, 720),
        target_track=track,
        obstacle_field=obstacle_field,
        ui_state=None,
        visual_triggers={"target_visible": visible, "in_range_estimated": visible},
        os_focus=FocusState(focused=True),
        stale=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run low-frequency obstacle recovery test.")
    parser.add_argument("--scenario", choices=["simple", "blocked", "impossible"], required=True)
    parser.add_argument("--seconds", type=float, default=30.0)
    args = parser.parse_args()

    run_id = str(uuid.uuid4())
    run_dir = ROOT / "logs" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    trace_path = run_dir / "obstacle_recovery_trace.jsonl"
    timebase = Timebase()
    state_bus = StateBus()
    estimator = HeuristicObstacleEstimator()
    progress_supervisor = ProgressSupervisor(state_bus)
    obstacle_policy = ObstaclePolicy()
    recovery_policy = RecoveryPolicy()
    graph = OrchestrationGraph()
    state = TRACK_AND_APPROACH
    started = timebase.now()
    frame_id = 0

    with trace_path.open("a", encoding="utf-8") as trace:
        while timebase.now() - started < args.seconds:
            frame_id += 1
            now = timebase.now()
            frame = _frame(args.scenario, frame_id)
            obstacle_field = estimator.estimate(frame, frame_id, now)
            visible = args.scenario == "simple" or (args.scenario == "blocked" and frame_id > 35)
            observation = _observation(frame_id, now, obstacle_field, visible)
            state_bus.publish_observation(observation)
            progress = progress_supervisor.update(observation)
            decision = obstacle_policy.decide(obstacle_field, progress)
            recovery = recovery_policy.decide(progress)
            if decision.interrupt is not None:
                transition = graph.next_for_interrupt(state, decision.interrupt)
                state = transition.next_state
            elif recovery.interrupt is not None:
                transition = graph.next_for_interrupt(state, recovery.interrupt)
                state = transition.next_state
            elif decision.action in {"LOCAL_REROUTE", "ESCALATE"}:
                state = RECOVER
            event = {
                "timestamp": now,
                "event": "obstacle_sample",
                "scenario": args.scenario,
                "frame_id": frame_id,
                "obstacle_field": asdict(obstacle_field),
                "progress": asdict(progress),
                "obstacle_decision": asdict(decision),
                "recovery_decision": asdict(recovery),
                "orchestrator_state": state,
            }
            trace.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            trace.flush()
            print(
                "[obstacle_panel] "
                f"frame_id={frame_id} scenario={args.scenario} "
                f"front={obstacle_field.sectors.get('front', 0.0):.2f} "
                f"decision={decision.action} recovery={recovery.action} "
                f"frustration={progress.frustration:.1f} state={state}",
                flush=True,
            )
            if args.scenario == "simple" and frame_id > 15:
                break
            if args.scenario == "blocked" and frame_id > 45 and state == RECOVER:
                break
            if args.scenario == "impossible" and progress.active_interrupt is not None:
                break
            time.sleep(0.1)
    print(f"[obstacle_test] run_id={run_id} trace={trace_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
