from __future__ import annotations

import numpy as np

from perception.visual_trigger_detector import VisualTriggerDetector, VisualTriggerDetectorConfig


def test_visual_trigger_detector_detects_green_center_trigger() -> None:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[330:394, 608:672] = (20, 220, 80)
    detector = VisualTriggerDetector(VisualTriggerDetectorConfig(centered_threshold_px=80.0))

    track = detector.detect_target(frame, frame_id=7, timestamp=1.0)
    triggers = detector.detect_triggers(frame, track)

    assert track is not None
    assert track.appearance_signature == {"color_state": "GREEN"}
    assert triggers["target_visible"]
    assert triggers["target_centered"]
    assert triggers["target_visible_and_centered"]
    assert triggers["target_color_green"]
    assert triggers["in_range_estimated"]
    assert triggers["visual_action_completed"]


def test_visual_trigger_detector_red_target_is_not_green() -> None:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[330:394, 608:672] = (220, 20, 20)
    detector = VisualTriggerDetector(VisualTriggerDetectorConfig(centered_threshold_px=80.0))

    track = detector.detect_target(frame, frame_id=8, timestamp=1.0)
    triggers = detector.detect_triggers(frame, track)

    assert track is not None
    assert triggers["target_visible"]
    assert triggers["target_centered"]
    assert not triggers["target_color_green"]
