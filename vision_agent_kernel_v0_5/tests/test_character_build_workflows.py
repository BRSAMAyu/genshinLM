"""Tests for character build workflows and resource management (R-15~R-30, M-05~M-16)."""
from __future__ import annotations

import pytest

from planning.character_build_workflows import (
    ArtifactEval,
    ArtifactEvaluator,
    ArtifactSalvager,
    ArtifactSubstat,
    ArtifactTransmuter,
    CondensedResinCrafter,
    ElementGemConverter,
    ElementalResonance,
    ElementalResonanceCalculator,
    InventoryChecker,
    MaterialSynthesizer,
    ParametricTransformer,
    PartyManager,
    PartyPreset,
    RealmManager,
    SubstatType,
    TeamAdapter,
    WeaponRefinery,
    EnemyProfile,
)


# ---------------------------------------------------------------------------
# ArtifactEvaluator (R-20)
# ---------------------------------------------------------------------------
class TestArtifactEvaluator:
    def test_great_artifact(self) -> None:
        ev = ArtifactEvaluator()
        result = ev.evaluate([
            ArtifactSubstat(SubstatType.CRIT_RATE, 7.0, 7.8),
            ArtifactSubstat(SubstatType.CRIT_DMG, 14.0, 15.4),
            ArtifactSubstat(SubstatType.ATK_PERCENT, 5.0, 5.8),
            ArtifactSubstat(SubstatType.ENERGY_RECHARGE, 6.0, 6.5),
        ])
        assert result.is_great
        assert result.should_keep

    def test_bad_artifact(self) -> None:
        ev = ArtifactEvaluator()
        result = ev.evaluate([
            ArtifactSubstat(SubstatType.FLAT_HP, 50, 300),
            ArtifactSubstat(SubstatType.FLAT_DEF, 5, 30),
            ArtifactSubstat(SubstatType.FLAT_ATK, 3, 25),
        ])
        assert result.recommended_fodder
        assert not result.should_keep

    def test_empty_substats(self) -> None:
        ev = ArtifactEvaluator()
        result = ev.evaluate([])
        assert result.score == 0.0
        assert result.recommended_fodder

    def test_priority_stats_boost(self) -> None:
        ev = ArtifactEvaluator()
        subs = [
            ArtifactSubstat(SubstatType.CRIT_RATE, 5.0, 7.8),
            ArtifactSubstat(SubstatType.FLAT_HP, 50, 300),
        ]
        normal = ev.evaluate(subs)
        boosted = ev.evaluate(subs, priority_stats=[SubstatType.CRIT_RATE])
        assert boosted.score > normal.score

    def test_find_fodder(self) -> None:
        ev = ArtifactEvaluator()
        artifacts = [
            [ArtifactSubstat(SubstatType.CRIT_RATE, 7.0, 7.8)],       # good
            [ArtifactSubstat(SubstatType.FLAT_HP, 20, 300)],           # bad
            [ArtifactSubstat(SubstatType.FLAT_DEF, 3, 30)],            # bad
        ]
        fodder = ev.find_fodder(artifacts)
        assert 1 in fodder
        assert 2 in fodder
        assert 0 not in fodder


# ---------------------------------------------------------------------------
# WeaponRefinery (R-15)
# ---------------------------------------------------------------------------
class TestWeaponRefinery:
    def test_can_refine(self) -> None:
        ref = WeaponRefinery()
        assert ref.can_refine("sword", 1, 1)
        assert not ref.can_refine("sword", 5, 1)  # max refinement
        assert not ref.can_refine("sword", 1, 0)  # no dupes

    def test_refine_success(self) -> None:
        ref = WeaponRefinery()
        result = ref.refine("sword", 2, 1)
        assert result is not None
        assert result.new_refinement == 3
        assert result.duplicates_consumed == 1

    def test_refine_max(self) -> None:
        ref = WeaponRefinery()
        result = ref.refine("sword", 5, 1)
        assert result is None


# ---------------------------------------------------------------------------
# ArtifactSalvager (R-23)
# ---------------------------------------------------------------------------
class TestArtifactSalvager:
    def test_plan_salvage_5star(self) -> None:
        salvager = ArtifactSalvager()
        plan = salvager.plan_salvage("target", 5, 3)
        assert plan.estimated_xp == 3 * 2520
        assert plan.mora_cost > 0

    def test_plan_salvage_3star(self) -> None:
        salvager = ArtifactSalvager()
        plan = salvager.plan_salvage("target", 3, 5)
        assert plan.estimated_xp == 5 * 630

    def test_salvage_mora_per_xp(self) -> None:
        salvager = ArtifactSalvager()
        plan = salvager.plan_salvage("target", 5, 1)
        assert plan.mora_cost == plan.estimated_xp * 1  # MORA_PER_XP = 1


# ---------------------------------------------------------------------------
# ArtifactTransmuter (R-24)
# ---------------------------------------------------------------------------
class TestArtifactTransmuter:
    def test_plan_transmute_success(self) -> None:
        transmuter = ArtifactTransmuter()
        result = transmuter.plan_transmute(
            ["a1", "a2", "a3"], "crimson_witch", "sands"
        )
        assert result is not None
        assert len(result.input_artifacts) == 3
        assert result.target_set == "crimson_witch"

    def test_plan_transmute_insufficient(self) -> None:
        transmuter = ArtifactTransmuter()
        result = transmuter.plan_transmute(["a1"], "set", "sands")
        assert result is None

    def test_plan_transmute_rejects_non_5star(self) -> None:
        transmuter = ArtifactTransmuter()
        result = transmuter.plan_transmute(
            ["a1", "a2", "a3"], "crimson_witch", "sands",
            input_rarities=[5, 4, 5],
        )
        assert result is None

    def test_plan_transmute_accepts_all_5star(self) -> None:
        transmuter = ArtifactTransmuter()
        result = transmuter.plan_transmute(
            ["a1", "a2", "a3"], "crimson_witch", "sands",
            input_rarities=[5, 5, 5],
        )
        assert result is not None
        assert len(result.input_artifacts) == 3


# ---------------------------------------------------------------------------
# ElementalResonance (R-29)
# ---------------------------------------------------------------------------
class TestElementalResonance:
    def test_double_pyro(self) -> None:
        calc = ElementalResonanceCalculator()
        result = calc.get_active_resonances(["pyro", "pyro", "hydro", "anemo"])
        assert ElementalResonance.FERVENT_FLAMES in result
        assert len(result) == 1

    def test_double_dbl_element(self) -> None:
        calc = ElementalResonanceCalculator()
        result = calc.get_active_resonances(["pyro", "pyro", "hydro", "hydro"])
        assert ElementalResonance.FERVENT_FLAMES in result
        assert ElementalResonance.SOOTHING_WATERS in result
        assert len(result) == 2

    def test_no_resonance(self) -> None:
        calc = ElementalResonanceCalculator()
        result = calc.get_active_resonances(["pyro", "hydro", "electro", "cryo"])
        assert len(result) == 0


# ---------------------------------------------------------------------------
# TeamAdapter (R-30)
# ---------------------------------------------------------------------------
class TestTeamAdapter:
    def test_shield_counter_recommendation(self) -> None:
        adapter = TeamAdapter()
        enemy = EnemyProfile("boss", element_shield="hydro")
        recs = adapter.recommend_changes(["pyro", "anemo", "geo", "dendro"], enemy)
        assert len(recs) >= 1

    def test_no_change_needed(self) -> None:
        adapter = TeamAdapter()
        enemy = EnemyProfile("boss")
        recs = adapter.recommend_changes(["pyro", "hydro", "electro", "cryo"], enemy)
        assert len(recs) == 0


# ---------------------------------------------------------------------------
# CondensedResinCrafter (M-05)
# ---------------------------------------------------------------------------
class TestCondensedResinCrafter:
    def test_can_craft(self) -> None:
        crafter = CondensedResinCrafter()
        assert crafter.can_craft(40, 1)
        assert not crafter.can_craft(30, 1)
        assert not crafter.can_craft(40, 0)

    def test_craft_success(self) -> None:
        crafter = CondensedResinCrafter()
        assert crafter.craft(100, 5)

    def test_craft_fail(self) -> None:
        crafter = CondensedResinCrafter()
        assert not crafter.craft(30, 0)


# ---------------------------------------------------------------------------
# MaterialSynthesizer (M-07)
# ---------------------------------------------------------------------------
class TestMaterialSynthesizer:
    def test_can_synthesize(self) -> None:
        synth = MaterialSynthesizer()
        assert synth.can_synthesize(3)
        assert not synth.can_synthesize(2)

    def test_plan_synthesis(self) -> None:
        synth = MaterialSynthesizer()
        plan = synth.plan_synthesis("damaged_mask", 9)
        assert plan["operations"] == 3
        assert plan["output"] == 3

    def test_plan_insufficient(self) -> None:
        synth = MaterialSynthesizer()
        plan = synth.plan_synthesis("item", 2)
        assert plan["operations"] == 0


# ---------------------------------------------------------------------------
# ElementGemConverter (M-08)
# ---------------------------------------------------------------------------
class TestElementGemConverter:
    def test_plan_conversion(self) -> None:
        converter = ElementGemConverter()
        plan = converter.plan_conversion("pyro", "hydro", 3, 5)
        assert plan["gem_count"] == 5
        assert plan["dust_cost"] == 5


# ---------------------------------------------------------------------------
# PartyManager (R-27, R-28)
# ---------------------------------------------------------------------------
class TestPartyManager:
    def test_save_preset(self) -> None:
        mgr = PartyManager()
        preset = mgr.save_preset("p1", "Vape Team", ["hutao", "xingqiu", "sucrose", "bennett"])
        assert preset is not None
        assert preset.name == "Vape Team"

    def test_save_wrong_size(self) -> None:
        mgr = PartyManager()
        result = mgr.save_preset("p1", "Bad", ["hutao", "xingqiu"])
        assert result is None

    def test_load_preset(self) -> None:
        mgr = PartyManager()
        mgr.save_preset("p1", "Team 1", ["a", "b", "c", "d"])
        preset = mgr.load_preset("p1")
        assert preset is not None
        assert preset.is_active

    def test_load_nonexistent(self) -> None:
        mgr = PartyManager()
        assert mgr.load_preset("missing") is None

    def test_delete_preset(self) -> None:
        mgr = PartyManager()
        mgr.save_preset("p1", "Team 1", ["a", "b", "c", "d"])
        assert mgr.delete_preset("p1")
        assert mgr.load_preset("p1") is None

    def test_active_preset_tracking(self) -> None:
        mgr = PartyManager()
        mgr.save_preset("p1", "Team 1", ["a", "b", "c", "d"])
        mgr.save_preset("p2", "Team 2", ["e", "f", "g", "h"])
        mgr.load_preset("p1")
        assert mgr.active_preset is not None
        assert mgr.active_preset.preset_id == "p1"
        mgr.load_preset("p2")
        assert mgr.active_preset.preset_id == "p2"


# ---------------------------------------------------------------------------
# InventoryChecker (M-06)
# ---------------------------------------------------------------------------
class TestInventoryChecker:
    def test_update_and_check(self) -> None:
        inv = InventoryChecker()
        inv.update_item("mask_1", "Damaged Mask", 10, "material")
        assert inv.get_quantity("mask_1") == 10

    def test_check_materials_missing(self) -> None:
        inv = InventoryChecker()
        inv.update_item("a", "Item A", 3)
        missing = inv.check_materials({"a": 5, "b": 2})
        assert missing["a"] == 2
        assert missing["b"] == 2

    def test_check_materials_sufficient(self) -> None:
        inv = InventoryChecker()
        inv.update_item("a", "Item A", 10)
        missing = inv.check_materials({"a": 5})
        assert len(missing) == 0

    def test_items_by_category(self) -> None:
        inv = InventoryChecker()
        inv.update_item("m1", "Mat 1", 5, "material")
        inv.update_item("f1", "Food 1", 3, "food")
        inv.update_item("m2", "Mat 2", 7, "material")
        materials = inv.items_by_category("material")
        assert len(materials) == 2


# ---------------------------------------------------------------------------
# ParametricTransformer (M-15)
# ---------------------------------------------------------------------------
class TestParametricTransformer:
    def test_can_use(self) -> None:
        pt = ParametricTransformer()
        assert pt.can_use(7)
        assert not pt.can_use(6)

    def test_calculate_points(self) -> None:
        pt = ParametricTransformer()
        points = pt.calculate_points({"mat_a": 10, "mat_b": 5}, {"mat_a": 2, "mat_b": 3})
        assert points == 10 * 2 + 5 * 3

    def test_plan_submission(self) -> None:
        pt = ParametricTransformer()
        available = {"cheap_mat": 200}
        values = {"cheap_mat": 1}
        plan = pt.plan_submission(available, values)
        assert plan["cheap_mat"] == 150

    def test_plan_submission_uses_cheapest(self) -> None:
        pt = ParametricTransformer()
        available = {"expensive": 200, "cheap": 200}
        values = {"expensive": 10, "cheap": 1}
        plan = pt.plan_submission(available, values)
        # Should prefer cheap (value=1) over expensive (value=10)
        assert "cheap" in plan


# ---------------------------------------------------------------------------
# RealmManager (M-16)
# ---------------------------------------------------------------------------
class TestRealmManager:
    def test_should_collect(self) -> None:
        mgr = RealmManager()
        mgr.update_currency(2000)
        assert mgr.currency.should_collect

    def test_should_not_collect(self) -> None:
        mgr = RealmManager()
        mgr.update_currency(100)
        assert not mgr.currency.should_collect

    def test_collect(self) -> None:
        mgr = RealmManager()
        mgr.update_currency(1500)
        amount = mgr.collect()
        assert amount == 1500
        assert mgr.currency.current == 0
