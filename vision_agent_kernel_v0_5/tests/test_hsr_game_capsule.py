"""Tests for capsules/hsr/hsr_game_capsule.py — validates HSR Capsule without Kernel changes."""
from __future__ import annotations

import pytest

from agent_kernel.protocols import GameCapsule
from agent_kernel.types import SkillRecipe
from capsules.hsr.hsr_game_capsule import (
    HSR_ACTION_VOCABULARY,
    HSR_RISK_POLICY,
    HSR_SCREEN_VOCABULARY,
    HSRGameCapsule,
)


class TestHSRProtocolConformance:

    def test_implements_game_capsule_protocol(self) -> None:
        capsule = HSRGameCapsule()
        assert isinstance(capsule, GameCapsule)

    def test_has_required_methods(self) -> None:
        capsule = HSRGameCapsule()
        assert callable(getattr(capsule, "screen_vocabulary", None))
        assert callable(getattr(capsule, "action_vocabulary", None))
        assert callable(getattr(capsule, "skill_library", None))
        assert callable(getattr(capsule, "risk_policy", None))


class TestHSRCoreProperties:

    def test_game_id(self) -> None:
        assert HSRGameCapsule().game_id == "hsr"

    def test_game_id_is_different_from_genshin(self) -> None:
        from capsules.genshin.genshin_game_capsule import GenshinGameCapsule
        assert HSRGameCapsule().game_id != GenshinGameCapsule().game_id


class TestHsrScreenVocabulary:

    def test_returns_tuple(self) -> None:
        vocab = HSRGameCapsule().screen_vocabulary()
        assert isinstance(vocab, tuple)
        assert len(vocab) > 0

    def test_contains_hsr_specific_states(self) -> None:
        vocab = HSRGameCapsule().screen_vocabulary()
        hsr_states = ("turn_based_combat", "dialog_choice", "phone_menu", "light_cone", "relics")
        for state in hsr_states:
            assert state in vocab, f"Missing HSR state: {state}"

    def test_does_not_contain_genshin_states(self) -> None:
        """HSR vocabulary must NOT contain Genshin-specific states."""
        vocab = set(HSRGameCapsule().screen_vocabulary())
        genshin_only = {"world_hud", "paimon_menu", "full_menu", "domain_entrance"}
        for state in genshin_only:
            assert state not in vocab, f"HSR vocab contains Genshin state: {state}"

    def test_no_duplicates(self) -> None:
        vocab = HSRGameCapsule().screen_vocabulary()
        assert len(vocab) == len(set(vocab))


class TestHsrActionVocabulary:

    def test_returns_tuple(self) -> None:
        vocab = HSRGameCapsule().action_vocabulary()
        assert isinstance(vocab, tuple)
        assert len(vocab) > 0

    def test_contains_turn_based_actions(self) -> None:
        vocab = HSRGameCapsule().action_vocabulary()
        for action in ("basic_attack", "skill", "ultimate", "technique", "defend"):
            assert action in vocab, f"Missing HSR action: {action}"

    def test_does_not_contain_genshin_actions(self) -> None:
        vocab = set(HSRGameCapsule().action_vocabulary())
        genshin_only = {"elemental_skill", "elemental_burst", "normal_attack", "sprint", "aim"}
        for action in genshin_only:
            assert action not in vocab, f"HSR vocab contains Genshin action: {action}"


class TestHsrSkillLibrary:

    def test_returns_dict(self) -> None:
        lib = HSRGameCapsule().skill_library()
        assert isinstance(lib, dict)
        assert len(lib) > 0

    def test_all_values_are_skill_recipes(self) -> None:
        for key, recipe in HSRGameCapsule().skill_library().items():
            assert isinstance(recipe, SkillRecipe)
            assert recipe.skill_id == key

    def test_contains_hsr_skills(self) -> None:
        lib = HSRGameCapsule().skill_library()
        assert "hsr_combat" in lib
        assert "hsr_navigation" in lib
        assert "hsr_dialog" in lib
        assert "hsr_claim_rewards" in lib

    def test_hsr_combat_is_turn_based(self) -> None:
        recipe = HSRGameCapsule().skill_library()["hsr_combat"]
        assert "turn_based_combat" in recipe.applicable_context

    def test_no_genshin_skills(self) -> None:
        """HSR skill library must not contain Genshin skills."""
        lib = HSRGameCapsule().skill_library()
        for key in lib:
            assert "genshin" not in key.lower(), f"HSR library contains Genshin skill: {key}"

    def test_cached(self) -> None:
        capsule = HSRGameCapsule()
        assert capsule.skill_library() is capsule.skill_library()


class TestHsrRiskPolicy:

    def test_returns_dict(self) -> None:
        policy = HSRGameCapsule().risk_policy()
        assert isinstance(policy, dict)

    def test_all_values_valid(self) -> None:
        valid = {"low", "medium", "high", "critical"}
        for action, level in HSRGameCapsule().risk_policy().items():
            assert level in valid, f"Invalid risk '{level}' for '{action}'"

    def test_combat_lower_risk_than_genshin(self) -> None:
        """Turn-based combat is lower risk than ARPG combat."""
        hsr_policy = HSRGameCapsule().risk_policy()
        assert hsr_policy.get("basic_attack") == "low"

    def test_returns_copy(self) -> None:
        capsule = HSRGameCapsule()
        assert capsule.risk_policy() is not capsule.risk_policy()


class TestKernelNotModified:

    def test_hsr_capsule_does_not_import_kernel_internals(self) -> None:
        """Verify HSR capsule only imports from agent_kernel (public API)."""
        import capsules.hsr.hsr_game_capsule as module
        source = module.__file__
        assert source is not None
        with open(source, encoding="utf-8") as f:
            content = f.read()
        # Should only import from agent_kernel (public Kernel API)
        assert "from agent_kernel.types import" in content
        # Should NOT import from core, execution, perception, planning, etc.
        forbidden = ["from core.", "from execution.", "from perception.", "from planning."]
        for imp in forbidden:
            assert imp not in content, f"HSR capsule imports Kernel internal: {imp}"

    def test_both_capsules_coexist(self) -> None:
        """Both Genshin and HSR capsules can coexist without conflict."""
        from capsules.genshin.genshin_game_capsule import GenshinGameCapsule
        genshin = GenshinGameCapsule()
        hsr = HSRGameCapsule()
        assert genshin.game_id != hsr.game_id
        assert genshin.screen_vocabulary() != hsr.screen_vocabulary()
        assert genshin.skill_library() != hsr.skill_library()
