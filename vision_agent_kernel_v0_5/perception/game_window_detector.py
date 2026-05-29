"""Authorized safe-window detector for Aurora QA/testbed runs.

This module intentionally does not enumerate or bind to commercial game
clients. It only recognizes windows whose titles explicitly opt in to Aurora's
safe-window/testbed contract.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
from dataclasses import dataclass, field


AUTHORIZED_WINDOW_MARKERS: tuple[str, ...] = (
    "Aurora QA Safe Window",
    "Aurora Genshin-like Testbed",
    "Aurora Pseudo3D",
    "vision_agent_kernel_v0_5 pseudo3d_scene",
)


@dataclass(frozen=True, slots=True)
class GameProfile:
    game_id: str
    display_name: str
    exact_titles: tuple[str, ...]
    partial_keywords: tuple[str, ...]
    window_classes: tuple[str, ...] = ()
    process_names: tuple[str, ...] = ()


GAME_REGISTRY: tuple[GameProfile, ...] = (
    GameProfile(
        game_id="genshin_like",
        display_name="Aurora Genshin-like Testbed",
        exact_titles=("Aurora Genshin-like Testbed",),
        partial_keywords=AUTHORIZED_WINDOW_MARKERS,
    ),
    GameProfile(
        game_id="qa_safe_window",
        display_name="Aurora QA Safe Window",
        exact_titles=("Aurora QA Safe Window",),
        partial_keywords=AUTHORIZED_WINDOW_MARKERS,
    ),
)


@dataclass(slots=True)
class GameWindow:
    hwnd: int
    title: str
    class_name: str
    width: int
    height: int
    pid: int
    game_id: str
    match_method: str


@dataclass(slots=True)
class DetectionResult:
    windows: list[GameWindow] = field(default_factory=list)

    @property
    def best(self) -> GameWindow | None:
        if not self.windows:
            return None
        priority = {"exact_title": 0, "authorized_keyword": 1}
        return min(self.windows, key=lambda w: priority.get(w.match_method, 99))

    @property
    def found(self) -> bool:
        return bool(self.windows)


def _windows_available() -> bool:
    return os.name == "nt" and hasattr(ctypes, "windll")


def _user32():
    if not _windows_available():
        raise RuntimeError("Windows user32 APIs are unavailable on this platform")
    return ctypes.windll.user32


def _is_authorized_title(title: str) -> bool:
    title_lower = title.lower()
    return any(marker.lower() in title_lower for marker in AUTHORIZED_WINDOW_MARKERS)


def _get_window_text(hwnd: int) -> str:
    user32 = _user32()
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _get_class_name(hwnd: int) -> str:
    user32 = _user32()
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _get_window_pid(hwnd: int) -> int:
    user32 = _user32()
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _get_window_size(hwnd: int) -> tuple[int, int]:
    user32 = _user32()
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (int(rect.right - rect.left), int(rect.bottom - rect.top))


def detect_game_windows(
    game_id: str = "",
    *,
    explicit_title: str | None = None,
    allow_unmarked_explicit_title: bool = False,
) -> DetectionResult:
    """Return authorized QA/testbed windows.

    `explicit_title` supports real-machine QA where the operator names the
    target window at launch time. Unmarked explicit titles are accepted only
    when `allow_unmarked_explicit_title=True`; the detector still never scans
    process names or embeds client-specific title lists.
    """
    if not _windows_available():
        return DetectionResult()

    profiles = GAME_REGISTRY
    if game_id:
        profiles = tuple(
            p for p in profiles
            if p.game_id == game_id or p.game_id.endswith(game_id) or game_id in {"genshin", "hsr"}
        )

    exact: dict[str, GameProfile] = {}
    for profile in profiles:
        for title in profile.exact_titles:
            exact[title.lower()] = profile

    result = DetectionResult()
    user32 = _user32()
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

    def check_window(hwnd: int) -> None:
        if not user32.IsWindowVisible(hwnd):
            return
        title = _get_window_text(hwnd)
        if not title:
            return
        title_lower = title.lower()
        profile = exact.get(title_lower)
        match_method = "exact_title" if profile else ""
        explicit_match = bool(explicit_title and title == explicit_title)
        if profile is None and _is_authorized_title(title):
            profile = profiles[0] if profiles else GAME_REGISTRY[0]
            match_method = "authorized_keyword"
        elif profile is None and explicit_match and allow_unmarked_explicit_title:
            profile = profiles[0] if profiles else GAME_REGISTRY[0]
            match_method = "explicit_title"
        if profile is None:
            return
        width, height = _get_window_size(hwnd)
        if width < 200 or height < 200:
            return
        result.windows.append(
            GameWindow(
                hwnd=int(hwnd),
                title=title,
                class_name=_get_class_name(hwnd),
                width=width,
                height=height,
                pid=_get_window_pid(hwnd),
                game_id=profile.game_id,
                match_method=match_method,
            )
        )

    def callback(hwnd: int, _lparam: int) -> bool:
        check_window(hwnd)
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    return result


def focus_window(hwnd: int) -> bool:
    """Focus an already authorized QA/testbed window."""
    if not _windows_available():
        return False
    title = _get_window_text(hwnd)
    if not _is_authorized_title(title):
        return False
    user32 = _user32()
    user32.ShowWindow(hwnd, 9)
    return bool(user32.SetForegroundWindow(hwnd))


def list_all_game_windows() -> list[GameWindow]:
    return detect_game_windows().windows
