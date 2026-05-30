from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

ScreenStateKind = Literal[
    "overworld",
    "combat",
    "turn_based_combat",
    "dialog",
    "menu",
    "map",
    "loading",
    "inventory",
    "shop",
    "quest_log",
    "reward_screen",
    "boss_fight",
    "cutscene",
    "death_screen",
    "character_select",
    "adventure_rank_up",
    "notification",
    "domain_entrance",
    "cooking",
    "forging",
    "unknown",
]

ClaimSource = Literal["vlm", "ocr", "classifier", "template", "hybrid", "unknown"]


@dataclass(frozen=True, slots=True)
class UIElementClaim:
    element_id: str
    role: str
    text: str
    bbox_norm: tuple[float, float, float, float]
    confidence: float
    source: str
    clickable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlayerStatusClaim:
    health_pct: float | None = None
    stamina_pct: float | None = None
    skill_points: int | None = None
    position: str = "unknown"


@dataclass(frozen=True, slots=True)
class ScreenStateClaim:
    game_id: str
    screen_state: ScreenStateKind
    confidence: float
    source: ClaimSource
    ui_elements: tuple[UIElementClaim, ...] = ()
    player_status: PlayerStatusClaim = field(default_factory=PlayerStatusClaim)
    visible_objects: tuple[dict[str, str], ...] = ()
    interaction_prompt: str = ""
    scene_description: str = ""
    frame_id: int = 0
    timestamp: float = 0.0
    raw_vlm_text: str = ""
    raw_ocr_texts: tuple[str, ...] = ()

    def actionable_elements(self) -> list[UIElementClaim]:
        return [e for e in self.ui_elements if e.clickable or e.role in (
            "button", "menu_item", "list_item", "dialog_option",
            "quest_entry", "reward_item", "teleport_point",
        )]

    def text_elements(self) -> dict[str, str]:
        return {e.element_id: e.text for e in self.ui_elements if e.text}

    def find_element(self, role: str) -> UIElementClaim | None:
        for e in self.ui_elements:
            if e.role == role:
                return e
        return None

    def find_elements_by_text(self, keyword: str) -> list[UIElementClaim]:
        kw = keyword.lower()
        return [e for e in self.ui_elements if kw in e.text.lower()]


@dataclass(frozen=True, slots=True)
class ActionAffordance:
    action_id: str
    action_type: str
    target_label: str
    confidence: float
    requires_confirmation: bool = False
    semantic_action: str = ""
    precondition: str = ""
    risk_level: str = "low"


@dataclass(frozen=True, slots=True)
class TaskStateSnapshot:
    claim: ScreenStateClaim
    available_actions: tuple[ActionAffordance, ...] = ()
    mission_context: str = ""

    def safe_actions(self) -> list[ActionAffordance]:
        return [a for a in self.available_actions if a.risk_level in ("low", "medium")]

    def has_action_type(self, action_type: str) -> bool:
        return any(a.action_type == action_type for a in self.available_actions)
