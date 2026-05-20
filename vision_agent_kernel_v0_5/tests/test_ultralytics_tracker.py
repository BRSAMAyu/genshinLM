from __future__ import annotations

import math

import numpy as np

from perception.ultralytics_tracker import UltralyticsTracker, UltralyticsTrackerConfig


class FakeBox:
    def __init__(self, xyxy, track_id: int, confidence: float = 0.8) -> None:
        self.xyxy = [np.array(xyxy, dtype=float)]
        self.id = np.array([track_id], dtype=float)
        self.conf = np.array([confidence], dtype=float)
        self.cls = np.array([1], dtype=float)


class FakeResult:
    names = {1: "target"}

    def __init__(self, boxes) -> None:
        self.boxes = boxes


class FakeModel:
    def __init__(self) -> None:
        self.results = [
            [FakeResult([FakeBox([10.0, 20.0, 30.0, 60.0], 42)])],
            [FakeResult([FakeBox([20.0, 20.0, 40.0, 60.0], 42)])],
            [FakeResult([])],
        ]
        self.calls = 0

    def track(self, *args, **kwargs):
        result = self.results[self.calls]
        self.calls += 1
        return result


def test_ultralytics_tracker_outputs_track_and_coasts() -> None:
    tracker = UltralyticsTracker(
        UltralyticsTrackerConfig(model_path="unused.pt", tracker="botsort.yaml"),
        model=FakeModel(),
    )
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    first = tracker.update(frame, frame_id=1, timestamp=1.0)
    second = tracker.update(frame, frame_id=2, timestamp=1.1)
    coasting = tracker.update(frame, frame_id=3, timestamp=1.2)

    assert first is not None
    assert first.track_id == "42"
    assert first.state == "TRACKED"
    assert second is not None
    assert math.isclose(second.velocity_px_s[0], 100.0, abs_tol=1e-9)
    assert second.velocity_px_s[1] == 0.0
    assert coasting is not None
    assert coasting.state == "COASTING"
    assert coasting.smoothed_center_px[0] > second.smoothed_center_px[0]
