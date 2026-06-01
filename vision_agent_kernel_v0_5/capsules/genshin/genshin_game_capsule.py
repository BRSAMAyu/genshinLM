"""GenshinGameCapsule — concrete GameCapsule implementation for Genshin Impact.

Implements the GameCapsule protocol from agent_kernel.protocols.
This is the Capsule side of the Kernel/Capsule boundary: it provides all
game-specific vocabulary, skill recipes, and risk policies that the
Kernel needs to operate on Genshin.

See: docs/SPARKLE_AGENT_KERNEL_DESIGN.md §6 (Game Capsule Protocol)
See: agent_kernel/protocols.py GameCapsule
"""
from __future__ import annotations

import logging
from typing import Any

from agent_kernel.types import SkillRecipe, SkillStep

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Screen state vocabulary — all known Genshin screen states
# ---------------------------------------------------------------------------

GENSHIN_SCREEN_VOCABULARY: tuple[str, ...] = (
    # Core states (from perception/genshin_screen_classifier.py)
    "world_hud",
    "combat",
    "dialog",
    "loading_screen",
    "death_screen",
    "cutscene",
    "domain_entrance",
    "notification",
    "full_menu",
    "paimon_menu",
    "no_hud",
    # Standardized states (from planning/screen_state_claim.py)
    "overworld",
    "turn_based_combat",
    "menu",
    "map",
    "loading",
    "inventory",
    "shop",
    "quest_log",
    "reward_screen",
    "boss_fight",
    "character_select",
    "adventure_rank_up",
    "cooking",
    "forging",
    "unknown",
)

# ---------------------------------------------------------------------------
# Action vocabulary — all known Genshin action types
# ---------------------------------------------------------------------------

GENSHIN_ACTION_VOCABULARY: tuple[str, ...] = (
    # Input primitives
    "click",
    "press_key",
    "hold_key",
    "scroll",
    "drag",
    # UIFlow step types
    "action_sequence",
    "checkpoint",
    "guard",
    "branch_on_visual_state",
    "wait_visual_trigger",
    "move_to_target",
    "camera_align",
    # Genshin-specific actions
    "normal_attack",
    "elemental_skill",
    "elemental_burst",
    "sprint",
    "jump",
    "aim",
    "interact",
    "teleport",
    "switch_character",
    "use_food",
    "open_menu",
    "close_menu",
    "wait",
)

# ---------------------------------------------------------------------------
# Risk policy — maps action types to risk levels
# ---------------------------------------------------------------------------

GENSHIN_RISK_POLICY: dict[str, str] = {
    # Low risk — UI navigation, observation
    "click": "low",
    "scroll": "low",
    "open_menu": "low",
    "close_menu": "low",
    "wait": "low",
    "press_key": "low",
    "checkpoint": "low",
    # Medium risk — character changes, resource consumption
    "normal_attack": "medium",
    "elemental_skill": "medium",
    "sprint": "medium",
    "jump": "medium",
    "switch_character": "medium",
    "move_to_target": "medium",
    "camera_align": "medium",
    "interact": "medium",
    "drag": "medium",
    # High risk — burst abilities, navigation
    "elemental_burst": "high",
    "hold_key": "high",
    "aim": "high",
    "teleport": "high",
    "use_food": "high",
    "action_sequence": "high",
    "branch_on_visual_state": "high",
    # Critical risk — irreversible actions
    "guard": "critical",
    "wait_visual_trigger": "critical",
}

# ---------------------------------------------------------------------------
# Skill recipes — hardcoded minimal set; YAML-based skills loaded at runtime
# ---------------------------------------------------------------------------

def _build_skill_recipes() -> dict[str, SkillRecipe]:
    """Build the static skill recipe library for Genshin."""
    recipes: dict[str, SkillRecipe] = {}

    recipes["safe_combat_genshin_v1"] = SkillRecipe(
        skill_id="safe_combat_genshin_v1",
        title="Genshin Safe Combat Loop v1",
        goal_template="Defeat enemies using safe rotation with dodge interrupts",
        applicable_context=("combat", "overworld", "domain"),
        preconditions=("team_alive", "skills_off_cooldown"),
        steps=(
            SkillStep(step_id="s1", intent="assess_threats", target_query="enemy positions"),
            SkillStep(step_id="s2", intent="dodge_if_danger", target_query="incoming attacks"),
            SkillStep(step_id="s3", intent="execute_rotation", target_query="current active character skills"),
            SkillStep(step_id="s4", intent="switch_if_low_hp", target_query="team hp bars"),
        ),
        verifiers=("combat_state_clear", "danger_cleared"),
        recovery_policies=("retreat_and_heal", "pause_and_reacquire"),
        risk_level="high",
        version="1.0",
    )

    recipes["boss_combat_genshin_v1"] = SkillRecipe(
        skill_id="boss_combat_genshin_v1",
        title="Genshin Boss Combat v1",
        goal_template="Defeat boss enemy with phase-aware reactions",
        applicable_context=("boss_fight", "combat"),
        preconditions=("team_alive", "boss_detected"),
        steps=(
            SkillStep(step_id="b1", intent="identify_boss_phase", target_query="boss animation state"),
            SkillStep(step_id="b2", intent="react_to_phase_mechanic", target_query="phase mechanic indicator"),
            SkillStep(step_id="b3", intent="execute_damage_rotation", target_query="optimal skill chain"),
            SkillStep(step_id="b4", intent="emergency_heal_if_needed", target_query="team hp bars"),
        ),
        verifiers=("combat_state_clear", "danger_cleared", "boss_defeated"),
        recovery_policies=("retreat_and_heal", "abort_and_report"),
        risk_level="critical",
        version="1.0",
    )

    recipes["dodge_reflex_genshin_v1"] = SkillRecipe(
        skill_id="dodge_reflex_genshin_v1",
        title="Genshin Reflex Dodge v1",
        goal_template="Dodge incoming attack using iframe dash",
        applicable_context=("combat", "boss_fight", "overworld"),
        preconditions=("dash_available",),
        steps=(
            SkillStep(step_id="d1", intent="detect_danger", target_query="incoming projectile or aoe telegraph"),
            SkillStep(step_id="d2", intent="dash_to_safety", target_query="safe direction"),
        ),
        verifiers=("danger_cleared",),
        recovery_policies=("retreat_and_heal",),
        risk_level="high",
        version="1.0",
    )

    recipes["teleport_and_navigate_v1"] = SkillRecipe(
        skill_id="teleport_and_navigate_v1",
        title="Genshin Teleport and Navigate v1",
        goal_template="Navigate to a destination using map teleport + walking",
        applicable_context=("overworld", "map"),
        preconditions=("map_accessible",),
        steps=(
            SkillStep(step_id="n1", intent="open_map", target_query="map button"),
            SkillStep(step_id="n2", intent="select_waypoint", target_query="destination waypoint"),
            SkillStep(step_id="n3", intent="confirm_teleport", target_query="teleport confirm button"),
            SkillStep(step_id="n4", intent="walk_to_target", target_query="minimap quest marker"),
        ),
        verifiers=("marker_visible", "route_progress"),
        recovery_policies=("pause_and_reacquire", "skip_and_log"),
        risk_level="medium",
        version="1.0",
    )

    recipes["handle_dialog_v1"] = SkillRecipe(
        skill_id="handle_dialog_v1",
        title="Genshin NPC Dialog Handler v1",
        goal_template="Progress through NPC dialog with smart skip and branch selection",
        applicable_context=("dialog", "cutscene"),
        preconditions=("in_dialog",),
        steps=(
            SkillStep(step_id="dl1", intent="skip_text", target_query="dialog text area"),
            SkillStep(step_id="dl2", intent="detect_branch", target_query="dialog option buttons"),
            SkillStep(step_id="dl3", intent="select_best_option", target_query="dialog options"),
        ),
        verifiers=("dialog_progressed",),
        recovery_policies=("pause_and_reacquire",),
        risk_level="low",
        version="1.0",
    )

    recipes["open_chest_genshin_v1"] = SkillRecipe(
        skill_id="open_chest_genshin_v1",
        title="Genshin Chest Opening v1",
        goal_template="Open a treasure chest and collect rewards",
        applicable_context=("overworld",),
        preconditions=("chest_nearby",),
        steps=(
            SkillStep(step_id="c1", intent="approach_chest", target_query="chest interaction prompt"),
            SkillStep(step_id="c2", intent="interact_with_chest", target_query="F key prompt"),
            SkillStep(step_id="c3", intent="wait_animation", target_query="chest opening animation"),
        ),
        verifiers=("reward_collected",),
        recovery_policies=("skip_and_log",),
        risk_level="low",
        version="1.0",
    )

    return recipes


# ---------------------------------------------------------------------------
# GenshinGameCapsule — implements GameCapsule protocol
# ---------------------------------------------------------------------------

class GenshinGameCapsule:
    """Concrete GameCapsule implementation for Genshin Impact.

    Implements the GameCapsule protocol from agent_kernel.protocols.
    The Kernel uses this interface to query game-specific vocabulary,
    skills, and risk policies without importing any Genshin-specific code.

    Usage:
        capsule = GenshinGameCapsule()
        print(capsule.game_id)  # "genshin"
        print(capsule.screen_vocabulary())
        skills = capsule.skill_library()
    """

    def __init__(self) -> None:
        self._skill_cache: dict[str, SkillRecipe] | None = None

    @property
    def game_id(self) -> str:
        return "genshin"

    def screen_vocabulary(self) -> tuple[str, ...]:
        """Return all known Genshin screen state names."""
        return GENSHIN_SCREEN_VOCABULARY

    def action_vocabulary(self) -> tuple[str, ...]:
        """Return all known Genshin action types."""
        return GENSHIN_ACTION_VOCABULARY

    def skill_library(self) -> dict[str, SkillRecipe]:
        """Return all skills provided by this capsule."""
        if self._skill_cache is None:
            self._skill_cache = _build_skill_recipes()
        return self._skill_cache

    def risk_policy(self) -> dict[str, str]:
        """Return risk level mappings for Genshin actions."""
        return dict(GENSHIN_RISK_POLICY)
