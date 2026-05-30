from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from planning.screen_state_claim import ScreenStateClaim

log = logging.getLogger(__name__)

SAFE_EXPLORATION_ACTIONS = {
    "observe",
    "wait",
    "click_anchor",
    "click_text",
    "select_list_item",
    "confirm_dialog",
    "back",
    "open_menu",
    "skip_cutscene",
    "interact",
    "move_forward",
    "advance_dialog",
    "select_option",
    "click_button",
    "confirm",
}


@dataclass(frozen=True, slots=True)
class ExplorationAction:
    action_type: str
    target: str
    rationale: str
    expected_claim: dict[str, Any]
    requires_human_approval: bool


class ExplorationAgent:
    """Handles slow-path multi-modal exploration using VLM and OCR inputs.

    Proposed in Phase 2 of the Unified Execution Plan.
    """

    def __init__(self, perception: Any, risk_level: str = "medium") -> None:
        self._perception = perception
        self._risk_level = risk_level

    def _normalize_vlm_action(self, action: str) -> str:
        if not action:
            return "observe"
        act = action.strip().lower()
        # Synonym mappings to canonical SAFE_EXPLORATION_ACTIONS
        mappings = {
            "interact": "interact",
            "interact_f": "interact",
            "interact f": "interact",
            "press_f": "interact",
            "press f": "interact",
            "f": "interact",
            "walk": "move_forward",
            "move_forward": "move_forward",
            "walk_forward": "move_forward",
            "walk forward": "move_forward",
            "go_forward": "move_forward",
            "go forward": "move_forward",
            "combat": "click_anchor",
            "fight": "click_anchor",
            "attack": "click_anchor",
            "basic_attack": "click_anchor",
            "basic attack": "click_anchor",
            "skip": "skip_cutscene",
            "skip_cutscene": "skip_cutscene",
            "skip cutscene": "skip_cutscene",
            "dialog_skip": "skip_cutscene",
            "dialog skip": "skip_cutscene",
            "dialog": "advance_dialog",
            "dialog_advance": "advance_dialog",
            "dialog advance": "advance_dialog",
            "advance_dialog": "advance_dialog",
            "advance dialog": "advance_dialog",
            "space": "advance_dialog",
            "select": "select_option",
            "click_option": "select_option",
            "click option": "select_option",
            "select_option": "select_option",
            "select option": "select_option",
            "select_dialog_option": "select_option",
            "select dialog option": "select_option",
            "map": "open_menu",
            "open_map": "open_menu",
            "open map": "open_menu",
            "escape": "back",
            "back": "back",
            "go_back": "back",
            "go back": "back",
            "wait": "wait",
            "observe": "observe",
            "confirm": "confirm",
            "click_button": "click_button",
            "click button": "click_button",
        }
        return mappings.get(act, act)

    def explore_next_step(self, frame: np.ndarray, goal: str, state: ScreenStateClaim) -> ExplorationAction:
        """Invokes VLM/OCR reasoning to propose a safe exploratory action."""
        actionable = state.actionable_elements()

        # Check safety/approval level
        requires_approval = self._risk_level in ("high", "critical") or state.confidence < 0.55

        # Try to call high-accuracy VLM
        try:
            vlm_res = self._perception.analyze_vlm(frame, state.game_id)
            if vlm_res is not None and hasattr(vlm_res, "suggested_action") and vlm_res.suggested_action:
                # Resolve VLM Latency Mismatch: verify the visual state is still identical
                current_state_str = str(state.screen_state)
                vlm_state_str = str(getattr(vlm_res, "screen_state", ""))
                if vlm_state_str and vlm_state_str != "unknown" and vlm_state_str != current_state_str:
                    log.warning(
                        "[ExplorationAgent] VLM latency mismatch: VLM state was %r but current state is %r. "
                        "Discarding stale visual suggestion.",
                        vlm_state_str,
                        current_state_str,
                    )
                    return ExplorationAction(
                        action_type="observe",
                        target="screen",
                        rationale=f"VLM suggestion stale due to transition: {vlm_state_str} -> {current_state_str}",
                        expected_claim={"screen_state": current_state_str},
                        requires_human_approval=False,
                    )

                suggested_action = self._normalize_vlm_action(str(vlm_res.suggested_action))
                if suggested_action not in SAFE_EXPLORATION_ACTIONS:
                    log.warning("[ExplorationAgent] Unsafe VLM action rejected: %s", suggested_action)
                    return ExplorationAction(
                        action_type="observe",
                        target="screen",
                        rationale=f"Rejected unsafe VLM action: {suggested_action}",
                        expected_claim={"screen_state": state.screen_state},
                        requires_human_approval=True,
                    )
                target_prompt = "target"
                if isinstance(vlm_res.ui_elements, dict):
                    target_prompt = vlm_res.ui_elements.get("interaction_prompt", "target")

                return ExplorationAction(
                    action_type=suggested_action,
                    target=target_prompt or "target",
                    rationale=getattr(vlm_res, "scene_description", "VLM suggestion"),
                    expected_claim={"screen_state": getattr(vlm_res, "screen_state", state.screen_state)},
                    requires_human_approval=requires_approval,
                )
        except Exception as exc:
            log.warning("[ExplorationAgent] VLM call failed: %s", exc)

        # Fallback 1: Direct text/OCR keyword matching
        for el in actionable:
            if goal.lower() in el.text.lower() or el.text.lower() in goal.lower():
                return ExplorationAction(
                    action_type="click_anchor",
                    target=el.element_id,
                    rationale=f"Goal matched actionable UI element: '{el.text}'",
                    expected_claim={"screen_state": state.screen_state},
                    requires_human_approval=requires_approval,
                )

        # Fallback 2: Interactive elements exist, click the first one if safe
        if actionable:
            first = actionable[0]
            return ExplorationAction(
                action_type="click_anchor",
                target=first.element_id,
                rationale=f"Probing first actionable element: '{first.text}' role={first.role}",
                expected_claim={"screen_state": state.screen_state},
                requires_human_approval=requires_approval,
            )

        # Default fallback: Observe
        return ExplorationAction(
            action_type="observe",
            target="screen",
            rationale="No actionable elements found; performing observation",
            expected_claim={"screen_state": state.screen_state},
            requires_human_approval=requires_approval,
        )
