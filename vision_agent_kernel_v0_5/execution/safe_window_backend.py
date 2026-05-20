from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from core.timebase import Timebase


INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001


class SafeWindowInputError(RuntimeError):
    pass


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


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
    ) -> None:
        self.target_window_title = target_window_title
        self.pixels_per_degree = pixels_per_degree
        self._timebase = timebase or Timebase()
        self._user32 = ctypes.windll.user32
        self._configure_win32()
        self._released = True

    def mouse_move(self, dx: float, dy: float, reason: str = "") -> None:
        self._ensure_target_focused()
        pixel_dx = int(round(dx * self.pixels_per_degree))
        pixel_dy = int(round(dy * self.pixels_per_degree))
        extra = ctypes.c_ulong(0)
        input_packet = INPUT(
            type=INPUT_MOUSE,
            union=INPUT_UNION(
                mi=MOUSEINPUT(
                    dx=pixel_dx,
                    dy=pixel_dy,
                    mouseData=0,
                    dwFlags=MOUSEEVENTF_MOVE,
                    time=0,
                    dwExtraInfo=ctypes.pointer(extra),
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

    def key_down(self, key: str, reason: str = "") -> None:
        self._ensure_target_focused()
        print(
            "[SafeWindowInputBackend] "
            f"{self._timebase.now():.6f} key_down ignored key={key!r} reason={reason!r}",
            flush=True,
        )

    def key_up(self, key: str, reason: str = "") -> None:
        print(
            "[SafeWindowInputBackend] "
            f"{self._timebase.now():.6f} key_up ignored key={key!r} reason={reason!r}",
            flush=True,
        )

    def release_all(self, reason: str = "") -> None:
        self._released = True
        print(
            "[SafeWindowInputBackend] "
            f"{self._timebase.now():.6f} release_all reason={reason!r}",
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
        self._user32.SetForegroundWindow(hwnd)
        x, y = self.client_rect().center
        self._user32.SetCursorPos(x, y)

    def is_target_focused(self) -> bool:
        try:
            hwnd = self._find_target_window()
        except SafeWindowInputError:
            return False
        return self._user32.GetForegroundWindow() == hwnd

    def _ensure_target_focused(self) -> None:
        if not self.is_target_focused():
            self.release_all(reason="target_window_not_focused")
            raise SafeWindowInputError(
                f"target window is not focused: {self.target_window_title!r}"
            )

    def _find_target_window(self) -> int:
        hwnd = self._user32.FindWindowW(None, self.target_window_title)
        if not hwnd:
            raise SafeWindowInputError(f"target window not found: {self.target_window_title!r}")
        return hwnd

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
