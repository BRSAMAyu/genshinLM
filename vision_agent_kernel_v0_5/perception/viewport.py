from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class ViewportConfig:
    width: int = 1280
    height: int = 720


@dataclass(frozen=True, slots=True)
class ViewportMapping:
    source_size: tuple[int, int]
    target_size: tuple[int, int]
    scale_x: float
    scale_y: float


class ViewportTransformer:
    def __init__(self, config: ViewportConfig | None = None) -> None:
        self._config = config or ViewportConfig()

    @property
    def size(self) -> tuple[int, int]:
        return (self._config.width, self._config.height)

    def mapping_for(self, source_size: tuple[int, int]) -> ViewportMapping:
        source_width, source_height = source_size
        if source_width <= 0 or source_height <= 0:
            raise ValueError("source dimensions must be positive")
        return ViewportMapping(
            source_size=source_size,
            target_size=self.size,
            scale_x=self._config.width / source_width,
            scale_y=self._config.height / source_height,
        )

    def normalize(self, image: np.ndarray) -> np.ndarray:
        if image.ndim < 2:
            raise ValueError("image must have at least two dimensions")
        target_width, target_height = self.size
        source_height, source_width = image.shape[:2]
        if source_width == target_width and source_height == target_height:
            return np.ascontiguousarray(image)
        return self._resize_nearest(image, target_width=target_width, target_height=target_height)

    def source_to_viewport(
        self,
        point: tuple[float, float],
        source_size: tuple[int, int],
    ) -> tuple[float, float]:
        mapping = self.mapping_for(source_size)
        x, y = point
        return (x * mapping.scale_x, y * mapping.scale_y)

    def viewport_to_source(
        self,
        point: tuple[float, float],
        source_size: tuple[int, int],
    ) -> tuple[float, float]:
        mapping = self.mapping_for(source_size)
        x, y = point
        return (x / mapping.scale_x, y / mapping.scale_y)

    def _resize_nearest(
        self,
        image: np.ndarray,
        target_width: int,
        target_height: int,
    ) -> np.ndarray:
        source_height, source_width = image.shape[:2]
        y_indices = np.linspace(0, source_height - 1, target_height).astype(np.int64)
        x_indices = np.linspace(0, source_width - 1, target_width).astype(np.int64)
        resized = image[y_indices][:, x_indices]
        return np.ascontiguousarray(resized)
