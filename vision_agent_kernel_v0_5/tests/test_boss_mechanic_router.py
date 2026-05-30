"""Tests for BossMechanicRouter: 7 major boss encounter mechanics."""
from __future__ import annotations

from typing import Any

from combat.boss_mechanic_router import (
    BossMechanicConfig,
    BossMechanicRouter,
    BossPhaseResult,
)
from execution.console_backend import ConsoleInputBackend


def test_all_7_bosses_defined():
    router = BossMechanicRouter(backend=ConsoleInputBackend())
    assert len(router.get_boss_phases("stormterror_dvalin")) == 3
    assert len(router.get_boss_phases("childe_tartaglia")) == 3
    assert len(router.get_boss_phases("la_signora")) == 2
    assert len(router.get_boss_phases("raiden_shogun_weekly")) == 2
    assert len(router.get_boss_phases("shouki_no_kami")) == 2
    assert len(router.get_boss_phases("all_devouring_narwhal")) == 2
    assert len(router.get_boss_phases("gosoythoth")) == 3


def test_unknown_boss_returns_failure():
    router = BossMechanicRouter(backend=ConsoleInputBackend())
    result = router.execute_boss_mechanics("unknown_boss")
    assert result.success is False
    assert result.phase == "unknown"


def test_dvalin_execution():
    router = BossMechanicRouter(backend=ConsoleInputBackend())
    result = router.execute_boss_mechanics("stormterror_dvalin")
    assert isinstance(result, BossPhaseResult)
    assert result.boss_id == "stormterror_dvalin"
    assert result.success is True
    assert result.duration_sec > 0


def test_childe_3_phases():
    router = BossMechanicRouter(backend=ConsoleInputBackend())
    result = router.execute_boss_mechanics("childe_tartaglia")
    assert result.success is True


def test_signora_temperature_mechanic():
    router = BossMechanicRouter(backend=ConsoleInputBackend())
    result = router.execute_boss_mechanics("la_signora")
    assert result.success is True


def test_scaramouche_engine_destruction():
    router = BossMechanicRouter(backend=ConsoleInputBackend())
    phases = router.get_boss_phases("shouki_no_kami")
    assert "normal" in phases
    assert "nirvana_engine" in phases
    result = router.execute_boss_mechanics("shouki_no_kami")
    assert result.success is True


def test_narwhal_dual_space():
    router = BossMechanicRouter(backend=ConsoleInputBackend())
    phases = router.get_boss_phases("all_devouring_narwhal")
    assert "surface" in phases
    assert "inside" in phases
    result = router.execute_boss_mechanics("all_devouring_narwhal")
    assert result.success is True


def test_gosoythoth_character_switch():
    router = BossMechanicRouter(backend=ConsoleInputBackend())
    phases = router.get_boss_phases("gosoythoth")
    assert "traveler_dps" in phases
    assert "mavuika_dps" in phases
    assert "heal_cycle" in phases
    result = router.execute_boss_mechanics("gosoythoth")
    assert result.success is True


def test_boss_weakness():
    router = BossMechanicRouter(backend=ConsoleInputBackend())
    weakness = router.get_boss_weakness("childe_tartaglia")
    assert "electro" in weakness
    assert "pyro" in weakness


def test_boss_phase_specific_weakness():
    router = BossMechanicRouter(backend=ConsoleInputBackend())
    weakness = router.get_boss_weakness("childe_tartaglia", phase="hydro_bow")
    assert "electro" in weakness
    assert "pyro" not in weakness


def test_config_max_retries():
    config = BossMechanicConfig(max_phase_retries=1)
    router = BossMechanicRouter(backend=ConsoleInputBackend(), config=config)
    result = router.execute_boss_mechanics("stormterror_dvalin")
    assert result.success is True
