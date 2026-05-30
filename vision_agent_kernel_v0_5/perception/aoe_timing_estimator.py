"""AoE timing estimator: predict safe dodge windows from visual AoE indicators.

Tracks active AoE warning circles on the ground and estimates time-to-impact
based on animation speed and circle fill rate, enabling predictive dodging
instead of reactive dodging.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AoEWarning:
    """An active AoE warning zone on screen."""
    center_x: float
    center_y: float
    radius: float
    fill_ratio: float      # 0.0-1.0, how filled the warning circle is
    aoe_type: str = ""     # "circle", "line", "cone", "cross"
    element: str = ""      # "pyro", "cryo", "electro", "hydro", "none"
    timestamp: float = 0.0


@dataclass(frozen=True, slots=True)
class DodgeWindow:
    """Estimated safe dodge window for an AoE attack."""
    time_to_impact: float   # Seconds until AoE deals damage
    safe_direction: str     # "left", "right", "away", "any"
    urgency: str            # "immediate", "soon", "caution"
    aoe_type: str = ""


@dataclass(slots=True)
class AoETimingState:
    """Tracking state for AoE timing estimation."""
    warnings: list[AoEWarning] = field(default_factory=list)
    last_update: float = 0.0
    dodge_count: int = 0
    hit_count: int = 0


class AoETimingEstimator:
    """Estimate dodge windows from AoE visual indicators.

    Uses fill-ratio progression rate to predict time-to-impact:
    - Circle AoE: fill_ratio increases linearly ~0.3/sec
    - Line AoE: appears instantly, ~1.5s to damage
    - Cone AoE: fill_ratio increases ~0.4/sec

    When time_to_impact < dodge_threshold, recommends immediate dodge.
    """

    FILL_RATE_CIRCLE: float = 0.30   # fill_ratio per second
    FILL_RATE_CONE: float = 0.40
    FILL_RATE_LINE: float = 1.0      # Instant appearance
    DODGE_THRESHOLD: float = 0.4     # Dodge when < 0.4s to impact
    MAX_TRACKED: int = 10
    HISTORY_WINDOW: float = 2.0      # Keep warnings for 2s

    def __init__(self) -> None:
        self._state = AoETimingState()

    def update(self, warnings: list[AoEWarning]) -> list[DodgeWindow]:
        """Update with current frame's AoE warnings and return dodge recommendations."""
        now = time.perf_counter()
        self._state.last_update = now

        # Merge new warnings with existing, trim old
        self._state.warnings = [
            w for w in self._state.warnings
            if now - w.timestamp < self.HISTORY_WINDOW
        ]
        self._state.warnings.extend(warnings)
        if len(self._state.warnings) > self.MAX_TRACKED:
            self._state.warnings = self._state.warnings[-self.MAX_TRACKED:]

        # Calculate dodge windows for each warning
        windows: list[DodgeWindow] = []
        for w in self._state.warnings:
            tti = self._estimate_tti(w, now)
            if tti is None:
                continue
            urgency = self._classify_urgency(tti)
            direction = self._recommend_direction(w)
            windows.append(DodgeWindow(
                time_to_impact=tti,
                safe_direction=direction,
                urgency=urgency,
                aoe_type=w.aoe_type,
            ))

        # Sort by urgency (lowest TTI first)
        windows.sort(key=lambda dw: dw.time_to_impact)
        return windows

    def _estimate_tti(self, warning: AoEWarning, now: float) -> float | None:
        """Estimate time-to-impact from fill ratio and AoE type."""
        remaining = 1.0 - warning.fill_ratio
        if remaining <= 0.0:
            return 0.0

        rate = {
            "circle": self.FILL_RATE_CIRCLE,
            "cone": self.FILL_RATE_CONE,
            "line": self.FILL_RATE_LINE,
            "cross": self.FILL_RATE_CIRCLE,
        }.get(warning.aoe_type, self.FILL_RATE_CIRCLE)

        tti = remaining / rate
        # Clamp to reasonable range
        return max(0.0, min(tti, 5.0))

    def _classify_urgency(self, tti: float) -> str:
        if tti < self.DODGE_THRESHOLD:
            return "immediate"
        if tti < 1.0:
            return "soon"
        return "caution"

    def _recommend_direction(self, warning: AoEWarning) -> str:
        """Recommend dodge direction based on AoE position relative to screen center."""
        # If AoE is on left side of screen, dodge right and vice versa
        if warning.center_x < 0.4:
            return "right"
        if warning.center_x > 0.6:
            return "left"
        # If centered, dodge away (backward)
        return "away"

    def record_dodge(self, successful: bool) -> None:
        if successful:
            self._state.dodge_count += 1
        else:
            self._state.hit_count += 1

    @property
    def dodge_rate(self) -> float:
        total = self._state.dodge_count + self._state.hit_count
        if total == 0:
            return 0.0
        return self._state.dodge_count / total

    @property
    def stats(self) -> dict[str, int]:
        return {
            "dodges": self._state.dodge_count,
            "hits": self._state.hit_count,
            "active_warnings": len(self._state.warnings),
        }
