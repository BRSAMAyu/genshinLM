from __future__ import annotations

import ctypes
import io
from ctypes import wintypes
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True, slots=True)
class WindowRectView:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    def to_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True, slots=True)
class WindowInfo:
    title: str
    pid: int
    handle: int
    rect: WindowRectView
    focused: bool
    visible: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["rect"] = self.rect.to_dict()
        return data


class WindowSelectionError(RuntimeError):
    pass


class WindowSelector:
    def __init__(self) -> None:
        self._selected: WindowInfo | None = None
        self._user32 = ctypes.windll.user32
        self._configure()

    @property
    def selected(self) -> WindowInfo | None:
        return self._selected

    def list_windows(self) -> list[WindowInfo]:
        windows: list[WindowInfo] = []
        foreground = self._user32.GetForegroundWindow()

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_proc(hwnd: int, lparam: int) -> bool:
            del lparam
            if not self._user32.IsWindowVisible(hwnd):
                return True
            length = self._user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            self._user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
            if not title:
                return True
            rect = wintypes.RECT()
            if not self._user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            pid = wintypes.DWORD()
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width <= 0 or height <= 0:
                return True
            windows.append(
                WindowInfo(
                    title=title,
                    pid=int(pid.value),
                    handle=int(hwnd),
                    rect=WindowRectView(rect.left, rect.top, rect.right, rect.bottom),
                    focused=hwnd == foreground,
                    visible=True,
                )
            )
            return True

        self._user32.EnumWindows(enum_proc, 0)
        return sorted(windows, key=lambda item: item.title.lower())

    def select_window(self, title: str | None = None, handle: int | None = None) -> WindowInfo:
        for window in self.list_windows():
            if (handle is not None and window.handle == handle) or (title is not None and window.title == title):
                self._selected = window
                return window
        raise WindowSelectionError("No matching visible window was found. Start the test environment or choose another window.")

    def focus_ok(self) -> bool:
        if self._selected is None:
            return False
        return self._user32.GetForegroundWindow() == self._selected.handle

    def selected_or_raise(self) -> WindowInfo:
        if self._selected is None:
            raise WindowSelectionError("No target window selected. Choose a window in the calibration wizard first.")
        refreshed = self.select_window(handle=self._selected.handle)
        if not refreshed.visible:
            raise WindowSelectionError("The selected window is not visible. Restore it and try again.")
        return refreshed

    def snapshot_png(self) -> bytes:
        window = self.selected_or_raise()
        try:
            from PIL import ImageGrab
        except ImportError as exc:
            raise WindowSelectionError("Pillow is required for window snapshots. Install pillow and retry.") from exc
        rect = window.rect
        image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _configure(self) -> None:
        self._user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
        self._user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self._user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self._user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self._user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self._user32.GetForegroundWindow.argtypes = []
        self._user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
