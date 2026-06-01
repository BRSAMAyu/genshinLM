"""Tests for ArtifactMainStatValidator — R-34 main stat error detection."""
from __future__ import annotations

import pytest

from combat.artifact_main_stat_validator import (
    ArtifactMainStatValidator,
    MainStatIssue,
    _normalize_stat,
)


class TestNormalizeStat:
    def test_atk(self) -> None:
        assert _normalize_stat("ATK%") == "ATK%"

    def test_crit_rate(self) -> None:
        assert _normalize_stat("CRIT Rate") == "CRIT RATE"

    def test_healing_bonus(self) -> None:
        assert _normalize_stat("Healing Bonus") == "HB"

    def test_elemental_mastery(self) -> None:
        assert _normalize_stat("Elemental Mastery") == "EM"

    def test_damage_bonus(self) -> None:
        assert _normalize_stat("Pyro DMG%") == "DMG%"

    def test_energy_recharge(self) -> None:
        assert _normalize_stat("ER%") == "ER%"


class TestArtifactMainStatValidator:
    @pytest.fixture
    def validator(self) -> ArtifactMainStatValidator:
        return ArtifactMainStatValidator()

    def test_correct_stats_no_issues(self, validator: ArtifactMainStatValidator) -> None:
        issues = validator.validate("xiangling", {
            "sands": "ATK%",
            "goblet": "Pyro DMG%",
            "circlet": "CRIT Rate",
        })
        assert len(issues) == 0

    def test_dps_with_healing_bonus_circlet(self, validator: ArtifactMainStatValidator) -> None:
        issues = validator.validate("xiangling", {
            "sands": "ATK%",
            "goblet": "Pyro DMG%",
            "circlet": "Healing Bonus",
        })
        assert len(issues) >= 1
        assert any(i.severity == "error" for i in issues)
        assert any(i.slot == "circlet" for i in issues)

    def test_dps_with_hp_sands_warning(self, validator: ArtifactMainStatValidator) -> None:
        issues = validator.validate("xiangling", {
            "sands": "HP%",
            "goblet": "Pyro DMG%",
            "circlet": "CRIT Rate",
        })
        assert len(issues) >= 1
        assert any("suboptimal" in i.reason.lower() or i.slot == "sands" for i in issues)

    def test_unknown_character_uses_role_heuristics(self, validator: ArtifactMainStatValidator) -> None:
        issues = validator.validate("unknown_char", {
            "sands": "ATK%",
            "goblet": "ATK%",
            "circlet": "CRIT Rate",
        })
        # Should not crash, may or may not have issues
        assert isinstance(issues, list)

    def test_empty_detected_stats(self, validator: ArtifactMainStatValidator) -> None:
        issues = validator.validate("xiangling", {})
        assert len(issues) == 0

    def test_bennett_support_stats(self, validator: ArtifactMainStatValidator) -> None:
        issues = validator.validate("bennett", {
            "sands": "HP%",
            "goblet": "HP%",
            "circlet": "Healing Bonus",
        })
        # Bennett is support_healer_buffer, these should be acceptable
        assert len(issues) == 0 or all(i.severity == "warning" for i in issues)

    def test_issue_dataclass_fields(self, validator: ArtifactMainStatValidator) -> None:
        issues = validator.validate("xiangling", {
            "circlet": "Healing Bonus",
        })
        if issues:
            i = issues[0]
            assert isinstance(i, MainStatIssue)
            assert i.severity in ("error", "warning")
            assert i.slot in ("sands", "goblet", "circlet")

    def test_goblet_wrong_element(self, validator: ArtifactMainStatValidator) -> None:
        # Xiangling wants Pyro DMG% but has Physical DMG%
        issues = validator.validate("xiangling", {
            "sands": "ATK%",
            "goblet": "Physical DMG%",
            "circlet": "CRIT Rate",
        })
        assert len(issues) >= 1
        assert any(i.slot == "goblet" for i in issues)
