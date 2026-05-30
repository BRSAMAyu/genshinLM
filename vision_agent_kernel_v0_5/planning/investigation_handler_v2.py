"""Q-27: Investigation clue visibility handler (线索可见性).

Handles investigation quests where clues become visible after
certain conditions are met (defeating enemies, using elements, etc.).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


class ClueState(str, Enum):
    HIDDEN = "hidden"          # Not yet visible
    VISIBLE = "visible"       # Can be collected
    COLLECTED = "collected"   # Already collected
    LOCKED = "locked"         # Requires condition to unlock


@dataclass(frozen=True, slots=True)
class Clue:
    """A single investigation clue."""
    clue_id: str
    clue_type: str  # "enemy_defeat", "element_use", "interact", etc.
    state: ClueState
    position: tuple[float, float]  # normalized 0-1
    required_condition: str | None
    hint_text: str | None = None


@dataclass(frozen=True, slots=True)
class InvestigationProgress:
    """Progress on an investigation quest."""
    quest_id: str
    clues: list[Clue]
    visible_count: int
    collected_count: int
    total_count: int
    completion_ratio: float


class InvestigationHandlerV2:
    """Handle investigation clue visibility."""

    def __init__(
        self,
        on_clue_revealed: Any = None,
        on_all_clues_collected: Any = None,
    ) -> None:
        self._current_quest: str | None = None
        self._clues: dict[str, Clue] = {}
        self._on_clue_revealed = on_clue_revealed
        self._on_all_clues_collected = on_all_clues_collected

    def start_investigation(self, quest_id: str, clue_specs: list[dict[str, Any]]) -> InvestigationProgress:
        """Start tracking an investigation quest.

        Args:
            quest_id: Unique identifier for the quest
            clue_specs: List of clue specifications

        Returns:
            InvestigationProgress for the quest
        """
        self._current_quest = quest_id
        self._clues = {}

        for spec in clue_specs:
            clue = Clue(
                clue_id=spec["id"],
                clue_type=spec.get("type", "interact"),
                state=ClueState.HIDDEN,
                position=spec.get("position", (0.5, 0.5)),
                required_condition=spec.get("condition"),
                hint_text=spec.get("hint"),
            )
            self._clues[clue.clue_id] = clue

        log.info("[InvestigationHandler] Started investigation %s with %d clues", quest_id, len(self._clues))
        return self._get_progress()

    def trigger_condition(self, condition: str) -> InvestigationProgress:
        """Trigger a condition that may reveal clues.

        Args:
            condition: The condition that was triggered

        Returns:
            InvestigationProgress with updated clue states
        """
        if not self._current_quest:
            return InvestigationProgress(
                quest_id="",
                clues=[],
                visible_count=0,
                collected_count=0,
                total_count=0,
                completion_ratio=0.0,
            )

        revealed_any = False

        for clue_id, clue in self._clues.items():
            if clue.state != ClueState.HIDDEN:
                continue

            if clue.required_condition == condition:
                self._clues[clue_id] = Clue(
                    clue_id=clue.clue_id,
                    clue_type=clue.clue_type,
                    state=ClueState.VISIBLE,
                    position=clue.position,
                    required_condition=clue.required_condition,
                    hint_text=clue.hint_text,
                )
                revealed_any = True
                log.info("[InvestigationHandler] Clue revealed: %s (condition: %s)", clue_id, condition)

                if self._on_clue_revealed:
                    try:
                        self._on_clue_revealed(clue_id, condition)
                    except Exception as exc:
                        log.warning("[InvestigationHandler] Clue revealed callback failed: %s", exc)

        return self._get_progress()

    def collect_clue(self, clue_id: str) -> InvestigationProgress:
        """Mark a clue as collected.

        Args:
            clue_id: ID of the clue to mark as collected

        Returns:
            InvestigationProgress with updated states
        """
        if clue_id in self._clues:
            clue = self._clues[clue_id]
            if clue.state == ClueState.VISIBLE:
                self._clues[clue_id] = Clue(
                    clue_id=clue.clue_id,
                    clue_type=clue.clue_type,
                    state=ClueState.COLLECTED,
                    position=clue.position,
                    required_condition=clue.required_condition,
                    hint_text=clue.hint_text,
                )
                log.info("[InvestigationHandler] Clue collected: %s", clue_id)

                # Check if all collected
                progress = self._get_progress()
                if progress.collected_count >= progress.total_count:
                    if self._on_all_clues_collected:
                        try:
                            self._on_all_clues_collected(self._current_quest)
                        except Exception as exc:
                            log.warning("[InvestigationHandler] All collected callback failed: %s", exc)

        return self._get_progress()

    def force_reveal_clue(self, clue_id: str) -> InvestigationProgress:
        """Force reveal a specific clue (debug/testing).

        Args:
            clue_id: ID of clue to reveal

        Returns:
            InvestigationProgress
        """
        if clue_id in self._clues:
            clue = self._clues[clue_id]
            self._clues[clue_id] = Clue(
                clue_id=clue.clue_id,
                clue_type=clue.clue_type,
                state=ClueState.VISIBLE,
                position=clue.position,
                required_condition=clue.required_condition,
                hint_text=clue.hint_text,
            )
        return self._get_progress()

    def _get_progress(self) -> InvestigationProgress:
        """Get current investigation progress."""
        clues_list = list(self._clues.values())
        visible = sum(1 for c in clues_list if c.state == ClueState.VISIBLE)
        collected = sum(1 for c in clues_list if c.state == ClueState.COLLECTED)
        total = len(clues_list)

        return InvestigationProgress(
            quest_id=self._current_quest or "",
            clues=clues_list,
            visible_count=visible,
            collected_count=collected,
            total_count=total,
            completion_ratio=collected / max(total, 1),
        )

    def get_visible_clues(self) -> list[Clue]:
        """Get all visible (collectible) clues."""
        return [c for c in self._clues.values() if c.state == ClueState.VISIBLE]

    def get_nearest_visible_clue(self, current_pos: tuple[float, float]) -> Clue | None:
        """Get the nearest visible clue to current position."""
        visible = self.get_visible_clues()
        if not visible:
            return None

        def distance(c: Clue) -> float:
            dx = c.position[0] - current_pos[0]
            dy = c.position[1] - current_pos[1]
            return dx * dx + dy * dy

        return min(visible, key=distance)

    def get_hint_for_clue(self, clue_id: str) -> str | None:
        """Get hint text for a hidden clue."""
        if clue_id in self._clues:
            return self._clues[clue_id].hint_text
        return None

    def is_complete(self) -> bool:
        """Check if investigation is complete."""
        progress = self._get_progress()
        return progress.collected_count >= progress.total_count and progress.total_count > 0

    def reset(self) -> None:
        """Reset handler state."""
        self._current_quest = None
        self._clues = {}
        log.info("[InvestigationHandler] Handler reset")