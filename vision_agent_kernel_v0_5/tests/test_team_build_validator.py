"""Tests for TeamBuildValidator — R-33 combat safety checks."""
from __future__ import annotations

import pytest

from combat.boss_schema import BossProfile
from combat.team_build_validator import TeamBuildValidator, TeamValidationResult
from combat.team_capability import CharacterCapability, TeamProfile


def _char(
    cid: str = "test_char",
    slot: int = 1,
    element: str = "pyro",
    role: str = "dps",
    survival_tools: list[str] | None = None,
    known: bool = True,
) -> CharacterCapability:
    return CharacterCapability(
        character_id=cid,
        slot=slot,
        element=element,
        role=role,
        survival_tools=survival_tools or [],
        known=known,
    )


def _team(chars: list[CharacterCapability]) -> TeamProfile:
    return TeamProfile(characters=chars)


def _boss(
    boss_id: str = "test_boss",
    resistances: dict[str, float] | None = None,
    recommended: list[str] | None = None,
) -> BossProfile:
    return BossProfile(
        boss_id=boss_id,
        display_name="Test Boss",
        phases=[],
        attack_patterns={},
        recommended_reactions=recommended or [],
        elemental_resistance=resistances or {},
    )


def test_empty_team_blocked() -> None:
    v = TeamBuildValidator()
    result = v.validate(_team([]))
    assert not result.valid
    assert not result.safe_to_proceed
    assert any("empty" in b.lower() for b in result.blockers)
    assert result.safety_score == 0.0


def test_team_with_healer_passes() -> None:
    v = TeamBuildValidator()
    team = _team([
        _char("dps", 1, "pyro", "dps"),
        _char("healer", 2, "hydro", "healer", survival_tools=["heal"]),
        _char("sub", 3, "cryo", "sub_dps"),
        _char("support", 4, "anemo", "support"),
    ])
    result = v.validate(team)
    assert result.valid
    assert result.safe_to_proceed
    assert result.safety_score >= 0.7


def test_team_with_shielder_passes() -> None:
    v = TeamBuildValidator()
    team = _team([
        _char("dps", 1, "pyro", "dps"),
        _char("shield", 2, "geo", "shielder", survival_tools=["shield"]),
        _char("sub", 3, "cryo", "sub_dps"),
        _char("support", 4, "hydro", "support"),
    ])
    result = v.validate(team)
    assert result.valid
    assert result.safety_score >= 0.5


def test_team_no_sustain_warns() -> None:
    v = TeamBuildValidator()
    team = _team([
        _char("dps1", 1, "pyro", "dps"),
        _char("dps2", 2, "hydro", "dps"),
        _char("dps3", 3, "cryo", "dps"),
        _char("dps4", 4, "electro", "dps"),
    ])
    result = v.validate(team)
    assert result.valid  # warnings don't block by default
    assert any("sustain" in w.lower() for w in result.warnings)


def test_strict_mode_blocks_no_sustain() -> None:
    v = TeamBuildValidator()
    team = _team([
        _char("dps1", 1, "pyro", "dps"),
        _char("dps2", 2, "hydro", "dps"),
    ])
    result = v.validate(team, strict=True)
    assert not result.valid
    assert any("sustain" in b.lower() for b in result.blockers)


def test_all_unknown_blocked() -> None:
    v = TeamBuildValidator()
    team = _team([
        _char("unk1", 1, "unknown", "unknown", known=False),
        _char("unk2", 2, "unknown", "unknown", known=False),
    ])
    result = v.validate(team)
    assert not result.valid
    assert any("unknown" in b.lower() for b in result.blockers)


def test_boss_elemental_resistance_warning() -> None:
    v = TeamBuildValidator()
    team = _team([
        _char("dps", 1, "pyro", "dps"),
        _char("healer", 2, "hydro", "healer", survival_tools=["heal"]),
    ])
    boss = _boss(resistances={"pyro": 0.8})
    result = v.validate(team, boss=boss)
    assert any("resists" in w.lower() for w in result.warnings)


def test_boss_recommended_reactions_missing() -> None:
    v = TeamBuildValidator()
    team = _team([
        _char("dps", 1, "geo", "dps"),
        _char("healer", 2, "geo", "healer", survival_tools=["heal"]),
    ])
    boss = _boss(recommended=["Vaporize", "Melt"])
    result = v.validate(team, boss=boss)
    assert any("recommended" in w.lower() for w in result.warnings)


def test_boss_recommended_reactions_present() -> None:
    v = TeamBuildValidator()
    team = _team([
        _char("dps", 1, "pyro", "dps"),
        _char("sub", 2, "hydro", "sub_dps"),
        _char("healer", 3, "cryo", "healer", survival_tools=["heal"]),
    ])
    boss = _boss(recommended=["Vaporize"])
    result = v.validate(team, boss=boss)
    assert not any("recommended" in w.lower() for w in result.warnings)


def test_empty_slot_warning() -> None:
    v = TeamBuildValidator()
    team = _team([
        _char("dps", 1, "pyro", "dps"),
        _char("healer", 2, "hydro", "healer", survival_tools=["heal"]),
    ])
    result = v.validate(team)
    assert any("slot" in w.lower() for w in result.warnings)


def test_safety_score_bounded() -> None:
    v = TeamBuildValidator()
    team = _team([
        _char("dps", 1, "pyro", "dps"),
        _char("healer", 2, "hydro", "healer", survival_tools=["heal"]),
        _char("sub", 3, "cryo", "sub_dps"),
        _char("shield", 4, "geo", "shielder", survival_tools=["shield"]),
    ])
    result = v.validate(team)
    assert 0.0 <= result.safety_score <= 1.0
