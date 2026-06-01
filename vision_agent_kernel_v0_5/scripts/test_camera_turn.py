"""Quick camera turn test — find how much dx=angle gives you 60 deg rotation.

Usage (admin):
  python scripts/test_camera_turn.py

Tests the full 60-degree turn that will be needed for navigation coverage.
"""
from __future__ import annotations

import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_camera_turn.log")
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

    # Test with very high sensitivity to find upper bound
    backend = SafeWindowInputBackend(
        target_window_title="原神",
        pixels_per_degree=128.0,  # 16x default — very high
    )

    try:
        backend.focus_target_window()
        time.sleep(0.5)
    except Exception as e:
        log(f"FOCUS ERROR: {e}")
        return

    log("=== CAMERA TURN TEST (ppd=128.0) ===")
    log("ppd=128 means dx=1.0 gives 128px mouse input.")
    log("With ppd=128: dx=60 gives 7680px (very large move)")
    log("=" * 60)

    # Test increasing angles until we find 60 deg
    # With ppd=128: dx=1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 45.0, 60.0
    test_angles = [5.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
    for angle in test_angles:
        log(f"Turn RIGHT {angle} deg: dx={angle} (ppd=128 -> {int(angle*128)} px)")
        try:
            backend.mouse_move(angle, 0, reason=f"right_{angle}deg")
            log("OK")
        except Exception as e:
            log(f"FAIL: {e}")
        time.sleep(2.5)

    log("=" * 60)
    log("Tell me which dx value gives you approximately 60 deg of rotation.")
    log("Example: if dx=30.0 looked like 60 deg, then your ppd target = 128 * 30 / 60 = 64.0")
    log("=" * 60)


if __name__ == "__main__":
    main()