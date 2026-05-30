"""Tests for character progression knowledge and build planner."""
from __future__ import annotations

import pytest

from knowledge.genshin_character_progression import (
    EXP_BOOKS,
    MORA_PER_EXP,
    AscensionMats,
    AR_BREAKTHROUGHS,
    BUILD_INVESTMENT_PRIORITY,
    CHARACTER_TALENT_BOOKS,
    GEM_NAMES,
    BOSS_MATERIALS,
    TALENT_BOOK_DOMAINS,
    TALENT_BOOK_SCHEDULE,
    WEEKLY_BOSSES,
    books_available_today,
    exp_to_level,
    get_ascension_cost,
    get_talent_cost,
    total_ascension_mats_to_level,
)
from planning.character_build_planner import (
    AcquisitionPlan,
    BuildPlan,
    CharacterBuildPlanner,
    CharacterState,
    MaterialCategory,
    MaterialNeed,
)


# ---------------------------------------------------------------------------
# Character progression knowledge tests
# ---------------------------------------------------------------------------

class TestExpBooks:
    def test_heros_wit_value(self) -> None:
        assert EXP_BOOKS["heros_wit"].exp_value == 20000

    def test_mora_costs_exist(self) -> None:
        for book_id in EXP_BOOKS:
            assert book_id in MORA_PER_EXP

    def test_exp_to_level(self) -> None:
        assert exp_to_level(1) == 0
        assert exp_to_level(20) == 13_395
        assert exp_to_level(90) == 1_677_405

    def test_exp_to_level_clamps(self) -> None:
        assert exp_to_level(0) == 0
        assert exp_to_level(-1) == 0


class TestAscensionMats:
    def test_level_20_cost(self) -> None:
        cost = get_ascension_cost(20)
        assert cost is not None
        assert cost.mora == 2000
        assert cost.gem_sliver == 1
        assert cost.boss_material == 0

    def test_level_80_cost(self) -> None:
        cost = get_ascension_cost(80)
        assert cost is not None
        assert cost.gem_gemstone == 6
        assert cost.boss_material == 20
        assert cost.mora == 60000

    def test_invalid_level_returns_none(self) -> None:
        assert get_ascension_cost(30) is None
        assert get_ascension_cost(100) is None

    def test_total_mats_to_level_40(self) -> None:
        mats = total_ascension_mats_to_level(40, "Pyro")
        # Only ascension at 20 needed to reach level 40 (20 ascension unlocks 21-40)
        assert mats["mora"] == 2000
        assert "Agnidus Agate Sliver" in mats

    def test_total_mats_to_level_60(self) -> None:
        mats = total_ascension_mats_to_level(60, "Pyro")
        # Ascensions at 20 + 40 + 50 needed
        assert mats["mora"] == 42000  # 2000 + 20000 + 20000
        assert "Everflame Seed" in mats

    def test_total_mats_all_elements(self) -> None:
        for element in ("Pyro", "Hydro", "Electro", "Cryo", "Anemo", "Geo", "Dendro"):
            mats = total_ascension_mats_to_level(40, element)
            assert mats["mora"] > 0
            assert len(mats) > 2


class TestTalentCosts:
    def test_level_1_to_2(self) -> None:
        cost = get_talent_cost(1)
        assert cost is not None
        assert cost.book_teachings == 3
        assert cost.mora == 12500

    def test_level_9_to_10(self) -> None:
        cost = get_talent_cost(9)
        assert cost is not None
        assert cost.crown is True
        assert cost.boss_material == 2
        assert cost.mora == 700000

    def test_boss_mats_from_level_7(self) -> None:
        cost = get_talent_cost(7)
        assert cost is not None
        assert cost.boss_material == 1

    def test_invalid_level_returns_none(self) -> None:
        assert get_talent_cost(0) is None
        assert get_talent_cost(10) is None


class TestTalentBookSchedule:
    def test_monday_books(self) -> None:
        books = books_available_today(0)
        assert "Freedom" in books
        assert "Prosperity" in books

    def test_sunday_all_available(self) -> None:
        books = books_available_today(6)
        assert len(books) > 10  # all books

    def test_character_book_mapping(self) -> None:
        assert CHARACTER_TALENT_BOOKS["bennett"] == "Resistance"
        assert CHARACTER_TALENT_BOOKS["kaeya"] == "Ballad"

    def test_gem_names_complete(self) -> None:
        for element in ("Pyro", "Hydro", "Electro", "Cryo", "Anemo", "Geo", "Dendro"):
            assert element in GEM_NAMES
            assert len(GEM_NAMES[element]) == 4


class TestWeeklyBosses:
    def test_boss_data_exists(self) -> None:
        assert len(WEEKLY_BOSSES) >= 4

    def test_resin_costs(self) -> None:
        for boss in WEEKLY_BOSSES.values():
            assert boss.resin_discount == 30
            assert boss.full_cost == 60

    def test_talent_drops(self) -> None:
        dvalin = WEEKLY_BOSSES["dvalin"]
        assert len(dvalin.talent_materials) == 3


class TestARBreakthroughs:
    def test_breakthroughs_exist(self) -> None:
        assert 25 in AR_BREAKTHROUGHS
        assert 35 in AR_BREAKTHROUGHS
        assert 45 in AR_BREAKTHROUGHS

    def test_team_recommendations(self) -> None:
        for ar, bt in AR_BREAKTHROUGHS.items():
            assert len(bt.recommended_team) == 4


class TestBuildInvestmentPriority:
    def test_weapon_first(self) -> None:
        assert BUILD_INVESTMENT_PRIORITY[0]["category"] == "weapon_level"

    def test_ordered_by_roi(self) -> None:
        rois = [item["roi"] for item in BUILD_INVESTMENT_PRIORITY]
        assert rois == sorted(rois, reverse=True)


# ---------------------------------------------------------------------------
# Build Planner tests
# ---------------------------------------------------------------------------

class TestMaterialNeed:
    def test_gap_calculation(self) -> None:
        need = MaterialNeed("heros_wit", "Hero's Wit", MaterialCategory.EXP_BOOK, 10, 3)
        assert need.gap == 7
        assert not need.satisfied

    def test_satisfied(self) -> None:
        need = MaterialNeed("mora", "Mora", MaterialCategory.MORA, 100, 200)
        assert need.gap == 0
        assert need.satisfied


class TestCharacterBuildPlanner:
    def _planner(self) -> CharacterBuildPlanner:
        return CharacterBuildPlanner()

    def test_plan_character_basic(self) -> None:
        planner = self._planner()
        state = CharacterState(character_id="xiangling", level=20, weapon_level=20)
        plan = planner.plan_character(state, target_level=40)
        assert plan.character_id == "xiangling"
        assert plan.target_level == 40
        assert plan.mora_estimate > 0

    def test_plan_max_level_clamp(self) -> None:
        planner = self._planner()
        state = CharacterState(character_id="bennett", level=70)
        plan = planner.plan_character(state)
        assert plan.target_level <= 90

    def test_plan_no_overlevel(self) -> None:
        planner = self._planner()
        state = CharacterState(character_id="kaeya", level=80)
        plan = planner.plan_character(state, target_level=60)
        # Should not need ascension mats if already past target
        assert plan.target_level == 60

    def test_acquisition_plan(self) -> None:
        planner = self._planner()
        state = CharacterState(character_id="xiangling", level=1, weapon_level=1)
        plan = planner.plan_character(state, target_level=40)
        acq = planner.generate_acquisition_plan(plan)
        assert len(acq.tasks) > 0
        assert acq.total_resin >= 0

    def test_prioritize_characters(self) -> None:
        planner = self._planner()
        chars = [
            CharacterState("bennett", level=40, weapon_level=20),
            CharacterState("xiangling", level=60, weapon_level=60),
            CharacterState("xingqiu", level=30, weapon_level=10),
        ]
        ranked = planner.prioritize_characters(chars)
        assert len(ranked) == 3
        # Bennett should be first (BUILD_PRIORITY[0]) and undergeared
        assert ranked[0][0] == "bennett"

    def test_plan_uses_build_talent_priority(self) -> None:
        planner = self._planner()
        state = CharacterState(character_id="xiangling", level=40, weapon_level=40)
        plan = planner.plan_character(state)
        # Xiangling's talent priority: burst > skill > normal
        assert "burst" in plan.talent_targets
        assert plan.talent_targets["burst"] >= plan.talent_targets.get("normal_attack", 0)

    def test_unsatisfied_needs(self) -> None:
        planner = self._planner()
        state = CharacterState(character_id="amber", level=1, weapon_level=1)
        plan = planner.plan_character(state, target_level=20)
        unsatisfied = plan.unsatisfied_needs
        assert len(unsatisfied) > 0  # new character will always have gaps


class TestAcquisitionPlan:
    def test_tasks_sorted(self) -> None:
        acq = AcquisitionPlan("xiangling")
        from planning.character_build_planner import AcquisitionTask
        acq.tasks = [
            AcquisitionTask("domain", "B", 20, {}, 30),
            AcquisitionTask("boss", "A", 40, {}, 10),
        ]
        sorted_tasks = acq.tasks_by_priority()
        assert sorted_tasks[0].priority == 10

    def test_empty_plan(self) -> None:
        acq = AcquisitionPlan("xiangling")
        assert acq.total_resin == 0
        assert len(acq.tasks_by_priority()) == 0
