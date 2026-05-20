from __future__ import annotations

import argparse
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run final MVP demo: testbed + task graph + telemetry.")
    parser.add_argument("--mode", choices=["dry-run", "safe-window"], default="dry-run")
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--record-video", action="store_true")
    parser.add_argument("--chaos", choices=["none", "mild", "heavy"], default="none")
    parser.add_argument("--task", default=str(ROOT / "configs" / "demo_task.yaml"))
    args = parser.parse_args()

    title = f"vision_agent_kernel_v0_5 final_demo {uuid.uuid4()}"
    testbed_args = [sys.executable, str(ROOT / "scripts" / "run_testbed.py"), "--title", title]
    if args.chaos != "none":
        testbed_args.extend(["--auto-chaos", "occlusion" if args.chaos == "mild" else "distractor", "--auto-chaos-delay", "5"])
    testbed = subprocess.Popen(testbed_args)
    if args.record_video:
        print("[final_demo] warning: video recording backend is optional and not configured; continuing", flush=True)
    time.sleep(1.0)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_task_demo.py"),
        "--task",
        args.task,
        "--seconds",
        str(args.seconds),
        "--mode",
        args.mode,
        "--target-window-title",
        title,
    ]
    try:
        print(f"[final_demo] command={' '.join(command)}", flush=True)
        return subprocess.call(command)
    finally:
        if testbed.poll() is None:
            testbed.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
