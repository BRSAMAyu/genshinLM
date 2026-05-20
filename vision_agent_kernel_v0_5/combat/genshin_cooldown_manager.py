from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class SkillCooldownState:
    skill_id: str
    ready: bool
    remaining_ms: float
    confidence: float
    detection_method: str  # "ocr", "greyed", "sweep", "glow", "unknown"


class GenshinCooldownManager:
    """Genshin-specific cooldown detection via visual analysis of skill icons."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillCooldownState] = {}

    def update_from_ui(
        self,
        skill_id: str,
        skill_roi: np.ndarray,
        ocr_number: int | None = None,
    ) -> SkillCooldownState:
        """Determine skill cooldown state from skill icon ROI.

        Priority order:
        1. OCR number countdown (highest confidence)
        2. Greyed-out detection (icon desaturated = on cooldown)
        3. Sweep angle estimation (partial cooldown)
        4. Element glow detection (Q burst energy full)
        """
        state = self._ocr_state(skill_id, ocr_number)
        if state is not None:
            self._skills[skill_id] = state
            return state

        is_greyed, grey_conf = self._detect_greyed_out(skill_roi)
        if is_greyed:
            remaining_ratio, sweep_conf = self._detect_sweep_angle(skill_roi)
            sweep_combined = min(grey_conf, sweep_conf)
            state = SkillCooldownState(
                skill_id=skill_id,
                ready=False,
                remaining_ms=remaining_ratio * 10000.0,
                confidence=sweep_combined,
                detection_method="sweep",
            )
            self._skills[skill_id] = state
            return state

        is_glowing, glow_conf = self._detect_element_glow(skill_roi)
        if is_glowing:
            state = SkillCooldownState(
                skill_id=skill_id,
                ready=True,
                remaining_ms=0.0,
                confidence=glow_conf,
                detection_method="glow",
            )
            self._skills[skill_id] = state
            return state

        if grey_conf > 0.6:
            state = SkillCooldownState(
                skill_id=skill_id,
                ready=True,
                remaining_ms=0.0,
                confidence=grey_conf,
                detection_method="greyed",
            )
            self._skills[skill_id] = state
            return state

        state = SkillCooldownState(
            skill_id=skill_id,
            ready=True,
            remaining_ms=0.0,
            confidence=0.5,
            detection_method="unknown",
        )
        self._skills[skill_id] = state
        return state

    def get_state(self, skill_id: str) -> SkillCooldownState:
        if skill_id in self._skills:
            return self._skills[skill_id]
        return SkillCooldownState(
            skill_id=skill_id,
            ready=True,
            remaining_ms=0.0,
            confidence=0.0,
            detection_method="unknown",
        )

    def is_ready(self, skill_id: str) -> bool:
        return self.get_state(skill_id).ready

    def _detect_greyed_out(self, roi: np.ndarray) -> tuple[bool, float]:
        """Check if icon is desaturated (cooldown active).

        Greyed icons have very low saturation across the ROI.
        Returns (is_greyed, confidence).
        """
        if roi.size == 0 or roi.ndim < 3:
            return (False, 0.0)

        rgb = roi.astype(np.float32) / 255.0
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        maxc = np.maximum(np.maximum(r, g), b)
        minc = np.minimum(np.minimum(r, g), b)
        delta = maxc - minc
        saturation = np.divide(
            delta, maxc, out=np.zeros_like(delta), where=maxc > 1e-6
        )

        mean_sat = float(saturation.mean())
        is_greyed = mean_sat < 0.15
        confidence = min(1.0, abs(mean_sat - 0.15) / 0.15)
        return (is_greyed, confidence)

    def _detect_sweep_angle(self, roi: np.ndarray) -> tuple[float, float]:
        """Estimate cooldown progress from arc sweep pattern.

        Returns (remaining_ratio 0-1, confidence).
        When a skill is on CD, the icon has a dark arc that sweeps clockwise.
        """
        if roi.size == 0 or roi.ndim < 3:
            return (0.5, 0.3)

        gray = np.mean(roi.astype(np.float32), axis=2)
        threshold = gray.mean() * 0.6
        dark_mask = gray < threshold

        total_pixels = float(dark_mask.size)
        dark_ratio = float(dark_mask.sum()) / total_pixels if total_pixels > 0 else 0.0

        remaining_ratio = max(0.0, min(1.0, dark_ratio))
        confidence = min(0.8, remaining_ratio * 1.5) if remaining_ratio > 0 else 0.4
        return (remaining_ratio, confidence)

    def _detect_element_glow(self, roi: np.ndarray) -> tuple[bool, float]:
        """Detect Q burst energy full (icon glows with element color).

        Full energy = bright saturated pixels above threshold.
        Returns (is_glowing, confidence).
        """
        if roi.size == 0 or roi.ndim < 3:
            return (False, 0.0)

        rgb = roi.astype(np.float32) / 255.0
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        maxc = np.maximum(np.maximum(r, g), b)
        minc = np.minimum(np.minimum(r, g), b)
        delta = maxc - minc
        saturation = np.divide(
            delta, maxc, out=np.zeros_like(delta), where=maxc > 1e-6
        )
        value = maxc

        bright_saturated = (saturation > 0.5) & (value > 0.7)
        ratio = float(bright_saturated.sum()) / float(bright_saturated.size) if bright_saturated.size > 0 else 0.0

        is_glowing = ratio > 0.25
        confidence = min(1.0, ratio * 2.0)
        return (is_glowing, confidence)

    def _ocr_state(
        self, skill_id: str, ocr_number: int | None
    ) -> SkillCooldownState | None:
        """Build state from OCR number if available."""
        if ocr_number is None:
            return None

        remaining_ms = float(ocr_number) * 1000.0
        return SkillCooldownState(
            skill_id=skill_id,
            ready=remaining_ms <= 0,
            remaining_ms=remaining_ms,
            confidence=0.95,
            detection_method="ocr",
        )
