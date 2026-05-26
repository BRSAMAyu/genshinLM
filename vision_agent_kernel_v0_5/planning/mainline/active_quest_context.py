"""ActiveQuestContext — the fact chain that drives mainline progression.

Unlike the old QuestState (regex-based), ActiveQuestContext integrates:
- Quest objective text
- Dialogue facts
- Map marker facts
- Screen state facts
- Inventory/team facts
- Completed claims
- Known blockers

Each context update produces a versioned snapshot and optionally a StateDeltaClaim.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field, replace
from typing import Any, Literal

ObjectiveType = Literal[
    "dialog",
    "go_to_marker",
    "combat",
    "collect",
    "domain",
    "upgrade",
    "puzzle",
    "escort",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class DialogueTurn:
    speaker: str
    text: str
    turn_index: int
    is_player_choice: bool = False


@dataclass(frozen=True, slots=True)
class MapMarker:
    marker_id: str
    name: str
    marker_type: str  # quest | teleport | custom | unknown
    region: str = ""
    distance_estimate: float = -1.0
    is_tracked: bool = False


@dataclass(frozen=True, slots=True)
class QuestBlocker:
    blocker_id: str
    blocker_type: str  # prerequisite | resource | level | quest_lock | unknown
    description: str
    resolution_hint: str = ""


@dataclass(frozen=True, slots=True)
class ActiveQuestContext:
    """Versioned snapshot of the current quest state.

    Immutable — each update creates a new version via evolve().
    """
    quest_id: str
    quest_title: str
    objective_text: str
    objective_type: ObjectiveType
    evidence_refs: tuple[str, ...] = ()
    last_dialogue_turns: tuple[DialogueTurn, ...] = ()
    map_marker: MapMarker | None = None
    screen_state: str = "unknown"
    known_blockers: tuple[QuestBlocker, ...] = ()
    confidence: float = 0.5
    version: int = 1
    created_at: float = 0.0
    updated_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.created_at == 0.0:
            object.__setattr__(self, "created_at", time.perf_counter())
            object.__setattr__(self, "updated_at", self.created_at)

    @property
    def is_blocked(self) -> bool:
        return len(self.known_blockers) > 0

    @property
    def has_objective(self) -> bool:
        return bool(self.objective_text)

    def evolve(self, **overrides: Any) -> ActiveQuestContext:
        """Create next version with updated fields."""
        import dataclasses
        return dataclasses.replace(
            self,
            version=self.version + 1,
            updated_at=time.perf_counter(),
            **overrides,
        )


def classify_objective(text: str) -> ObjectiveType:
    """Classify an objective text into a type using keyword heuristics."""
    lower = text.lower()
    dialog_kw = ("对话", "交谈", "talk", "speak", "dialogue", "对话完成", "go to")
    combat_kw = ("击败", "消灭", "战斗", "defeat", "kill", "combat", "fight", "boss")
    collect_kw = ("收集", "采集", "找到", "collect", "gather", "find", "obtain")
    marker_kw = ("前往", "到达", "go to", "reach", "navigate", "抵达", "移动到")
    domain_kw = ("秘境", "副本", "domain", "dungeon", "深渊")
    upgrade_kw = ("升级", "强化", "upgrade", "enhance", "突破", "ascend")
    puzzle_kw = ("解谜", "机关", "puzzle", "mechanism")
    escort_kw = ("护送", "escort", "protect")

    for kw in combat_kw:
        if kw in lower:
            return "combat"
    for kw in domain_kw:
        if kw in lower:
            return "domain"
    for kw in dialog_kw:
        if kw in lower:
            return "dialog"
    for kw in collect_kw:
        if kw in lower:
            return "collect"
    for kw in marker_kw:
        if kw in lower:
            return "go_to_marker"
    for kw in upgrade_kw:
        if kw in lower:
            return "upgrade"
    for kw in puzzle_kw:
        if kw in lower:
            return "puzzle"
    for kw in escort_kw:
        if kw in lower:
            return "escort"
    return "unknown"


def quest_id_from_text(text: str) -> str:
    """Deterministic quest ID from objective text."""
    digest = hashlib.sha1(text.strip().casefold().encode("utf-8")).hexdigest()[:10]
    return f"quest_{digest}"
