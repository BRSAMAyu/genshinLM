"""Camera sensitivity calibration — find px/degree for Genshin camera.

Process:
1. User manually rotates camera to LEFT edge (60 deg left)
2. User manually rotates camera to RIGHT edge (60 deg right)
3. Script tests calibrated turns to find correct ratio
"""
from __future__ import annotations

import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_calibrate.log")

_log = open(_LOG_PATH, "w", encoding="utf-8", buffering=1)


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    _log.write(line + "\n")


def main() -> None:
    try:
        _main()
    except Exception as e:
        log(f"FATAL: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _log.close()


def _main() -> None:
    from execution.safe_window_backend import SafeWindowInputBackend

    backend = SafeWindowInputBackend(
        target_window_title="原神",
        pixels_per_degree=8.0,
    )

    try:
        backend.focus_target_window()
        time.sleep(0.5)
    except Exception as e:
        log(f"FOCUS ERROR: {e}")
        return

    log("=== CAMERA SENSITIVITY CALIBRATION ===")
    log("STEP 1: Go to Genshin, manually rotate camera to FAR LEFT")
    log("         (camera faces 60 deg left of forward).")
    log("         Press Enter when camera is at the LEFT edge.")
    input("Press Enter when ready...\n")
    log("LEFT edge recorded.")

    log("STEP 2: Go to Genshin, manually rotate camera to FAR RIGHT")
    log("         (camera faces 60 deg right of forward).")
    log("         Press Enter when camera is at the RIGHT edge.")
    input("Press Enter when ready...\n")
    log("RIGHT edge recorded.")

    log("=" * 60)
    log("Now I will test calibrated turns.")
    log("If the camera barely moved, pixels_per_degree needs to be HIGHER.")
    log("=" * 60)

    for angle in [15, 30, 60, -15, -30, -60]:
        log(f"Test: mouse_move({angle}, 0) -- {abs(angle)} deg {'right' if angle > 0 else 'left'}")
        try:
            backend.mouse_move(float(angle), 0, reason=f"calib_{angle}deg")
            log("OK")
        except Exception as e:
            log(f"FAIL: {e}")
        time.sleep(2.0)

    log("=" * 60)
    log("Tell me which angle (dx=N) gives you exactly 30 deg of rotation.")
    log("Then I can compute: ppd = N / 30.0")
    log("For 180-deg coverage: dx = ppd * 60 = px needed one way")
    log("=" * 60)


if __name__ == "__main__":
    main()
