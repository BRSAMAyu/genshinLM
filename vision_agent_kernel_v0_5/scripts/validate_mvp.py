from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], timeout: int = 120) -> int:
    print(f"[validate_mvp] {' '.join(command)}", flush=True)
    return subprocess.call(command, cwd=ROOT, timeout=timeout)


def main() -> int:
    checks = [
        ([sys.executable, "-m", "compileall", "core", "telemetry", "execution", "perception", "control", "orchestration", "scripts", "testbed", "tests"], 120),
        ([sys.executable, "-m", "pytest", "-q"], 120),
        ([sys.executable, "scripts/run_yolo_tracking_test.py", "--help"], 30),
        ([sys.executable, "scripts/run_task_demo.py", "--task", "configs/demo_task.yaml", "--seconds", "5", "--mode", "dry-run"], 60),
        ([sys.executable, "scripts/run_final_demo.py", "--mode", "dry-run", "--seconds", "5", "--chaos", "none"], 90),
    ]
    for command, timeout in checks:
        code = _run(command, timeout)
        if code != 0:
            print(f"[validate_mvp] failed code={code}", flush=True)
            return code
    print("[validate_mvp] all checks passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
