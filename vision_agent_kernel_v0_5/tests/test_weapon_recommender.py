"""Tests for WeaponRecommender — R-37 alternative weapon selection."""
from __future__ import annotations

import pytest

from knowledge.weapon_recommender import WeaponRecommender, WeaponRecommendation


class TestWeaponRecommender:
    @pytest.fixture
    def rec(self) -> WeaponRecommender:
        return WeaponRecommender()

    def test_best_weapon_no_inventory(self, rec: WeaponRecommender) -> None:
        result = rec.recommend("xiangling")
        assert result.selected == "The Catch R5"
        assert result.rank == 0

    def test_best_weapon_available(self, rec: WeaponRecommender) -> None:
        result = rec.recommend("xiangling", ["The Catch R5", "Skyward Spine"])
        assert result.selected == "The Catch R5"
        assert result.rank == 0

    def test_first_alt_when_best_missing(self, rec: WeaponRecommender) -> None:
        result = rec.recommend("xiangling", ["Dragon's Bane", "Crescent Pike"])
        assert result.selected == "Dragon's Bane"
        assert result.rank == 1

    def test_second_alt_when_first_missing(self, rec: WeaponRecommender) -> None:
        result = rec.recommend("xiangling", ["Kitain Cross Spear"])
        assert result.selected == "Kitain Cross Spear"
        assert result.rank == 2

    def test_nothing_owned_returns_target(self, rec: WeaponRecommender) -> None:
        result = rec.recommend("xiangling", ["Skyward Spine"])
        assert result.best_weapon == "The Catch R5"
        assert "craft" in result.reason.lower() or "obtain" in result.reason.lower()

    def test_unknown_character(self, rec: WeaponRecommender) -> None:
        result = rec.recommend("nonexistent_char")
        assert result.selected == "unknown"
        assert "no build" in result.reason.lower()

    def test_fuzzy_match(self, rec: WeaponRecommender) -> None:
        result = rec.recommend("xiangling", ["catch"])  # Partial match
        assert result.selected == "The Catch R5"

    def test_team_recommendations(self, rec: WeaponRecommender) -> None:
        results = rec.recommend_team(["xiangling", "bennett"])
        assert len(results) == 2
        assert all(isinstance(r, WeaponRecommendation) for r in results)

    def test_bennett_best_weapon(self, rec: WeaponRecommender) -> None:
        result = rec.recommend("bennett")
        assert "Sapwood" in result.best_weapon

    def test_result_dataclass_fields(self, rec: WeaponRecommender) -> None:
        result = rec.recommend("xiangling")
        assert isinstance(result, WeaponRecommendation)
        assert isinstance(result.available_alternatives, tuple)
        assert isinstance(result.rank, int)
        assert 0.0 <= result.rank
