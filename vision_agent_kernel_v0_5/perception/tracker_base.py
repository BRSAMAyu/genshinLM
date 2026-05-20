from __future__ import annotations

from typing import Protocol

import numpy as np

from core.types import TargetTrack


class Tracker(Protocol):
    def update(self, frame: np.ndarray, frame_id: int, timestamp: float) -> TargetTrack | None: ...
