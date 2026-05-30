"""Night mode adapter for low-light combat environments.

P-50: Adapts visual detection to night/dark environments.
Maintains environmental brightness baseline and normalizes combat visuals.

Features:
- Ambient brightness detection and baseline
- Dark environment compensation
- Combat effect normalization in low light
- Adaptive threshold adjustment
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class EnvironmentLightLevel(Enum):
    """Ambient light level classification."""
    BRIGHT = "bright"
    NORMAL = "normal"
    DIM = "dim"
    DARK = "dark"


@dataclass(frozen=True, slots=True)
class NightModeSettings:
    """Settings for night mode adaptation."""
    brightness_threshold: float      # Threshold for dark detection
    contrast_boost: float            # Contrast enhancement factor
    saturation_boost: float           # Saturation enhancement
    edge_threshold: int              # Canny edge threshold
    color_gain: float                # Overall color amplification
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class EnvironmentAnalysis:
    """Result of environment light analysis."""
    light_level: EnvironmentLightLevel
    ambient_brightness: float        # 0.0-1.0 average brightness
    dynamic_range: float            # Brightness variance
    is_night: bool
    adaptation_factor: float        # How much adaptation applied
    frame_id: int


@dataclass(frozen=True, slots=True)
class AdaptedFrame:
    """Frame with night mode adaptation applied."""
    original: np.ndarray
    adapted: np.ndarray
    analysis: EnvironmentAnalysis
    settings_used: NightModeSettings


class NightModeAdapter:
    """Adapt visual detection for night/dark environments.

    Features:
    - Real-time ambient brightness detection
    - Adaptive contrast enhancement
    - Color normalization for dark scenes
    - Combat effect normalization

    Automatically adjusts detection thresholds based on light level.
    """

    _REF_W = 1920
    _REF_H = 1080

    # Brightness thresholds (percentages)
    _BRIGHT_THRESHOLD = 0.6
    _NORMAL_THRESHOLD = 0.4
    _DIM_THRESHOLD = 0.25

    # Night environment regions
    _AMBIENT_ROI = (0.0, 0.0, 1.0, 0.3)  # Top third for sky/ambient
    _COMBAT_ROI = (0.2, 0.3, 0.8, 0.7)   # Center for combat detection

    # Adaptive thresholds for different light levels
    _EDGE_THRESHOLDS: dict[EnvironmentLightLevel, tuple[int, int]] = {
        EnvironmentLightLevel.BRIGHT: (50, 150),
        EnvironmentLightLevel.NORMAL: (40, 120),
        EnvironmentLightLevel.DIM: (30, 100),
        EnvironmentLightLevel.DARK: (20, 80),
    }

    def __init__(self, now_fn=None) -> None:
        """Initialize night mode adapter.

        Args:
            now_fn: Time function (default: time.perf_counter)
        """
        self._now_fn = now_fn or time.perf_counter
        self._baseline_brightness: float = 0.5
        self._adaptation_history: list[float] = []
        self._current_settings = self._create_default_settings()
        self._last_analysis: EnvironmentAnalysis | None = None

    @property
    def is_night_mode(self) -> bool:
        """Check if night mode is currently active."""
        return self._last_analysis.is_night if self._last_analysis else False

    @property
    def current_settings(self) -> NightModeSettings:
        """Get current adaptation settings."""
        return self._current_settings

    def analyze_environment(
        self,
        frame: np.ndarray,
        frame_id: int,
    ) -> EnvironmentAnalysis:
        """Analyze ambient light level of environment.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID

        Returns:
            EnvironmentAnalysis with light level classification
        """
        if frame.size == 0:
            return EnvironmentAnalysis(
                light_level=EnvironmentLightLevel.NORMAL,
                ambient_brightness=0.5,
                dynamic_range=0.0,
                is_night=False,
                adaptation_factor=0.0,
                frame_id=frame_id,
            )

        now = self._now_fn()

        # Get ambient region
        ambient = self._get_ambient_roi(frame)
        if ambient.size == 0:
            ambient = frame

        # Calculate brightness metrics
        gray = cv2.cvtColor(ambient, cv2.COLOR_BGR2GRAY) if cv2 else ambient[:, :, 0]

        # Mean brightness
        mean_brightness = np.mean(gray) / 255.0

        # Standard deviation (dynamic range)
        std_brightness = np.std(gray) / 255.0

        # Classify light level
        light_level = self._classify_light_level(mean_brightness)

        # Check for night indicators (dark with occasional bright spots)
        is_night = (
            mean_brightness < self._DIM_THRESHOLD and
            std_brightness > 0.15  # Variance suggests stars/lights
        )

        # Calculate adaptation factor
        if is_night:
            adaptation_factor = 1.0 - mean_brightness  # More adaptation in darker scenes
        else:
            adaptation_factor = (self._baseline_brightness - mean_brightness) * 2
            adaptation_factor = max(0.0, min(1.0, adaptation_factor))

        # Update baseline with EMA
        self._baseline_brightness = (
            self._baseline_brightness * 0.9 + mean_brightness * 0.1
        )

        # Store adaptation history
        self._adaptation_history.append(adaptation_factor)
        if len(self._adaptation_history) > 30:
            self._adaptation_history.pop(0)

        # Update settings based on analysis
        self._update_settings(light_level, is_night)

        self._last_analysis = EnvironmentAnalysis(
            light_level=light_level,
            ambient_brightness=mean_brightness,
            dynamic_range=std_brightness,
            is_night=is_night,
            adaptation_factor=adaptation_factor,
            frame_id=frame_id,
        )

        return self._last_analysis

    def adapt_frame(
        self,
        frame: np.ndarray,
        frame_id: int,
    ) -> AdaptedFrame:
        """Apply night mode adaptation to frame.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID

        Returns:
            AdaptedFrame with original, adapted frame and analysis
        """
        # First analyze environment
        analysis = self.analyze_environment(frame, frame_id)

        # Apply adaptation if needed
        if self._current_settings.enabled and analysis.adaptation_factor > 0.1:
            adapted = self._apply_adaptation(frame, analysis)
        else:
            adapted = frame

        return AdaptedFrame(
            original=frame,
            adapted=adapted,
            analysis=analysis,
            settings_used=self._current_settings,
        )

    def _apply_adaptation(
        self,
        frame: np.ndarray,
        analysis: EnvironmentAnalysis,
    ) -> np.ndarray:
        """Apply adaptation to frame based on settings."""
        if cv2 is None:
            return frame

        result = frame.copy()
        factor = analysis.adaptation_factor

        settings = self._current_settings

        # Contrast boost
        if settings.contrast_boost > 1.0:
            alpha = 1.0 + (settings.contrast_boost - 1.0) * factor
            beta = -30 * factor  # Brightness adjustment
            result = cv2.convertScaleAbs(result, alpha=alpha, beta=beta)

        # Color gain
        if settings.color_gain > 1.0:
            gain = 1.0 + (settings.color_gain - 1.0) * factor
            result = np.clip(result * gain, 0, 255).astype(np.uint8)

        # Saturation boost
        if settings.saturation_boost > 1.0:
            hsv = cv2.cvtColor(result, cv2.COLOR_BGR2HSV)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * settings.saturation_boost, 0, 255).astype(np.uint8)
            result = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        return result

    def _classify_light_level(self, mean_brightness: float) -> EnvironmentLightLevel:
        """Classify light level based on mean brightness."""
        if mean_brightness >= self._BRIGHT_THRESHOLD:
            return EnvironmentLightLevel.BRIGHT
        elif mean_brightness >= self._NORMAL_THRESHOLD:
            return EnvironmentLightLevel.NORMAL
        elif mean_brightness >= self._DIM_THRESHOLD:
            return EnvironmentLightLevel.DIM
        else:
            return EnvironmentLightLevel.DARK

    def _update_settings(
        self,
        light_level: EnvironmentLightLevel,
        is_night: bool,
    ) -> None:
        """Update adaptation settings based on light level."""
        if light_level == EnvironmentLightLevel.BRIGHT:
            self._current_settings = NightModeSettings(
                brightness_threshold=0.5,
                contrast_boost=1.0,
                saturation_boost=1.0,
                edge_threshold=50,
                color_gain=1.0,
                enabled=False,  # No adaptation needed
            )
        elif light_level == EnvironmentLightLevel.NORMAL:
            self._current_settings = NightModeSettings(
                brightness_threshold=0.4,
                contrast_boost=1.0,
                saturation_boost=1.1,
                edge_threshold=40,
                color_gain=1.0,
                enabled=True,
            )
        elif light_level == EnvironmentLightLevel.DIM:
            self._current_settings = NightModeSettings(
                brightness_threshold=0.25,
                contrast_boost=1.2,
                saturation_boost=1.2,
                edge_threshold=30,
                color_gain=1.1,
                enabled=True,
            )
        else:  # Dark
            self._current_settings = NightModeSettings(
                brightness_threshold=0.15,
                contrast_boost=1.3,
                saturation_boost=1.3,
                edge_threshold=20,
                color_gain=1.2,
                enabled=True,
            )

        # If is_night, apply extra enhancement
        if is_night:
            self._current_settings = NightModeSettings(
                brightness_threshold=self._current_settings.brightness_threshold,
                contrast_boost=self._current_settings.contrast_boost * 1.1,
                saturation_boost=self._current_settings.saturation_boost * 1.1,
                edge_threshold=int(self._current_settings.edge_threshold * 0.8),
                color_gain=self._current_settings.color_gain * 1.1,
                enabled=True,
            )

    def _get_ambient_roi(self, frame: np.ndarray) -> np.ndarray:
        """Extract ambient light region from frame."""
        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        x1 = int(self._AMBIENT_ROI[0] * sx * self._REF_W)
        y1 = int(self._AMBIENT_ROI[1] * sy * self._REF_H)
        x2 = int(self._AMBIENT_ROI[2] * sx * self._REF_W)
        y2 = int(self._AMBIENT_ROI[3] * sy * self._REF_H)

        return frame[y1:y2, x1:x2]

    def get_adaptive_threshold(
        self,
        base_threshold: int,
        detection_type: Literal["edge", "color", "motion"],
    ) -> int:
        """Get adaptive threshold based on current light level.

        Args:
            base_threshold: Base threshold value
            detection_type: Type of detection

        Returns:
            Adjusted threshold for current conditions
        """
        if self._last_analysis is None:
            return base_threshold

        level = self._last_analysis.light_level
        thresholds = self._EDGE_THRESHOLDS.get(level, (40, 120))

        if detection_type == "edge":
            return thresholds[0]
        elif detection_type == "color":
            # Color detection needs lower threshold in dark
            factor = 1.0 - self._last_analysis.adaptation_factor * 0.3
            return int(base_threshold * factor)
        else:
            return base_threshold

    def force_night_mode(self, enabled: bool) -> None:
        """Manually enable/disable night mode."""
        self._current_settings = NightModeSettings(
            brightness_threshold=self._current_settings.brightness_threshold,
            contrast_boost=self._current_settings.contrast_boost,
            saturation_boost=self._current_settings.saturation_boost,
            edge_threshold=self._current_settings.edge_threshold,
            color_gain=self._current_settings.color_gain,
            enabled=enabled,
        )

    def reset(self) -> None:
        """Reset adapter state."""
        self._baseline_brightness = 0.5
        self._adaptation_history.clear()
        self._current_settings = self._create_default_settings()
        self._last_analysis = None

    def _create_default_settings(self) -> NightModeSettings:
        """Create default night mode settings."""
        return NightModeSettings(
            brightness_threshold=0.3,
            contrast_boost=1.2,
            saturation_boost=1.2,
            edge_threshold=30,
            color_gain=1.1,
            enabled=False,
        )