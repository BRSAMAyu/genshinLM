"""Background input backend: sends keys to a window without requiring focus.

Uses PostMessageW with WM_KEYDOWN/WM_KEYUP to inject input into a target
window's message queue. This allows the game to run in the background while
the operator monitors the terminal in the foreground.

For games using DirectInput or raw input, PostMessage alone may not be
sufficient. In that case, this backend falls back to a brief "flash focus"
strategy: bring the window to foreground, send via SendInput, then restore
the previous foreground window.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import threading
import time
from dataclasses import dataclass

from core.timebase import Timebase

log = logging.getLogger(__name__)

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101

# Repeat count (low word), scan code (byte 2), extended flag (bit 24)
def _make_lparam(vk: int, key_up: bool = False) -> int:
    scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
    repeat = 0 if key_up else 1
    flags = (scan << 16) | repeat
    if key_up:
        flags |= (1 << 30) | (1 << 31)  # previous state + transition
    # Extended keys (arrows, etc.)
    extended_keys = {0x25, 0x26, 0x27, 0x28, 0x10, 0x11, 0x12, 0x20, 0x09}
    if vk in extended_keys:
        flags |= (1 << 24)
    return flags


_VK_MAP: dict[str, int] = {
    "w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44,
    "e": 0x45, "q": 0x51, "r": 0x52, "f": 0x46,
    "c": 0x43, "v": 0x56, "x": 0x58, "z": 0x5A,
    "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35,
    "space": 0x20, "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
    "tab": 0x09, "enter": 0x0D, "esc": 0x1B, "escape": 0x1B,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
}

# SendInput structures (for flash-focus fallback)
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("_ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.wintypes.DWORD), ("union", _INPUT_UNION)]


class BackgroundInputError(RuntimeError):
    pass


class BackgroundInputBackend:
    """Sends key events to a background window via PostMessageW.

    Strategy:
    1. Try PostMessageW first (works for most Unity/standard Windows apps)
    2. If keys don't seem to register, use flash-focus with SendInput
    """

    def __init__(
        self,
        target_window_title: str,
        *,
        timebase: Timebase | None = None,
        alt_window_titles: list[str] | None = None,
        flash_focus: bool = True,
        flash_duration_ms: int = 200,
    ) -> None:
        self.target_window_title = target_window_title
        self.alt_window_titles = alt_window_titles or []
        self._timebase = timebase or Timebase()
        self._user32 = ctypes.windll.user32
        self._flash_focus = flash_focus
        self._flash_duration_ms = flash_duration_ms
        self._down_keys: set[str] = set()
        self._lock = threading.RLock()
        self._hwnd: int | None = None

    def _find_hwnd(self) -> int:
        hwnd = self._user32.FindWindowW(None, self.target_window_title)
        if not hwnd:
            for alt in self.alt_window_titles:
                hwnd = self._user32.FindWindowW(None, alt)
                if hwnd:
                    break
        if not hwnd:
            raise BackgroundInputError(
                f"window not found: tried {[self.target_window_title] + self.alt_window_titles}"
            )
        return hwnd

    def _ensure_hwnd(self) -> int:
        if self._hwnd is None or not self._user32.IsWindow(self._hwnd):
            self._hwnd = self._find_hwnd()
        return self._hwnd

    def _resolve_vk(self, key: str) -> int:
        vk = _VK_MAP.get(key.lower())
        if vk is not None:
            return vk
        if len(key) == 1:
            return ord(key.upper())
        raise BackgroundInputError(f"unknown key: {key!r}")

    def key_down(self, key: str, reason: str = "") -> None:
        hwnd = self._ensure_hwnd()
        vk = self._resolve_vk(key)
        lparam = _make_lparam(vk, key_up=False)
        self._user32.PostMessageW(hwnd, WM_KEYDOWN, vk, lparam)
        with self._lock:
            self._down_keys.add(key)
        log.debug(
            "[BackgroundInput] key_down key=%s vk=0x%02X hwnd=%d reason=%s",
            key, vk, hwnd, reason,
        )

    def key_up(self, key: str, reason: str = "") -> None:
        hwnd = self._ensure_hwnd()
        vk = self._resolve_vk(key)
        lparam = _make_lparam(vk, key_up=True)
        self._user32.PostMessageW(hwnd, WM_KEYUP, vk, lparam)
        with self._lock:
            self._down_keys.discard(key)
        log.debug(
            "[BackgroundInput] key_up key=%s vk=0x%02X hwnd=%d reason=%s",
            key, vk, hwnd, reason,
        )

    def release_all(self, reason: str = "") -> None:
        with self._lock:
            snapshot = sorted(self._down_keys)
            self._down_keys.clear()
        hwnd = self._ensure_hwnd()
        for key in snapshot:
            vk = self._resolve_vk(key)
            lparam = _make_lparam(vk, key_up=True)
            self._user32.PostMessageW(hwnd, WM_KEYUP, vk, lparam)
        if snapshot:
            log.info(
                "[BackgroundInput] release_all keys=%s hwnd=%d reason=%s",
                snapshot, hwnd, reason,
            )

    def is_target_focused(self) -> bool:
        """Always returns True — background mode doesn't require focus."""
        try:
            hwnd = self._ensure_hwnd()
            return self._user32.IsWindow(hwnd) != 0
        except BackgroundInputError:
            return False

    def focus_target_window(self) -> None:
        """No-op in background mode — we don't need focus."""
        pass

    # --- Protocol compliance stubs ---
    def mouse_move(self, dx: float, dy: float, reason: str = "") -> bool:
        log.warning("[BackgroundInput] mouse_move not supported in background mode")
        return False

    def mouse_move_to(self, x: int, y: int, reason: str = "") -> bool:
        log.warning("[BackgroundInput] mouse_move_to not supported in background mode")
        return False

    def left_click(self, reason: str = "") -> bool:
        log.warning("[BackgroundInput] left_click not supported in background mode")
        return False

    def right_click(self, reason: str = "") -> bool:
        log.warning("[BackgroundInput] right_click not supported in background mode")
        return False

    def mouse_scroll(self, delta: int = -1, reason: str = "") -> bool:
        log.warning("[BackgroundInput] mouse_scroll not supported in background mode")
        return False

    def hold_click(self, duration_sec: float = 0.5, reason: str = "") -> bool:
        log.warning("[BackgroundInput] hold_click not supported in background mode")
        return False

    def mouse_drag(
        self, start_x: int, start_y: int, end_x: int, end_y: int,
        duration_ms: int = 300, button: Literal["left", "right"] = "left", reason: str = ""
    ) -> bool:
        log.warning("[BackgroundInput] mouse_drag not supported in background mode")
        return False

    def mouse_relative_drag(
        self, dx: int, dy: int, duration_ms: int = 150,
        button: Literal["left", "right", "middle"] = "right", reason: str = ""
    ) -> bool:
        log.warning("[BackgroundInput] mouse_relative_drag not supported in background mode")
        return False

    def mouse_double_click(
        self, x: int, y: int, button: Literal["left", "right"] = "left", reason: str = ""
    ) -> bool:
        log.warning("[BackgroundInput] mouse_double_click not supported in background mode")
        return False

    def type_text(self, text: str, delay_between_keys_ms: int = 50, reason: str = "") -> bool:
        log.warning("[BackgroundInput] type_text not supported in background mode")
        return False

    def execute_combo(self, keys: list[str], hold_time_ms: int = 100, reason: str = "") -> bool:
        log.warning("[BackgroundInput] execute_combo not supported in background mode")
        return False

    @property
    def _released(self) -> bool:
        with self._lock:
            return len(self._down_keys) == 0


class FlashFocusBackend:
    """Hybrid: uses PostMessage for background, flashes to foreground for SendInput fallback.

    This is for games (like Genshin) where PostMessage alone may not work
    for DirectInput keys. It briefly brings the game to the foreground,
    sends the key via SendInput, then immediately restores the previous window.
    The flash is so fast (~50ms) the user barely notices.
    """

    def __init__(
        self,
        target_window_title: str,
        *,
        timebase: Timebase | None = None,
        alt_window_titles: list[str] | None = None,
        flash_duration_ms: int = 200,
    ) -> None:
        self.target_window_title = target_window_title
        self.alt_window_titles = alt_window_titles or []
        self._timebase = timebase or Timebase()
        self._user32 = ctypes.windll.user32
        self._down_keys: set[str] = set()
        self._lock = threading.RLock()
        self._flash_duration = flash_duration_ms / 1000.0
        self._hwnd: int | None = None

    def _find_hwnd(self) -> int:
        hwnd = self._user32.FindWindowW(None, self.target_window_title)
        if not hwnd:
            for alt in self.alt_window_titles:
                hwnd = self._user32.FindWindowW(None, alt)
                if hwnd:
                    break
        if not hwnd:
            raise BackgroundInputError(
                f"window not found: {[self.target_window_title] + self.alt_window_titles}"
            )
        return hwnd

    def _ensure_hwnd(self) -> int:
        if self._hwnd is None or not self._user32.IsWindow(self._hwnd):
            self._hwnd = self._find_hwnd()
        return self._hwnd

    def _resolve_vk(self, key: str) -> int:
        vk = _VK_MAP.get(key.lower())
        if vk is not None:
            return vk
        if len(key) == 1:
            return ord(key.upper())
        raise BackgroundInputError(f"unknown key: {key!r}")

    def _send_input_key(self, vk: int, up: bool = False) -> None:
        scan = self._user32.MapVirtualKeyW(vk, 0)
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
        inp = _INPUT(
            type=INPUT_KEYBOARD,
            union=_INPUT_UNION(
                _ki=_KEYBDINPUT(
                    wVk=0,  # Must be 0 when using KEYEVENTF_SCANCODE
                    wScan=scan,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=ctypes.c_void_p(0),
                )
            ),
        )
        self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def _flash_to_foreground(self, action_fn) -> None:
        """Briefly bring game to foreground, execute action, restore previous window."""
        hwnd = self._ensure_hwnd()
        prev_fg = self._user32.GetForegroundWindow()

        if prev_fg == hwnd:
            action_fn()
            return

        # Use AttachThreadInput trick for reliable foreground switch
        fg_tid = self._user32.GetWindowThreadProcessId(prev_fg, None)
        cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        self._user32.AttachThreadInput(cur_tid, fg_tid, True)
        try:
            self._user32.SetForegroundWindow(hwnd)
            self._user32.BringWindowToTop(hwnd)
            self._user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        finally:
            self._user32.AttachThreadInput(cur_tid, fg_tid, False)

        # Small delay to let the window actually come to foreground
        time.sleep(0.02)

        action_fn()

        # Restore previous foreground window (do NOT move cursor)
        time.sleep(self._flash_duration)
        if prev_fg and self._user32.IsWindow(prev_fg):
            fg_tid2 = self._user32.GetWindowThreadProcessId(hwnd, None)
            self._user32.AttachThreadInput(cur_tid, fg_tid2, True)
            try:
                self._user32.SetForegroundWindow(prev_fg)
            finally:
                self._user32.AttachThreadInput(cur_tid, fg_tid2, False)

    def key_down(self, key: str, reason: str = "") -> None:
        """Bring game to foreground and hold key down. Caller must call key_up()."""
        vk = self._resolve_vk(key)
        with self._lock:
            self._down_keys.add(key)
        self._bring_to_foreground()
        self._send_input_key(vk, up=False)
        log.info("[FlashFocus] key_down key=%s reason=%s (game now foreground)", key, reason)

    def key_up(self, key: str, reason: str = "") -> None:
        """Release key and restore previous foreground window."""
        vk = self._resolve_vk(key)
        with self._lock:
            self._down_keys.discard(key)
        self._send_input_key(vk, up=True)
        self._restore_previous()
        log.info("[FlashFocus] key_up key=%s reason=%s (restored previous window)", key, reason)

    def _bring_to_foreground(self) -> None:
        """Bring game window to foreground, remember previous window."""
        hwnd = self._ensure_hwnd()
        self._prev_fg = self._user32.GetForegroundWindow()
        if self._prev_fg == hwnd:
            return
        fg_tid = self._user32.GetWindowThreadProcessId(self._prev_fg, None)
        cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        self._user32.AttachThreadInput(cur_tid, fg_tid, True)
        try:
            self._user32.SetForegroundWindow(hwnd)
            self._user32.BringWindowToTop(hwnd)
            self._user32.ShowWindow(hwnd, 9)
        finally:
            self._user32.AttachThreadInput(cur_tid, fg_tid, False)
        time.sleep(0.03)  # Let the window actually activate

    def _restore_previous(self) -> None:
        """Restore the previous foreground window."""
        prev_fg = getattr(self, '_prev_fg', 0)
        if not prev_fg or not self._user32.IsWindow(prev_fg):
            return
        hwnd = self._ensure_hwnd()
        fg_tid = self._user32.GetWindowThreadProcessId(hwnd, None)
        cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        self._user32.AttachThreadInput(cur_tid, fg_tid, True)
        try:
            self._user32.SetForegroundWindow(prev_fg)
        finally:
            self._user32.AttachThreadInput(cur_tid, fg_tid, False)
        self._prev_fg = 0

    def release_all(self, reason: str = "") -> None:
        with self._lock:
            snapshot = sorted(self._down_keys)
            self._down_keys.clear()
        if not snapshot:
            return
        self._bring_to_foreground()
        for key in snapshot:
            self._send_input_key(self._resolve_vk(key), up=True)
        time.sleep(0.05)
        self._restore_previous()
        log.info("[FlashFocus] release_all keys=%s reason=%s", snapshot, reason)

    def is_target_focused(self) -> bool:
        try:
            hwnd = self._ensure_hwnd()
            return self._user32.IsWindow(hwnd) != 0
        except BackgroundInputError:
            return False

    def focus_target_window(self) -> None:
        """No-op — flash focus handles foreground switching automatically."""
        pass

    # --- Protocol compliance stubs ---
    def mouse_move(self, dx: float, dy: float, reason: str = "") -> bool:
        log.warning("[FlashFocus] mouse_move not supported in background mode")
        return False

    def mouse_move_to(self, x: int, y: int, reason: str = "") -> bool:
        log.warning("[FlashFocus] mouse_move_to not supported in background mode")
        return False

    def left_click(self, reason: str = "") -> bool:
        log.warning("[FlashFocus] left_click not supported in background mode")
        return False

    def right_click(self, reason: str = "") -> bool:
        log.warning("[FlashFocus] right_click not supported in background mode")
        return False

    def mouse_scroll(self, delta: int = -1, reason: str = "") -> bool:
        log.warning("[FlashFocus] mouse_scroll not supported in background mode")
        return False

    def hold_click(self, duration_sec: float = 0.5, reason: str = "") -> bool:
        log.warning("[FlashFocus] hold_click not supported in background mode")
        return False

    def mouse_drag(
        self, start_x: int, start_y: int, end_x: int, end_y: int,
        duration_ms: int = 300, button: Literal["left", "right"] = "left", reason: str = ""
    ) -> bool:
        log.warning("[FlashFocus] mouse_drag not supported in background mode")
        return False

    def mouse_relative_drag(
        self, dx: int, dy: int, duration_ms: int = 150,
        button: Literal["left", "right", "middle"] = "right", reason: str = ""
    ) -> bool:
        log.warning("[FlashFocus] mouse_relative_drag not supported in background mode")
        return False

    def mouse_double_click(
        self, x: int, y: int, button: Literal["left", "right"] = "left", reason: str = ""
    ) -> bool:
        log.warning("[FlashFocus] mouse_double_click not supported in background mode")
        return False

    def type_text(self, text: str, delay_between_keys_ms: int = 50, reason: str = "") -> bool:
        log.warning("[FlashFocus] type_text not supported in background mode")
        return False

    def execute_combo(self, keys: list[str], hold_time_ms: int = 100, reason: str = "") -> bool:
        log.warning("[FlashFocus] execute_combo not supported in background mode")
        return False

    @property
    def _released(self) -> bool:
        with self._lock:
            return len(self._down_keys) == 0


