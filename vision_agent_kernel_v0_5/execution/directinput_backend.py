"""DirectInput hardware backend: scan-code level input for DX11/DX12 games.

This backend uses hardware scan codes that bypass higher-level virtual key hooks
used by some games' anti-cheat systems. Supports all next-generation human-like
computer use behaviors.
"""
from __future__ import annotations

import ctypes
import logging
import random
import threading
import time
from ctypes import wintypes
from typing import Literal

log = logging.getLogger(__name__)

# Windows constants
INPUT_KEYBOARD = 1
INPUT_MOUSE = 0
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001

# Mouse constants
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
WHEEL_DELTA = 120

# Virtual key to hardware scan code mapping (fully expanded whitelist)
_VK_TO_SCAN: dict[int, int] = {
    0x57: 0x11,  # W
    0x41: 0x1E,  # A
    0x53: 0x1F,  # S
    0x44: 0x20,  # D
    0x45: 0x12,  # E
    0x51: 0x10,  # Q
    0x52: 0x13,  # R
    0x46: 0x21,  # F
    0x43: 0x2E,  # C
    0x56: 0x2F,  # V
    0x58: 0x2D,  # X
    0x5A: 0x2C,  # Z
    0x31: 0x02,  # 1
    0x32: 0x03,  # 2
    0x33: 0x04,  # 3
    0x34: 0x05,  # 4
    0x35: 0x06,  # 5
    0x36: 0x07,  # 6
    0x37: 0x08,  # 7
    0x38: 0x09,  # 8
    0x39: 0x0A,  # 9
    0x30: 0x0B,  # 0
    0x49: 0x17,  # I (Inventory)
    0x42: 0x30,  # B (Bag)
    0x4A: 0x24,  # J (Quest Log)
    0x4D: 0x32,  # M (Map)
    0x50: 0x19,  # P (Paimon Menu)
    0x59: 0x15,  # Y (Coop Accept/Yes)
    0x55: 0x16,  # U (Domain)
    0x47: 0x22,  # G (Tutorial Archive)
    0x70: 0x3B,  # F1
    0x71: 0x3C,  # F2
    0x72: 0x3D,  # F3
    0x73: 0x3E,  # F4
    0x74: 0x3F,  # F5
    0x20: 0x39,  # Space
    0x10: 0x2A,  # Shift
    0x11: 0x1D,  # Ctrl
    0x12: 0x38,  # Alt
    0x09: 0x0F,  # Tab
    0x0D: 0x1C,  # Enter
    0x1B: 0x01,  # Escape
    0x25: 0x4B,  # Left (extended)
    0x26: 0x48,  # Up (extended)
    0x27: 0x4D,  # Right (extended)
    0x28: 0x50,  # Down (extended)
}

# Key name to VK code (fully expanded whitelist)
_KEY_TO_VK: dict[str, int] = {
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

# Extended keys that need KEYEVENTF_EXTENDEDKEY
_EXTENDED_KEYS = {0x25, 0x26, 0x27, 0x28}  # arrow keys


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    _anonymous_ = ("_input",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_input", _INPUT),
    ]


def _make_key_input(scan_code: int, flags: int) -> INPUT:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki.wVk = 0  # Must be 0 when using scan codes
    inp.ki.wScan = scan_code
    inp.ki.dwFlags = KEYEVENTF_SCANCODE | flags
    inp.ki.time = 0
    inp.ki.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
    return inp


def _make_mouse_input(dx: int, dy: int, flags: int, data: int = 0) -> INPUT:
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.mi.dx = dx
    inp.mi.dy = dy
    inp.mi.mouseData = data
    inp.mi.dwFlags = flags
    inp.mi.time = 0
    inp.mi.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
    return inp


class DirectInputBackend:
    """Hardware-level scan-code input backend for DX11/DX12 games.

    Uses DirectInput scan codes via SendInput with KEYEVENTF_SCANCODE flag.
    This bypasses virtual key hooks that some games use for anti-cheat.
    """

    def __init__(self, target_window_title: str = "", pixels_per_degree: float = 8.0) -> None:
        self._target_title = target_window_title.lower()
        self.pixels_per_degree = pixels_per_degree
        self._down_keys: set[str] = set()
        self._mouse_down = False
        self._lock = threading.RLock()
        self._running = True

        # Focus watchdog
        self._watchdog = threading.Thread(
            target=self._focus_watchdog_loop,
            daemon=True,
            name="directinput-focus-watchdog",
        )
        self._watchdog.start()

    def key_down(self, key: str, reason: str = "") -> bool:
        """Press a key using hardware scan code."""
        vk = _KEY_TO_VK.get(key.lower())
        if vk is None:
            log.warning("[DirectInput] Unknown key: %s", key)
            return False

        scan = _VK_TO_SCAN.get(vk)
        if scan is None:
            log.warning("[DirectInput] No scan code for key: %s (vk=0x%02X)", key, vk)
            return False

        flags = KEYEVENTF_SCANCODE
        if vk in _EXTENDED_KEYS:
            flags |= KEYEVENTF_EXTENDEDKEY

        inp = _make_key_input(scan, flags)
        result = ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

        if result == 1:
            with self._lock:
                self._down_keys.add(key.lower())
            return True
        else:
            log.warning("[DirectInput] SendInput failed for key %s (scan=0x%02X)", key, scan)
            return False

    def key_up(self, key: str, reason: str = "") -> bool:
        """Release a key using hardware scan code."""
        vk = _KEY_TO_VK.get(key.lower())
        if vk is None:
            return False

        scan = _VK_TO_SCAN.get(vk)
        if scan is None:
            return False

        flags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
        if vk in _EXTENDED_KEYS:
            flags |= KEYEVENTF_EXTENDEDKEY

        inp = _make_key_input(scan, flags)
        result = ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

        with self._lock:
            self._down_keys.discard(key.lower())
        return result == 1

    def release_all(self, reason: str = "release_all") -> int:
        """Release all currently held keys and mouse buttons."""
        with self._lock:
            keys = sorted(self._down_keys)
            self._down_keys.clear()
            mouse_was_down = self._mouse_down
            self._mouse_down = False

        released = 0
        for key in keys:
            if self.key_up(key, reason=reason):
                released += 1
        if mouse_was_down:
            self._send_mouse_up()
        log.info("[DirectInput] release_all: %d keys released (reason=%s)", released, reason)
        return released

    # --- Mouse Actions ---

    def mouse_move(self, dx: float, dy: float, reason: str = "") -> bool:
        """Relative mouse movement (used for continuous 3D camera servoing)."""
        pixel_dx = int(round(dx * self.pixels_per_degree))
        pixel_dy = int(round(dy * self.pixels_per_degree))
        flags = MOUSEEVENTF_MOVE
        inp = _make_mouse_input(pixel_dx, pixel_dy, flags)
        result = ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        return result == 1

    def mouse_move_to(self, x: int, y: int, reason: str = "") -> bool:
        """Move mouse cursor instantly to absolute coordinate (x, y)."""
        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)
        if screen_w <= 0 or screen_h <= 0:
            return False
            
        norm_x = int((x / screen_w) * 65535)
        norm_y = int((y / screen_h) * 65535)
        
        move_inp = _make_mouse_input(norm_x, norm_y, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
        result = ctypes.windll.user32.SendInput(1, ctypes.byref(move_inp), ctypes.sizeof(INPUT))
        return result == 1

    def left_click(self, reason: str = "") -> bool:
        """Perform left click with natural timing hold."""
        down_inp = _make_mouse_input(0, 0, MOUSEEVENTF_LEFTDOWN)
        up_inp = _make_mouse_input(0, 0, MOUSEEVENTF_LEFTUP)
        
        ctypes.windll.user32.SendInput(1, ctypes.byref(down_inp), ctypes.sizeof(INPUT))
        hold_time = 0.045 + random.uniform(-0.015, 0.025)
        time.sleep(hold_time)
        ctypes.windll.user32.SendInput(1, ctypes.byref(up_inp), ctypes.sizeof(INPUT))
        return True

    def right_click(self, reason: str = "") -> bool:
        """Perform right click with natural timing hold."""
        down_inp = _make_mouse_input(0, 0, MOUSEEVENTF_RIGHTDOWN)
        up_inp = _make_mouse_input(0, 0, MOUSEEVENTF_RIGHTUP)
        
        ctypes.windll.user32.SendInput(1, ctypes.byref(down_inp), ctypes.sizeof(INPUT))
        hold_time = 0.045 + random.uniform(-0.015, 0.025)
        time.sleep(hold_time)
        ctypes.windll.user32.SendInput(1, ctypes.byref(up_inp), ctypes.sizeof(INPUT))
        return True

    def mouse_scroll(self, delta: int = -1, reason: str = "") -> bool:
        """Scroll mouse wheel. delta=-1 scrolls up (in), delta=1 scrolls down (out)."""
        inp = _make_mouse_input(0, 0, MOUSEEVENTF_WHEEL, delta * WHEEL_DELTA)
        result = ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        return result == 1

    def hold_click(self, duration_sec: float = 0.5, reason: str = "") -> bool:
        """Hold left mouse button down for a duration (charged attacks)."""
        down_inp = _make_mouse_input(0, 0, MOUSEEVENTF_LEFTDOWN)
        ctypes.windll.user32.SendInput(1, ctypes.byref(down_inp), ctypes.sizeof(INPUT))
        with self._lock:
            self._mouse_down = True
            
        elapsed = 0.0
        chunk = 0.05
        while elapsed < duration_sec:
            time.sleep(min(chunk, duration_sec - elapsed))
            elapsed += chunk
            if self._target_title:
                fg = ctypes.windll.user32.GetForegroundWindow()
                if fg:
                    buff = ctypes.create_unicode_buffer(256)
                    ctypes.windll.user32.GetWindowTextW(fg, buff, 256)
                    if self._target_title not in buff.value.lower():
                        self._send_mouse_up()
                        return False
                        
        self._send_mouse_up()
        return True

    # --- Next-Gen Computer Use Advanced Actions ---

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
        """Smoothly click, drag along a Cubic Bezier curve, and release."""
        self.mouse_move_to(start_x, start_y, reason=reason)
        time.sleep(0.05)

        down_flag = MOUSEEVENTF_RIGHTDOWN if button.lower() == "right" else MOUSEEVENTF_LEFTDOWN
        down_inp = _make_mouse_input(0, 0, down_flag)
        ctypes.windll.user32.SendInput(1, ctypes.byref(down_inp), ctypes.sizeof(INPUT))
        time.sleep(0.05)

        # Bezier interpolation
        import math
        dist = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
        steps = int(max(10, duration_ms // 15))
        step_delay = (duration_ms / 1000.0) / steps
        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)

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

            norm_x = int((x / screen_w) * 65535)
            norm_y = int((y / screen_h) * 65535)
            move_step = _make_mouse_input(norm_x, norm_y, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
            ctypes.windll.user32.SendInput(1, ctypes.byref(move_step), ctypes.sizeof(INPUT))
            time.sleep(max(0.001, step_delay * (1.0 + random.uniform(-0.1, 0.1))))

        time.sleep(0.05)
        up_flag = MOUSEEVENTF_RIGHTUP if button.lower() == "right" else MOUSEEVENTF_LEFTUP
        up_inp = _make_mouse_input(0, 0, up_flag)
        ctypes.windll.user32.SendInput(1, ctypes.byref(up_inp), ctypes.sizeof(INPUT))
        return True

    def mouse_relative_drag(
        self,
        dx: int,
        dy: int,
        duration_ms: int = 150,
        button: Literal["left", "right", "middle"] = "right",
        reason: str = "",
    ) -> bool:
        """relative drag continuous camera pan under button pressed down."""
        down_flag = MOUSEEVENTF_RIGHTDOWN if button.lower() == "right" else MOUSEEVENTF_LEFTDOWN
        down_inp = _make_mouse_input(0, 0, down_flag)
        ctypes.windll.user32.SendInput(1, ctypes.byref(down_inp), ctypes.sizeof(INPUT))
        time.sleep(0.02)

        steps = int(max(4, duration_ms // 15))
        step_dx = int(round(dx / steps))
        step_dy = int(round(dy / steps))
        step_delay = (duration_ms / 1000.0) / steps

        for _ in range(steps):
            move_inp = _make_mouse_input(step_dx, step_dy, MOUSEEVENTF_MOVE)
            ctypes.windll.user32.SendInput(1, ctypes.byref(move_inp), ctypes.sizeof(INPUT))
            time.sleep(step_delay)

        up_flag = MOUSEEVENTF_RIGHTUP if button.lower() == "right" else MOUSEEVENTF_LEFTUP
        up_inp = _make_mouse_input(0, 0, up_flag)
        ctypes.windll.user32.SendInput(1, ctypes.byref(up_inp), ctypes.sizeof(INPUT))
        return True

    def mouse_double_click(
        self,
        x: int,
        y: int,
        button: Literal["left", "right"] = "left",
        reason: str = "",
    ) -> bool:
        """Smoothly move to coordinates and issue two clicks separated by natural timing delay."""
        self.mouse_move_to(x, y, reason=reason)
        time.sleep(0.05)
        self.left_click(reason=f"{reason}_click1")
        time.sleep(0.08 + random.uniform(-0.015, 0.025))
        self.left_click(reason=f"{reason}_click2")
        return True

    # --- Advanced Keyboard Additions ---

    def execute_combo(self, keys: list[str], hold_time_ms: int = 100, reason: str = "") -> bool:
        """Hold keys concurrently, and release in strict reverse sequence."""
        pressed_vk: list[int] = []
        try:
            for key in keys:
                vk = _KEY_TO_VK.get(key.lower())
                if vk is None:
                    continue
                scan = _VK_TO_SCAN.get(vk)
                if scan is None:
                    continue
                flags = KEYEVENTF_SCANCODE
                if vk in _EXTENDED_KEYS:
                    flags |= KEYEVENTF_EXTENDEDKEY
                inp = _make_key_input(scan, flags)
                ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
                pressed_vk.append(vk)
                time.sleep(0.015)
                
            time.sleep(hold_time_ms / 1000.0)
        finally:
            for vk in reversed(pressed_vk):
                scan = _VK_TO_SCAN.get(vk)
                flags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
                if vk in _EXTENDED_KEYS:
                    flags |= KEYEVENTF_EXTENDEDKEY
                inp = _make_key_input(scan, flags)
                ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
                time.sleep(0.01)
        return len(pressed_vk) == len(keys)

    def type_text(self, text: str, delay_between_keys_ms: int = 50, reason: str = "") -> bool:
        """Simulate keyboard typing by emitting key sequence with shift handling."""
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
            time.sleep(max(0.01, (delay_between_keys_ms + random.uniform(-10.0, 15.0)) / 1000.0))
        return True

    def _send_mouse_up(self) -> None:
        up_inp = _make_mouse_input(0, 0, MOUSEEVENTF_LEFTUP)
        ctypes.windll.user32.SendInput(1, ctypes.byref(up_inp), ctypes.sizeof(INPUT))
        with self._lock:
            self._mouse_down = False

    @property
    def keys_held(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._down_keys)

    def is_target_focused(self) -> bool:
        if not self._target_title:
            return True
        fg = ctypes.windll.user32.GetForegroundWindow()
        if fg:
            buff = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(fg, buff, 256)
            return self._target_title in buff.value.lower()
        return False

    def close(self) -> None:
        """Stop the watchdog and release all keys."""
        self._running = False
        self.release_all(reason="shutdown")

    def _focus_watchdog_loop(self) -> None:
        """Monitor target window focus and release keys on focus loss."""
        while self._running:
            try:
                if self._target_title and self._down_keys:
                    fg = ctypes.windll.user32.GetForegroundWindow()
                    if fg:
                        length = 256
                        buff = ctypes.create_unicode_buffer(length)
                        ctypes.windll.user32.GetWindowTextW(fg, buff, length)
                        title = buff.value.lower()
                        if self._target_title not in title:
                            log.warning(
                                "[DirectInput] Focus lost (active=%r, target=%r), releasing keys",
                                title, self._target_title,
                            )
                            self.release_all(reason="focus_lost")
                time.sleep(0.05)  # 20 Hz check
            except Exception as exc:
                log.error("[DirectInput] Watchdog error: %s", exc)
                time.sleep(0.5)
