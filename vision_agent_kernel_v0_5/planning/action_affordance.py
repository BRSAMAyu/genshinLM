from __future__ import annotations

import logging
import re
from typing import Any

from planning.screen_state_claim import (
    ActionAffordance,
    ScreenStateClaim,
    ScreenStateKind,
    UIElementClaim,
)

log = logging.getLogger(__name__)

_AFFORDANCE_RULES: dict[ScreenStateKind, list[dict[str, Any]]] = {
    "overworld": [
        {"action_type": "move", "target_label": "forward", "semantic_action": "move_forward"},
        {"action_type": "interact", "target_label": "interaction_prompt", "semantic_action": "interact",
         "precondition": "interaction_prompt is not empty"},
        {"action_type": "open_menu", "target_label": "menu_key", "semantic_action": "open_menu"},
        {"action_type": "open_map", "target_label": "map_key", "semantic_action": "open_map"},
        {"action_type": "attack", "target_label": "enemy", "semantic_action": "attack",
         "precondition": "enemy visible in range"},
        {"action_type": "sprint", "target_label": "sprint_key", "semantic_action": "sprint"},
    ],
    "combat": [
        {"action_type": "attack", "target_label": "normal_attack", "semantic_action": "basic_attack"},
        {"action_type": "skill", "target_label": "elemental_skill", "semantic_action": "use_skill",
         "precondition": "skill not on cooldown"},
        {"action_type": "burst", "target_label": "elemental_burst", "semantic_action": "use_burst",
         "precondition": "burst energy full"},
        {"action_type": "dodge", "target_label": "dodge_direction", "semantic_action": "dodge"},
        {"action_type": "switch_character", "target_label": "party_slot", "semantic_action": "switch_char"},
    ],
    "turn_based_combat": [
        {"action_type": "basic_attack", "target_label": "attack_button", "semantic_action": "basic_attack"},
        {"action_type": "skill", "target_label": "skill_button", "semantic_action": "use_skill",
         "precondition": "SP >= 1"},
        {"action_type": "ultimate", "target_label": "ultimate_button", "semantic_action": "use_ultimate",
         "precondition": "ultimate ready"},
        {"action_type": "auto_battle", "target_label": "auto_toggle", "semantic_action": "toggle_auto"},
    ],
    "dialog": [
        {"action_type": "advance_dialog", "target_label": "dialog_box", "semantic_action": "advance_dialog"},
        {"action_type": "select_option", "target_label": "dialog_option", "semantic_action": "select_dialog_option",
         "requires_confirmation": True},
    ],
    "menu": [
        {"action_type": "navigate_menu", "target_label": "menu_item", "semantic_action": "navigate_to"},
        {"action_type": "close_menu", "target_label": "back_button", "semantic_action": "go_back"},
        {"action_type": "select_item", "target_label": "list_item", "semantic_action": "select_item",
         "requires_confirmation": True},
    ],
    "map": [
        {"action_type": "select_waypoint", "target_label": "map_marker", "semantic_action": "select_waypoint",
         "requires_confirmation": True},
        {"action_type": "teleport", "target_label": "teleport_button", "semantic_action": "teleport",
         "precondition": "waypoint selected", "requires_confirmation": True},
        {"action_type": "close_map", "target_label": "close_button", "semantic_action": "close_map"},
    ],
    "loading": [],
    "inventory": [
        {"action_type": "select_item", "target_label": "inventory_item", "semantic_action": "select_item"},
        {"action_type": "use_item", "target_label": "use_button", "semantic_action": "use_item"},
        {"action_type": "sort_items", "target_label": "sort_button", "semantic_action": "sort"},
        {"action_type": "close_menu", "target_label": "close_button", "semantic_action": "go_back"},
    ],
    "quest_log": [
        {"action_type": "select_quest", "target_label": "quest_entry", "semantic_action": "select_quest"},
        {"action_type": "track_quest", "target_label": "track_button", "semantic_action": "track_quest"},
        {"action_type": "close_menu", "target_label": "close_button", "semantic_action": "go_back"},
    ],
    "reward_screen": [
        {"action_type": "claim_reward", "target_label": "claim_button", "semantic_action": "claim_reward"},
        {"action_type": "claim_all", "target_label": "claim_all_button", "semantic_action": "claim_all"},
        {"action_type": "close_menu", "target_label": "close_button", "semantic_action": "go_back"},
    ],
    "shop": [
        {"action_type": "buy_item", "target_label": "shop_item", "semantic_action": "buy_item",
         "requires_confirmation": True, "risk_level": "medium"},
        {"action_type": "close_menu", "target_label": "close_button", "semantic_action": "go_back"},
    ],
    "boss_fight": [
        {"action_type": "attack", "target_label": "boss_target", "semantic_action": "attack"},
        {"action_type": "skill", "target_label": "elemental_skill", "semantic_action": "use_skill"},
        {"action_type": "burst", "target_label": "elemental_burst", "semantic_action": "use_burst"},
        {"action_type": "dodge", "target_label": "boss_attack_indicator", "semantic_action": "dodge"},
        {"action_type": "heal", "target_label": "heal_skill", "semantic_action": "heal",
         "precondition": "healer in team, HP < 50%"},
    ],
    "cutscene": [
        {"action_type": "skip_cutscene", "target_label": "skip_button", "semantic_action": "skip",
         "requires_confirmation": True},
    ],
    "unknown": [
        {"action_type": "observe", "target_label": "full_screen", "semantic_action": "observe"},
    ],
}


class AffordanceDeriver:
    """Derives available actions from current screen state and UI elements."""

    def derive(self, claim: ScreenStateClaim) -> list[ActionAffordance]:
        state = claim.screen_state
        rules = _AFFORDANCE_RULES.get(state, _AFFORDANCE_RULES["unknown"])
        actions: list[ActionAffordance] = []

        for i, rule in enumerate(rules):
            action = self._build_from_rule(rule, claim, i)
            if action is not None:
                actions.append(action)

        for elem in claim.actionable_elements():
            action = self._build_from_element(elem, state)
            if action is not None:
                actions.append(action)

        return actions

    def _build_from_rule(
        self, rule: dict[str, Any], claim: ScreenStateClaim, index: int,
    ) -> ActionAffordance | None:
        precondition = str(rule.get("precondition", ""))
        if precondition and not self._check_precondition(precondition, claim):
            return None
        return ActionAffordance(
            action_id=f"{claim.screen_state}:{rule['action_type']}:{index}",
            action_type=str(rule["action_type"]),
            target_label=str(rule["target_label"]),
            confidence=claim.confidence * 0.9,
            requires_confirmation=bool(rule.get("requires_confirmation", False)),
            semantic_action=str(rule.get("semantic_action", rule["action_type"])),
            precondition=precondition,
            risk_level=str(rule.get("risk_level", "low")),
        )

    def _build_from_element(
        self, elem: UIElementClaim, state: ScreenStateKind,
    ) -> ActionAffordance | None:
        if elem.role == "button":
            action_type = self._infer_action_type(elem.text, state)
            return ActionAffordance(
                action_id=f"elem:{elem.element_id}",
                action_type=action_type,
                target_label=elem.text,
                confidence=elem.confidence,
                requires_confirmation=action_type in ("buy_item", "use_item", "teleport"),
                semantic_action=action_type,
            )
        if elem.role == "dialog_option":
            return ActionAffordance(
                action_id=f"elem:{elem.element_id}",
                action_type="select_option",
                target_label=elem.text,
                confidence=elem.confidence,
                requires_confirmation=True,
                semantic_action="select_dialog_option",
            )
        if elem.role == "quest_entry":
            return ActionAffordance(
                action_id=f"elem:{elem.element_id}",
                action_type="select_quest",
                target_label=elem.text,
                confidence=elem.confidence,
                semantic_action="select_quest",
            )
        if elem.role in ("menu_item", "list_item"):
            return ActionAffordance(
                action_id=f"elem:{elem.element_id}",
                action_type="navigate_menu",
                target_label=elem.text,
                confidence=elem.confidence,
                semantic_action="navigate_to",
            )
        return None

    @staticmethod
    def _check_precondition(precondition: str, claim: ScreenStateClaim) -> bool:
        pc = precondition.lower()
        if "interaction_prompt" in pc:
            return bool(claim.interaction_prompt)
        if "enemy visible" in pc:
            return any(o.get("type") == "enemy" for o in claim.visible_objects)
        if "skill not on cooldown" in pc or "burst energy full" in pc:
            return True
        if "sp >=" in pc:
            match = re.search(r"sp\s*>=\s*(\d+)", pc)
            if match:
                threshold = int(match.group(1))
                sp = claim.player_status.skill_points
                return sp is not None and sp >= threshold
            return True
        if "ultimate ready" in pc:
            return True
        if "waypoint selected" in pc:
            return True
        if "healer in team" in pc:
            return True
        return True

    @staticmethod
    def _infer_action_type(text: str, state: ScreenStateKind) -> str:
        t = text.lower()
        if any(w in t for w in ("领取", "领取全部", "一键领取", "claim", "claim all")):
            return "claim_reward"
        if any(w in t for w in ("确认", "确定", "confirm", "ok", "accept")):
            return "confirm"
        if any(w in t for w in ("取消", "返回", "关闭", "cancel", "back", "close")):
            return "go_back"
        if any(w in t for w in ("传送", "前往", "teleport")):
            return "teleport"
        if any(w in t for w in ("追踪", "导航", "track", "navigate")):
            return "track_quest"
        if any(w in t for w in ("自动", "自动战斗", "auto")):
            return "toggle_auto"
        if any(w in t for w in ("购买", "兑换", "buy", "exchange")):
            return "buy_item"
        if any(w in t for w in ("使用", "打开", "use", "open")):
            return "use_item"
        return "click"
