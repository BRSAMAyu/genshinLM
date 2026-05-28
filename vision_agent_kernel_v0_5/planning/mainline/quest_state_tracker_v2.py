"""QuestStateTrackerV2 — upgrades QuestStateTracker with ActiveQuestContext.

Key improvements over V1:
- Integrates OCR, VLM, ClaimGraph summary, dialogue transcript, map markers
- Outputs ActiveQuestContext (versioned, immutable) instead of QuestState
- Emits StateDeltaClaim when objective changes
- Confidence decay when OCR is missing
- Can distinguish objective change from screen state change
"""
from __future__ import annotations

import hashlib
import math
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from planning.mainline.active_quest_context import (
    ActiveQuestContext,
    ClaimSummaryFact,
    DialogueTurn,
    InventoryFact,
    MapMarker,
    ObjectiveType,
    QuestBlocker,
    ResourceFact,
    TeamFact,
    classify_objective,
    quest_id_from_text,
)
from planning.screen_state_claim import ScreenStateClaim, UIElementClaim

log = logging.getLogger(__name__)

# Regex patterns for quest objective extraction
_QUEST_PATTERNS = [
    re.compile(r"(?:quest|task|track|objective)\s*[：:]\s*(.*)", re.IGNORECASE),
    re.compile(r"(?:任务|委托|目标|追踪)\s*[：:]\s*(.*)"),
    re.compile(r"(?:传说任务|活动任务|深渊|指引)\s*[：:]*\s*(.*)"),
    re.compile(r"委托\s*(.*)"),
    re.compile(r"追踪\s*(.*)"),
]

_BLOCKED_RE = re.compile(
    r"(?:(?:^|[\s,.;!?])blocked|(?:^|[\s,.;!?])stuck|(?:^|[\s,.;!?])failed"
    r"|无法|卡住|障碍物|未解锁)",
    re.IGNORECASE,
)

_DIALOGUE_ROLE_RE = re.compile(r"^((?:旅行者|派蒙|Paimon|Traveler|[一-鿿]+))\s*[：:]\s*(.*)")


@dataclass(frozen=True, slots=True)
class QuestContextDelta:
    """Describes what changed between two quest context versions."""
    previous_version: int
    new_version: int
    objective_changed: bool
    dialogue_advanced: bool
    marker_changed: bool
    blocker_added: bool
    confidence_changed: float
    reason: str


class QuestStateTrackerV2:
    """Upgraded quest tracker producing ActiveQuestContext."""

    def __init__(self, confidence_decay_rate: float = 2.0) -> None:
        self._context = ActiveQuestContext(
            quest_id="unknown",
            quest_title="",
            objective_text="",
            objective_type="unknown",
            confidence=0.0,
        )
        self._confidence_decay_rate = confidence_decay_rate
        self._last_ocr_had_quest = False
        self._last_update_time: float = time.perf_counter()

    def update(
        self,
        claim: ScreenStateClaim,
        dialogue_turns: list[DialogueTurn] | None = None,
        map_marker: MapMarker | None = None,
        claim_graph_summary: dict[str, Any] | None = None,
    ) -> tuple[ActiveQuestContext, QuestContextDelta | None]:
        """Update quest context from current perception.

        Returns (new_context, delta) where delta is None if nothing changed.
        """
        objective_text = ""
        quest_title = ""
        blocked: list[QuestBlocker] = []

        # 1. Extract quest info from OCR + UI elements
        ocr_lines = list(claim.raw_ocr_texts)
        for element in claim.ui_elements:
            if element.text:
                ocr_lines.append(element.text)

        has_quest_text = False

        # Extract objective
        for line in ocr_lines:
            line_str = line.strip()
            for pattern in _QUEST_PATTERNS:
                match = pattern.search(line_str)
                if match:
                    objective_text = match.group(1).strip()
                    has_quest_text = True
                    break
            if objective_text:
                break

        # Fallback: VLM scene description
        if not objective_text and claim.scene_description:
            vlm_match = re.search(
                r"(?:quest|task|objective|goal is|任务|目标)\s*([\w\s一-鿿]+)",
                claim.scene_description,
                re.IGNORECASE,
            )
            if vlm_match:
                objective_text = vlm_match.group(1).strip()
                has_quest_text = True

        # Fallback: use claim graph summary if a verified upstream component
        # already extracted quest context.
        if not objective_text and claim_graph_summary:
            summary_objective = (
                claim_graph_summary.get("objective_text")
                or claim_graph_summary.get("active_objective")
                or claim_graph_summary.get("active_quest_objective")
            )
            if isinstance(summary_objective, str) and summary_objective.strip():
                objective_text = summary_objective.strip()
                has_quest_text = True

        # 2. Extract quest title (from quest_log role elements)
        for element in claim.ui_elements:
            if element.role == "quest_entry" and element.text:
                quest_title = element.text.strip()
                break

        # 3. Detect blockers
        for line in ocr_lines:
            if _BLOCKED_RE.search(line.strip()):
                blocked.append(QuestBlocker(
                    blocker_id=f"blocker_{hashlib.md5(line.strip().encode()).hexdigest()[:4]}",
                    blocker_type="unknown",
                    description=line.strip(),
                ))

        # 4. Detect dialogue turns from OCR
        parsed_dialogue = dialogue_turns or []
        if not parsed_dialogue:
            for element in claim.ui_elements:
                if element.role == "dialogue_text" and element.text:
                    match = _DIALOGUE_ROLE_RE.match(element.text)
                    if match:
                        parsed_dialogue.append(DialogueTurn(
                            speaker=match.group(1),
                            text=match.group(2),
                            turn_index=len(parsed_dialogue),
                        ))

        # 5. Compute confidence (time-based exponential decay)
        now = time.perf_counter()
        elapsed = now - self._last_update_time
        confidence = self._context.confidence
        if has_quest_text:
            # Boost confidence when quest text is found
            confidence = min(1.0, 0.7 + 0.3 * min(len(objective_text) / 20.0, 1.0))
            self._last_ocr_had_quest = True
        elif self._last_ocr_had_quest:
            # First dropout: moderate decay
            decay = 1.0 - math.exp(-self._confidence_decay_rate * elapsed)
            confidence = max(0.1, confidence * (1.0 - decay))
            self._last_ocr_had_quest = False
        else:
            # Sustained dropout: faster decay
            decay = 1.0 - math.exp(-self._confidence_decay_rate * 2 * elapsed)
            confidence = max(0.05, confidence * (1.0 - decay))
        self._last_update_time = now

        # 6. Build new context
        if objective_text:
            quest_id = quest_id_from_text(objective_text)
            obj_type = classify_objective(objective_text)
        else:
            quest_id = self._context.quest_id
            objective_text = self._context.objective_text
            obj_type = self._context.objective_type

        new_context = self._context.evolve(
            quest_id=quest_id,
            quest_title=quest_title or self._context.quest_title,
            objective_text=objective_text,
            objective_type=obj_type,
            last_dialogue_turns=tuple(parsed_dialogue[-10:]),  # Keep last 10 turns
            map_marker=map_marker or self._context.map_marker,
            screen_state=claim.screen_state,
            inventory_facts=tuple(_inventory_facts(claim_graph_summary)) or self._context.inventory_facts,
            team_facts=tuple(_team_facts(claim_graph_summary)) or self._context.team_facts,
            resource_facts=tuple(_resource_facts(claim_graph_summary)) or self._context.resource_facts,
            completed_claims=tuple(_claim_summary_facts(claim_graph_summary, "completed_claims")),
            blocked_claims=tuple(_claim_summary_facts(claim_graph_summary, "blocked_claims")),
            known_blockers=tuple(blocked),
            evidence_refs=tuple(_evidence_refs(claim, claim_graph_summary)),
            confidence=confidence,
            metadata={
                "frame_id": claim.frame_id,
                "source": claim.source,
            },
        )

        # 7. Compute delta
        delta = self._compute_delta(self._context, new_context)

        self._context = new_context
        return new_context, delta

    def get_context(self) -> ActiveQuestContext:
        return self._context

    def _compute_delta(
        self,
        old: ActiveQuestContext,
        new: ActiveQuestContext,
    ) -> QuestContextDelta | None:
        """Compute what changed between two context versions."""
        if new.version == old.version:
            return None

        obj_changed = old.objective_text != new.objective_text and new.objective_text != ""
        dialogue_advanced = (
            len(new.last_dialogue_turns) > len(old.last_dialogue_turns)
            or (
                len(new.last_dialogue_turns) > 0
                and len(old.last_dialogue_turns) > 0
                and new.last_dialogue_turns[-1].text != old.last_dialogue_turns[-1].text
            )
        )
        marker_changed = (
            (old.map_marker is None) != (new.map_marker is None)
            or (
                old.map_marker is not None
                and new.map_marker is not None
                and old.map_marker.marker_id != new.map_marker.marker_id
            )
        )
        blocker_added = len(new.known_blockers) > len(old.known_blockers)
        conf_delta = abs(new.confidence - old.confidence)

        # Nothing meaningful changed
        if not any([obj_changed, dialogue_advanced, marker_changed, blocker_added, conf_delta > 0.05]):
            return None

        reasons: list[str] = []
        if obj_changed:
            reasons.append("objective_changed")
        if dialogue_advanced:
            reasons.append("dialogue_advanced")
        if marker_changed:
            reasons.append("marker_changed")
        if blocker_added:
            reasons.append("blocker_added")
        if conf_delta > 0.05:
            reasons.append(f"confidence_{new.confidence - old.confidence:+.2f}")
        if not reasons:
            reasons.append("screen_state_update")

        return QuestContextDelta(
            previous_version=old.version,
            new_version=new.version,
            objective_changed=obj_changed,
            dialogue_advanced=dialogue_advanced,
            marker_changed=marker_changed,
            blocker_added=blocker_added,
            confidence_changed=conf_delta,
            reason="; ".join(reasons),
        )


def _evidence_refs(
    claim: ScreenStateClaim,
    claim_graph_summary: dict[str, Any] | None,
) -> list[str]:
    refs = [e.element_id for e in claim.ui_elements if e.role == "quest_entry"]
    if claim_graph_summary:
        raw_refs = claim_graph_summary.get("evidence_refs", ())
        if isinstance(raw_refs, (list, tuple)):
            refs.extend(str(ref) for ref in raw_refs if ref)
    return list(dict.fromkeys(refs))


def _claim_summary_facts(
    claim_graph_summary: dict[str, Any] | None,
    key: str,
) -> list[ClaimSummaryFact]:
    if not claim_graph_summary:
        return []
    raw = claim_graph_summary.get(key, ())
    facts: list[ClaimSummaryFact] = []
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, dict):
                claim_id = str(item.get("claim_id") or item.get("id") or "")
                claim_type = str(item.get("claim_type") or item.get("type") or "")
                status = str(item.get("status") or ("verified" if key == "completed_claims" else "blocked"))
                if claim_id or claim_type:
                    facts.append(ClaimSummaryFact(
                        claim_id=claim_id,
                        claim_type=claim_type,
                        status=status,
                        target=str(item.get("target", "")),
                    ))
    return facts


def _inventory_facts(claim_graph_summary: dict[str, Any] | None) -> list[InventoryFact]:
    if not claim_graph_summary:
        return []
    raw = claim_graph_summary.get("inventory_facts", ())
    facts: list[InventoryFact] = []
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, dict) and item.get("item_id"):
                facts.append(InventoryFact(
                    item_id=str(item.get("item_id")),
                    quantity=int(item.get("quantity", 0)),
                    evidence_ref=str(item.get("evidence_ref", "")),
                ))
    return facts


def _team_facts(claim_graph_summary: dict[str, Any] | None) -> list[TeamFact]:
    if not claim_graph_summary:
        return []
    raw = claim_graph_summary.get("team_facts", ())
    facts: list[TeamFact] = []
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, dict) and item.get("member_id"):
                facts.append(TeamFact(
                    member_id=str(item.get("member_id")),
                    level=int(item.get("level", 0)),
                    role=str(item.get("role", "")),
                    evidence_ref=str(item.get("evidence_ref", "")),
                ))
    return facts


def _resource_facts(claim_graph_summary: dict[str, Any] | None) -> list[ResourceFact]:
    if not claim_graph_summary:
        return []
    raw = claim_graph_summary.get("resource_facts", ())
    facts: list[ResourceFact] = []
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, dict) and item.get("resource_id"):
                facts.append(ResourceFact(
                    resource_id=str(item.get("resource_id")),
                    value=float(item.get("value", 0.0)),
                    evidence_ref=str(item.get("evidence_ref", "")),
                ))
    return facts
