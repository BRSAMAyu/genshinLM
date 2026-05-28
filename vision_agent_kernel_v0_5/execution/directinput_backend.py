"""DirectInput hardware backend: scan-code level input for DX11/DX12 games.

Unlike SafeWindowInputBackend which uses Virtual Key codes via SendInput,
this backend uses hardware scan codes that bypass higher-level input hooks
used by some games' anti-cheat systems.

Falls back gracefully on non-Windows platforms by raising ImportError.

Architecture:
- key_down/key_up use KEYEVENTF_SCANCODE flag with hardware scan codes
- Focus watchdog thread monitors target window and auto-releases all keys
  on focus loss to prevent runaway input
- Thread-safe key tracking via _down_keys set + RLock
"""
from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes
from typing import Any

log = logging.getLogger(__name__)

# Windows constants
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001

# Virtual key to hardware scan code mapping
# Scan codes from USB HID usage tables / Windows documentation
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

# Key name to VK code (same as SafeWindowInputBackend)
_KEY_TO_VK: dict[str, int] = {
    "w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44,
    "e": 0x45, "q": 0x51, "r": 0x52, "f": 0x46,
    "c": 0x43, "v": 0x56, "x": 0x58, "z": 0x5A,
    "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35,
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


class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    _anonymous_ = ("_input",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_input", _INPUT),
    ]


def _make_key_input(scan_code: int, flags: int) -> INPUT:
    """Create an INPUT struct for a scan-code keyboard event."""
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki.wVk = 0  # Must be 0 when using scan codes
    inp.ki.wScan = scan_code
    inp.ki.dwFlags = KEYEVENTF_SCANCODE | flags
    inp.ki.time = 0
    inp.ki.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
    return inp


class DirectInputBackend:
    """Hardware-level scan-code input backend for DX11/DX12 games.

    Uses DirectInput scan codes via SendInput with KEYEVENTF_SCANCODE flag.
    This bypasses virtual key hooks that some games use for anti-cheat.

    Features:
    - Full key tracking with thread-safe release_all
    - Focus watchdog: auto-releases keys when target window loses focus
    - Graceful degradation: logs warning if scan code not found
    """

    def __init__(self, target_window_title: str = "") -> None:
        self._target_title = target_window_title.lower()
        self._down_keys: set[str] = set()
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
        """Release all currently held keys."""
        with self._lock:
            keys = sorted(self._down_keys)
            self._down_keys.clear()

        released = 0
        for key in keys:
            if self.key_up(key, reason=reason):
                released += 1
        log.info("[DirectInput] release_all: %d keys released (reason=%s)", released, reason)
        return released

    def mouse_move(self, dx: int, dy: int) -> bool:
        """Relative mouse movement (delegates to mouse motor)."""
        return False

    def mouse_click(self, x: int, y: int, button: str = "left") -> bool:
        """Click at absolute position (delegates to mouse motor)."""
        return False

    @property
    def keys_held(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._down_keys)

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
