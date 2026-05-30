"""Tests for P2 combat enhancement modules."""
from __future__ import annotations

import pytest

from combat.coop_combat_manager import CoopModeDetector, TeamSyncManager
from combat.weakpoint_system import WeakpointTargetingSystem
from combat.energy_optimizer import EnergyRechargeOptimizer
from combat.enrage_timer import EnrageMechanismHandler, EnrageTimerConfig
from combat.reaction_damage_calc import ReactionDamageCalculator, ReactionType, Element


class TestCoopModeDetector:
    def test_can_be_instantiated(self) -> None:
        det = CoopModeDetector()
        assert det is not None


class TestTeamSyncManager:
    def test_can_be_instantiated(self) -> None:
        mgr = TeamSyncManager()
        assert mgr is not None


class TestWeakpointTargetingSystem:
    def test_can_be_instantiated(self) -> None:
        sys = WeakpointTargetingSystem()
        assert sys is not None


class TestEnergyRechargeOptimizer:
    def test_can_be_instantiated(self) -> None:
        opt = EnergyRechargeOptimizer()
        assert opt is not None


class TestEnrageMechanismHandler:
    def test_config_required(self) -> None:
        config = EnrageTimerConfig(time_limit_sec=480.0)
        assert config.time_limit_sec == 480.0


class TestReactionDamageCalculator:
    def test_can_be_instantiated(self) -> None:
        calc = ReactionDamageCalculator()
        assert calc is not None

    def test_reaction_type_enum(self) -> None:
        assert ReactionType.VAPORIZE is not None
        assert ReactionType.MELT is not None

    def test_element_enum(self) -> None:
        assert Element.PYRO is not None
        assert Element.HYDRO is not None
        assert Element.CRYO is not None