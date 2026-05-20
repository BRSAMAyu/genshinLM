from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from core.types import ObstacleField


class ObstacleEstimator(Protocol):
    def estimate(self, frame: np.ndarray, frame_id: int, timestamp: float) -> ObstacleField: ...


@dataclass(frozen=True, slots=True)
class HeuristicObstacleEstimatorConfig:
    dark_threshold: int = 45
    min_pressure: float = 0.0


class HeuristicObstacleEstimator:
    """Low-frequency obstacle estimator using image-region occupancy.

    The pseudo-3D testbed draws obstacles as blue/gray blocks. This estimator is
    intentionally simple and pluggable: it converts sector occupancy into
    pressure values in [0, 1] without keeping frame history.
    """

    def __init__(self, config: HeuristicObstacleEstimatorConfig | None = None) -> None:
        self._config = config or HeuristicObstacleEstimatorConfig()

    def estimate(self, frame: np.ndarray, frame_id: int, timestamp: float) -> ObstacleField:
        if frame.ndim != 3 or frame.shape[2] < 3:
            sectors = {name: 0.0 for name in ("front", "front_left", "front_right", "left", "right")}
            return ObstacleField(frame_id, timestamp, sectors, confidence=0.0, source="heuristic")
        red = frame[:, :, 0].astype(np.int16)
        green = frame[:, :, 1].astype(np.int16)
        blue = frame[:, :, 2].astype(np.int16)
        obstacle_mask = ((blue > red + 25) & (blue > green + 10)) | (
            (red > 80) & (green > 80) & (blue > 80) & (np.abs(red - green) < 35)
        )
        height, width = obstacle_mask.shape
        bands = {
            "left": obstacle_mask[int(height * 0.35) : int(height * 0.85), 0 : int(width * 0.25)],
            "front_left": obstacle_mask[int(height * 0.35) : int(height * 0.85), int(width * 0.25) : int(width * 0.45)],
            "front": obstacle_mask[int(height * 0.35) : int(height * 0.85), int(width * 0.45) : int(width * 0.55)],
            "front_right": obstacle_mask[int(height * 0.35) : int(height * 0.85), int(width * 0.55) : int(width * 0.75)],
            "right": obstacle_mask[int(height * 0.35) : int(height * 0.85), int(width * 0.75) : width],
        }
        sectors = {name: self._pressure(mask) for name, mask in bands.items()}
        return ObstacleField(
            frame_id=frame_id,
            timestamp=timestamp,
            sectors=sectors,
            confidence=max(sectors.values(), default=0.0),
            source="heuristic",
        )

    def _pressure(self, mask: np.ndarray) -> float:
        if mask.size == 0:
            return 0.0
        pressure = float(mask.mean()) * 8.0
        return max(self._config.min_pressure, min(1.0, pressure))


class OptionalDepthEstimator:
    def estimate(self, frame: np.ndarray, frame_id: int, timestamp: float) -> ObstacleField:
        raise RuntimeError(
            "Optional depth backend is not configured. Use HeuristicObstacleEstimator "
            "or install/configure a depth model in a later phase."
        )
