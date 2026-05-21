from __future__ import annotations

from dataclasses import dataclass, field

from app_service.skill_manager import RecordedEvent, SkillDraft
from execution.semantic_action import SemanticAction
from interaction.ui_anchor import UIAnchor, UIAnchorResolver, UIElement


@dataclass(frozen=True, slots=True)
class SemanticSkillDraft:
    draft_id: str
    semantic_actions: list[SemanticAction]
    ui_anchors: list[str] = field(default_factory=list)
    verifier_contracts: list[dict[str, object]] = field(default_factory=list)
    raw_event_count: int = 0
    notes: list[str] = field(default_factory=list)


class SemanticSkillDistiller:
    """Distill raw mouse/key traces into semantic actions when anchors explain them."""

    def __init__(self, resolver: UIAnchorResolver | None = None) -> None:
        self._resolver = resolver or UIAnchorResolver()

    def distill(
        self,
        draft: SkillDraft,
        anchors: list[UIAnchor],
        elements: list[UIElement],
        viewport: tuple[int, int],
        screen_state: str,
    ) -> SemanticSkillDraft:
        semantic_actions: list[SemanticAction] = []
        used_anchors: list[str] = []
        notes: list[str] = []
        for event in draft.raw_events:
            if event.event_type != "mouse_click":
                continue
            anchor_id = self._nearest_anchor(event, anchors, elements, viewport, screen_state)
            if anchor_id is None:
                notes.append("mouse_click could not be bound to UIAnchor; retained as fallback material")
                continue
            used_anchors.append(anchor_id)
            semantic_actions.append(
                SemanticAction(
                    action_id=f"semantic_{len(semantic_actions) + 1}",
                    kind="ui",
                    intent="click_anchor",
                    target=anchor_id,
                    parameters={"anchor_id": anchor_id},
                    requires_physical_input=True,
                )
            )
        verifier_contracts = [
            {
                "verifier_id": f"{anchor_id}_post_click",
                "success_criteria": ["screen_state_changed"],
            }
            for anchor_id in dict.fromkeys(used_anchors)
        ]
        return SemanticSkillDraft(
            draft_id=draft.draft_id,
            semantic_actions=semantic_actions,
            ui_anchors=list(dict.fromkeys(used_anchors)),
            verifier_contracts=verifier_contracts,
            raw_event_count=len(draft.raw_events),
            notes=notes,
        )

    def _nearest_anchor(
        self,
        event: RecordedEvent,
        anchors: list[UIAnchor],
        elements: list[UIElement],
        viewport: tuple[int, int],
        screen_state: str,
    ) -> str | None:
        x = float(event.payload.get("x", -1))
        y = float(event.payload.get("y", -1))
        if x < 0 or y < 0:
            return None
        best: tuple[float, str] | None = None
        for anchor in anchors:
            resolution = self._resolver.resolve(anchor, elements, viewport, screen_state=screen_state)
            if resolution.click_point is None:
                continue
            dx = resolution.click_point[0] - x
            dy = resolution.click_point[1] - y
            distance = (dx * dx + dy * dy) ** 0.5
            if best is None or distance < best[0]:
                best = (distance, anchor.anchor_id)
        if best is None or best[0] > max(viewport) * 0.08:
            return None
        return best[1]
