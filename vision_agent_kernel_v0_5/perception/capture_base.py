from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True, slots=True)
class CaptureConfig:
    target_fps: float = 60.0
    output_color: str = "RGB"
    region: tuple[int, int, int, int] | None = None


@dataclass(frozen=True, slots=True)
class FramePacket:
    frame_id: int
    timestamp: float
    image: np.ndarray
    source_size: tuple[int, int]
    color_format: str = "RGB"


class ScreenCapturer(Protocol):
    def start(self) -> None: ...

    def get_latest_frame(self) -> FramePacket | None: ...

    def stop(self) -> None: ...
