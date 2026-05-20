from __future__ import annotations

import argparse
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pseudo-3D FOV-aware servo test.")
    parser.add_argument("--fov", type=float, choices=[60.0, 90.0, 110.0], required=True)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--mode", choices=["dry-run", "safe-window"], default="dry-run")
    parser.add_argument("--invert-yaw", action="store_true")
    parser.add_argument("--invert-pitch", action="store_true")
    args = parser.parse_args()

    title = f"vision_agent_kernel_v0_5 fov_test {args.fov:g} {uuid.uuid4()}"
    testbed = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_testbed.py"),
            "--title",
            title,
            "--fov",
            str(args.fov),
        ]
    )
    time.sleep(1.0)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_visual_servo_test.py"),
        "--mode",
        args.mode,
        "--seconds",
        str(args.seconds),
        "--target-window-title",
        title,
        "--dead-zone-deg",
        "1.5",
        "--smoothing-alpha",
        "0.35",
    ]
    if args.invert_yaw:
        command.append("--invert-yaw")
    if args.invert_pitch:
        command.append("--invert-pitch")
    print(f"[fov_servo_test] fov={args.fov} command={' '.join(command)}", flush=True)
    try:
        return subprocess.call(command)
    finally:
        if testbed.poll() is None:
            testbed.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
