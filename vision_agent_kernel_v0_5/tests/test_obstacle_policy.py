from __future__ import annotations

import numpy as np

from control.obstacle_policy import ObstaclePolicy
from core.types import ObstacleField
from perception.depth_base import HeuristicObstacleEstimator


def test_heuristic_obstacle_estimator_outputs_sectors() -> None:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[300:550, 580:660, :] = (90, 100, 150)
    field = HeuristicObstacleEstimator().estimate(frame, frame_id=1, timestamp=1.0)

    assert set(field.sectors) == {"front", "front_left", "front_right", "left", "right"}
    assert field.sectors["front"] > 0.0


def test_obstacle_policy_reroutes_when_front_blocked() -> None:
    field = ObstacleField(
        frame_id=1,
        timestamp=1.0,
        sectors={"front": 0.8, "front_left": 0.2, "front_right": 0.7, "left": 0.1, "right": 0.5},
        confidence=0.8,
        source="unit",
    )

    decision = ObstaclePolicy().decide(field)

    assert decision.action == "LOCAL_REROUTE"
    assert decision.movement_intent is not None
    assert decision.movement_intent.move_right == 1.0
