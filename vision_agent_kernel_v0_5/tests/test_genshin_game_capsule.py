"""Tests for capsules/genshin/genshin_game_capsule.py"""
from __future__ import annotations

import pytest

from agent_kernel.protocols import GameCapsule
from agent_kernel.types import SkillRecipe
from capsules.genshin.genshin_game_capsule import (
    GENSHIN_ACTION_VOCABULARY,
    GENSHIN_RISK_POLICY,
    GENSHIN_SCREEN_VOCABULARY,
    GenshinGameCapsule,
)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestGameCapsuleProtocol:

    def test_implements_game_capsule_protocol(self) -> None:
        capsule = GenshinGameCapsule()
        assert isinstance(capsule, GameCapsule)

    def test_has_required_methods(self) -> None:
        capsule = GenshinGameCapsule()
        assert hasattr(capsule, "game_id")
        assert hasattr(capsule, "screen_vocabulary")
        assert hasattr(capsule, "action_vocabulary")
        assert hasattr(capsule, "skill_library")
        assert hasattr(capsule, "risk_policy")


# ---------------------------------------------------------------------------
# Core properties
# ---------------------------------------------------------------------------

class TestGenshinGameCapsule:

    def test_game_id(self) -> None:
        assert GenshinGameCapsule().game_id == "genshin"

    def test_game_id_is_property(self) -> None:
        capsule = GenshinGameCapsule()
        assert isinstance(capsule.game_id, str)


# ---------------------------------------------------------------------------
# Screen vocabulary
# ---------------------------------------------------------------------------

class TestScreenVocabulary:

    def test_returns_tuple(self) -> None:
        vocab = GenshinGameCapsule().screen_vocabulary()
        assert isinstance(vocab, tuple)
        assert len(vocab) > 0

    def test_contains_core_states(self) -> None:
        vocab = GenshinGameCapsule().screen_vocabulary()
        core = ("world_hud", "combat", "dialog", "loading_screen", "full_menu", "unknown")
        for state in core:
            assert state in vocab, f"Missing core state: {state}"

    def test_no_duplicates(self) -> None:
        vocab = GenshinGameCapsule().screen_vocabulary()
        assert len(vocab) == len(set(vocab))

    def test_all_strings(self) -> None:
        for item in GenshinGameCapsule().screen_vocabulary():
            assert isinstance(item, str)
            assert len(item) > 0


# ---------------------------------------------------------------------------
# Action vocabulary
# ---------------------------------------------------------------------------

class TestActionVocabulary:

    def test_returns_tuple(self) -> None:
        vocab = GenshinGameCapsule().action_vocabulary()
        assert isinstance(vocab, tuple)
        assert len(vocab) > 0

    def test_contains_input_primitives(self) -> None:
        vocab = GenshinGameCapsule().action_vocabulary()
        for action in ("click", "press_key", "hold_key", "scroll"):
            assert action in vocab, f"Missing primitive: {action}"

    def test_contains_genshin_actions(self) -> None:
        vocab = GenshinGameCapsule().action_vocabulary()
        for action in ("normal_attack", "elemental_skill", "elemental_burst", "teleport"):
            assert action in vocab, f"Missing Genshin action: {action}"

    def test_no_duplicates(self) -> None:
        vocab = GenshinGameCapsule().action_vocabulary()
        assert len(vocab) == len(set(vocab))


# ---------------------------------------------------------------------------
# Skill library
# ---------------------------------------------------------------------------

class TestSkillLibrary:

    def test_returns_dict(self) -> None:
        lib = GenshinGameCapsule().skill_library()
        assert isinstance(lib, dict)
        assert len(lib) > 0

    def test_all_values_are_skill_recipes(self) -> None:
        for key, recipe in GenshinGameCapsule().skill_library().items():
            assert isinstance(key, str)
            assert isinstance(recipe, SkillRecipe)
            assert recipe.skill_id == key

    def test_contains_core_skills(self) -> None:
        lib = GenshinGameCapsule().skill_library()
        assert "safe_combat_genshin_v1" in lib
        assert "boss_combat_genshin_v1" in lib
        assert "dodge_reflex_genshin_v1" in lib
        assert "teleport_and_navigate_v1" in lib
        assert "handle_dialog_v1" in lib
        assert "open_chest_genshin_v1" in lib

    def test_skill_recipes_have_steps(self) -> None:
        for skill_id, recipe in GenshinGameCapsule().skill_library().items():
            assert len(recipe.steps) > 0, f"Skill {skill_id} has no steps"

    def test_skill_recipes_have_verifiers(self) -> None:
        for skill_id, recipe in GenshinGameCapsule().skill_library().items():
            assert len(recipe.verifiers) > 0, f"Skill {skill_id} has no verifiers"

    def test_cached_on_second_call(self) -> None:
        capsule = GenshinGameCapsule()
        lib1 = capsule.skill_library()
        lib2 = capsule.skill_library()
        assert lib1 is lib2  # same object (cached)


# ---------------------------------------------------------------------------
# Risk policy
# ---------------------------------------------------------------------------

class TestRiskPolicy:

    def test_returns_dict(self) -> None:
        policy = GenshinGameCapsule().risk_policy()
        assert isinstance(policy, dict)
        assert len(policy) > 0

    def test_all_values_are_valid_risk_levels(self) -> None:
        valid = {"low", "medium", "high", "critical"}
        for action, level in GenshinGameCapsule().risk_policy().items():
            assert level in valid, f"Invalid risk level '{level}' for action '{action}'"

    def test_returns_copy(self) -> None:
        capsule = GenshinGameCapsule()
        p1 = capsule.risk_policy()
        p2 = capsule.risk_policy()
        assert p1 is not p2  # defensive copy

    def test_combat_actions_are_high_risk(self) -> None:
        policy = GenshinGameCapsule().risk_policy()
        assert policy["elemental_burst"] in ("high", "critical")
        assert policy["teleport"] in ("high", "critical")

    def test_ui_actions_are_low_risk(self) -> None:
        policy = GenshinGameCapsule().risk_policy()
        assert policy["click"] == "low"
        assert policy["open_menu"] == "low"


# ---------------------------------------------------------------------------
# Vocabulary constants
# ---------------------------------------------------------------------------

class TestVocabularyConstants:

    def test_screen_vocabulary_constant(self) -> None:
        assert len(GENSHIN_SCREEN_VOCABULARY) >= 20

    def test_action_vocabulary_constant(self) -> None:
        assert len(GENSHIN_ACTION_VOCABULARY) >= 15

    def test_risk_policy_constant(self) -> None:
        assert len(GENSHIN_RISK_POLICY) >= 10

    def test_world_knowledge(self) -> None:
        cap = GenshinGameCapsule()
        wk = cap.world_knowledge()
        assert "regions" in wk
        assert len(wk["regions"]) >= 3

    def test_verifier_bundle(self) -> None:
        cap = GenshinGameCapsule()
        vb = cap.verifier_bundle()
        assert "screen_state_confidence_threshold" in vb


# ---------------------------------------------------------------------------
# Integration: OperatorAgent + Capsule keywords
# ---------------------------------------------------------------------------

class TestOperatorAgentWithCapsule:

    def test_operator_agent_with_genshin_keywords(self) -> None:
        from agent_kernel.operator_agent import OperatorAgent
        from data.genshin_operator_keywords import GENSHIN_TASK_KEYWORDS

        agent = OperatorAgent(task_keywords=GENSHIN_TASK_KEYWORDS)
        response = agent.handle_user_message("升级胡桃到90级", {})
        assert response["technical_action"]["intent"] == "set_goal"
        assert response["technical_action"]["task"].objective == "character_level_up"

    def test_capsule_and_operator_together(self) -> None:
        from agent_kernel.operator_agent import SimpleOperatorAgent
        from data.genshin_operator_keywords import GENSHIN_TASK_KEYWORDS

        capsule = GenshinGameCapsule()
        agent = SimpleOperatorAgent(task_keywords=GENSHIN_TASK_KEYWORDS)

        # Verify capsule provides the vocabulary that agent matches against
        response = agent.handle_user_message("去传送锚点", {})
        assert response["technical_action"]["intent"] == "set_goal"
        assert "teleport" in capsule.action_vocabulary()
