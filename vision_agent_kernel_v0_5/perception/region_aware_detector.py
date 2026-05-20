from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class RegionParams:
    region_id: str
    bg_hue_range: tuple[float, float]
    min_saturation_boost: float
    bg_saturation_range: tuple[float, float]
    bg_value_range: tuple[float, float]


class RegionAwareDetector:
    """Adjust detection parameters based on current Genshin region."""

    REGION_PARAMS: dict[str, RegionParams] = {
        "mondstadt": RegionParams("mondstadt", (80.0, 120.0), 0.1, (30.0, 100.0), (80.0, 200.0)),
        "liyue": RegionParams("liyue", (20.0, 40.0), 0.15, (60.0, 100.0), (120.0, 200.0)),
        "inazuma": RegionParams("inazuma", (250.0, 290.0), 0.1, (30.0, 60.0), (80.0, 180.0)),
        "sumeru_rainforest": RegionParams("sumeru_rainforest", (80.0, 130.0), 0.2, (60.0, 100.0), (60.0, 150.0)),
        "sumeru_desert": RegionParams("sumeru_desert", (25.0, 45.0), 0.2, (50.0, 90.0), (160.0, 240.0)),
        "fontaine": RegionParams("fontaine", (190.0, 220.0), 0.1, (40.0, 80.0), (120.0, 220.0)),
        "natlan": RegionParams("natlan", (0.0, 20.0), 0.25, (60.0, 100.0), (120.0, 220.0)),
    }

    def __init__(self) -> None:
        self._current_region: str = "unknown"

    def detect_region(self, frame: np.ndarray) -> str:
        """Detect current region from frame's dominant color.

        Samples the main view area (excluding HUD) and computes
        dominant hue to match against known region profiles.
        """
        if frame.size == 0 or frame.ndim < 3:
            self._current_region = "unknown"
            return self._current_region

        h, w = frame.shape[:2]
        roi = frame[h // 6 : h * 5 // 6, w // 6 : w * 5 // 6]
        if roi.size == 0:
            self._current_region = "unknown"
            return self._current_region

        hist = self._compute_hue_histogram(roi)
        dominant = self._dominant_hue(hist)
        self._current_region = self._match_region(dominant)
        return self._current_region

    @property
    def current_region(self) -> str:
        return self._current_region

    def get_params(self) -> RegionParams:
        """Get detection parameters for current region."""
        if self._current_region in self.REGION_PARAMS:
            return self.REGION_PARAMS[self._current_region]
        return RegionParams("unknown", (0.0, 360.0), 0.0, (0.0, 100.0), (0.0, 255.0))

    def adjust_saturation_threshold(self, base_threshold: float) -> float:
        """Adjust color saturation threshold based on region.

        Regions with colorful backgrounds (Sumeru, Liyue) need
        higher thresholds to avoid false positives.
        """
        params = self.get_params()
        return base_threshold + params.min_saturation_boost

    def _compute_hue_histogram(self, roi: np.ndarray) -> np.ndarray:
        """Compute hue histogram for region classification."""
        rgb = roi.astype(np.float32) / 255.0
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
        saturated_mask = saturation > 0.15
        valid_hue = hue_deg[saturated_mask]

        bins = np.arange(0.0, 370.0, 10.0)
        hist, _ = np.histogram(valid_hue, bins=bins)
        return hist.astype(np.float64)

    def _dominant_hue(self, hue_hist: np.ndarray) -> float:
        """Find the dominant hue from histogram."""
        if hue_hist.sum() == 0:
            return 0.0
        bin_index = int(np.argmax(hue_hist))
        return float(bin_index * 10.0 + 5.0)

    def _match_region(self, dominant_hue: float) -> str:
        """Match dominant hue to known region profiles."""
        best_region = "unknown"
        best_distance = float("inf")

        for region_id, params in self.REGION_PARAMS.items():
            lo, hi = params.bg_hue_range
            if lo <= hi:
                if lo <= dominant_hue <= hi:
                    center = (lo + hi) / 2.0
                    distance = abs(dominant_hue - center)
                    if distance < best_distance:
                        best_distance = distance
                        best_region = region_id
            else:
                if dominant_hue >= lo or dominant_hue <= hi:
                    span = (360.0 - lo) + hi
                    center = (lo + span / 2.0) % 360.0
                    diff = abs(dominant_hue - center)
                    distance = min(diff, 360.0 - diff)
                    if distance < best_distance:
                        best_distance = distance
                        best_region = region_id

        return best_region
