from __future__ import annotations

from typing import Protocol

import numpy as np

from core.types import TargetCandidate


class Detector(Protocol):
    def detect(self, frame: np.ndarray, frame_id: int) -> list[TargetCandidate]: ...
