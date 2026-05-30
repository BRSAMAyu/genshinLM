from __future__ import annotations

import numpy as np
import pytest

from combat.genshin_cooldown_manager import GenshinCooldownManager, SkillCooldownState
from combat.genshin_element_reactions import ElementReaction, GenshinReactionTable
from perception.region_aware_detector import RegionAwareDetector, RegionParams


# ---------------------------------------------------------------------------
# GenshinCooldownManager tests
# ---------------------------------------------------------------------------


class TestCooldownGreyedOutDetection:
    def test_greyed_out_detected(self) -> None:
        mgr = GenshinCooldownManager()
        grey = np.full((64, 64, 3), 80, dtype=np.uint8)
        is_greyed, conf = mgr._detect_greyed_out(grey)
        assert is_greyed is True
        assert conf > 0.0

    def test_colorful_not_greyed(self) -> None:
        mgr = GenshinCooldownManager()
        colorful = np.zeros((64, 64, 3), dtype=np.uint8)
        colorful[:, :, 1] = 200
        colorful[:, :, 0] = 50
        is_greyed, conf = mgr._detect_greyed_out(colorful)
        assert is_greyed is False

    def test_empty_roi(self) -> None:
        mgr = GenshinCooldownManager()
        is_greyed, conf = mgr._detect_greyed_out(np.ndarray((0, 0, 3), dtype=np.uint8))
        assert is_greyed is False


class TestCooldownElementGlowDetection:
    def test_glowing_detected(self) -> None:
        mgr = GenshinCooldownManager()
        glow = np.zeros((64, 64, 3), dtype=np.uint8)
        glow[:, :, 0] = 230
        glow[:, :, 1] = 100
        glow[:, :, 2] = 50
        is_glowing, conf = mgr._detect_element_glow(glow)
        assert is_glowing is True
        assert conf > 0.0

    def test_dim_not_glowing(self) -> None:
        mgr = GenshinCooldownManager()
        dim = np.full((64, 64, 3), 60, dtype=np.uint8)
        is_glowing, conf = mgr._detect_element_glow(dim)
        assert is_glowing is False

    def test_empty_roi(self) -> None:
        mgr = GenshinCooldownManager()
        is_glowing, conf = mgr._detect_element_glow(np.ndarray((0, 0, 3), dtype=np.uint8))
        assert is_glowing is False


class TestCooldownOcrNumber:
    def test_ocr_with_number(self) -> None:
        mgr = GenshinCooldownManager()
        dummy_roi = np.full((64, 64, 3), 128, dtype=np.uint8)
        state = mgr.update_from_ui("skill_e", dummy_roi, ocr_number=5)
        assert state.ready is False
        assert state.remaining_ms == 5000.0
        assert state.detection_method == "ocr"
        assert state.confidence == 0.95

    def test_ocr_zero_means_ready(self) -> None:
        mgr = GenshinCooldownManager()
        dummy_roi = np.full((64, 64, 3), 128, dtype=np.uint8)
        state = mgr.update_from_ui("skill_e", dummy_roi, ocr_number=0)
        assert state.ready is True
        assert state.remaining_ms == 0.0


class TestCooldownIsReadyDefault:
    def test_unknown_skill_is_ready(self) -> None:
        mgr = GenshinCooldownManager()
        assert mgr.is_ready("unknown_skill") is True

    def test_get_state_default(self) -> None:
        mgr = GenshinCooldownManager()
        state = mgr.get_state("nonexistent")
        assert state.ready is True
        assert state.confidence == 0.0
        assert state.detection_method == "unknown"


# ---------------------------------------------------------------------------
# RegionAwareDetector tests
# ---------------------------------------------------------------------------


class TestRegionDetectMondstadt:
    def test_green_frame_mondstadt(self) -> None:
        det = RegionAwareDetector()
        green = np.zeros((720, 1280, 3), dtype=np.uint8)
        green[:, :, 0] = 80
        green[:, :, 1] = 130
        green[:, :, 2] = 30
        region = det.detect_region(green)
        assert region == "mondstadt"


class TestRegionDetectLiyue:
    def test_amber_frame_liyue(self) -> None:
        det = RegionAwareDetector()
        amber = np.zeros((720, 1280, 3), dtype=np.uint8)
        amber[:, :, 0] = 220
        amber[:, :, 1] = 109
        amber[:, :, 2] = 30
        region = det.detect_region(amber)
        assert region == "liyue"


class TestRegionDetectNatlan:
    def test_red_frame_natlan(self) -> None:
        det = RegionAwareDetector()
        red = np.zeros((720, 1280, 3), dtype=np.uint8)
        red[:, :, 0] = 220
        red[:, :, 1] = 40
        red[:, :, 2] = 40
        region = det.detect_region(red)
        assert region == "natlan"


class TestRegionAdjustSaturation:
    def test_mondstadt_boost(self) -> None:
        det = RegionAwareDetector()
        green = np.zeros((720, 1280, 3), dtype=np.uint8)
        green[:, :, 0] = 80
        green[:, :, 1] = 130
        green[:, :, 2] = 30
        det.detect_region(green)
        adjusted = det.adjust_saturation_threshold(0.5)
        params = det.get_params()
        assert adjusted == 0.5 + params.min_saturation_boost

    def test_unknown_region_no_boost(self) -> None:
        det = RegionAwareDetector()
        adjusted = det.adjust_saturation_threshold(0.5)
        assert adjusted == 0.5


# ---------------------------------------------------------------------------
# GenshinReactionTable tests
# ---------------------------------------------------------------------------


class TestReactionVaporize:
    def test_pyro_on_hydro(self) -> None:
        table = GenshinReactionTable()
        r = table.get_reaction("pyro", "hydro")
        assert r is not None
        assert r.name == "Vaporize"
        assert r.damage_multiplier == 2.0
        assert r.tactical_value == "High"

    def test_reverse_vaporize(self) -> None:
        table = GenshinReactionTable()
        r = table.get_reaction("hydro", "pyro")
        assert r is not None
        assert r.name == "Vaporize_Reverse"
        assert r.damage_multiplier == 1.5

    def test_no_reaction(self) -> None:
        table = GenshinReactionTable()
        r = table.get_reaction("geo", "geo")
        assert r is None

    def test_swirl_any(self) -> None:
        table = GenshinReactionTable()
        r = table.get_reaction("anemo", "pyro")
        assert r is not None
        assert r.name == "Swirl"


class TestReactionShieldCounter:
    def test_pyro_shield(self) -> None:
        table = GenshinReactionTable()
        assert table.get_shield_counter("pyro") == "hydro"

    def test_hydro_shield(self) -> None:
        table = GenshinReactionTable()
        assert table.get_shield_counter("hydro") == "cryo"

    def test_cryo_shield(self) -> None:
        table = GenshinReactionTable()
        assert table.get_shield_counter("cryo") == "pyro"

    def test_electro_shield(self) -> None:
        table = GenshinReactionTable()
        assert table.get_shield_counter("electro") == "pyro"

    def test_dendro_shield(self) -> None:
        table = GenshinReactionTable()
        assert table.get_shield_counter("dendro") == "pyro"

    def test_geo_shield_returns_none(self) -> None:
        table = GenshinReactionTable()
        assert table.get_shield_counter("geo") == "none"

    def test_anemo_shield_returns_none(self) -> None:
        table = GenshinReactionTable()
        assert table.get_shield_counter("anemo") == "none"

    def test_unknown_shield_returns_unknown(self) -> None:
        table = GenshinReactionTable()
        assert table.get_shield_counter("unknown_element") == "unknown"


class TestReactionTeamReactions:
    def test_pyro_hydro_team(self) -> None:
        table = GenshinReactionTable()
        reactions = table.get_team_reactions(["pyro", "hydro"])
        names = [r.name for r in reactions]
        assert "Vaporize" in names
        assert "Vaporize_Reverse" in names

    def test_single_element_no_reactions(self) -> None:
        table = GenshinReactionTable()
        reactions = table.get_team_reactions(["pyro"])
        assert len(reactions) == 0

    def test_three_element_team(self) -> None:
        table = GenshinReactionTable()
        reactions = table.get_team_reactions(["pyro", "hydro", "cryo"])
        names = [r.name for r in reactions]
        assert "Vaporize" in names
        assert "Frozen" in names


class TestElementReactionTableCompleteness:
    def test_all_16_reactions_present(self) -> None:
        table = GenshinReactionTable()
        assert len(table.REACTIONS) == 16

    def test_all_unique_names(self) -> None:
        table = GenshinReactionTable()
        names = [r.name for r in table.REACTIONS]
        assert len(names) == len(set(names))

    def test_reaction_dataclass_frozen(self) -> None:
        r = GenshinReactionTable.REACTIONS[0]
        assert isinstance(r, ElementReaction)
        with pytest.raises(AttributeError):
            r.name = "modified"  # type: ignore[misc]
