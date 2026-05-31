"""QuestLogReader: OCR + VLM reading of live quest log text.

Matches detected objective text against knowledge/genshin_archon_quests.py content
to auto-detect quest progress without manual state tracking.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    import numpy as np
    from core.state_bus import StateBus
    from knowledge.genshin_archon_quests import QuestStep


log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class QuestLogEntry:
    """A single objective line from the quest log."""
    quest_id: str
    step_index: int
    objective_text: str
    raw_text: str = ""
    confidence: float = 0.8


@dataclass(frozen=True, slots=True)
class QuestProgressClaim:
    """Claim about current quest progress."""
    quest_id: str
    step_index: int
    status: str  # "completed" | "in_progress" | "not_started" | "unknown"
    matched_text: str = ""
    confidence: float = 0.5


class QuestLogReader:
    """Reads live quest log text and matches against quest knowledge base.

    Pipeline:
        ocr_fn(frame) → raw text → parse_quest_lines() → QuestLogEntry[]
        → match_to_knowledge() → QuestProgressClaim[]
        → publish to StateBus
    """

    def __init__(
        self,
        quest_knowledge: list[QuestStep] | None = None,
        ocr_fn: Callable[[Any], list[str]] | None = None,
        vlm_describe_fn: Callable[[Any, dict[str, Any]], str] | None = None,
        state_bus: StateBus | None = None,
        vlm_confidence_threshold: float = 0.7,
    ) -> None:
        self._quest_knowledge = quest_knowledge or []
        self._ocr_fn = ocr_fn
        self._vlm_fn = vlm_describe_fn
        self._state_bus = state_bus
        self._vlm_threshold = vlm_confidence_threshold

    def read_from_frame(self, frame: Any) -> list[QuestLogEntry]:
        """OCR read quest log from a game frame.

        Returns a list of QuestLogEntry objects representing detected
        objective lines.
        """
        if self._ocr_fn is None:
            return []

        try:
            texts = self._ocr_fn(frame)
        except Exception as exc:
            log.debug("[QuestLogReader] OCR failed: %s", exc)
            return []

        entries: list[QuestLogEntry] = []
        for text in texts:
            entry = self._parse_line(text)
            if entry is not None:
                entries.append(entry)

        return entries

    def match_progress(
        self,
        entries: list[QuestLogEntry],
    ) -> list[QuestProgressClaim]:
        """Match quest log entries against knowledge base to produce progress claims."""
        claims: list[QuestProgressClaim] = []

        for entry in entries:
            matched = self._find_best_match(entry.objective_text)
            if matched is not None:
                claims.append(QuestProgressClaim(
                    quest_id=matched.quest_id,
                    step_index=matched.step_index,
                    status="in_progress",
                    matched_text=entry.objective_text,
                    confidence=min(entry.confidence, 0.9),
                ))

        return claims

    def auto_detect_and_publish(self, frame: Any) -> list[QuestProgressClaim]:
        """Convenience: read + match + publish to StateBus."""
        entries = self.read_from_frame(frame)
        claims = self.match_progress(entries)

        if claims and self._state_bus is not None:
            slot = self._state_bus.get_slot("quest_progress")
            if slot is not None:
                slot.put(claims)

        return claims

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _parse_line(self, text: str) -> QuestLogEntry | None:
        """Parse a single OCR line into a QuestLogEntry.

        Expected format: "1. [Objective text]" or "Quest Name / Step text"
        """
        text = text.strip()
        if not text or len(text) < 3:
            return None

        quest_id, step_idx = self._infer_quest_id(text)
        return QuestLogEntry(
            quest_id=quest_id,
            step_index=step_idx,
            objective_text=text,
            raw_text=text,
            confidence=0.8,
        )

    def _infer_quest_id(self, text: str) -> tuple[str, int]:
        """Infer quest ID and step index from raw text.

        Uses simple keyword matching against knowledge base.
        """
        text_lower = text.lower()

        for qs in self._quest_knowledge:
            if qs.quest_id in text_lower or qs.objective.lower() in text_lower:
                return (qs.quest_id, qs.step_index)

        return ("unknown", 0)

    def _find_best_match(self, text: str) -> QuestStep | None:
        """Find the QuestStep that best matches the given text."""
        text_lower = text.lower()
        best: QuestStep | None = None
        best_score = 0

        for qs in self._quest_knowledge:
            obj_lower = qs.objective.lower()
            # Exact match
            if obj_lower == text_lower:
                return qs
            # Keyword overlap
            words = set(text_lower.split())
            obj_words = set(obj_lower.split())
            overlap = len(words & obj_words)
            score = overlap / max(len(words), len(obj_words))
            if score > best_score and score > 0.3:
                best = qs
                best_score = score

        return best