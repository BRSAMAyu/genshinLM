"""ScreenStateTree — structured screen state representation.

Provides a typed, hierarchical view of the current screen state with:
- Semantic roles for UI elements
- Modal state tracking
- Evidence references for Claim/BAGEL integration
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ScreenPageId = Literal[
    "world_viewport",
    "dialogue",
    "map",
    "character_menu",
    "inventory",
    "quest_log",
    "shop",
    "reward_screen",
    "loading",
    "cutscene",
    "combat",
    "boss_fight",
    "domain",
    "settings",
    "unknown",
]

ElementSource = Literal["ocr", "detector", "vlm", "template", "fused"]


@dataclass(frozen=True, slots=True)
class NormalizedRect:
    """Bounding box in normalized [0,1] coordinates."""
    left: float
    top: float
    right: float
    bottom: float

    @property
    def center(self) -> tuple[float, float]:
        return ((self.left + self.right) / 2, (self.top + self.bottom) / 2)

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass(frozen=True, slots=True)
class UIElementNode:
    """A single UI element on screen with semantic metadata."""
    element_id: str
    semantic_role: str  # button, menu_item, dialog_option, quest_entry, etc.
    text: str
    bbox_norm: NormalizedRect
    clickable: bool
    enabled: bool = True
    confidence: float = 0.5
    source: ElementSource = "ocr"
    anchor_candidates: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TextBlock:
    """A detected text block (OCR output)."""
    text: str
    bbox_norm: NormalizedRect
    confidence: float
    language: str = "unknown"


@dataclass(frozen=True, slots=True)
class RegionNode:
    """A named region of the screen (minimap, HUD, dialog area, etc.)."""
    region_id: str
    region_type: str
    bbox_norm: NormalizedRect
    confidence: float = 0.5


@dataclass(frozen=True, slots=True)
class ModalState:
    """Active modal overlay (dialog box, popup, notification)."""
    modal_type: str  # dialog, popup, notification, tooltip, reward
    title: str = ""
    options: tuple[str, ...] = ()
    is_dismissable: bool = True
    confidence: float = 0.5


@dataclass(frozen=True, slots=True)
class ScreenStateTree:
    """Complete structured representation of current screen state.

    Frozen for thread safety — create new instances for each frame.
    """
    frame_id: int
    game_id: str
    screen_state: str
    page_id: ScreenPageId
    confidence: float
    elements: tuple[UIElementNode, ...] = ()
    text_blocks: tuple[TextBlock, ...] = ()
    regions: tuple[RegionNode, ...] = ()
    active_modal: ModalState | None = None
    focus_target: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def find_element_by_role(self, role: str) -> UIElementNode | None:
        for e in self.elements:
            if e.semantic_role == role:
                return e
        return None

    def find_element_by_text(self, keyword: str) -> list[UIElementNode]:
        kw = keyword.lower()
        return [e for e in self.elements if kw in e.text.lower()]

    def clickable_elements(self) -> list[UIElementNode]:
        return [e for e in self.elements if e.clickable and e.enabled]

    def dialog_options(self) -> list[UIElementNode]:
        return [e for e in self.elements if e.semantic_role == "dialog_option"]

    def quest_entries(self) -> list[UIElementNode]:
        return [e for e in self.elements if e.semantic_role == "quest_entry"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "game_id": self.game_id,
            "screen_state": self.screen_state,
            "page_id": self.page_id,
            "confidence": self.confidence,
            "element_count": len(self.elements),
            "text_block_count": len(self.text_blocks),
            "active_modal": self.active_modal.modal_type if self.active_modal else None,
            "focus_target": self.focus_target,
        }
