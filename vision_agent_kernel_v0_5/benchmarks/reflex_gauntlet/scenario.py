from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.timebase import Timebase
from perception.capture_base import FramePacket


@dataclass(slots=True)
class ReflexScenario:
    name: str
    description: str
    danger_delay_frames: int  # frames before danger appears
    danger_type: str  # "ground", "projectile", "hp_drop", "occlusion", "repeated", "false_positive"
    danger_duration_frames: int  # frames danger persists
    expected_dodges: int
    expected_false_clears: int = 0


SCENARIOS = [
    ReflexScenario("ground_danger", "Ground danger zone appears", 10, "ground", 20, 1),
    ReflexScenario("projectile_danger", "Projectile approaching", 15, "projectile", 15, 1),
    ReflexScenario("hp_drop_danger", "HP sudden drop signal", 20, "hp_drop", 10, 1),
    ReflexScenario("target_occlusion", "Target occluded during danger", 10, "occlusion", 25, 1),
    ReflexScenario("repeated_danger", "Repeated danger with cooldown", 10, "repeated", 60, 3),
    ReflexScenario(
        "false_positive",
        "Danger false positive",
        10,
        "false_positive",
        0,
        0,
        expected_false_clears=0,
    ),
]


def create_frame_for_scenario(
    scenario: ReflexScenario,
    frame_id: int,
    timebase: Timebase,
    danger_active: bool,
) -> FramePacket:
    """Create a synthetic frame for the given scenario."""
    image = np.zeros((360, 640, 3), dtype=np.uint8)
    # Always draw target (green box)
    x = 280
    image[150:210, x : x + 80, 1] = 200
    image[150:210, x : x + 80, 0] = 50
    image[150:210, x : x + 80, 2] = 50

    if danger_active:
        if scenario.danger_type in ("ground", "repeated"):
            # Red danger zone at bottom
            image[240:350, 200:440, 2] = 200
            image[240:350, 200:440, 1] = 50
            image[240:350, 200:440, 0] = 50
        elif scenario.danger_type == "projectile":
            # Moving red blob
            px = 100 + frame_id * 30
            if px < 500:
                image[150:200, px : px + 40, 2] = 200
                image[150:200, px : px + 40, 1] = 50
        elif scenario.danger_type in ("hp_drop", "occlusion"):
            # Red tint overlay
            image[0:60, :, 2] = 100

    return FramePacket(
        frame_id=frame_id,
        timestamp=timebase.now(),
        image=image,
        source_size=(640, 360),
    )


def compute_danger_score_for_frame(
    scenario: ReflexScenario,
    frame_id: int,
    danger_active: bool,
) -> float:
    """Compute a synthetic danger score for the given scenario state.

    Returns a value in [0.0, 1.0].
    """
    if not danger_active:
        return 0.0
    if scenario.danger_type == "false_positive":
        return 0.1  # below threshold always
    # Danger is active; produce a high score
    if scenario.danger_type == "repeated":
        # Pulse: danger blinks on/off every 10 frames
        cycle_pos = (frame_id - scenario.danger_delay_frames) % 20
        if cycle_pos < 10:
            return 0.8
        return 0.0
    return 0.8
