"""Tests for perception/genshin_combat_detector.py — CombatSignal enrichment."""
from __future__ import annotations

import time

import numpy as np
import pytest

from perception.genshin_combat_detector import GenshinCombatDetector
from perception.fusion_runtime import CombatSignal


def _make_frame(w=1920, h=1080) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def _make_shield_frame(element: str, w=1920, h=1080) -> np.ndarray:
    """Create a frame with a shield aura in the enemy ROI area."""
    frame = _make_frame(w, h)
    # OpenCV HSV H range: 0-179 (half of standard 0-360)
    hsv_colors = {
        "hydro": (100, 200, 200),    # matches _SHIELD_HYDRO H=90-115
        "pyro": (5, 200, 200),       # matches _SHIELD_PYRO H=0-10
        "cryo": (95, 150, 180),      # matches _SHIELD_CRYO H=85-105
        "electro": (120, 200, 200),   # matches _SHIELD_ELECTRO H=100-135
    }
    h_val, s_val, v_val = hsv_colors.get(element, (0, 0, 0))

    hsv_frame = np.zeros((h, w, 3), dtype=np.uint8)
    # Fill enemy ROI area with shield color
    hsv_frame[100:600, 200:1600] = [h_val, s_val, v_val]

    # Convert HSV to BGR
    bgr = cv2.cvtColor(hsv_frame, cv2.COLOR_HSV2BGR)
    return bgr


try:
    import cv2
except ImportError:
    cv2 = None


class TestGenshinCombatDetector:

    def test_instantiate(self) -> None:
        d = GenshinCombatDetector()
        assert d._viewport == (1920, 1080)

    def test_detect_returns_combat_signal(self) -> None:
        if cv2 is None:
            pytest.skip("cv2 not available")
        d = GenshinCombatDetector()
        frame = _make_frame()
        signal = d.detect(frame)
        assert isinstance(signal, CombatSignal)

    def test_detect_no_shield_on_black_frame(self) -> None:
        if cv2 is None:
            pytest.skip("cv2 not available")
        d = GenshinCombatDetector()
        frame = _make_frame()
        signal = d.detect(frame)
        assert signal.enemy_shield_element == ""

    def test_detect_shield_hydro(self) -> None:
        if cv2 is None:
            pytest.skip("cv2 not available")
        d = GenshinCombatDetector()
        frame = _make_shield_frame("hydro")
        signal = d.detect(frame)
        assert signal.enemy_shield_element == "hydro"

    def test_detect_shield_pyro(self) -> None:
        if cv2 is None:
            pytest.skip("cv2 not available")
        d = GenshinCombatDetector()
        frame = _make_shield_frame("pyro")
        signal = d.detect(frame)
        assert signal.enemy_shield_element == "pyro"

    def test_detect_boss_phase_default(self) -> None:
        if cv2 is None:
            pytest.skip("cv2 not available")
        d = GenshinCombatDetector()
        frame = _make_frame()
        signal = d.detect(frame)
        assert signal.boss_phase == 1
        assert signal.boss_enraged is False

    def test_detect_hitstun_no_false_positive(self) -> None:
        if cv2 is None:
            pytest.skip("cv2 not available")
        d = GenshinCombatDetector()
        frame = _make_frame()
        signal = d.detect(frame)
        assert signal.incoming_hitstun is False

    def test_detect_stamina_on_black_frame(self) -> None:
        if cv2 is None:
            pytest.skip("cv2 not available")
        d = GenshinCombatDetector()
        frame = _make_frame()
        signal = d.detect(frame)
        assert 0.0 <= signal.player_stamina_ratio <= 1.0

    def test_danger_score_bounds(self) -> None:
        if cv2 is None:
            pytest.skip("cv2 not available")
        d = GenshinCombatDetector()
        frame = _make_frame()
        signal = d.detect(frame)
        assert 0.0 <= signal.danger_score <= 1.0

    def test_scale_roi(self) -> None:
        scaled = GenshinCombatDetector._scale_roi((100, 50, 200, 100), 2.0, 2.0)
        assert scaled == (200, 100, 400, 200)

    def test_detect_combat_signal_has_frame_id(self) -> None:
        """Verify detect() returns signal compatible with fusion_runtime injection."""
        if cv2 is None:
            pytest.skip("cv2 not available")
        d = GenshinCombatDetector()
        frame = _make_frame()
        signal = d.detect(frame)
        # frame_id and timestamp are set by fusion_runtime after detect()
        assert hasattr(signal, "frame_id")
        assert hasattr(signal, "timestamp")

    def test_detect_electro_shield(self) -> None:
        if cv2 is None:
            pytest.skip("cv2 not available")
        d = GenshinCombatDetector()
        frame = _make_shield_frame("electro")
        signal = d.detect(frame)
        assert signal.enemy_shield_element == "electro"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
