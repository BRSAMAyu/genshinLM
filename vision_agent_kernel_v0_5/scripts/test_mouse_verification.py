"""Mouse sensitivity calibration — find the right sensitivity for Genshin camera.

Tests with increasing sensitivity values. pixels_per_degree controls how many
pixels of input = 1 degree of angle. Higher = more camera rotation per call.
"""
from __future__ import annotations

import os
import sys
import time
import ctypes

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_mouse_verify.log")
open(_LOG_PATH, "w", encoding="utf-8").close()


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> None:
    try:
        _main()
    except Exception as e:
        log(f"FATAL: {e}")
        import traceback
        traceback.print_exc()
    finally:
        log("Done.")


def _main() -> None:
    from execution.safe_window_backend import SafeWindowInputBackend

    # Test with high sensitivity (more pixels per degree = more camera rotation)
    backend = SafeWindowInputBackend(
        target_window_title="原神",
        pixels_per_degree=32.0,  # 4x default
    )

    try:
        backend.focus_target_window()
        time.sleep(0.5)
    except Exception as e:
        log(f"FOCUS ERROR: {e}")
        return

    log("Sensitivity test: pixels_per_degree=32.0 (4x default)")

    log("=== STEP 1: dx=1.0 (should be ~32px input) ===")
    try:
        backend.mouse_move(1.0, 0, reason="s32_1deg")
        log("OK: dx=1.0, dy=0")
    except Exception as e:
        log(f"FAIL: {e}")
    time.sleep(2.0)

    log("=== STEP 2: dx=2.0 (should be ~64px input) ===")
    try:
        backend.mouse_move(2.0, 0, reason="s32_2deg")
        log("OK: dx=2.0, dy=0")
    except Exception as e:
        log(f"FAIL: {e}")
    time.sleep(2.0)

    log("=== STEP 3: dx=5.0 (should be ~160px input) ===")
    try:
        backend.mouse_move(5.0, 0, reason="s32_5deg")
        log("OK: dx=5.0, dy=0")
    except Exception as e:
        log(f"FAIL: {e}")
    time.sleep(2.0)

    log("=== STEP 4: dx=10.0 (should be ~320px input) ===")
    try:
        backend.mouse_move(10.0, 0, reason="s32_10deg")
        log("OK: dx=10.0, dy=0")
    except Exception as e:
        log(f"FAIL: {e}")
    time.sleep(2.0)

    log("=== STEP 5: dy=5.0 (vertical look up) ===")
    try:
        backend.mouse_move(0, 5.0, reason="s32_look_up")
        log("OK: dx=0, dy=5.0")
    except Exception as e:
        log(f"FAIL: {e}")
    time.sleep(2.0)

    log("=== STEP 6: Rapid small pulses (multiple inputs) ===")
    log("5x dx=2.0 rapid — for smoother but faster rotation")
    for i in range(5):
        try:
            backend.mouse_move(2.0, 0, reason=f"pulse_{i}")
        except Exception as e:
            log(f"FAIL pulse_{i}: {e}")
        time.sleep(0.15)
    log("Pulse sequence done")


if __name__ == "__main__":
    main()