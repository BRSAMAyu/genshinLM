"""Tests for Genshin visual detectors."""
from __future__ import annotations

import numpy as np
import pytest

from perception.genshin_visual_detectors import (
    BossPhaseDetection,
    BossPhaseIndicator,
    ChestDetection,
    ChestQuality,
    CountdownTimer,
    ElementalAuraDetection,
    ElementType,
    EnvironmentGauge,
    GenshinVisualDetector,
    StaminaBarState,
)


def _make_frame(h: int = 1080, w: int = 1920, color: tuple[int, int, int] = (0, 0, 0)) -> np.ndarray:
    return np.full((h, w, 3), color, dtype=np.uint8)


def _fill_roi(frame: np.ndarray, roi: tuple[int, int, int, int],
              color: tuple[int, int, int]) -> None:
    x1, y1, x2, y2 = roi
    frame[y1:y2, x1:x2] = color


class TestBossPhaseDetection:
    def test_dark_frame_idle(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        result = det.detect_boss_phase(frame)
        assert result.phase == BossPhaseIndicator.IDLE

    def test_boss_hp_bar_aggressive(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        # Fill boss HP bar region with yellow-ish (HP bar visible but no glow)
        _fill_roi(frame, (400, 30, 1520, 80), (40, 140, 220))
        result = det.detect_boss_phase(frame)
        assert result.phase in (BossPhaseIndicator.AGGRESSIVE, BossPhaseIndicator.TRANSITIONING)

    def test_invulnerable_glow(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        # HP bar + heavy yellow glow (invulnerable indicator)
        _fill_roi(frame, (400, 30, 1520, 80), (0, 220, 255))  # BGR: bright yellow
        result = det.detect_boss_phase(frame)
        assert result.phase == BossPhaseIndicator.INVULNERABLE

    def test_enraged_red(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        # HP bar on left half, red glow on right half
        _fill_roi(frame, (400, 30, 960, 80), (40, 140, 220))  # yellow HP bar
        _fill_roi(frame, (960, 30, 1520, 80), (0, 0, 220))    # red enraged glow
        result = det.detect_boss_phase(frame)
        assert result.phase == BossPhaseIndicator.ENRAGED


class TestElementalAuraDetection:
    def test_no_aura_empty_frame(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        result = det.detect_elemental_auras(frame)
        assert len(result) == 0

    def test_pyro_aura_detected(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        # Fill center region with red (Pyro glow)
        _fill_roi(frame, (800, 400, 1120, 600), (0, 50, 240))
        result = det.detect_elemental_auras(frame, target_roi=(800, 400, 1120, 600))
        assert len(result) >= 1
        elements = [d.element for d in result]
        assert ElementType.PYRO in elements

    def test_hydro_aura_detected(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        # Blue glow (Hydro)
        _fill_roi(frame, (800, 400, 1120, 600), (230, 100, 30))
        result = det.detect_elemental_auras(frame, target_roi=(800, 400, 1120, 600))
        assert len(result) >= 1

    def test_sorted_by_intensity(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        _fill_roi(frame, (800, 400, 1120, 600), (0, 50, 240))
        result = det.detect_elemental_auras(frame, target_roi=(800, 400, 1120, 600))
        if len(result) > 1:
            for i in range(len(result) - 1):
                assert result[i].intensity >= result[i + 1].intensity


class TestEnvironmentGauge:
    def test_no_gauge(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        result = det.detect_environment_gauge(frame)
        assert result.gauge_type == "none"
        assert not result.is_active

    def test_sheer_cold_gauge(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        # Fill env gauge ROI with blue (Sheer Cold)
        _fill_roi(frame, (10, 700, 60, 900), (200, 150, 30))
        result = det.detect_environment_gauge(frame)
        assert result.gauge_type == "sheer_cold"
        assert result.is_active

    def test_balethunder_gauge(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        # Fill with purple (Balethunder)
        _fill_roi(frame, (10, 700, 60, 900), (200, 50, 150))
        result = det.detect_environment_gauge(frame)
        assert result.gauge_type == "balethunder"
        assert result.is_active


class TestStaminaBar:
    def test_no_stamina(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        result = det.detect_stamina_bar(frame)
        assert not result.is_visible

    def test_stamina_visible(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        # Fill stamina ROI with yellow (stamina bar)
        _fill_roi(frame, (870, 910, 1050, 940), (0, 220, 220))
        result = det.detect_stamina_bar(frame)
        assert result.is_visible
        assert result.ratio > 0.0


class TestCountdownTimer:
    def test_no_timer(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        result = det.detect_countdown_timer(frame)
        assert not result.is_active

    def test_timer_active(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        # Fill timer ROI with yellow (timer text)
        _fill_roi(frame, (800, 50, 1120, 130), (0, 200, 220))
        result = det.detect_countdown_timer(frame)
        assert result.is_active


class TestChestQuality:
    def test_no_chest(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        result = det.detect_chest_quality(frame, (800, 400, 900, 500))
        assert result is None

    def test_common_chest(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        # Brown/wood color
        _fill_roi(frame, (800, 400, 900, 500), (20, 100, 140))
        result = det.detect_chest_quality(frame, (800, 400, 900, 500))
        assert result is not None
        assert result.quality == ChestQuality.COMMON

    def test_luxurious_chest(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        # Gold glow
        _fill_roi(frame, (800, 400, 900, 500), (0, 200, 240))
        result = det.detect_chest_quality(frame, (800, 400, 900, 500))
        assert result is not None
        assert result.quality == ChestQuality.LUXURIOUS

    def test_chest_position(self) -> None:
        det = GenshinVisualDetector()
        frame = _make_frame()
        _fill_roi(frame, (800, 400, 900, 500), (0, 200, 240))
        result = det.detect_chest_quality(frame, (800, 400, 900, 500))
        assert result is not None
        assert result.position == (850, 450)


class TestFrozenDataclass:
    def test_boss_phase_frozen(self) -> None:
        d = BossPhaseDetection(BossPhaseIndicator.IDLE, 0.5, 0.0)
        with pytest.raises(AttributeError):
            d.confidence = 0.9  # type: ignore[misc]

    def test_stamina_frozen(self) -> None:
        s = StaminaBarState(0.8, True)
        with pytest.raises(AttributeError):
            s.ratio = 0.5  # type: ignore[misc]

    def test_countdown_frozen(self) -> None:
        c = CountdownTimer(60.0, True)
        with pytest.raises(AttributeError):
            c.seconds_remaining = 30  # type: ignore[misc]

    def test_chest_frozen(self) -> None:
        c = ChestDetection(ChestQuality.PRECIOUS, (100, 200))
        with pytest.raises(AttributeError):
            c.quality = ChestQuality.COMMON  # type: ignore[misc]
