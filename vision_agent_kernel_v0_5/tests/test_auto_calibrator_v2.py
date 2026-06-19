"""Tests for AutoCalibratorV2."""
from __future__ import annotations

import numpy as np

from perception.auto_calibrator_v2 import AutoCalibratorV2, Landmark


class _MockVLM:
    def __init__(self, description: str = "") -> None:
        self.description = description

    def describe_image(self, image: object, prompt: str) -> object:
        return _MockResult(self.description)

    def ground_ui(self, image: object, description: str) -> object:
        return _MockResult("")


class _MockResult:
    def __init__(self, description: str) -> None:
        self.description = description


class TestAutoCalibratorV2:
    def test_no_vlm_returns_heuristic_landmarks(self) -> None:
        cal = AutoCalibratorV2(vlm=None)
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = cal.calibrate(frame, game_id="test")
        assert len(result.landmarks) >= 3  # heuristic fallback

    def test_vlm_json_parsing(self) -> None:
        response = '[{"name": "hp", "type": "health_bar", "bbox": [0.3, 0.9, 0.7, 0.95]}]'
        vlm = _MockVLM(description=response)
        cal = AutoCalibratorV2(vlm=vlm)
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = cal.calibrate(frame, game_id="test")
        assert len(result.landmarks) >= 1
        assert result.landmarks[0].name == "hp"

    def test_fallback_heuristic_landmarks(self) -> None:
        vlm = _MockVLM(description="no json here")
        cal = AutoCalibratorV2(vlm=vlm)
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = cal.calibrate(frame, game_id="test")
        assert len(result.landmarks) >= 3  # health_bar, minimap, skill_icons

    def test_profile_stored(self) -> None:
        cal = AutoCalibratorV2(vlm=None)
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cal.calibrate(frame, game_id="genshin")
        profile = cal.get_profile("genshin")
        assert profile is not None
        assert profile.game_id == "genshin"

    def test_get_landmark(self) -> None:
        cal = AutoCalibratorV2(vlm=None)
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cal.calibrate(frame, game_id="test")
        hp = cal.get_landmark("test", "health_bar")
        assert hp is not None
        assert hp.element_type == "health_bar"

    def test_screen_resolution_recorded(self) -> None:
        cal = AutoCalibratorV2(vlm=None)
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = cal.calibrate(frame, game_id="test")
        assert result.screen_resolution == (1280, 720)
