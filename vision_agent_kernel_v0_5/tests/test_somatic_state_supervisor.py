"""Tests for control/sentinel/somatic_state_supervisor.py."""
from __future__ import annotations

import pytest

from control.sentinel.somatic_state_supervisor import (
    SomaticStateSupervisor,
    SomaticConfig,
    StaminaZone,
    HealthZone,
    HazardLevel,
    VitalSigns,
)


class TestSomaticConfig:
    def test_defaults(self) -> None:
        cfg = SomaticConfig()
        assert cfg.stamina_full_threshold == 0.80
        assert cfg.stamina_normal_threshold == 0.40
        assert cfg.stamina_low_threshold == 0.15
        assert cfg.stamina_critical_threshold == 0.05
        assert cfg.health_full_threshold == 0.80
        assert cfg.health_critical_threshold == 0.20
        assert cfg.food_cooldown_sec == 15.0


class TestSomaticStateSupervisor:
    def test_instantiation(self) -> None:
        sup = SomaticStateSupervisor()
        assert sup is not None

    def test_stamina_zones(self) -> None:
        sup = SomaticStateSupervisor()
        assert StaminaZone.FULL is not None
        assert StaminaZone.CRITICAL is not None
        assert StaminaZone.EMPTY is not None

    def test_health_zones(self) -> None:
        assert HealthZone.FULL is not None
        assert HealthZone.CRITICAL is not None
        assert HealthZone.DEAD is not None

    def test_hazard_levels(self) -> None:
        assert HazardLevel.SAFE is not None
        assert HazardLevel.DANGER is not None
        assert HazardLevel.LETHAL is not None

    def test_recovery_mode_default_false(self) -> None:
        sup = SomaticStateSupervisor()
        assert sup.recovery_mode is False

    def test_hazard_level_default_safe(self) -> None:
        sup = SomaticStateSupervisor()
        assert sup.hazard_level == HazardLevel.SAFE

    def test_default_state_no_frame(self) -> None:
        sup = SomaticStateSupervisor()
        state = sup.check_frame(None, frame_id=0)
        assert state.stamina_ratio > 0
        assert state.health_ratio > 0
        assert state.stamina_zone == StaminaZone.FULL
        assert state.recovery_mode is False

    def test_reset(self) -> None:
        sup = SomaticStateSupervisor()
        sup._recovery_mode = True
        sup.reset()
        assert sup.recovery_mode is False

    def test_check_frame_returns_somatic_state(self) -> None:
        sup = SomaticStateSupervisor()
        state = sup.check_frame(None)
        assert isinstance(state, VitalSigns)
        assert state.timestamp > 0
        assert state.recommended_action != ""

    def test_config_custom_thresholds(self) -> None:
        cfg = SomaticConfig(
            stamina_full_threshold=0.90,
            stamina_low_threshold=0.10,
            health_critical_threshold=0.25,
        )
        assert cfg.stamina_full_threshold == 0.90
        assert cfg.stamina_low_threshold == 0.10
        assert cfg.health_critical_threshold == 0.25
        sup = SomaticStateSupervisor(config=cfg)
        state = sup.check_frame(None)
        assert state.stamina_ratio > 0

    def test_oxygen_and_buffer_fields(self) -> None:
        sup = SomaticStateSupervisor()
        state = sup.check_frame(None)
        assert hasattr(state, "oxygen_ratio")
        assert hasattr(state, "stamina_buffer")
        assert state.oxygen_ratio == 1.0
        assert state.stamina_buffer == 1.0

    def test_oxygen_bar_detector_with_mock_frame(self) -> None:
        import numpy as np
        sup = SomaticStateSupervisor()
        mock_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        # Verify it runs without error
        ratio = sup._detect_oxygen_bar(mock_frame)
        assert 0.0 <= ratio <= 1.0