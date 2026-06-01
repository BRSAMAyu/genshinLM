"""Non-interactive control verification — test all inputs in sequence.

Usage (admin terminal):
  python scripts/test_control_verification.py

No user interaction needed. Just observe Genshin and check the log.
"""
from __future__ import annotations

import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_SCRIPT_DIR)
LOG_PATH = os.path.join(_PROJECT_DIR, "_control_verify.log")

_log = open(LOG_PATH, "w", encoding="utf-8", buffering=1)


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    _log.write(line + "\n")


def safe_press(key: str, backend, reason: str, hold: float = 0.12) -> bool:
    try:
        backend.key_down(key, reason=reason)
        time.sleep(hold)
        backend.key_up(key, reason=reason)
        log(f"OK: {key} ({reason})")
        return True
    except Exception as e:
        log(f"FAIL: {key} ({reason}) — {e}")
        return False


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
    import dxcam

    # ---- Resolution check ----
    log("=== RESOLUTION CHECK ===")
    camera = dxcam.create(output_idx=0, output_color="RGB")
    frame = camera.grab()
    if frame is None:
        log("ERROR: no frame")
        camera.release()
        return

    h, w = frame.shape[:2]
    log(f"Native: {w}x{h}")
    TARGET_W, TARGET_H = 1280, 720

    if w != TARGET_W or h != TARGET_H:
        log(f"WILL RESIZE: {w}x{h} -> {TARGET_W}x{TARGET_H}")
    else:
        log(f"Resolution OK: {w}x{h}")
    camera.release()

    # ---- Backend ----
    log("=== BACKEND INIT ===")
    backend = SafeWindowInputBackend(target_window_title="原神", pixels_per_degree=8.0)
    try:
        backend.focus_target_window()
        time.sleep(0.5)
    except Exception as e:
        log(f"FOCUS ERROR: {e}")
        return

    if not backend.is_target_focused():
        log("ERROR: window not focused")
        return
    log("Window focused. Starting tests.")
    log("=" * 60)

    # ---- TEST 1: Movement keys ----
    log("=== MOVEMENT KEYS ===")
    for key, desc in [("w", "forward"), ("a", "left"), ("s", "backward"), ("d", "right")]:
        log(f"Test: {key} ({desc})")
        safe_press(key, backend, desc, hold=1.0)
        time.sleep(1.5)

    # ---- TEST 2: Interaction keys ----
    log("=== INTERACTION KEYS ===")
    for key, desc in [
        ("space", "advance_dialog"),
        ("f", "interact"),
        ("enter", "confirm"),
        ("esc", "back/cancel"),
    ]:
        log(f"Test: {key} ({desc})")
        safe_press(key, backend, desc, hold=0.1)
        time.sleep(0.8)

    # ---- TEST 3: Skill keys ----
    log("=== SKILL KEYS ===")
    for key, desc in [("e", "elemental_skill"), ("q", "elemental_burst"), ("r", "reload")]:
        log(f"Test: {key} ({desc})")
        safe_press(key, backend, desc, hold=0.1)
        time.sleep(0.8)

    # ---- TEST 4: Number keys ----
    log("=== NUMBER KEYS ===")
    for key in ["1", "2", "3", "4", "5"]:
        log(f"Test: {key} (slot)")
        safe_press(key, backend, f"slot_{key}", hold=0.1)
        time.sleep(0.5)

    # ---- TEST 5: Tab (switch character) ----
    log("=== TAB (switch) ===")
    safe_press("tab", backend, "switch_char", hold=0.3)
    time.sleep(1.0)

    # ---- TEST 6: Shift (sprint) ----
    log("=== SHIFT (sprint) ===")
    safe_press("shift", backend, "sprint", hold=1.0)
    time.sleep(1.5)

    # ---- TEST 7: Mouse normal click ----
    log("=== MOUSE LEFT CLICK ===")
    try:
        backend.left_click(reason="normal_click")
        log("OK: left_click")
    except Exception as e:
        log(f"FAIL: left_click — {e}")
    time.sleep(0.8)

    # ---- TEST 8: Alt + Mouse (interface mode) ----
    log("=== ALT + MOUSE (interface mode) ===")
    try:
        backend.key_down("alt", reason="alt_hold")
        time.sleep(0.3)
        log("Alt held")

        backend.mouse_move(0.3, 0, reason="alt_move")
        log("Mouse moved")
        time.sleep(0.3)

        backend.left_click(reason="alt_click")
        log("Click at cursor")
        time.sleep(0.3)

        backend.key_up("alt", reason="alt_release")
        log("Alt released — Alt+Mouse test done")
    except Exception as e:
        log(f"FAIL: Alt+Mouse — {e}")
    time.sleep(1.0)

    # ---- TEST 9: Camera movement (mouse look) ----
    log("=== CAMERA (mouse look) ===")
    try:
        backend.mouse_move(0.5, 0, reason="look_right")
        log("Mouse look right")
        time.sleep(0.5)
        backend.mouse_move(-0.5, 0, reason="look_left")
        log("Mouse look left")
        time.sleep(0.5)
        backend.mouse_move(0, 0.3, reason="look_up")
        log("Mouse look up")
        time.sleep(0.5)
    except Exception as e:
        log(f"FAIL: mouse_move — {e}")

    log("=" * 60)
    log("=== ALL TESTS DONE ===")
    log("Check log above for PASS/FAIL per key.")
    log("If all show OK, all input channels are verified.")


if __name__ == "__main__":
    main()