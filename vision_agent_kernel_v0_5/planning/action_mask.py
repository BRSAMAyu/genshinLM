"""ActionMask — constrains available actions per screen state.

Each screen state defines a set of allowed symbolic actions. LLM/Explorer
can only select actions from the mask. Actions outside the mask are rejected.

This prevents:
- WASD movement in UI pages
- Combat actions in dialogue
- Raw coordinate clicks in unknown states
- Unconstrained actions that bypass the action system
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from perception.screen_state_tree import ScreenPageId

# -- Action definitions ---------------------------------------------------

@dataclass(frozen=True, slots=True)
class MaskedAction:
    """A single allowed action within a screen state."""
    action_id: str
    display_name: str
    category: str  # navigation, interaction, combat, ui, meta
    requires_target: bool = False
    risk_level: str = "low"


# -- Per-page action masks ------------------------------------------------

_WORLD_ACTIONS = (
    MaskedAction("observe", "Observe", "navigation"),
    MaskedAction("open_menu", "Open Menu", "ui"),
    MaskedAction("open_map", "Open Map", "ui"),
    MaskedAction("interact_prompt", "Interact", "interaction", requires_target=True),
    MaskedAction("heading_servo", "Move Toward Target", "navigation"),
    MaskedAction("safe_pause", "Pause", "meta"),
    MaskedAction("wasd_move", "Move (WASD)", "navigation"),
    MaskedAction("start_combat", "Engage Enemy", "combat", risk_level="medium"),
)

_DIALOGUE_ACTIONS = (
    MaskedAction("advance_dialogue", "Continue Dialogue", "interaction"),
    MaskedAction("select_dialogue_option", "Select Option", "interaction", requires_target=True),
    MaskedAction("back", "Go Back", "navigation"),
    MaskedAction("observe", "Observe", "navigation"),
)

_MAP_ACTIONS = (
    MaskedAction("select_marker", "Select Marker", "interaction", requires_target=True),
    MaskedAction("teleport", "Teleport", "navigation", risk_level="medium"),
    MaskedAction("back", "Go Back", "navigation"),
    MaskedAction("observe", "Observe", "navigation"),
)

_CHARACTER_MENU_ACTIONS = (
    MaskedAction("select_tab", "Select Tab", "ui", requires_target=True),
    MaskedAction("select_character", "Select Character", "ui", requires_target=True),
    MaskedAction("upgrade", "Upgrade", "ui", risk_level="medium"),
    MaskedAction("equip", "Equip", "ui"),
    MaskedAction("back", "Go Back", "navigation"),
    MaskedAction("observe", "Observe", "navigation"),
)

_COMBAT_ACTIONS = (
    MaskedAction("normal_attack", "Normal Attack", "combat"),
    MaskedAction("e_skill", "Elemental Skill", "combat"),
    MaskedAction("q_burst", "Elemental Burst", "combat"),
    MaskedAction("switch_character", "Switch Character", "combat"),
    MaskedAction("dodge", "Dodge", "combat"),
    MaskedAction("observe", "Observe", "navigation"),
    MaskedAction("retreat", "Retreat", "navigation"),
)

_UNKNOWN_ACTIONS = (
    MaskedAction("observe", "Observe", "navigation"),
    MaskedAction("back", "Go Back", "navigation"),
    MaskedAction("ask_user", "Ask User", "meta"),
    MaskedAction("safe_probe", "Safe Probe", "meta"),
)

_LOADING_ACTIONS = (
    MaskedAction("observe", "Observe", "navigation"),
    MaskedAction("wait", "Wait", "meta"),
)

_INVENTORY_ACTIONS = (
    MaskedAction("select_item", "Select Item", "ui", requires_target=True),
    MaskedAction("use_item", "Use Item", "ui"),
    MaskedAction("sort", "Sort", "ui"),
    MaskedAction("back", "Go Back", "navigation"),
    MaskedAction("observe", "Observe", "navigation"),
)

_QUEST_LOG_ACTIONS = (
    MaskedAction("select_quest", "Select Quest", "ui", requires_target=True),
    MaskedAction("track_quest", "Track Quest", "ui"),
    MaskedAction("back", "Go Back", "navigation"),
    MaskedAction("observe", "Observe", "navigation"),
)

_SHOP_ACTIONS = (
    MaskedAction("select_item", "Select Item", "ui", requires_target=True),
    MaskedAction("buy", "Buy", "ui", risk_level="medium"),
    MaskedAction("back", "Go Back", "navigation"),
    MaskedAction("observe", "Observe", "navigation"),
)

_REWARD_ACTIONS = (
    MaskedAction("claim_reward", "Claim Reward", "interaction"),
    MaskedAction("back", "Go Back", "navigation"),
    MaskedAction("observe", "Observe", "navigation"),
)

_CUTSCENE_ACTIONS = (
    MaskedAction("observe", "Observe", "navigation"),
    MaskedAction("skip", "Skip Cutscene", "meta", risk_level="low"),
)

_DOMAIN_ACTIONS = (
    MaskedAction("observe", "Observe", "navigation"),
    MaskedAction("advance_dialogue", "Continue", "interaction"),
    MaskedAction("start_challenge", "Start Challenge", "combat", risk_level="high"),
    MaskedAction("leave_domain", "Leave Domain", "navigation"),
)

_SETTINGS_ACTIONS = (
    MaskedAction("select_setting", "Select Setting", "ui", requires_target=True),
    MaskedAction("back", "Go Back", "navigation"),
    MaskedAction("observe", "Observe", "navigation"),
)

_PAGE_MASKS: dict[str, tuple[MaskedAction, ...]] = {
    "world_viewport": _WORLD_ACTIONS,
    "dialogue": _DIALOGUE_ACTIONS,
    "map": _MAP_ACTIONS,
    "character_menu": _CHARACTER_MENU_ACTIONS,
    "combat": _COMBAT_ACTIONS,
    "boss_fight": _COMBAT_ACTIONS,
    "domain": _DOMAIN_ACTIONS,
    "unknown": _UNKNOWN_ACTIONS,
    "loading": _LOADING_ACTIONS,
    "inventory": _INVENTORY_ACTIONS,
    "quest_log": _QUEST_LOG_ACTIONS,
    "shop": _SHOP_ACTIONS,
    "reward_screen": _REWARD_ACTIONS,
    "cutscene": _CUTSCENE_ACTIONS,
    "settings": _SETTINGS_ACTIONS,
}

# Forbidden actions that should NEVER be allowed via LLM
_FORBIDDEN_ACTION_IDS = frozenset({
    "raw_coordinate_click",
    "raw_key_input",
    "raw_mouse_input",
    "direct_click",
    "direct_press_key",
    "bypass_safety",
})


class ActionMask:
    """Determines which actions are allowed for a given screen state."""

    def __init__(self, custom_masks: dict[str, tuple[MaskedAction, ...]] | None = None) -> None:
        self._masks = {**_PAGE_MASKS}
        if custom_masks:
            self._masks.update(custom_masks)

    def allowed_actions(self, page_id: str) -> tuple[MaskedAction, ...]:
        """Get allowed actions for a screen page."""
        return self._masks.get(page_id, _UNKNOWN_ACTIONS)

    def is_action_allowed(self, page_id: str, action_id: str) -> bool:
        """Check if a specific action is allowed for a screen page."""
        if action_id in _FORBIDDEN_ACTION_IDS:
            return False
        allowed = self.allowed_actions(page_id)
        return any(a.action_id == action_id for a in allowed)

    def validate_action(
        self, page_id: str, action_id: str,
    ) -> tuple[bool, str]:
        """Validate an action and return (allowed, reason)."""
        if action_id in _FORBIDDEN_ACTION_IDS:
            return False, f"action {action_id!r} is globally forbidden"

        allowed = self.allowed_actions(page_id)
        if any(a.action_id == action_id for a in allowed):
            return True, "allowed"

        allowed_ids = [a.action_id for a in allowed]
        return False, f"action {action_id!r} not in mask for {page_id!r}: {allowed_ids}"

    def combat_allowed(self, page_id: str) -> bool:
        """Check if combat actions are allowed."""
        return page_id in ("world_viewport", "combat", "boss_fight", "domain")

    def movement_allowed(self, page_id: str) -> bool:
        """Check if WASD movement is allowed."""
        return page_id in ("world_viewport",)

    def action_ids(self, page_id: str) -> list[str]:
        """Get just the action IDs for a page."""
        return [a.action_id for a in self.allowed_actions(page_id)]

    def categories(self, page_id: str) -> set[str]:
        """Get unique action categories for a page."""
        return {a.category for a in self.allowed_actions(page_id)}
