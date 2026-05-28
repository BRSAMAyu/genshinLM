"""AnchorBinder — bind episode actions to UI anchors and produce SkillDef drafts.

Converts an Episode (sequence of RecordedActions) into a SkillDef at
raw_trace or draft tier, depending on whether anchors are bound.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from skills.schema import (
    SkillApplicability,
    SkillDef,
    SkillStep,
    SkillProducedClaim,
    SkillFallback,
)
from learning.skill_induction.episode_segmenter import Episode


@dataclass(frozen=True, slots=True)
class BindingResult:
    """Result of anchor binding attempt."""
    skill: SkillDef | None
    bound_anchor_count: int
    coordinate_only: bool
    reason: str = ""


class AnchorBinder:
    """Binds episode actions to anchors and creates SkillDef drafts."""

    def bind(self, episode: Episode) -> BindingResult:
        """Convert an episode into a SkillDef draft."""
        if not episode.actions:
            return BindingResult(None, 0, True, "empty episode")

        steps: list[SkillStep] = []
        anchors: list[str] = []
        has_coordinate_only = False
        prev_timestamp = 0.0

        for action in episode.actions:
            action_type = self._normalize_action_type(action.action_type)
            # Compute inter-step delay from recorded timestamps
            delay_ms = 0
            if prev_timestamp > 0 and hasattr(action, "timestamp") and action.timestamp > 0:
                delay_ms = max(0, int((action.timestamp - prev_timestamp) * 1000))
            if hasattr(action, "timestamp") and action.timestamp > 0:
                prev_timestamp = action.timestamp
            step = SkillStep(
                action=action_type,  # type: ignore
                target=action.anchor_id or action.target,
                timeout_ms=5000,
                params={"delay_ms": delay_ms} if delay_ms > 0 else {},
            )
            steps.append(step)

            if action.anchor_id:
                anchors.append(action.anchor_id)
            elif action.x != 0.0 or action.y != 0.0:
                has_coordinate_only = True

        unique_anchors = list(dict.fromkeys(anchors))
        coordinate_only = len(unique_anchors) == 0
        tier = "raw_trace" if coordinate_only else "draft"

        produced_claim = self._infer_claim(episode)

        skill = SkillDef(
            skill_id=f"induced_{episode.goal[:20]}_{uuid.uuid4().hex[:6]}",
            kind="procedure",
            tier=tier,
            applicability=SkillApplicability(
                screen_states=(episode.screen_state,) if episode.screen_state else (),
                required_anchors=tuple(unique_anchors),
            ),
            steps=tuple(steps),
            produced_claims=(produced_claim,) if produced_claim else (),
            fallbacks=(SkillFallback(recovery_recipe="UI_LOST_RECOVERY"),) if not coordinate_only else (),
            metadata={"coordinate_only": coordinate_only},
        )

        return BindingResult(
            skill=skill,
            bound_anchor_count=len(unique_anchors),
            coordinate_only=coordinate_only,
            reason="ok" if not coordinate_only else "coordinate-only, raw_trace only",
        )

    def _normalize_action_type(self, action_type: str) -> str:
        mapping = {
            "click": "click_anchor",
            "click_anchor": "click_anchor",
            "click_text": "click_text",
            "press_key": "press_key",
            "select": "select_list_item",
            "select_list_item": "select_list_item",
            "confirm": "confirm_dialog",
            "confirm_dialog": "confirm_dialog",
            "navigate_to": "navigate_to",
            "interact": "interact",
            "observe": "observe",
        }
        return mapping.get(action_type, action_type)

    def _infer_claim(self, episode: Episode) -> SkillProducedClaim | None:
        """Infer what claim the episode produces from its goal and screen state."""
        state = episode.screen_state
        if "dialogue" in state or "dialog" in state:
            return SkillProducedClaim(
                claim_type="dialogue_advanced",
                target="active_dialogue.turn_index",
                claim_role="dependency",
                verifier_recipe="dialogue_delta.default",
            )
        if "combat" in state:
            return SkillProducedClaim(
                claim_type="combat_action_completed",
                target="combat_state",
                verifier_recipe="combat_state.default",
            )
        if "map" in state:
            return SkillProducedClaim(
                claim_type="map_interaction_completed",
                target="map_state",
                verifier_recipe="screen_state_stable.default",
            )
        if "inventory" in state or "menu" in state or "character" in state:
            return SkillProducedClaim(
                claim_type="ui_procedure_completed",
                target="screen_state",
                verifier_recipe="screen_state_stable.default",
            )
        if episode.actions and state and state != "unknown":
            return SkillProducedClaim(
                claim_type="ui_action_completed",
                target=state,
                verifier_recipe="screen_state_stable.default",
            )
        return None
