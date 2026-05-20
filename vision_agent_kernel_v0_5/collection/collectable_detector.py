from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class CollectableCandidate:
    center: tuple[float, float]
    confidence: float
    area: float


class CollectableDetector:
    def detect(self, frame: np.ndarray) -> list[CollectableCandidate]:
        if frame.size == 0:
            return []
        green = frame[..., 1] if frame.shape[-1] == 3 else frame
        mask = green > 160
        if not mask.any():
            return []
        ys, xs = np.where(mask)
        area = float(mask.sum())
        return [CollectableCandidate((float(xs.mean()), float(ys.mean())), min(1.0, area / 5000.0), area)]

