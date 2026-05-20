from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class HPBarResult:
    hp_ratio: float
    confidence: float


class HPBarTracker:
    def estimate_hsv_mask_ratio(self, image: np.ndarray, red_channel_threshold: int = 120) -> HPBarResult:
        if image.size == 0:
            return HPBarResult(1.0, 0.0)
        if image.ndim < 3 or image.shape[-1] != 3:
            mask = image > red_channel_threshold
        else:
            rgb = image.astype(np.float32) / 255.0
            r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
            maxc = np.maximum(np.maximum(r, g), b)
            minc = np.minimum(np.minimum(r, g), b)
            delta = maxc - minc
            hue = np.zeros_like(maxc)
            nonzero = delta > 1e-6
            safe_delta = np.where(nonzero, delta, 1.0)
            hue = np.where((maxc == r) & nonzero, ((g - b) / safe_delta) % 6.0, hue)
            hue = np.where((maxc == g) & nonzero, ((b - r) / safe_delta) + 2.0, hue)
            hue = np.where((maxc == b) & nonzero, ((r - g) / safe_delta) + 4.0, hue)
            hue_deg = hue * 60.0
            saturation = np.divide(delta, maxc, out=np.zeros_like(delta), where=maxc > 1e-6)
            value = maxc
            mask = ((hue_deg <= 18.0) | (hue_deg >= 342.0)) & (saturation >= 0.45) & (value * 255.0 >= red_channel_threshold)
        ratio = float(mask.sum()) / float(mask.size)
        return HPBarResult(max(0.0, min(1.0, ratio)), 0.75)

    def estimate_red_bar_ratio(self, image: np.ndarray, red_channel_threshold: int = 120) -> HPBarResult:
        return self.estimate_hsv_mask_ratio(image, red_channel_threshold)


class ResourceManager:
    def __init__(self) -> None:
        self.hp_tracker = HPBarTracker()

    def update_hp_from_bar(self, image: np.ndarray) -> HPBarResult:
        return self.hp_tracker.estimate_hsv_mask_ratio(image)
