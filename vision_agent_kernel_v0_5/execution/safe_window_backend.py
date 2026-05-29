from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.timebase import Timebase

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

# Common virtual key codes
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


class SafeWindowInputBackend:
    def __init__(
        self,
        target_window_title: str,
        pixels_per_degree: float = 8.0,
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
        self._lock = threading.RLock()

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

    def mouse_move(self, dx: float, dy: float, reason: str = "") -> None:
        self._ensure_target_focused()
        pixel_dx = int(round(dx * self.pixels_per_degree))
        pixel_dy = int(round(dy * self.pixels_per_degree))
        input_packet = INPUT(
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
        sent = self._user32.SendInput(1, ctypes.byref(input_packet), ctypes.sizeof(INPUT))
        if sent != 1:
            raise SafeWindowInputError("SendInput failed")
        self._released = False
        print(
            "[SafeWindowInputBackend] "
            f"{self._timebase.now():.6f} mouse_move angle=({dx:.3f},{dy:.3f}) "
            f"pixels=({pixel_dx},{pixel_dy}) reason={reason!r}",
            flush=True,
        )

    def left_click(self, reason: str = "") -> None:
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
        import time as _time
        _time.sleep(0.05)
        self._user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
        self._released = False
        print(
            "[SafeWindowInputBackend] "
            f"{self._timebase.now():.6f} left_click reason={reason!r}",
            flush=True,
        )

    def click_at(self, screen_x: int, screen_y: int, reason: str = "") -> None:
        self._ensure_target_focused()
        self._user32.SetCursorPos(screen_x, screen_y)
        import time as _time
        _time.sleep(0.02)
        self.left_click(reason=reason)

    def key_down(self, key: str, reason: str = "") -> None:
        self._ensure_target_focused()
        vk = self._resolve_vk(key)
        input_packet = INPUT(
            type=INPUT_KEYBOARD,
            union=INPUT_UNION(
                ki=KEYBDINPUT(
                    wVk=vk,
                    wScan=0,
                    dwFlags=0,
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
            f"{self._timebase.now():.6f} key_down key={key!r} vk=0x{vk:02X} reason={reason!r}",
            flush=True,
        )

    def key_up(self, key: str, reason: str = "") -> None:
        self._ensure_target_focused()
        vk = self._resolve_vk(key)
        input_packet = INPUT(
            type=INPUT_KEYBOARD,
            union=INPUT_UNION(
                ki=KEYBDINPUT(
                    wVk=vk,
                    wScan=0,
                    dwFlags=KEYEVENTF_KEYUP,
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
            f"{self._timebase.now():.6f} key_up key={key!r} vk=0x{vk:02X} reason={reason!r}",
            flush=True,
        )

    @staticmethod
    def _resolve_vk(key: str) -> int:
        vk = _VK_MAP.get(key.lower())
        if vk is not None:
            return vk
        if len(key) == 1:
            return ord(key.upper())
        raise SafeWindowInputError(f"unknown key: {key!r}")

    def release_all(self, reason: str = "") -> None:
        with self._lock:
            snapshot = sorted(self._down_keys)
            self._down_keys.clear()
        self._released = True
        for key in snapshot:
            vk = self._resolve_vk(key)
            input_packet = INPUT(
                type=INPUT_KEYBOARD,
                union=INPUT_UNION(
                    ki=KEYBDINPUT(
                        wVk=vk,
                        wScan=0,
                        dwFlags=KEYEVENTF_KEYUP,
                        time=0,
                        dwExtraInfo=ctypes.c_void_p(0),
                    )
                ),
            )
            self._user32.SendInput(1, ctypes.byref(input_packet), ctypes.sizeof(INPUT))
        print(
            "[SafeWindowInputBackend] "
            f"{self._timebase.now():.6f} release_all keys={snapshot} reason={reason!r}",
            flush=True,
        )

    def window_rect(self) -> WindowRect:
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
            # Attempt to bring target to foreground before failing.
            # Windows restricts SetForegroundWindow, so we use AttachThreadInput
            # + AllowSetForegroundWindow + BringWindowToTop as a stronger approach.
            try:
                hwnd = self._find_target_window()
                self._force_foreground(hwnd)
            except Exception:
                pass
            import time
            time.sleep(0.1)
            if not self.is_target_focused():
                self.release_all(reason="target_window_not_focused")
                raise SafeWindowInputError(
                    f"target window is not focused: {self.target_window_title!r}"
                )

    def _force_foreground(self, hwnd: int) -> None:
        """Attempt to force a window to the foreground despite Windows restrictions."""
        import ctypes
        foreground = self._user32.GetForegroundWindow()
        if foreground == hwnd:
            return
        # Get thread info
        fg_tid = self._user32.GetWindowThreadProcessId(foreground, None)
        cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        # Attach our thread input to the foreground thread
        self._user32.AttachThreadInput(cur_tid, fg_tid, True)
        try:
            self._user32.SetForegroundWindow(hwnd)
            self._user32.BringWindowToTop(hwnd)
            self._user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        finally:
            self._user32.AttachThreadInput(cur_tid, fg_tid, False)

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
