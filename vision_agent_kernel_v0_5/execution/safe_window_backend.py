from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.timebase import Timebase

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app_service.calibration import CalibrationProfile


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001

# Common virtual key codes
_VK_MAP: dict[str, int] = {
    "w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44,
    "e": 0x45, "q": 0x51, "r": 0x52, "f": 0x46,
    "c": 0x43, "v": 0x56, "x": 0x58, "z": 0x5A,
    "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35,
    "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39, "0": 0x30,
    "i": 0x49, "b": 0x42, "j": 0x4A, "m": 0x4D, "p": 0x50,
    "y": 0x59, "u": 0x55, "g": 0x47,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
    "space": 0x20, "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
    "tab": 0x09, "enter": 0x0D, "esc": 0x1B, "escape": 0x1B,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
}

# Hardware scan codes for DirectInput compatibility
_SCAN_MAP: dict[str, int] = {
    "w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20,
    "e": 0x12, "q": 0x10, "r": 0x13, "f": 0x21,
    "c": 0x2E, "v": 0x2F, "x": 0x2D, "z": 0x2C,
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
    "i": 0x17, "b": 0x30, "j": 0x24, "m": 0x32, "p": 0x19,
    "y": 0x15, "u": 0x16, "g": 0x22,
    "f1": 0x3B, "f2": 0x3C, "f3": 0x3D, "f4": 0x3E, "f5": 0x3F,
    "space": 0x39, "shift": 0x2A, "ctrl": 0x1D, "alt": 0x38,
    "tab": 0x0F, "enter": 0x1C, "esc": 0x01, "escape": 0x01,
    "left": 0x4B, "up": 0x48, "right": 0x4D, "down": 0x50,
}

# Keys that need KEYEVENTF_EXTENDEDKEY (arrow keys, etc.)
_EXTENDED_KEYS: set[str] = {"left", "up", "right", "down"}


class SafeWindowInputError(RuntimeError):
    pass


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


@dataclass(frozen=True, slots=True)
class WindowRect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)


MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_ABSOLUTE = 0x8000
WHEEL_DELTA = 120


class SafeWindowInputBackend:
    def __init__(
        self,
        target_window_title: str,
        pixels_per_degree: float = 64.0,
        # Calibrated: ppd=64 means dx=1.0 → 64px → ~10 deg (Genshin default sensitivity)
        # For 60-deg coverage one way: dx = 60 * (8/64) ≈ 7.5 with default ppd=8
        # With ppd=64: dx = 60/64 ≈ 0.94 → 60px → ~60 deg
        timebase: Timebase | None = None,
        alt_window_titles: list[str] | None = None,
    ) -> None:
        self.target_window_title = target_window_title
        self.pixels_per_degree = pixels_per_degree
        self.alt_window_titles = alt_window_titles or []
        self._timebase = timebase or Timebase()
        self._user32 = ctypes.windll.user32
        self._configure_win32()
        self._released = True
        self._down_keys: set[str] = set()
        self._mouse_down: bool = False
        self._lock = threading.RLock()
        # Cooldown to prevent focus oscillation (positive feedback trap)
        self._last_focus_attempt: float = -999.0
        self._focus_cooldown_sec: float = 2.0

    @classmethod
    def from_profile(
        cls,
        profile: CalibrationProfile,
        pixels_per_degree: float = 8.0,
        timebase: Timebase | None = None,
    ) -> SafeWindowInputBackend:
        alt_titles: list[str] = []
        if profile.alt_window_title is not None:
            alt_titles.append(profile.alt_window_title)
        return cls(
            target_window_title=profile.window_title,
            pixels_per_degree=pixels_per_degree,
            timebase=timebase,
            alt_window_titles=alt_titles,
        )

    def mouse_move(self, dx: float, dy: float, reason: str = "") -> bool:
        self._ensure_target_focused()

        # ---- Option A: relative move (standard, works for most games) ----
        pixel_dx = int(round(dx * self.pixels_per_degree))
        pixel_dy = int(round(dy * self.pixels_per_degree))

        rel_input = INPUT(
            type=INPUT_MOUSE,
            union=INPUT_UNION(
                mi=MOUSEINPUT(
                    dx=pixel_dx,
                    dy=pixel_dy,
                    mouseData=0,
                    dwFlags=MOUSEEVENTF_MOVE,
                    time=0,
                    dwExtraInfo=ctypes.c_void_p(0),
                )
            ),
        )
        sent = self._user32.SendInput(1, ctypes.byref(rel_input), ctypes.sizeof(INPUT))
        if sent == 1:
            with self._lock:
                self._released = False
            print(
                "[SafeWindowInputBackend] "
                f"{self._timebase.now():.6f} mouse_move relative pixels=({pixel_dx},{pixel_dy}) reason={reason!r}",
                flush=True,
            )
            return True

        # ---- Option B: absolute move (for DirectInput games) ----
        user32 = self._user32
        hwnd = self._find_target_window()
        rect = ctypes.byref(ctypes.wintypes.RECT())
        user32.GetWindowRect(hwnd, rect)
        r = rect.contents
        win_w = r.right - r.left
        win_h = r.bottom - r.top

        # Get current cursor position
        cur = ctypes.wintypes.POINT()
        self._user32.GetCursorPos(ctypes.byref(cur))

        # Target: current cursor + relative delta
        target_x = cur.x + pixel_dx
        target_y = cur.y + pixel_dy

        # Clamp to screen bounds
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        if screen_w <= 0 or screen_h <= 0:
            raise SafeWindowInputError(f"invalid screen metrics: {screen_w}x{screen_h}")
        target_x = max(0, min(screen_w - 1, target_x))
        target_y = max(0, min(screen_h - 1, target_y))

        # Normalize to 0-65535
        norm_x = int((target_x / screen_w) * 65535)
        norm_y = int((target_y / screen_h) * 65535)

        abs_input = INPUT(
            type=INPUT_MOUSE,
            union=INPUT_UNION(
                mi=MOUSEINPUT(
                    dx=norm_x,
                    dy=norm_y,
                    mouseData=0,
                    dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
                    time=0,
                    dwExtraInfo=ctypes.c_void_p(0),
                )
            ),
        )
        sent2 = self._user32.SendInput(1, ctypes.byref(abs_input), ctypes.sizeof(INPUT))
        if sent2 != 1:
            raise SafeWindowInputError("SendInput failed (both relative and absolute)")
        with self._lock:
            self._released = False
        print(
            "[SafeWindowInputBackend] "
            f"{self._timebase.now():.6f} mouse_move absolute target=({target_x},{target_y}) reason={reason!r}",
            flush=True,
        )
        return True

    def mouse_move_to(self, x: int, y: int, reason: str = "") -> bool:
        """Move mouse cursor to screen pixel position (x, y)."""
        self._ensure_target_focused()
        user32 = self._user32
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        if screen_w <= 0 or screen_h <= 0:
            raise SafeWindowInputError(f"invalid screen metrics: {screen_w}x{screen_h}")
        x = max(0, min(screen_w - 1, x))
        y = max(0, min(screen_h - 1, y))
        norm_x = int((x / screen_w) * 65535)
        norm_y = int((y / screen_h) * 65535)

        input_packet = INPUT(
            type=INPUT_MOUSE,
            union=INPUT_UNION(
                mi=MOUSEINPUT(
                    dx=norm_x,
                    dy=norm_y,
                    mouseData=0,
                    dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
                    time=0,
                    dwExtraInfo=ctypes.c_void_p(0),
                )
            ),
        )
        sent = self._user32.SendInput(1, ctypes.byref(input_packet), ctypes.sizeof(INPUT))
        if sent != 1:
            raise SafeWindowInputError("SendInput failed")
        with self._lock:
            self._released = False
        print(
            f"[SafeWindowInputBackend] {self._timebase.now():.6f} mouse_move_to ({x},{y}) reason={reason!r}",
            flush=True,
        )
        return True

    def left_click(self, reason: str = "") -> bool:
        self._ensure_target_focused()
        down = INPUT(
            type=INPUT_MOUSE,
            union=INPUT_UNION(
                mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTDOWN, time=0, dwExtraInfo=ctypes.c_void_p(0)),
            ),
        )
        up = INPUT(
            type=INPUT_MOUSE,
            union=INPUT_UNION(
                mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTUP, time=0, dwExtraInfo=ctypes.c_void_p(0)),
            ),
        )
        self._user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
        import random
        import time as _time
        hold_time = 0.045 + random.uniform(-0.015, 0.025)
        _time.sleep(hold_time)
        self._user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
        with self._lock:
            self._released = False
        print(
            "[SafeWindowInputBackend] "
            f"{self._timebase.now():.6f} left_click hold_time={hold_time:.4f}s reason={reason!r}",
            flush=True,
        )
        return True

    def move_cursor(self, screen_x: int, screen_y: int, reason: str = "") -> None:
        self._ensure_target_focused()
        import math
        import random
        import time as _time
        
        point = wintypes.POINT()
        if not self._user32.GetCursorPos(ctypes.byref(point)):
            self._user32.SetCursorPos(screen_x, screen_y)
            return

        start_x, start_y = point.x, point.y
        dist = math.sqrt((screen_x - start_x)**2 + (screen_y - start_y)**2)
        if dist < 5:
            self._user32.SetCursorPos(screen_x, screen_y)
            return

        # Smooth Cubic Bezier trajectory with random control points (biological Minimum Jerk simulation)
        steps = int(max(8, min(25, dist / 15.0)))
        deviation = dist * 0.1
        c1x = start_x + (screen_x - start_x) * 0.25 + random.uniform(-deviation, deviation)
        c1y = start_y + (screen_y - start_y) * 0.25 - dist * 0.05 + random.uniform(-deviation, deviation)
        c2x = start_x + (screen_x - start_x) * 0.75 + random.uniform(-deviation, deviation)
        c2y = start_y + (screen_y - start_y) * 0.75 + dist * 0.05 + random.uniform(-deviation, deviation)

        duration_ms = max(100, min(300, int(dist * 0.8 + random.randint(-20, 20))))
        step_sleep = (duration_ms / 1000.0) / steps

        for i in range(1, steps + 1):
            t = i / steps
            # Cubic Bezier
            x = (1.0 - t)**3 * start_x + 3.0 * (1.0 - t)**2 * t * c1x + 3.0 * (1.0 - t) * t**2 * c2x + t**3 * screen_x
            y = (1.0 - t)**3 * start_y + 3.0 * (1.0 - t)**2 * t * c1y + 3.0 * (1.0 - t) * t**2 * c2y + t**3 * screen_y

            # Biological micro-tremors (1-2px jitter)
            if 0 < i < steps:
                x += random.uniform(-1.2, 1.2)
                y += random.uniform(-1.2, 1.2)

            self._user32.SetCursorPos(round(x), round(y))
            
            # Timing noise
            jittered_sleep = max(0.001, step_sleep * (1.0 + random.uniform(-0.15, 0.15)))
            _time.sleep(jittered_sleep)

        self._user32.SetCursorPos(screen_x, screen_y)
        _time.sleep(0.01)

    def click_at(self, screen_x: int, screen_y: int, reason: str = "") -> None:
        self._ensure_target_focused()
        self.move_cursor(screen_x, screen_y, reason=reason)
        self.left_click(reason=reason)

    def right_click(self, reason: str = "") -> bool:
        self._ensure_target_focused()
        down = INPUT(
            type=INPUT_MOUSE,
            union=INPUT_UNION(
                mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_RIGHTDOWN, time=0, dwExtraInfo=ctypes.c_void_p(0)),
            ),
        )
        up = INPUT(
            type=INPUT_MOUSE,
            union=INPUT_UNION(
                mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_RIGHTUP, time=0, dwExtraInfo=ctypes.c_void_p(0)),
            ),
        )
        self._user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
        import random
        import time as _time
        hold_time = 0.045 + random.uniform(-0.015, 0.025)
        _time.sleep(hold_time)
        self._user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
        with self._lock:
            self._released = False
        return True

    def mouse_scroll(self, delta: int = -1, reason: str = "") -> bool:
        """Scroll mouse wheel. delta=-1 scrolls up (zoom in), delta=1 scrolls down (zoom out)."""
        self._ensure_target_focused()
        inp = INPUT(
            type=INPUT_MOUSE,
            union=INPUT_UNION(
                mi=MOUSEINPUT(dx=0, dy=0, mouseData=delta * WHEEL_DELTA, dwFlags=MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=ctypes.c_void_p(0)),
            ),
        )
        self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        return True

    def hold_click(self, duration_sec: float = 0.5, reason: str = "") -> bool:
        """Hold left mouse button for a duration (charged attacks), with interruptible focus checks."""
        _MAX_HOLD_SEC = 5.0
        if duration_sec > _MAX_HOLD_SEC:
            log.warning("[SafeWindow] hold_click clamped %.1fs → %.1fs", duration_sec, _MAX_HOLD_SEC)
            duration_sec = _MAX_HOLD_SEC
        self._ensure_target_focused()
        down = INPUT(
            type=INPUT_MOUSE,
            union=INPUT_UNION(
                mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTDOWN, time=0, dwExtraInfo=ctypes.c_void_p(0)),
            ),
        )
        self._user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
        with self._lock:
            self._mouse_down = True
        import time as _time
        elapsed = 0.0
        chunk = 0.05
        while elapsed < duration_sec:
            _time.sleep(min(chunk, duration_sec - elapsed))
            elapsed += chunk
            if not self.is_target_focused():
                self._send_mouse_up()
                return False
        self._send_mouse_up()
        with self._lock:
            self._released = False
        return True

    def mouse_drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int = 300,
        button: Literal["left", "right"] = "left",
        reason: str = "",
    ) -> bool:
        """Perform a smooth, biometrical mouse drag from start to end pixel."""
        self._ensure_target_focused()
        self.move_cursor(start_x, start_y, reason=reason)
        import time as _time
        _time.sleep(0.05)

        down_flag = MOUSEEVENTF_RIGHTDOWN if button.lower() == "right" else MOUSEEVENTF_LEFTDOWN
        down_inp = INPUT(
            type=INPUT_MOUSE,
            union=INPUT_UNION(
                mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=down_flag, time=0, dwExtraInfo=ctypes.c_void_p(0)),
            ),
        )
        self._user32.SendInput(1, ctypes.byref(down_inp), ctypes.sizeof(INPUT))
        _time.sleep(0.05)

        # Bezier drag interpolation
        import math
        import random
        dist = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
        steps = int(max(10, duration_ms // 15))
        step_delay = (duration_ms / 1000.0) / steps

        deviation = dist * 0.05
        c1x = start_x + (end_x - start_x) * 0.25 + random.uniform(-deviation, deviation)
        c1y = start_y + (end_y - start_y) * 0.25 + random.uniform(-deviation, deviation)
        c2x = start_x + (end_x - start_x) * 0.75 + random.uniform(-deviation, deviation)
        c2y = start_y + (end_y - start_y) * 0.75 + random.uniform(-deviation, deviation)

        for i in range(1, steps + 1):
            t = i / steps
            x = (1.0 - t)**3 * start_x + 3.0 * (1.0 - t)**2 * t * c1x + 3.0 * (1.0 - t) * t**2 * c2x + t**3 * end_x
            y = (1.0 - t)**3 * start_y + 3.0 * (1.0 - t)**2 * t * c1y + 3.0 * (1.0 - t) * t**2 * c2y + t**3 * end_y

            if 0 < i < steps:
                x += random.uniform(-0.8, 0.8)
                y += random.uniform(-0.8, 0.8)

            self._user32.SetCursorPos(round(x), round(y))
            _time.sleep(max(0.001, step_delay * (1.0 + random.uniform(-0.1, 0.1))))

        _time.sleep(0.05)
        up_flag = MOUSEEVENTF_RIGHTUP if button.lower() == "right" else MOUSEEVENTF_LEFTUP
        up_inp = INPUT(
            type=INPUT_MOUSE,
            union=INPUT_UNION(
                mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=up_flag, time=0, dwExtraInfo=ctypes.c_void_p(0)),
            ),
        )
        self._user32.SendInput(1, ctypes.byref(up_inp), ctypes.sizeof(INPUT))
        with self._lock:
            self._released = False
        return True

    def mouse_relative_drag(
        self,
        dx: int,
        dy: int,
        duration_ms: int = 150,
        button: Literal["left", "right", "middle"] = "right",
        reason: str = "",
    ) -> bool:
        """Hold down mouse button, relative move step-by-step, and release."""
        self._ensure_target_focused()
        import time as _time
        down_flag = MOUSEEVENTF_RIGHTDOWN if button.lower() == "right" else MOUSEEVENTF_LEFTDOWN
        down_inp = INPUT(
            type=INPUT_MOUSE,
            union=INPUT_UNION(
                mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=down_flag, time=0, dwExtraInfo=ctypes.c_void_p(0)),
            ),
        )
        self._user32.SendInput(1, ctypes.byref(down_inp), ctypes.sizeof(INPUT))
        _time.sleep(0.02)

        steps = int(max(4, duration_ms // 15))
        step_dx = int(round(dx / steps))
        step_dy = int(round(dy / steps))
        step_delay = (duration_ms / 1000.0) / steps

        for _ in range(steps):
            move_inp = INPUT(
                type=INPUT_MOUSE,
                union=INPUT_UNION(
                    mi=MOUSEINPUT(dx=step_dx, dy=step_dy, mouseData=0, dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=ctypes.c_void_p(0)),
                ),
            )
            self._user32.SendInput(1, ctypes.byref(move_inp), ctypes.sizeof(INPUT))
            _time.sleep(step_delay)

        up_flag = MOUSEEVENTF_RIGHTUP if button.lower() == "right" else MOUSEEVENTF_LEFTUP
        up_inp = INPUT(
            type=INPUT_MOUSE,
            union=INPUT_UNION(
                mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=up_flag, time=0, dwExtraInfo=ctypes.c_void_p(0)),
            ),
        )
        self._user32.SendInput(1, ctypes.byref(up_inp), ctypes.sizeof(INPUT))
        with self._lock:
            self._released = False
        return True

    def mouse_double_click(
        self,
        x: int,
        y: int,
        button: Literal["left", "right"] = "left",
        reason: str = "",
    ) -> bool:
        """Perform a human-calibrated double click at pixel coordinate (x, y)."""
        self._ensure_target_focused()
        self.move_cursor(x, y, reason=reason)
        import time as _time
        import random
        self.left_click(reason=f"{reason}_click1")
        _time.sleep(0.07 + random.uniform(-0.01, 0.03))
        self.left_click(reason=f"{reason}_click2")
        return True

    def key_down(self, key: str, reason: str = "") -> bool:
        self._ensure_target_focused()
        vk = self._resolve_vk(key)
        scan = self._resolve_scan(key)
        flags = KEYEVENTF_SCANCODE
        if key.lower() in _EXTENDED_KEYS:
            flags |= KEYEVENTF_EXTENDEDKEY
        input_packet = INPUT(
            type=INPUT_KEYBOARD,
            union=INPUT_UNION(
                ki=KEYBDINPUT(
                    wVk=0,
                    wScan=scan,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=ctypes.c_void_p(0),
                )
            ),
        )
        sent = self._user32.SendInput(1, ctypes.byref(input_packet), ctypes.sizeof(INPUT))
        if sent != 1:
            raise SafeWindowInputError(f"SendInput key_down failed for key={key!r}")
        self._released = False
        with self._lock:
            self._down_keys.add(key)
        print(
            "[SafeWindowInputBackend] "
            f"{self._timebase.now():.6f} key_down key={key!r} vk=0x{vk:02X} scan=0x{scan:02X} reason={reason!r}",
            flush=True,
        )
        return True

    def key_up(self, key: str, reason: str = "") -> bool:
        self._ensure_target_focused()
        vk = self._resolve_vk(key)
        scan = self._resolve_scan(key)
        flags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
        if key.lower() in _EXTENDED_KEYS:
            flags |= KEYEVENTF_EXTENDEDKEY
        input_packet = INPUT(
            type=INPUT_KEYBOARD,
            union=INPUT_UNION(
                ki=KEYBDINPUT(
                    wVk=0,
                    wScan=scan,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=ctypes.c_void_p(0),
                )
            ),
        )
        sent = self._user32.SendInput(1, ctypes.byref(input_packet), ctypes.sizeof(INPUT))
        if sent != 1:
            raise SafeWindowInputError(f"SendInput key_up failed for key={key!r}")
        with self._lock:
            self._down_keys.discard(key)
        print(
            "[SafeWindowInputBackend] "
            f"{self._timebase.now():.6f} key_up key={key!r} vk=0x{vk:02X} scan=0x{scan:02X} reason={reason!r}",
            flush=True,
        )
        return True

    @staticmethod
    def _resolve_vk(key: str) -> int:
        vk = _VK_MAP.get(key.lower())
        if vk is not None:
            return vk
        if len(key) == 1:
            return ord(key.upper())
        raise SafeWindowInputError(f"unknown key: {key!r}")

    @staticmethod
    def _resolve_scan(key: str) -> int:
        scan = _SCAN_MAP.get(key.lower())
        if scan is not None:
            return scan
        # For unknown keys, MapVirtualKey gives the scan code from VK code
        vk = SafeWindowInputBackend._resolve_vk(key)
        scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
        if scan:
            return scan
        raise SafeWindowInputError(f"no scan code for key: {key!r}")

    def release_all(self, reason: str = "") -> int:
        with self._lock:
            snapshot = sorted(self._down_keys)
            self._down_keys.clear()
            mouse_was_down = self._mouse_down
            self._mouse_down = False
            self._released = True
        for key in snapshot:
            scan = self._resolve_scan(key)
            flags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
            if key.lower() in _EXTENDED_KEYS:
                flags |= KEYEVENTF_EXTENDEDKEY
            input_packet = INPUT(
                type=INPUT_KEYBOARD,
                union=INPUT_UNION(
                    ki=KEYBDINPUT(
                        wVk=0,
                        wScan=scan,
                        dwFlags=flags,
                        time=0,
                        dwExtraInfo=ctypes.c_void_p(0),
                    )
                ),
            )
            self._user32.SendInput(1, ctypes.byref(input_packet), ctypes.sizeof(INPUT))
        if mouse_was_down:
            self._send_mouse_up()
        print(
            "[SafeWindowInputBackend] "
            f"{self._timebase.now():.6f} release_all keys={snapshot} mouse={mouse_was_down} reason={reason!r}",
            flush=True,
        )
        return len(snapshot)

    def execute_combo(self, keys: list[str], hold_time_ms: int = 100, reason: str = "") -> bool:
        self._ensure_target_focused()
        import time as _time
        pressed_keys = []
        try:
            for key in keys:
                self.key_down(key, reason=f"{reason}_combo_down")
                pressed_keys.append(key)
                _time.sleep(0.015)
            _time.sleep(hold_time_ms / 1000.0)
        finally:
            for key in reversed(pressed_keys):
                self.key_up(key, reason=f"{reason}_combo_up")
                _time.sleep(0.01)
        return len(pressed_keys) == len(keys)

    def type_text(self, text: str, delay_between_keys_ms: int = 50, reason: str = "") -> bool:
        self._ensure_target_focused()
        import time as _time
        import random
        
        symbol_shift_map = {
            "!": "1", "@": "2", "#": "3", "$": "4", "%": "5",
            "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
            "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\",
            ":": ";", '"': "'", "<": ",", ">": ".", "?": "/"
        }
        
        for char in text:
            is_upper = char.isupper()
            is_shifted_symbol = char in symbol_shift_map
            
            key_to_press = char.lower()
            if is_shifted_symbol:
                key_to_press = symbol_shift_map[char]
                
            keys = []
            if is_upper or is_shifted_symbol:
                keys.append("shift")
            keys.append(key_to_press)
            
            self.execute_combo(keys, hold_time_ms=30, reason=f"type_{char}")
            
            jitter = random.uniform(-10.0, 15.0)
            _time.sleep(max(0.01, (delay_between_keys_ms + jitter) / 1000.0))
            
        return True

    def _send_mouse_up(self) -> None:
        """Send MOUSEEVENTF_LEFTUP to release a held mouse button."""
        up = INPUT(
            type=INPUT_MOUSE,
            union=INPUT_UNION(
                mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTUP, time=0, dwExtraInfo=ctypes.c_void_p(0)),
            ),
        )
        self._user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
        with self._lock:
            self._mouse_down = False

        hwnd = self._find_target_window()
        rect = wintypes.RECT()
        if not self._user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise SafeWindowInputError("GetWindowRect failed")
        return WindowRect(rect.left, rect.top, rect.right, rect.bottom)

    def client_rect(self) -> WindowRect:
        hwnd = self._find_target_window()
        rect = wintypes.RECT()
        if not self._user32.GetClientRect(hwnd, ctypes.byref(rect)):
            raise SafeWindowInputError("GetClientRect failed")
        top_left = wintypes.POINT(rect.left, rect.top)
        bottom_right = wintypes.POINT(rect.right, rect.bottom)
        if not self._user32.ClientToScreen(hwnd, ctypes.byref(top_left)):
            raise SafeWindowInputError("ClientToScreen top-left failed")
        if not self._user32.ClientToScreen(hwnd, ctypes.byref(bottom_right)):
            raise SafeWindowInputError("ClientToScreen bottom-right failed")
        return WindowRect(top_left.x, top_left.y, bottom_right.x, bottom_right.y)

    def focus_target_window(self) -> None:
        hwnd = self._find_target_window()
        self._force_foreground(hwnd)

    def is_target_focused(self) -> bool:
        try:
            hwnd = self._find_target_window()
        except SafeWindowInputError:
            return False
        return self._user32.GetForegroundWindow() == hwnd

    def _ensure_target_focused(self) -> None:
        if not self.is_target_focused():
            # Cooldown: do not spam focus attempts. This prevents the positive
            # feedback trap where every failed attempt triggers another attempt.
            now = self._timebase.now()
            with self._lock:
                elapsed = now - self._last_focus_attempt
                if elapsed < self._focus_cooldown_sec:
                    self._released = True
                    raise SafeWindowInputError(
                        f"focus cooldown active, last attempt {elapsed:.1f}s ago"
                    )
                self._last_focus_attempt = now

            try:
                hwnd = self._find_target_window()
                self._force_foreground(hwnd)
            except SafeWindowInputError:
                raise
            except Exception as exc:
                log.warning("focus attempt failed: %s", exc)
            import time
            time.sleep(0.1)
            if not self.is_target_focused():
                with self._lock:
                    self._released = True
                raise SafeWindowInputError(
                    f"target window is not focused: {self.target_window_title!r}"
                )

    def _force_foreground(self, hwnd: int) -> None:
        """Bring target window to foreground with throttle to prevent oscillation.

        Throttle rules (prevents focus feedback loop):
        - ALT key trick: once per FOCUS_COOLDOWN_SEC, not on every call
        - Layer 1-4 approach: still used but gated by cooldown
        """
        import ctypes
        import time as _time

        user32 = self._user32
        kernel32 = ctypes.windll.kernel32

        if user32.GetForegroundWindow() == hwnd:
            return

        user32.ShowWindow(hwnd, 9)  # SW_RESTORE

        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        HWND_TOPMOST = ctypes.c_void_p(-1)
        HWND_NOTOPMOST = ctypes.c_void_p(-2)

        # Throttled ALT key trick — only once per cooldown window.
        # Un-throttled, this resets the fg lock timer on every call, which is
        # the root cause of the oscillation feedback loop.
        now = self._timebase.now()
        do_alt_trick = (now - self._last_focus_attempt) >= self._focus_cooldown_sec
        if do_alt_trick:
            user32.keybd_event(0x12, 0, 0, 0)   # VK_MENU down
            user32.keybd_event(0x12, 0, 2, 0)   # VK_MENU up
            _time.sleep(0.05)

        fg_hwnd = user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
        cur_tid = kernel32.GetCurrentThreadId()

        try:
            user32.AllowSetForegroundWindow(0xFFFFFFFF)
        except AttributeError:
            pass

        attached = False
        try:
            attached = user32.AttachThreadInput(cur_tid, fg_tid, True)
        except Exception:
            pass

        try:
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
            _time.sleep(0.01)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
        finally:
            if attached:
                try:
                    user32.AttachThreadInput(cur_tid, fg_tid, False)
                except Exception:
                    pass

        for attempt in range(3):
            if user32.GetForegroundWindow() == hwnd:
                return
            _time.sleep(0.1)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)

        fg_after = user32.GetForegroundWindow()
        if fg_after != hwnd:
            log.warning(
                "[SafeWindowInputBackend] _force_foreground failed "
                "(fg=%s, target=%s)", fg_after, hwnd,
            )

        fg_after = user32.GetForegroundWindow()
        if fg_after != hwnd:
            log.warning(
                "[SafeWindowInputBackend] _force_foreground failed after all attempts "
                "(fg=%s, target=%s)", fg_after, hwnd,
            )

    def _find_target_window(self) -> int:
        hwnd = self._user32.FindWindowW(None, self.target_window_title)
        if hwnd:
            return hwnd
        for alt_title in self.alt_window_titles:
            hwnd = self._user32.FindWindowW(None, alt_title)
            if hwnd:
                return hwnd
        tried = [self.target_window_title] + self.alt_window_titles
        raise SafeWindowInputError(f"target window not found: tried {tried!r}")

    def _configure_win32(self) -> None:
        self._user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        self._user32.FindWindowW.restype = wintypes.HWND
        self._user32.GetForegroundWindow.argtypes = []
        self._user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self._user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self._user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self._user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        self._user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        self._user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        self._user32.SendInput.restype = wintypes.UINT
