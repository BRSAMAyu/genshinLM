from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from interaction.ui_anchor import NormalizedRect


MousePathMode = Literal["straight", "bezier", "jitter_bounded", "instant"]
ActionFamily = Literal[
    "ui_click",
    "fallback_visual_agent",
    "calibration",
    "navigation_hold",
    "combat_reflex",
    "system",
]


@dataclass(frozen=True, slots=True)
class CoordinateMapper:
    """Map normalized window coordinates into viewport pixel coordinates."""

    viewport: tuple[int, int]

    def norm_to_px(self, point: tuple[float, float]) -> tuple[int, int]:
        x, y = point
        width, height = self.viewport
        return (round(max(0.0, min(1.0, x)) * width), round(max(0.0, min(1.0, y)) * height))

    def rect_center_px(self, rect: NormalizedRect) -> tuple[int, int]:
        return self.norm_to_px(rect.center_norm())


@dataclass(frozen=True, slots=True)
class MousePath:
    mode: MousePathMode
    points: list[tuple[int, int]]
    duration_ms: int
    coordinate_space: str = "viewport_px"


@dataclass(frozen=True, slots=True)
class MousePathPolicy:
    mode: MousePathMode = "bezier"
    steps: int = 12
    duration_ms: int = 160
    max_jitter_px: int = 2

    def build_path(self, start: tuple[int, int], end: tuple[int, int]) -> MousePath:
        if self.mode == "instant":
            return MousePath(self.mode, [end], 0)
        if self.steps <= 1 or self.mode == "straight":
            return MousePath(self.mode, [start, end], self.duration_ms)
        
        import random
        points: list[tuple[int, int]] = []
        sx, sy = start
        ex, ey = end
        
        # Calculate human-like Cubic Bezier control points ( Minimum Jerk biological model )
        deviation = abs(ex - sx) * 0.08
        c1x = sx + (ex - sx) * 0.25 + random.uniform(-deviation, deviation)
        c1y = sy + (ey - sy) * 0.25 - abs(ex - sx) * 0.04 + random.uniform(-deviation, deviation)
        c2x = sx + (ex - sx) * 0.75 + random.uniform(-deviation, deviation)
        c2y = sy + (ey - sy) * 0.75 + abs(ex - sx) * 0.04 + random.uniform(-deviation, deviation)
        
        for i in range(self.steps + 1):
            t = i / self.steps
            if self.mode in {"bezier", "jitter_bounded"}:
                # Cubic Bezier C2 continuous curve
                x = (1.0 - t)**3 * sx + 3.0 * (1.0 - t)**2 * t * c1x + 3.0 * (1.0 - t) * t**2 * c2x + t**3 * ex
                y = (1.0 - t)**3 * sy + 3.0 * (1.0 - t)**2 * t * c1y + 3.0 * (1.0 - t) * t**2 * c2y + t**3 * ey
            else:
                x = sx + (ex - sx) * t
                y = sy + (ey - sy) * t
            
            if self.mode == "jitter_bounded" and 0 < i < self.steps:
                # Biological micro-tremor model
                tremor_x = random.uniform(-self.max_jitter_px, self.max_jitter_px)
                tremor_y = random.uniform(-self.max_jitter_px, self.max_jitter_px)
                x += tremor_x
                y += tremor_y
            points.append((round(x), round(y)))
            
        # Non-deterministic timing jitter per path
        jittered_duration = max(20, self.duration_ms + random.randint(-15, 15))
        return MousePath(self.mode, points, jittered_duration)


def mouse_policy_for_action_family(action_family: ActionFamily, *, dry_run: bool = False) -> MousePathPolicy:
    """Return the single canonical mouse policy for an action family.

    This prevents each controller from inventing its own motion style. `instant`
    is only returned for dry-run/testbed paths; live execution should always
    produce auditable intermediate points.
    """

    if dry_run:
        return MousePathPolicy(mode="instant", steps=1, duration_ms=0, max_jitter_px=0)
    if action_family == "ui_click":
        return MousePathPolicy(mode="bezier", steps=12, duration_ms=160, max_jitter_px=2)
    if action_family == "fallback_visual_agent":
        return MousePathPolicy(mode="jitter_bounded", steps=16, duration_ms=220, max_jitter_px=2)
    if action_family == "calibration":
        return MousePathPolicy(mode="straight", steps=6, duration_ms=120, max_jitter_px=0)
    if action_family == "navigation_hold":
        return MousePathPolicy(mode="straight", steps=2, duration_ms=60, max_jitter_px=0)
    if action_family == "combat_reflex":
        return MousePathPolicy(mode="straight", steps=2, duration_ms=35, max_jitter_px=0)
    return MousePathPolicy(mode="bezier", steps=10, duration_ms=140, max_jitter_px=1)


@dataclass(frozen=True, slots=True)
class ClickReceipt:
    anchor_id: str
    click_point: tuple[int, int]
    path: MousePath
    pre_click_frame_id: int | None = None
    post_click_frame_id: int | None = None
    coordinate_space: str = "viewport_px"
    evidence_ids: list[str] = field(default_factory=list)
