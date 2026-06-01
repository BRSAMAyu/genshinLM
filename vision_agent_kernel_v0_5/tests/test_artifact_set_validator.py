"""Tests for ArtifactSetValidator — R-32 artifact set matching."""
from __future__ import annotations

import pytest

from combat.artifact_set_validator import (
    ArtifactSetResult,
    ArtifactSetValidator,
    _normalize_set_name,
    _parse_set_spec,
)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


class TestParseSetSpec:
    def test_single_4pc(self) -> None:
        result = _parse_set_spec("Emblem of Severed Fate 4pc")
        assert result == [("Emblem of Severed Fate", 4)]

    def test_two_2pc(self) -> None:
        result = _parse_set_spec("Noblesse Oblige 2pc + Crimson Witch 2pc")
        assert result == [("Noblesse Oblige", 2), ("Crimson Witch", 2)]

    def test_empty_string(self) -> None:
        assert _parse_set_spec("") == []

    def test_no_piece_count(self) -> None:
        assert _parse_set_spec("Emblem of Severed Fate") == []


class TestNormalizeSetName:
    def test_lowercase_and_strip(self) -> None:
        assert _normalize_set_name("  Emblem of Severed Fate  ") == "emblem of severed fate"

    def test_hyphen_to_space(self) -> None:
        assert _normalize_set_name("Ocean-Hued Clam") == "ocean hued clam"

    def test_apostrophe_removed(self) -> None:
        assert _normalize_set_name("Gladiator's Finale") == "gladiators finale"


# ---------------------------------------------------------------------------
# Single character validation
# ---------------------------------------------------------------------------


class TestArtifactSetValidator:
    def test_exact_4pc_match(self) -> None:
        v = ArtifactSetValidator()
        result = v.validate("xiangling", ["Emblem of Severed Fate"])
        assert result.matched
        assert result.match_score >= 0.9
        assert not result.warnings

    def test_alt_set_match(self) -> None:
        v = ArtifactSetValidator()
        result = v.validate("xiangling", ["Noblesse Oblige", "Crimson Witch"])
        assert result.matched
        assert result.match_score >= 0.5

    def test_no_match(self) -> None:
        v = ArtifactSetValidator()
        result = v.validate("xiangling", ["Blizzard Strayer"])
        assert not result.matched
        assert result.match_score < 0.5
        assert any("don't match" in w.lower() for w in result.warnings)

    def test_unknown_character(self) -> None:
        v = ArtifactSetValidator()
        result = v.validate("nonexistent_char", ["Some Set"])
        assert not result.matched
        assert any("unknown" in w.lower() for w in result.warnings)

    def test_no_detected_sets(self) -> None:
        v = ArtifactSetValidator()
        result = v.validate("bennett", [])
        assert not result.matched
        assert result.match_score == 0.0
        assert len(result.warnings) > 0
        assert "no artifact" in result.warnings[0].lower() or "cannot validate" in result.warnings[0].lower()

    def test_fuzzy_match_partial_name(self) -> None:
        v = ArtifactSetValidator()
        # "Emblem" should match "Emblem of Severed Fate"
        result = v.validate("xiangling", ["Emblem"])
        assert result.matched

    def test_bennett_noblesse_match(self) -> None:
        v = ArtifactSetValidator()
        result = v.validate("bennett", ["Noblesse Oblige"])
        assert result.matched
        assert result.match_score >= 0.9

    def test_bennett_alt_emblem(self) -> None:
        v = ArtifactSetValidator()
        result = v.validate("bennett", ["Emblem of Severed Fate"])
        assert result.matched

    def test_fischl_golden_troupe(self) -> None:
        v = ArtifactSetValidator()
        result = v.validate("fischl", ["Golden Troupe"])
        assert result.matched

    def test_result_dataclass_fields(self) -> None:
        v = ArtifactSetValidator()
        result = v.validate("xiangling", ["Emblem of Severed Fate"])
        assert isinstance(result, ArtifactSetResult)
        assert result.character_id == "xiangling"
        assert 0.0 <= result.match_score <= 1.0
        assert isinstance(result.detected_sets, tuple)
        assert isinstance(result.warnings, tuple)
        assert isinstance(result.matched, bool)


# ---------------------------------------------------------------------------
# Team validation
# ---------------------------------------------------------------------------


class TestTeamValidation:
    def test_team_all_match(self) -> None:
        v = ArtifactSetValidator()
        results = v.validate_team(
            ["xiangling", "bennett"],
            [["Emblem of Severed Fate"], ["Noblesse Oblige"]],
        )
        assert len(results) == 2
        assert all(r.matched for r in results)

    def test_team_mixed(self) -> None:
        v = ArtifactSetValidator()
        results = v.validate_team(
            ["xiangling", "bennett"],
            [["Emblem of Severed Fate"], ["Blizzard Strayer"]],
        )
        assert results[0].matched
        assert not results[1].matched

    def test_team_unknown_char(self) -> None:
        v = ArtifactSetValidator()
        results = v.validate_team(
            ["fake_char"],
            [["Some Set"]],
        )
        assert len(results) == 1
        assert not results[0].matched
