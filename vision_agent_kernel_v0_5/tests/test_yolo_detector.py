from __future__ import annotations

import numpy as np

from perception.yolo_detector import YoloDetector, YoloDetectorConfig


class FakeBox:
    def __init__(self) -> None:
        self.xyxy = [np.array([10.0, 20.0, 30.0, 60.0])]
        self.conf = np.array([0.75])
        self.cls = np.array([2])


class FakeResult:
    names = {2: "target"}

    def __init__(self) -> None:
        self.boxes = [FakeBox()]


class FakeModel:
    def predict(self, *args, **kwargs):
        return [FakeResult()]


def test_yolo_detector_outputs_target_candidates() -> None:
    detector = YoloDetector(
        YoloDetectorConfig(model_path="unused.pt"),
        model=FakeModel(),
    )

    candidates = detector.detect(np.zeros((720, 1280, 3), dtype=np.uint8), frame_id=7)

    assert len(candidates) == 1
    assert candidates[0].frame_id == 7
    assert candidates[0].class_id == "target"
    assert candidates[0].bbox_xyxy == (10.0, 20.0, 30.0, 60.0)
    assert candidates[0].center_px == (20.0, 40.0)
    assert candidates[0].area_px == 800.0
