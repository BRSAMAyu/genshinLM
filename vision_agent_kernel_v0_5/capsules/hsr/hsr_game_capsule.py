"""HSRGameCapsule — concrete GameCapsule implementation for Honkai: Star Rail.

Implements the GameCapsule protocol from agent_kernel.protocols.
This is the Capsule side of the Kernel/Capsule boundary: it provides all
HSR-specific vocabulary, skill recipes, and risk policies.

Key validation: HSR Capsule does NOT modify any Kernel code.
See: docs/SPARKLE_AGENT_KERNEL_DESIGN.md §6 (Game Capsule Protocol)
See: agent_kernel/protocols.py GameCapsule
"""
from __future__ import annotations

import logging

from agent_kernel.types import SkillRecipe, SkillStep

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Screen state vocabulary — all known HSR screen states
# ---------------------------------------------------------------------------

HSR_SCREEN_VOCABULARY: tuple[str, ...] = (
    # Overworld states
    "overworld",
    "map",
    "menu",
    "loading",
    "unknown",
    # Combat states (turn-based)
    "combat",
    "turn_based_combat",
    "combat_victory",
    "combat_defeat",
    # Dialog states
    "dialog",
    "dialog_choice",
    "cutscene",
    # Menu states
    "inventory",
    "character_select",
    "light_cone",
    "relics",
    "shop",
    "quest_log",
    "reward_screen",
    # System states
    "notification",
    "death_screen",
    "phone_menu",
    "tutorial",
)

# ---------------------------------------------------------------------------
# Action vocabulary — all known HSR action types
# ---------------------------------------------------------------------------

HSR_ACTION_VOCABULARY: tuple[str, ...] = (
    # Input primitives
    "click",
    "press_key",
    "hold_key",
    "scroll",
    "drag",
    "wait",
    # HSR-specific actions (turn-based combat)
    "basic_attack",
    "skill",
    "ultimate",
    "technique",
    "defend",
    "auto_combat_toggle",
    "speed_toggle",
    # Navigation
    "move_to_target",
    "camera_align",
    "interact",
    "teleport",
    # Menu
    "open_menu",
    "close_menu",
    "confirm",
    "cancel",
    # Dialog
    "advance_dialog",
    "select_dialog_option",
)

# ---------------------------------------------------------------------------
# Risk policy — maps action types to risk levels
# ---------------------------------------------------------------------------

HSR_RISK_POLICY: dict[str, str] = {
    # Low risk — UI navigation, observation
    "click": "low",
    "scroll": "low",
    "open_menu": "low",
    "close_menu": "low",
    "wait": "low",
    "press_key": "low",
    "advance_dialog": "low",
    "select_dialog_option": "low",
    "speed_toggle": "low",
    # Medium risk — combat (turn-based, lower stakes than ARPG)
    "basic_attack": "low",
    "skill": "medium",
    "defend": "low",
    "auto_combat_toggle": "medium",
    "interact": "medium",
    "confirm": "medium",
    "cancel": "low",
    "move_to_target": "medium",
    "camera_align": "medium",
    # High risk — powerful abilities, navigation
    "ultimate": "high",
    "technique": "high",
    "teleport": "high",
    "hold_key": "high",
    "drag": "medium",
    # Critical risk — irreversible
    "combat": "critical",
}

# ---------------------------------------------------------------------------
# Skill recipes
# ---------------------------------------------------------------------------

def _build_skill_recipes() -> dict[str, SkillRecipe]:
    """Build the skill recipe library for HSR."""
    recipes: dict[str, SkillRecipe] = {}

    recipes["hsr_combat"] = SkillRecipe(
        skill_id="hsr_combat",
        title="HSR Turn-Based Combat",
        goal_template="Win a turn-based combat encounter",
        applicable_context=("combat", "turn_based_combat"),
        preconditions=("team_alive", "in_combat"),
        steps=(
            SkillStep(step_id="hc1", intent="assess_enemy_weakness", target_query="enemy type and weakness"),
            SkillStep(step_id="hc2", intent="select_skill_or_attack", target_query="optimal skill for weakness"),
            SkillStep(step_id="hc3", intent="use_ultimate_if_ready", target_query="ultimate gauge"),
            SkillStep(step_id="hc4", intent="end_turn", target_query="action complete"),
        ),
        verifiers=("combat_finished",),
        recovery_policies=("retry_with_different_strategy", "abort_and_report"),
        risk_level="high",
        version="1.0",
    )

    recipes["hsr_navigation"] = SkillRecipe(
        skill_id="hsr_navigation",
        title="HSR Map Navigation",
        goal_template="Navigate to a destination on the map",
        applicable_context=("overworld", "map"),
        preconditions=("map_accessible",),
        steps=(
            SkillStep(step_id="hn1", intent="open_map", target_query="map button"),
            SkillStep(step_id="hn2", intent="select_destination", target_query="target waypoint"),
            SkillStep(step_id="hn3", intent="confirm_teleport", target_query="teleport confirm"),
            SkillStep(step_id="hn4", intent="walk_to_target", target_query="navigation marker"),
        ),
        verifiers=("nav_destination_reached",),
        recovery_policies=("pause_and_reacquire",),
        risk_level="medium",
        version="1.0",
    )

    recipes["hsr_dialog"] = SkillRecipe(
        skill_id="hsr_dialog",
        title="HSR Dialog Progression",
        goal_template="Progress through NPC dialog",
        applicable_context=("dialog", "dialog_choice"),
        preconditions=("in_dialog",),
        steps=(
            SkillStep(step_id="hd1", intent="advance_text", target_query="dialog text area"),
            SkillStep(step_id="hd2", intent="detect_choice", target_query="dialog choice buttons"),
            SkillStep(step_id="hd3", intent="select_choice", target_query="best dialog option"),
        ),
        verifiers=("dialog_progressed",),
        recovery_policies=("pause_and_reacquire",),
        risk_level="low",
        version="1.0",
    )

    recipes["hsr_claim_rewards"] = SkillRecipe(
        skill_id="hsr_claim_rewards",
        title="HSR Reward Claiming",
        goal_template="Claim available rewards from menus",
        applicable_context=("menu", "reward_screen"),
        preconditions=("rewards_available",),
        steps=(
            SkillStep(step_id="hr1", intent="find_claim_button", target_query="claim/领取 button"),
            SkillStep(step_id="hr2", intent="confirm_claim", target_query="confirm button"),
        ),
        verifiers=("reward_claimed",),
        recovery_policies=("skip_and_log",),
        risk_level="medium",
        version="1.0",
    )

    return recipes


# ---------------------------------------------------------------------------
# HSRGameCapsule — implements GameCapsule protocol
# ---------------------------------------------------------------------------

class HSRGameCapsule:
    """Concrete GameCapsule implementation for Honkai: Star Rail.

    Validates the Kernel/Capsule boundary: this Capsule provides all
    HSR-specific data without modifying any Kernel code.

    Usage:
        capsule = HSRGameCapsule()
        assert capsule.game_id == "hsr"
        skills = capsule.skill_library()
    """

    def __init__(self) -> None:
        self._skill_cache: dict[str, SkillRecipe] | None = None

    @property
    def game_id(self) -> str:
        return "hsr"

    def screen_vocabulary(self) -> tuple[str, ...]:
        return HSR_SCREEN_VOCABULARY

    def action_vocabulary(self) -> tuple[str, ...]:
        return HSR_ACTION_VOCABULARY

    def skill_library(self) -> dict[str, SkillRecipe]:
        if self._skill_cache is None:
            self._skill_cache = _build_skill_recipes()
        return self._skill_cache

    def risk_policy(self) -> dict[str, str]:
        return dict(HSR_RISK_POLICY)
