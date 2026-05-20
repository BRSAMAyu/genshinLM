from __future__ import annotations

import time
from typing import Any
import numpy as np

from core.timebase import Timebase
from perception.capture_base import FramePacket, ScreenCapturer


class DemoFrameSource:
    """Produces frames with moving target and optional danger zones for dry-run/testing."""
    
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._timebase = Timebase()
        self._frame_id = 0
        self._danger_active = False
        self._running = False
        self._target_x = 40

    def start(self) -> None:
        self._running = True

    def get_latest_frame(self) -> FramePacket | None:
        if not self._running:
            return None
        self._frame_id += 1
        
        # Draw frame
        image = np.zeros((360, 640, 3), dtype=np.uint8)
        
        # Moving target (blue box, BGR format: B is channel 0)
        self._target_x = (self._target_x + 5) % 520
        x = self._target_x
        image[150:210, x:x + 80, 0] = 200
        image[150:210, x:x + 80, 1] = 50
        image[150:210, x:x + 80, 2] = 50
        
        # Optional ground danger zone (red area, BGR format: R is channel 2)
        if self._danger_active or self._config.get("danger_active", False):
            image[240:350, 200:440, 2] = 200
            image[240:350, 200:440, 1] = 50
            image[240:350, 200:440, 0] = 50
            
        return FramePacket(
            frame_id=self._frame_id,
            timestamp=self._timebase.now(),
            image=image,
            source_size=(640, 360),
            color_format="BGR"
        )

    def stop(self) -> None:
        self._running = False

    def activate_danger(self) -> None:
        self._danger_active = True

    def clear_danger(self) -> None:
        self._danger_active = False


class Win32WindowCapturer:
    """Captures frames from a specific Win32 window (Stub/Fallbacks enabled)."""
    
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._window_title = self._config.get("window_title", "Genshin Impact")
        self._timebase = Timebase()
        self._frame_id = 0
        self._running = False

    def start(self) -> None:
        self._running = True

    def get_latest_frame(self) -> FramePacket | None:
        if not self._running:
            return None
        self._frame_id += 1
        
        # Win32 capture stub: returns a safe black placeholder frame with a target box in the center
        image = np.zeros((360, 640, 3), dtype=np.uint8)
        # Static target box in center (green, BGR format: G is channel 1)
        image[150:210, 280:360, 1] = 200
        image[150:210, 280:360, 0] = 50
        image[150:210, 280:360, 2] = 50
        
        return FramePacket(
            frame_id=self._frame_id,
            timestamp=self._timebase.now(),
            image=image,
            source_size=(640, 360),
            color_format="BGR"
        )

    def stop(self) -> None:
        self._running = False


class FrameSourceFactory:
    """Unified factory to dynamically resolve and instantiate screen frame sources."""
    
    @staticmethod
    def create_source(source_type: str, config: dict[str, Any] | None = None) -> ScreenCapturer:
        cfg = config or {}
        if source_type == "demo":
            return DemoFrameSource(cfg)
        elif source_type in {"win32", "real", "safe-window"}:
            return Win32WindowCapturer(cfg)
        raise ValueError(f"Unknown FrameSource type: {source_type}")
