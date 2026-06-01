"""Tests for perception/combat_perception.py — P2.1, P2.2, P2.3."""
from __future__ import annotations

import time

import numpy as np
import pytest

from perception.combat_perception import (
    EnemyHPBarDetector, EnemyHPReading, EnemyHPBar,
    CharacterSwitchDetector, CharacterSwitchState,
    StaminaTracker, StaminaReading,
)


def _make_frame(w=1920, h=1080) -> np.ndarray:
    """Create a real numpy frame that is subscriptable."""
    return np.zeros((h, w, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# P2.1: EnemyHPBarDetector
# ---------------------------------------------------------------------------

def test_enemy_hp_bar_detector_instantiate() -> None:
    d = EnemyHPBarDetector()
    assert d is not None
    assert d._viewport == (1920, 1080)


def test_enemy_hp_bar_detector_returns_reading() -> None:
    d = EnemyHPBarDetector()
    frame = _make_frame()
    reading = d.detect(frame, frame_id=1)
    assert isinstance(reading, EnemyHPReading)
    assert reading.frame_id == 1
    assert reading.timestamp > 0


def test_enemy_hp_bar_reading_fields() -> None:
    bar = EnemyHPBar(
        screen_x=0.5, screen_y=0.3,
        width_px=100.0, height_px=8.0,
        fill_ratio=0.7, bar_color="red",
        confidence=0.8, frame_id=10,
    )
    reading = EnemyHPReading(
        bars=(bar,),
        lowest_ratio=0.7,
        highest_ratio=0.7,
        count=1,
        has_shield=False,
        frame_id=10,
        timestamp=time.perf_counter(),
    )
    assert reading.count == 1
    assert reading.bars[0].fill_ratio == 0.7
    assert reading.lowest_ratio == 0.7


def test_enemy_hp_bar_scale_roi() -> None:
    d = EnemyHPBarDetector(viewport=(3840, 2160))
    scaled = d._scale_roi((100, 50, 200, 100), 2.0, 2.0)
    assert scaled == (200, 100, 400, 200)


# ---------------------------------------------------------------------------
# P2.2: CharacterSwitchDetector
# ---------------------------------------------------------------------------

def test_character_switch_detector_instantiate() -> None:
    d = CharacterSwitchDetector()
    assert d is not None


def test_character_switch_detector_returns_state() -> None:
    d = CharacterSwitchDetector()
    frame = _make_frame()
    state = d.detect(frame, frame_id=1)
    assert isinstance(state, CharacterSwitchState)
    assert hasattr(state, "visible")
    assert hasattr(state, "slot_count")
    assert hasattr(state, "slot_hp_pcts")


def test_character_switch_state_fields() -> None:
    state = CharacterSwitchState(
        visible=True,
        slot_count=4,
        selected_slot=2,
        slot_hp_pcts=(1.0, 0.8, 0.6, 0.9),
        frame_id=5,
    )
    assert state.visible is True
    assert state.slot_count == 4
    assert len(state.slot_hp_pcts) == 4


# ---------------------------------------------------------------------------
# P2.3: StaminaTracker
# ---------------------------------------------------------------------------

def test_stamina_tracker_instantiate() -> None:
    t = StaminaTracker()
    assert t is not None
    assert t._max_history == 30


def test_stamina_tracker_instantiate_with_history_size() -> None:
    t = StaminaTracker(history_size=10)
    assert t._max_history == 10


def test_stamina_tracker_returns_reading() -> None:
    t = StaminaTracker()
    frame = _make_frame()
    reading = t.detect(frame, frame_id=1)
    assert isinstance(reading, StaminaReading)
    assert 0.0 <= reading.ratio <= 1.0
    assert reading.activity in ("idle", "climbing", "swimming", "gliding", "running", "sprinting")


def test_stamina_tracker_is_critical() -> None:
    t = StaminaTracker()
    assert t.is_critical() is False
    frame = _make_frame()
    t.detect(frame, frame_id=1)
    # After detection, last_reading exists
    # is_critical depends on ratio < 0.2
    assert isinstance(t.is_critical(), bool)


def test_stamina_tracker_is_depleted() -> None:
    t = StaminaTracker()
    assert t.is_depleted() is False
    frame = _make_frame()
    t.detect(frame, frame_id=1)
    assert isinstance(t.is_depleted(), bool)


def test_stamina_reading_fields() -> None:
    r = StaminaReading(
        ratio=0.5,
        activity="running",
        critical=False,
        depleted=False,
        frame_id=10,
        timestamp=time.perf_counter(),
    )
    assert r.ratio == 0.5
    assert r.activity == "running"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])